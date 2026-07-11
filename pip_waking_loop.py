#!/usr/bin/env python3
"""
Waking Loop v1.1 – Persistent Semantic Memory Daemon (patched)

Changes from v1.0, each one tied to something that actually broke when
tested, not a style preference:

  1. FIXED: missing `import logging` — v1.0 crashed on startup, always.
  2. generate_thought() now calls a real local model (Ollama) instead of
     LexRank extraction. The old version could only ever recombine
     existing sentences verbatim; tested over 5 ticks it locked onto
     repeating its own top sentence (1 unique output / 5 ticks).
  3. cft_score replaced with cft_v2 (imported from cft_v2.py) — the old
     keyword-count version scored keyword salad at 0.739 (promoted) and
     a real substantive thought at 0.039 (deleted within a day). Tested,
     confirmed, replaced.
  4. Every heartbeat now writes an append-only receipt (raw context sent,
     raw model output, full score breakdown) to receipts.jsonl. Nothing
     is silently pruned or consolidated without a record of what it was
     and why it was scored the way it was scored — matches the
     append-only discipline used elsewhere in this project.
  5. Unused imports removed (os, random, TfidfVectorizer, cosine_similarity
     were imported in v1.0 and never used).

KNOWN GAP, NOT FIXED HERE: cft_v2 still can't detect grammatical-but-
meaningless text built from real words with normal punctuation (only
catches literal non-language token spam). See cft_v2.py docstring.

RECOMMENDATION: run with --once manually for a while before trusting
the unattended --daemon loop. An unattended process calling a real
model on a schedule, then auto-deleting/consolidating its own history,
is real authority to hand a v1 system.

Usage:
    python waking_loop.py               # start daemon (heartbeat every 5 min)
    python waking_loop.py --once        # run one heartbeat and exit
    python waking_loop.py --consolidate # force nightly consolidation now

Dependencies: sentence-transformers, schedule, scikit-learn, requests
Requires: Ollama running locally (https://ollama.com) with a model pulled,
    e.g. `ollama pull llama3.2`
"""

import argparse
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests
import schedule
from sentence_transformers import SentenceTransformer, util

from cft_v2 import cft_score
from contracts import Thought
from circuit_breaker import CircuitBreaker, BreakerOpenError
from policy_layer import PolicyEngine, PolicyViolation, MAX_BLAST_RADIUS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path.home() / ".waking_loop"
CORPUS_DIR = BASE_DIR / "corpus"
LEDGER_DIR = BASE_DIR / "ledgers"
MAIN_LEDGER = LEDGER_DIR / "main.jsonl"
SIDE_LEDGER = LEDGER_DIR / "side.jsonl"
RECEIPTS_FILE = BASE_DIR / "receipts.jsonl"   # append-only, never pruned
LOG_FILE = BASE_DIR / "loop.log"

HEARTBEAT_MINUTES = 5
CONTEXT_DEPTH = 10
RETRIEVAL_K = 5
SIMILARITY_THRESHOLD = 0.4
CFT_THRESHOLD = 0.5
SIDE_PRUNE_DAYS = 1
MAIN_CONSOLIDATE_AGE_DAYS = 7
SUMMARISATION_RATIO = 0.3

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma4:e4b"
OLLAMA_TIMEOUT_SECONDS = 30

for d in [BASE_DIR, CORPUS_DIR, LEDGER_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("waking_loop")

model = SentenceTransformer(EMBEDDING_MODEL)


# ---------------------------------------------------------------------------
# Ledger + receipt I/O
# ---------------------------------------------------------------------------
def read_ledger(path):
    if not path.exists():
        return []
    thoughts = []
    with open(path, "r") as f:
        for line in f:
            try:
                thoughts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return thoughts


def get_trusted_main_entries():
    """The actual fix for the documented gap: 'nothing downstream checks
    reviewed before consuming.' Enforcing reviewed=True at PROMOTION time
    would break the existing design outright -- thoughts are meant to
    enter MAIN on CFT score, then get reviewed afterward via --review.
    Blocking promotion on reviewed=True would mean nothing ever gets
    promoted, since nothing is pre-reviewed before it exists.

    So the fix belongs at the READ boundary instead: any code that
    consumes MAIN entries downstream should call this, not
    read_ledger(MAIN_LEDGER) directly. This is the boundary where
    'reviewed' should actually matter."""
    return [t for t in read_ledger(MAIN_LEDGER)
           if t.get("reviewed") is True and not t.get("rejected")]


def append_to_ledger(path, thought):
    with open(path, "a") as f:
        f.write(json.dumps(thought) + "\n")


def append_receipt(entry: dict) -> str:
    """Append-only, never pruned or rewritten. Returns the real receipt
    ID, generated here -- previously the only 'receipt_id' anywhere in
    this codebase was a hardcoded 'pending' string in the consolidation
    policy check, which meant always_write_receipt always trivially
    passed (a truthy placeholder, not a verified receipt). Fixed: every
    receipt now gets an actual unique ID, returned so callers can use
    the real thing in policy checks."""
    receipt_id = str(uuid.uuid4())[:12]
    entry["receipt_id"] = receipt_id
    entry["logged_at"] = datetime.now().isoformat()
    with open(RECEIPTS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return receipt_id


def prune_ledger(path, max_age_days):
    thoughts = read_ledger(path)
    cutoff = datetime.now() - timedelta(days=max_age_days)
    kept = [t for t in thoughts if datetime.fromisoformat(t["timestamp"]) >= cutoff]
    with open(path, "w") as f:
        for t in kept:
            f.write(json.dumps(t) + "\n")
    log.info(f"Pruned {len(thoughts) - len(kept)} old thoughts from {path.name}")


# ---------------------------------------------------------------------------
# Corpus loading & embedding (unchanged from v1.0 — this part wasn't broken)
# ---------------------------------------------------------------------------
corpus_embeddings = {}
corpus_sentences = {}


def load_corpus():
    global corpus_embeddings, corpus_sentences
    corpus_embeddings.clear()
    corpus_sentences.clear()
    for txt_file in CORPUS_DIR.glob("*.txt"):
        with open(txt_file, "r") as f:
            text = f.read().strip()
            if not text:
                continue
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if not sentences:
            continue
        emb = model.encode(sentences, convert_to_tensor=True)
        corpus_embeddings[str(txt_file)] = emb
        corpus_sentences[str(txt_file)] = sentences
    log.info(f"Loaded {len(corpus_sentences)} corpus files.")


def retrieve_from_corpus(query, k=5):
    if not corpus_embeddings:
        return []
    query_emb = model.encode(query, convert_to_tensor=True)
    best_sentences = []
    for path, embs in corpus_embeddings.items():
        hits = util.semantic_search(query_emb, embs, top_k=k)
        for hit_group in hits:
            for hit in hit_group:
                if hit["score"] >= SIMILARITY_THRESHOLD:
                    best_sentences.append({
                        "text": corpus_sentences[path][hit["corpus_id"]],
                        "score": float(hit["score"]),
                        "source": path,
                    })
    best_sentences.sort(key=lambda x: x["score"], reverse=True)
    return best_sentences[:k]


def retrieve_from_ledgers(query_emb, ledgers, k=5):
    all_thoughts = []
    for path in ledgers:
        all_thoughts.extend(read_ledger(path))
    if not all_thoughts:
        return []
    texts = [t["text"] for t in all_thoughts]
    emb = model.encode(texts, convert_to_tensor=True)
    hits = util.semantic_search(query_emb, emb, top_k=k)
    results = []
    for hit_group in hits:
        for hit in hit_group:
            if hit["score"] >= SIMILARITY_THRESHOLD:
                results.append({
                    "text": texts[hit["corpus_id"]],
                    "score": float(hit["score"]),
                    "timestamp": all_thoughts[hit["corpus_id"]]["timestamp"],
                    "ledger": path.name,
                })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:k]


# ---------------------------------------------------------------------------
# Thought generation — NOW A REAL MODEL CALL, not extraction
# ---------------------------------------------------------------------------
GENERATION_PROMPT = (
    "Given this context, state ONE new claim or observation that is NOT "
    "already stated in it. Do not summarize or restate anything already "
    "present. Be specific and concrete, not abstract. If you have nothing "
    "genuinely new to add, respond with exactly: system: nothing new.\n\n"
    "CONTEXT:\n{context}"
)

# --- circuit breaker: reusable class, single interface (execute()) ----
# Lifted out of module globals into circuit_breaker.py specifically so
# this same breaker can wrap any future failure-prone call (a real API
# instead of Ollama, corpus loads, whatever comes next) without copying
# the state machine again. Behavior unchanged and re-verified after the
# lift (see circuit_breaker.py's own self-test).
ollama_breaker = CircuitBreaker(
    failure_threshold=3,
    base_cooldown_minutes=5,
    max_cooldown_minutes=60,
    name="ollama",
)


def _call_ollama(context_text: str) -> str:
    """The raw call, unwrapped -- execute() handles success/failure
    bookkeeping around this."""
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": GENERATION_PROMPT.format(context=context_text),
            "stream": False,
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    text = resp.json().get("response", "").strip()
    return text if text else "system: empty generation."


def generate_thought(context_text: str) -> str:
    if not context_text or len(context_text.split()) < 10:
        return "system: idle, no context to build on."
    try:
        return ollama_breaker.execute(_call_ollama, context_text)
    except BreakerOpenError as e:
        return f"system: breaker open ({e.state}), skipping generation."
    except requests.exceptions.RequestException:
        log.error("Ollama call failed.")
        return "system: generation failed (model unreachable)."


# ---------------------------------------------------------------------------
# Nightly consolidation (unchanged logic; still destructive by design —
# see note in class docstring. Recommend running manually, not on
# schedule, until you've watched a few cycles.)
# ---------------------------------------------------------------------------
policy_engine = PolicyEngine()


def log_contradiction(new_thought_timestamp: str, supersedes_timestamp: str, reason: str) -> str:
    """Records that one thought contradicts/supersedes another. NOT
    auto-detected -- inventing a crude contradiction detector would be
    another unsourced-precision claim, same mistake as invented
    capability scores earlier. This is the honest, cheap version: a
    human or role explicitly states the contradiction and why, and it's
    permanently recorded, append-only. The OLD thought is never
    overwritten or deleted -- this just adds a pointer saying it's been
    superseded and by what, so belief evolution stays inspectable
    instead of silently reinterpreted."""
    return append_receipt({
        "event": "contradiction",
        "new_thought_timestamp": new_thought_timestamp,
        "supersedes_timestamp": supersedes_timestamp,
        "reason": reason,
    })


def find_contradictions_for(timestamp: str) -> list:
    """Given a thought's timestamp, find every contradiction receipt
    naming it as either the new claim or the superseded one."""
    if not RECEIPTS_FILE.exists():
        return []
    receipts = [json.loads(l) for l in open(RECEIPTS_FILE) if l.strip()]
    return [r for r in receipts if r.get("event") == "contradiction"
           and (r.get("new_thought_timestamp") == timestamp
                or r.get("supersedes_timestamp") == timestamp)]


def policy_version() -> str:
    """Content hash of the current policy set, same identity-hash
    pattern as RoleConfig. Attach to every receipt so a decision traces
    to exactly which policy rules were active -- 'this happened under
    policy v_X' instead of guessing what the rules were at the time."""
    payload = json.dumps(
        [(p.name, p.on_fail_message) for p in policy_engine.policies],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def consolidate_main_ledger():
    thoughts = read_ledger(MAIN_LEDGER)
    cutoff = datetime.now() - timedelta(days=MAIN_CONSOLIDATE_AGE_DAYS)
    old = [t for t in thoughts if datetime.fromisoformat(t["timestamp"]) < cutoff]
    recent = [t for t in thoughts if datetime.fromisoformat(t["timestamp"]) >= cutoff]
    if not old:
        return

    # 'Fail small': if this run would touch more than MAX_BLAST_RADIUS
    # records, only process a safe batch now and leave the remainder for
    # the next run, instead of rewriting the whole ledger in one pass.
    # A bug here corrupts a bounded slice, not everything at once.
    overflow = []
    if len(old) > MAX_BLAST_RADIUS:
        overflow = old[MAX_BLAST_RADIUS:]
        old = old[:MAX_BLAST_RADIUS]
        log.info(f"Consolidation batch capped at {MAX_BLAST_RADIUS} of "
                f"{len(old) + len(overflow)} eligible thoughts. "
                f"{len(overflow)} deferred to next run.")

    # Receipt written FIRST, unconditionally -- gets a real ID back,
    # which the policy check then verifies against, instead of a
    # hardcoded placeholder that always trivially passed.
    receipt_id = append_receipt({
        "event": "consolidation",
        "thoughts_consolidated": old,  # full originals, permanent, in receipts
        "count": len(old),
        "deferred_count": len(overflow),
        "policy_version": policy_version(),
    })

    try:
        policy_engine.enforce_all({
            "receipt_id": receipt_id,
            "write_mode": "overwrite",
            "target": "consolidation",
            "records_affected": len(old),
        })
    except PolicyViolation as v:
        log.error(f"Consolidation blocked by policy: {v}")
        return

    old_text = " ".join(t["text"] for t in old)
    consolidated = Thought(
        text=f"[consolidation of {len(old)} old thoughts, originals in receipts.jsonl] {old_text[:200]}",
        timestamp=datetime.now().isoformat(),
        cft_score=0.5,
        source="consolidation",
        derived_from=[t["timestamp"] for t in old],  # lineage, not just a placeholder
    )

    with open(MAIN_LEDGER, "w") as f:
        for t in recent + overflow:  # overflow stays untouched, waits for next run
            f.write(json.dumps(t) + "\n")
        f.write(json.dumps(consolidated.to_dict()) + "\n")
    log.info(f"Consolidated {len(old)} old main thoughts, lineage preserved "
             f"via derived_from ({len(consolidated.derived_from)} timestamps). "
             f"{len(overflow)} left for next run.")


# ---------------------------------------------------------------------------
# Core heartbeat
# ---------------------------------------------------------------------------
def heartbeat():
    log.info("Heartbeat started.")

    try:
        load_corpus()
    except Exception as e:
        log.error(f"Corpus load failed, continuing without corpus context: {e}")

    main_thoughts = read_ledger(MAIN_LEDGER)
    recent = main_thoughts[-CONTEXT_DEPTH:] if main_thoughts else []
    recent_text = " ".join(t["text"] for t in recent)

    try:
        query_emb = model.encode(recent_text or "seed", convert_to_tensor=True)
        ledger_hits = retrieve_from_ledgers(query_emb, [MAIN_LEDGER, SIDE_LEDGER], k=RETRIEVAL_K)
        corpus_hits = retrieve_from_corpus(recent_text or "seed", k=RETRIEVAL_K)
    except Exception as e:
        log.error(f"Retrieval failed, continuing with recent-thoughts-only context: {e}")
        ledger_hits, corpus_hits = [], []

    ledger_context = "\n".join(f"- {h['text']}" for h in ledger_hits)
    corpus_context = "\n".join(f"- {h['text']}" for h in corpus_hits)

    full_context = f"RECENT THOUGHTS:\n{recent_text}\n\nPAST THOUGHTS:\n{ledger_context}\n\nCORPUS:\n{corpus_context}"

    new_thought_text = generate_thought(full_context)

    if new_thought_text.startswith("system: breaker open"):
        append_receipt({"event": "heartbeat_skipped", "reason": new_thought_text})
        log.info("Heartbeat skipped: breaker open.")
        return

    score_breakdown = cft_score(new_thought_text, full_context)
    score = score_breakdown["composite"]

    # NOT WIRED IN YET, deliberately: loop_detector.combined_is_orbiting()
    # would go here, passing the `model` object already loaded above and
    # the last 20 accepted MAIN thoughts as recent_accepted. Left
    # disconnected because the embedding half of that check has only
    # been verified against synthetic vectors in this sandbox (no
    # huggingface.co access to confirm real embedding behavior) --
    # wiring it in before that's confirmed on a machine that can
    # actually run the model would be claiming a verification that
    # hasn't happened. To activate once confirmed:
    #
    #   from loop_detector import combined_is_orbiting
    #   recent_main = [t["text"] for t in read_ledger(MAIN_LEDGER)[-20:]]
    #   orbit_check = combined_is_orbiting(new_thought_text, recent_main, model=model)
    #   if orbit_check["is_orbiting"]:
    #       score = min(score, 0.2)  # same treatment as cft_v2's garbage cap

    thought_entry = Thought(
        text=new_thought_text,
        timestamp=datetime.now().isoformat(),
        cft_score=score,
        source="auto",
    )

    # Receipt written BEFORE the promote/prune decision, unconditionally —
    # so even a thought that gets side-lined and later pruned has a
    # permanent record of what it was and why it scored that way.
    append_receipt({
        "event": "heartbeat",
        "context_sent": full_context,
        "raw_output": new_thought_text,
        "score_breakdown": score_breakdown,
        "decision": "main" if score >= CFT_THRESHOLD else "side",
        "policy_version": policy_version(),
    })

    if score >= CFT_THRESHOLD:
        append_to_ledger(MAIN_LEDGER, thought_entry.to_dict())
        log.info(f"Promoted thought (CFT {score:.2f}): {new_thought_text[:80]}...")
    else:
        append_to_ledger(SIDE_LEDGER, thought_entry.to_dict())
        log.info(f"Side thought (CFT {score:.2f}): {new_thought_text[:80]}...")

    prune_ledger(SIDE_LEDGER, SIDE_PRUNE_DAYS)
    log.info("Heartbeat complete.")


def review_pending():
    """Human checkpoint. Shows every MAIN entry not yet marked reviewed
    and asks for explicit approval before marking it reviewed. Nothing
    downstream should treat a MAIN entry as trustworthy until it's been
    through this -- currently nothing enforces that consumers check the
    flag, so this is a checkpoint, not a lock. Wire real enforcement in
    wherever MAIN entries actually get consumed."""
    thoughts = read_ledger(MAIN_LEDGER)
    pending = [t for t in thoughts if not t.get("reviewed", False)]

    if not pending:
        print("Nothing pending review.")
        return

    print(f"{len(pending)} unreviewed MAIN entries.\n")
    reviewed_texts = set()
    for t in pending:
        print(f"[{t['timestamp']}] (cft={t.get('cft_score','?')})")
        print(f"  {t['text']}\n")
        answer = input("  Approve? [y/n/skip]: ").strip().lower()
        if answer == "y":
            reviewed_texts.add(t["timestamp"])
        elif answer == "n":
            print("  Marked rejected -- will remain unreviewed and flagged.")
            t["rejected"] = True

    with open(MAIN_LEDGER, "w") as f:
        for t in thoughts:
            if t["timestamp"] in reviewed_texts:
                t["reviewed"] = True
            f.write(json.dumps(t) + "\n")
    print(f"\n{len(reviewed_texts)} entries marked reviewed.")


# ---------------------------------------------------------------------------
# Scheduler & main
# ---------------------------------------------------------------------------
def run_daemon():
    log.info("Waking Loop daemon started.")
    schedule.every(HEARTBEAT_MINUTES).minutes.do(heartbeat)
    heartbeat()
    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(description="Waking Loop v1.1")
    parser.add_argument("--once", action="store_true", help="Run one heartbeat and exit.")
    parser.add_argument("--consolidate", action="store_true", help="Force nightly consolidation now.")
    parser.add_argument("--review", action="store_true", help="Human checkpoint: review unreviewed MAIN entries.")
    args = parser.parse_args()

    if args.review:
        review_pending()
        return
    if args.consolidate:
        consolidate_main_ledger()
        return
    if args.once:
        heartbeat()
        return
    run_daemon()


if __name__ == "__main__":
    main()

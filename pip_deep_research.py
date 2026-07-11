#!/usr/bin/env python3
"""
pip_deep_research.py  v2 - Pip's research engine, three modes.

MODES (pick with --mode, or by phrasing the topic):
  external  - web (DuckDuckGo) + Internet Archive + Semantic Scholar
              (academic; Consensus has no public API, Semantic Scholar
              fills that role free)
  internal  - the brain corpus: loom weighted retrieval + brain_search
              text grep + filename navigation + a map of the folder tree
  full      - both, compiled into one synthesis (DEFAULT)

Topic phrasing shortcuts (used by the phone relay, no flags needed):
  "web: <topic>" / "external: <topic>"      -> external
  "local: <topic>" / "brain: <topic>"       -> internal
  anything else                             -> full

Safety/robustness (carried from v1 hardening):
  - PID recorded in imports/_research_status.json (watchdog-compatible)
  - every source wrapped in a CircuitBreaker; failures become
    "(source unavailable)" notes, never fake data
  - per-source truncation keeps the synthesis prompt inside chat budget

USAGE:
    python pip_deep_research.py <topic words...> [--mode external|internal|full]
"""
import sys
import argparse
import urllib.request
import urllib.parse
import urllib.error
import json
import subprocess
import time
import os
from pathlib import Path

from circuit_breaker import CircuitBreaker, BreakerOpenError

# Paths
ROOT = Path(__file__).resolve().parent
_env_brain = os.environ.get("BRAIN_ROOT")
BRAIN_ROOT = Path(_env_brain) if _env_brain else ROOT.parents[3]
BRAIN_SEARCH_PY = ROOT.parent.parent / "brain_search" / "brain_search.py"
LOOM_PY = BRAIN_ROOT / "02_pip_and_system_architecture" / "builds" / "ecosystem_loop" / "loom_on_brain.py"
WAKING_LOOP_LEDGER = Path.home() / ".waking_loop" / "ledgers" / "main.jsonl"
STATUS_FILE = ROOT / "imports" / "_research_status.json"

MAX_SOURCE_CHARS = 1100
EXCLUDE_DIRS = {"reference_examples", "_tmp_gdevelop_examples", "__pycache__",
                ".pytest_cache", ".git", ".edge-test-profile", "node_modules"}

_BREAKERS = {}


def _breaker(name):
    if name not in _BREAKERS:
        _BREAKERS[name] = CircuitBreaker()
    return _BREAKERS[name]


def set_status(state, topic=""):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if state == "idle":
            STATUS_FILE.write_text(json.dumps({"status": "idle"}), encoding="utf-8")
        else:
            STATUS_FILE.write_text(json.dumps({
                "status": state, "topic": topic,
                "start_time": time.time(), "pid": os.getpid()
            }), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# EXTERNAL SOURCES
# ---------------------------------------------------------------------------

def search_ddg(query):
    print(f"[research] Web (DuckDuckGo): {query}")
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8')
    snippets = []
    for line in html.split('\n'):
        if 'class="result__snippet' in line:
            clean = line.split('>', 1)[1].split('</a>')[0]
            clean = clean.replace('<b>', '').replace('</b>', '')
            snippets.append(clean)
    if not snippets:
        raise RuntimeError("no snippets (bot challenge likely)")
    return "\n".join(snippets[:5])


def search_archive(query):
    print(f"[research] Internet Archive: {query}")
    url = (f"https://archive.org/advancedsearch.php?q={urllib.parse.quote(query)}"
           "&output=json&rows=3&fl[]=title,description,creator,year")
    req = urllib.request.Request(url, headers={'User-Agent': 'Pip_Deep_Research_Agent'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    docs = data.get("response", {}).get("docs", [])
    if not docs:
        raise RuntimeError("no archive results")
    results = []
    for doc in docs:
        t = doc.get('title', 'Unknown Title')
        d = doc.get('description', '')
        y = doc.get('year', 'Unknown Year')
        if isinstance(d, list):
            d = " ".join(d)
        results.append(f"Title: {t} ({y})\nDesc: {str(d)[:200]}")
    return "\n\n".join(results)


def search_scholar(query):
    """Semantic Scholar - free academic search (fills the Consensus role)."""
    print(f"[research] Semantic Scholar: {query}")
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?"
           f"query={urllib.parse.quote(query)}&limit=3&fields=title,abstract,year,citationCount")
    req = urllib.request.Request(url, headers={'User-Agent': 'Pip_Deep_Research_Agent'})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    papers = data.get("data", [])
    if not papers:
        raise RuntimeError("no papers found")
    out = []
    for p in papers:
        ab = (p.get("abstract") or "")[:220]
        out.append(f"Paper: {p.get('title')} ({p.get('year')}, cited {p.get('citationCount', '?')}x)\n{ab}")
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# INTERNAL SOURCES (the brain folder, fully visible)
# ---------------------------------------------------------------------------

def _walk_brain():
    for dirpath, dirnames, filenames in os.walk(BRAIN_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            yield Path(dirpath) / f


def brain_map(_query=""):
    """Top-level shape of the brain, so Pip can see what exists.
    Counts prune excluded dirs and cap at 999 to stay fast."""
    lines = []
    for d in sorted(BRAIN_ROOT.iterdir()):
        if not (d.is_dir() and d.name not in EXCLUDE_DIRS and not d.name.startswith(".")):
            continue
        n = 0
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS and not x.startswith(".")]
            n += len(filenames)
            if n > 999:
                break
        lines.append(f"{d.name}/ ({'999+' if n > 999 else n} files)")
    return "Brain folder map:\n" + "\n".join(lines)


def search_filenames(query):
    """Find files whose NAMES match the query - navigation, not just grep."""
    print(f"[research] Filename search: {query}")
    tokens = [t.lower() for t in query.split() if len(t) > 2]
    if not tokens:
        raise RuntimeError("query too short for filename search")
    hits = []
    for fp in _walk_brain():
        name = fp.name.lower()
        score = sum(1 for t in tokens if t in name)
        if score:
            hits.append((score, str(fp.relative_to(BRAIN_ROOT))))
    if not hits:
        raise RuntimeError("no filename matches")
    hits.sort(reverse=True)
    return "Files matching by name:\n" + "\n".join(h[1] for h in hits[:15])


def search_loom(query):
    """Weighted retrieval over the corpus via the ecosystem loom."""
    print(f"[research] Loom retrieval: {query}")
    if not LOOM_PY.exists():
        raise RuntimeError("loom_on_brain.py not found")
    res = subprocess.run([sys.executable, str(LOOM_PY), "ask", query],
                         capture_output=True, text=True, timeout=60,
                         cwd=str(LOOM_PY.parent))
    out = (res.stdout or "").strip()
    if not out:
        raise RuntimeError("loom returned nothing (run loom build?)")
    return out


def search_brain_text(query):
    """brain_search grep + subconscious waking-loop ledger."""
    print(f"[research] Corpus text search: {query}")
    results = []
    if BRAIN_SEARCH_PY.exists():
        try:
            res = subprocess.run(
                [sys.executable, str(BRAIN_SEARCH_PY), "--query", query, "--limit", "5"],
                capture_output=True, text=True, timeout=20)
            if res.stdout.strip():
                results.append("--- Corpus text matches ---\n" + res.stdout.strip()[:900])
        except Exception as e:
            print(f"[research] brain_search failed: {e}")
    if WAKING_LOOP_LEDGER.exists():
        try:
            matches = []
            for line in reversed(WAKING_LOOP_LEDGER.read_text(encoding='utf-8').splitlines()):
                if query.lower() in line.lower():
                    try:
                        d = json.loads(line)
                        matches.append(f"Thought ({d.get('timestamp')}): {d.get('text')}")
                    except Exception:
                        matches.append(line.strip())
                    if len(matches) >= 3:
                        break
            if matches:
                results.append("--- Subconscious memories ---\n" + "\n".join(matches))
        except Exception as e:
            print(f"[research] subconscious search failed: {e}")
    if not results:
        raise RuntimeError("no corpus text matches")
    return "\n\n".join(results)


# ---------------------------------------------------------------------------
# MODES + PIPELINE
# ---------------------------------------------------------------------------

EXTERNAL_SOURCES = [("web", search_ddg), ("archive", search_archive),
                    ("scholar", search_scholar)]
INTERNAL_SOURCES = [("map", brain_map), ("files", search_filenames),
                    ("loom", search_loom), ("corpus", search_brain_text)]


def guarded(name, fn, query):
    try:
        result = _breaker(name).execute(fn, query)
    except BreakerOpenError as e:
        print(f"[research] {name} breaker open ({e.cooldown_remaining_min:.0f}m left)")
        return None
    except Exception as e:
        print(f"[research] {name} unavailable: {e}")
        return None
    return (result or "")[:MAX_SOURCE_CHARS]


def parse_mode(topic, flag_mode):
    low = topic.lower()
    for prefix, mode in [("web:", "external"), ("external:", "external"),
                         ("local:", "internal"), ("brain:", "internal"),
                         ("full:", "full")]:
        if low.startswith(prefix):
            return topic[len(prefix):].strip(), mode
    return topic, (flag_mode or "full")


def run_research(topic, mode):
    sources = []
    if mode in ("external", "full"):
        sources += EXTERNAL_SOURCES
    if mode in ("internal", "full"):
        sources += INTERNAL_SOURCES

    gathered, unavailable = [], []
    for name, fn in sources:
        r = guarded(name, fn, topic)
        if r:
            gathered.append((name, r))
        else:
            unavailable.append(name)
    return gathered, unavailable


def synthesize_and_learn(topic, mode, gathered, unavailable):
    from pip_engine import PipEngine
    import pip_notify
    import pip_traces
    import cft_v2

    engine = PipEngine()
    blocks = "\n\n".join(f"### {name.upper()}:\n{text}" for name, text in gathered)
    missing = f"\n\n(Sources unavailable this run: {', '.join(unavailable)})" if unavailable else ""
    scope = {"external": "outside sources only",
             "internal": "our own brain corpus only",
             "full": "outside sources AND our own corpus - weave them together, "
                     "and note where they agree or disagree"}[mode]
    prompt = (
        f"SYSTEM DIRECTIVE: You are Pip. You ran a deep research cycle on: '{topic}' "
        f"(mode: {mode} - {scope}).\n\n{blocks}{missing}\n\n"
        f"Synthesize into a concise, insightful 2-paragraph summary. If internal and "
        f"external sources both appear, connect them. This goes to the user's phone "
        f"AND into your Waking Loop memory. If the sources were thin, say so honestly."
    )

    print("[research] Synthesizing...")
    try:
        summary = engine.generate_chat_response(prompt)
    except Exception as e:
        summary = f"I pulled the research but my engine crashed during synthesis: {e}"
        print(f"[research] Engine error: {e}")

    try:
        WAKING_LOOP_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        thought_entry = {
            "id": f"research_{int(time.time())}",
            "text": f"Research ({mode}) on {topic}:\n{summary}",
            "type": "deep_research", "source": "pip_deep_research",
            "timestamp": time.time(), "pass": "waking"
        }
        with open(WAKING_LOOP_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(thought_entry) + "\n")
            
        # Push to the new Learning Hub Brain API
        try:
            import requests
            mem_payload = {
                "topic": topic,
                "data": {
                    "text": summary,
                    "type": "deep_research",
                    "mode": mode,
                    "sources_used": [name for name, _ in gathered]
                }
            }
            requests.post("http://127.0.0.1:8050/memory", json=mem_payload, timeout=5)
            print("[research] Pushed to Learning Hub.")
            
            # Record telemetry for Deep Offloading & Correct Thinking
            try:
                cft_result = cft_v2.cft_score(summary, blocks)
                pip_traces.record_trace(
                    kind="learning_hub_offload",
                    action="push_research",
                    details={
                        "bytes": len(summary),
                        "cft_score": cft_result["composite"],
                        "cft_breakdown": cft_result,
                        "topic": topic
                    }
                )
            except Exception as e:
                print(f"[research] Failed to record offload metric: {e}")
                
        except Exception as e:
            print(f"[research] Failed to push to Learning Hub: {e}")
            
    except Exception as e:
        print(f"[research] Failed to write to ledger: {e}")

    print("[research] Alerting user...")
    pip_notify.notify(summary, f"Deep Research ({mode})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pip Deep Research Agent v2")
    parser.add_argument("topic", type=str, nargs="+", help="The topic to research")
    parser.add_argument("--mode", choices=["external", "internal", "full"], default=None)
    args = parser.parse_args()

    raw_topic = " ".join(args.topic)
    topic, mode = parse_mode(raw_topic, args.mode)
    print(f"[research] mode={mode} topic={topic}")

    set_status("running", topic)
    try:
        gathered, unavailable = run_research(topic, mode)
        if gathered:
            synthesize_and_learn(topic, mode, gathered, unavailable)
        else:
            import pip_notify
            pip_notify.notify(
                f"Research on '{topic}' came back empty - every source was "
                f"unavailable ({', '.join(unavailable)}). Try again later.",
                "Deep Research")
        print("[research] Done.")
    finally:
        set_status("idle")

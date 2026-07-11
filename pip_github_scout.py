#!/usr/bin/env python3
"""
pip_github_scout.py - Pip's once-a-day GitHub scan for relevant recent builds.

Queries the GitHub search API for repositories matching the ecosystem's themes
(local AI agents, living memory, retrieval, personas, PLM, opencode, etc.),
keeps the recently-pushed ones Pip hasn't seen before, and drops a digest into
Claude's handoff queue (01_agent_context/handoffs/@CLAUDE_GitHub_Scout_<date>.txt)
so Claude can mine it for build sessions on the 8am/6pm shift.

Design (same spirit as the rest of the fleet):
  - stdlib only (urllib) - no dependency, runs headless.
  - config-driven queries (github_scout_config.json) so themes evolve without code.
  - dedup via a seen-log: each run reports only NEW repos.
  - read-only: fetches public search results, writes ONE digest + its seen-log.
    Works with NO auth (~10 req/min); an optional token raises the limit and
    allows private repos.
  - degrades quietly: rate limits / network errors are reported in the digest,
    never crash the caller (nightwatch).

    python pip_github_scout.py            # run a scan, write the digest
    python pip_github_scout.py --dry-run  # print, don't write digest or seen-log
    python pip_github_scout.py --stdout   # also print the digest

Optional auth: set env GITHUB_TOKEN, or add {"github_token": "ghp_..."} to
pip_secrets.json (git-ignored). Public read access is enough; add repo scope
only to scan private repos too.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECRETS_PATH = HERE / "pip_secrets.json"
try:
    import pip_platform
    BRAIN_ROOT = pip_platform.BRAIN_ROOT
except Exception:
    BRAIN_ROOT = HERE.parent.parent.parent.parent

HANDOFFS = BRAIN_ROOT / "01_agent_context" / "handoffs"
CONFIG_PATH = HERE / "github_scout_config.json"
SEEN_PATH = HERE / "github_scout_seen.json"
API = "https://api.github.com/search/repositories"

DEFAULT_CONFIG = {
    "queries": [
        "local LLM agent long term memory",
        "personal knowledge base AI assistant",
        "second brain AI notes retrieval",
        "AI agent orchestration persona",
        "opencode agent",
        "ollama agent framework tools",
        "retrieval augmented generation local",
        "self-improving AI agent memory ledger",
        "multi-agent handoff coding",
        "plant identification machine learning"
    ],
    "pushed_within_days": 30,
    "per_query": 5,
    "max_report": 12,
    "min_stars": 0,
    "seen_cap": 2000
}


def get_token():
    """GitHub PAT: env GITHUB_TOKEN wins, else 'github_token' in pip_secrets.json.
    Optional - without it the scout still works at the unauthenticated rate limit."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    if SECRETS_PATH.exists():
        try:
            return str(json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
                       .get("github_token", "")).strip() or None
        except Exception:
            return None
    return None


def load_config():
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**DEFAULT_CONFIG, **cfg}
        except Exception as e:
            print(f"[scout] bad config, using defaults: {e}")
    return dict(DEFAULT_CONFIG)


def load_seen():
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_seen(seen, cap):
    lst = list(seen)[-cap:]
    SEEN_PATH.write_text(json.dumps(lst), encoding="utf-8")


def search(query, since_date, per_page, token=None):
    q = f"{query} pushed:>={since_date}"
    url = f"{API}?" + urllib.parse.urlencode(
        {"q": q, "sort": "updated", "order": "desc", "per_page": per_page})
    headers = {
        "User-Agent": "pip-github-scout",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("items", [])


def scan(cfg, token=None):
    since = (datetime.now() - timedelta(days=cfg["pushed_within_days"])).strftime("%Y-%m-%d")
    seen = load_seen()
    found = {}
    errors = []
    gap = 0.5 if token else 1.0
    for query in cfg["queries"]:
        try:
            items = search(query, since, cfg["per_query"], token=token)
        except Exception as e:
            errors.append(f"{query!r}: {e}")
            time.sleep(2)
            continue
        for it in items:
            fn = it.get("full_name")
            if not fn or fn in seen or fn in found:
                continue
            if (it.get("stargazers_count", 0) or 0) < cfg["min_stars"]:
                continue
            found[fn] = {
                "full_name": fn,
                "url": it.get("html_url", ""),
                "desc": (it.get("description") or "").strip(),
                "stars": it.get("stargazers_count", 0) or 0,
                "pushed": (it.get("pushed_at") or "")[:10],
                "lang": it.get("language") or "-",
                "matched": query,
            }
        time.sleep(gap)
    ranked = sorted(found.values(),
                    key=lambda r: (r["pushed"], r["stars"]), reverse=True)
    return ranked[:cfg["max_report"]], len(found), errors, since


def build_digest(repos, total_found, errors, since, n_queries):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# GitHub Scout - {today}",
             "",
             f"Pip's daily scan for builds relevant to the ecosystem "
             f"(pushed since {since}). New repos Pip hasn't flagged before.",
             ""]
    if not repos:
        lines.append("No new relevant repos today.")
    for r in repos:
        lines += [f"## {r['full_name']}  (stars {r['stars']}, pushed {r['pushed']}, {r['lang']})",
                  r["url"],
                  f"matched: \"{r['matched']}\"",
                  r["desc"] or "(no description)",
                  ""]
    lines += ["---",
              f"Scanned {n_queries} queries; {total_found} new repos surfaced, "
              f"top {len(repos)} kept.",
              "For Claude: skim for anything worth adopting/adapting into a build; "
              "note it in a brief or ledger, then archive this handoff.",
              ""]
    if errors:
        lines += ["## Scan errors (rate limit / network)"] + [f"- {e}" for e in errors] + [""]
    return "\n".join(lines)


def run_scout(dry_run=False, to_stdout=False):
    """Programmatic entry point (nightwatch calls this - no argv parsing)."""
    cfg = load_config()
    token = get_token()
    repos, total, errors, since = scan(cfg, token=token)
    digest = build_digest(repos, total, errors, since, len(cfg["queries"]))
    if not token:
        digest += ("\n(Running unauthenticated at the public rate limit. Add a "
                   "github_token to pip_secrets.json to raise it / scan private repos.)\n")

    if to_stdout or dry_run:
        print(digest)

    if dry_run:
        return digest

    HANDOFFS.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    out = HANDOFFS / f"@CLAUDE_GitHub_Scout_{today}.txt"
    out.write_text(digest, encoding="utf-8")
    print(f"[scout] digest -> {out}")

    seen = load_seen()
    seen.update(r["full_name"] for r in repos)
    save_seen(seen, cfg["seen_cap"])

    try:
        import pip_phone_relay
        top = repos[0]["full_name"] if repos else "nothing new"
        pip_phone_relay.send_response(
            f"GitHub Scout: {len(repos)} new relevant repos (top: {top}). "
            f"Left a digest in Claude's handoff queue.")
    except Exception as e:
        print(f"[scout] phone relay skipped: {e}")
    return digest


def main():
    ap = argparse.ArgumentParser(description="Pip's daily GitHub relevance scout")
    ap.add_argument("--dry-run", action="store_true", help="don't write digest or seen-log")
    ap.add_argument("--stdout", action="store_true", help="print the digest too")
    args = ap.parse_args()
    run_scout(dry_run=args.dry_run, to_stdout=args.stdout)


if __name__ == "__main__":
    main()

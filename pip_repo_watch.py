#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pip_config


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "repo_watch_config.json"
USER_AGENT = "Pip-v0-local-repo-watch"
KEYWORDS = {
    "approval": ["approval", "permission", "policy", "gate"],
    "memory": ["memory", "recall", "store", "rag", "vector", "summary"],
    "tools": ["tool", "integration", "connector", "plugin", "mcp"],
    "compression": ["token", "compression", "context", "compact"],
    "scheduler": ["schedule", "background", "worker", "queue", "cron"],
    "security": ["security", "sandbox", "prompt injection", "guard", "secret"],
    "ui": ["dashboard", "desktop", "tauri", "panel", "mobile"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def repo_watch_dir() -> Path:
    path = pip_config.get_memory_path() / "repo_watch"
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_report_path() -> Path:
    return repo_watch_dir() / "latest_repo_watch.json"


def status_path() -> Path:
    return repo_watch_dir() / "repo_watch_status.json"


def read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"error": f"Could not parse {path.name}"}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(config_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("version", 1)
    data.setdefault("cadence_days", 7)
    data.setdefault("repos", [])
    return data


def _github_get(path: str, timeout: int = 12) -> dict[str, Any] | list[Any]:
    url = f"https://api.github.com{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe_get(path: str) -> tuple[Any, str | None]:
    try:
        return _github_get(path), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return None, str(exc)


def _repo_text(repo: dict[str, Any], commits: list[dict[str, Any]]) -> str:
    parts = [
        str(repo.get("description") or ""),
        " ".join(repo.get("topics") or []),
    ]
    for commit in commits:
        commit_data = commit.get("commit") or {}
        parts.append(str(commit_data.get("message") or ""))
    return " ".join(parts).lower()


def _topic_hits(text: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for topic, words in KEYWORDS.items():
        found = [word for word in words if word in text]
        if found:
            hits[topic] = found
    return hits


def _takeaways(name: str, text: str, hits: dict[str, list[str]]) -> list[str]:
    takeaways: list[str] = []
    if "approval" in hits or "security" in hits:
        takeaways.append("Review for permission-gate, prompt-guard, or safety-boundary ideas before expanding Pip actions.")
    if "memory" in hits:
        takeaways.append("Look for memory summarization or retrieval patterns that could strengthen Pip's tattoo/skin/fur memory.")
    if "tools" in hits:
        takeaways.append("Check whether new tool/connector patterns can be adapted as draft-only Pip skills.")
    if "compression" in hits:
        takeaways.append("Compare token/context compression ideas against Pip's Token Governor.")
    if "scheduler" in hits:
        takeaways.append("Scan for background-loop and queue ideas that keep weekly/ambient work supervised.")
    if "ui" in hits:
        takeaways.append("Review UI/control-surface changes for dashboard inspiration.")
    if not takeaways:
        takeaways.append(f"Skim {name} changes manually; no strong Pip-fit keyword cluster was detected.")
    return takeaways[:4]


def scan_one_repo(repo_config: dict[str, Any]) -> dict[str, Any]:
    full_name = repo_config.get("full_name", "")
    repo, repo_error = _safe_get(f"/repos/{full_name}")
    commits, commit_error = _safe_get(f"/repos/{full_name}/commits?per_page=5")
    release, release_error = _safe_get(f"/repos/{full_name}/releases/latest")
    commits_list = commits if isinstance(commits, list) else []
    repo_data = repo if isinstance(repo, dict) else {}
    text = _repo_text(repo_data, commits_list)
    hits = _topic_hits(text)
    recent_commits = []
    for item in commits_list[:5]:
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        recent_commits.append({
            "sha": str(item.get("sha", ""))[:12],
            "message": str(commit.get("message", "")).splitlines()[0][:180],
            "date": author.get("date"),
            "url": item.get("html_url"),
        })
    latest_release = release if isinstance(release, dict) else {}
    return {
        "name": repo_config.get("name") or full_name,
        "full_name": full_name,
        "why_watch": repo_config.get("why_watch", ""),
        "ok": bool(repo_data),
        "errors": [error for error in [repo_error, commit_error, release_error] if error and "404" not in error],
        "html_url": repo_data.get("html_url") or f"https://github.com/{full_name}",
        "description": repo_data.get("description"),
        "stars": repo_data.get("stargazers_count"),
        "forks": repo_data.get("forks_count"),
        "open_issues": repo_data.get("open_issues_count"),
        "pushed_at": repo_data.get("pushed_at"),
        "topics": repo_data.get("topics") or [],
        "latest_release": {
            "tag": latest_release.get("tag_name"),
            "name": latest_release.get("name"),
            "published_at": latest_release.get("published_at"),
            "url": latest_release.get("html_url"),
        } if latest_release else None,
        "recent_commits": recent_commits,
        "topic_hits": hits,
        "suggested_takeaways": _takeaways(repo_config.get("name") or full_name, text, hits),
    }


def build_report(repo_results: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    hot = [
        repo for repo in repo_results
        if repo.get("topic_hits") or repo.get("latest_release") or repo.get("recent_commits")
    ]
    proposal_lines = []
    for repo in hot[:5]:
        first_takeaway = (repo.get("suggested_takeaways") or ["Review manually."])[0]
        proposal_lines.append(f"{repo.get('name')}: {first_takeaway}")
    if not proposal_lines:
        proposal_lines.append("No strong update candidates found this scan.")
    return {
        "version": 1,
        "generated_at": utc_now(),
        "mode": "repo_watch_draft_only",
        "cadence_days": config.get("cadence_days", 7),
        "repo_count": len(repo_results),
        "proposal_card": {
            "proposal": f"Weekly repo watch scanned {len(repo_results)} public repos.",
            "evidence": " ".join(proposal_lines[:3]),
            "status": "proposed",
            "source_kind": "public_github_api",
            "score": round(min(1.0, 0.25 + len(hot) * 0.1), 3),
        },
        "repos": repo_results,
        "next_actions": proposal_lines[:8],
        "safety_contract": [
            "Reads public GitHub repository metadata only.",
            "Writes draft reports under Pip memory.",
            "Does not clone, patch, open PRs, or install dependencies.",
            "Any proposed Pip change still needs normal review and approval.",
        ],
    }


def scan_repo_watch(config_path: str | Path = DEFAULT_CONFIG_PATH, force: bool = True) -> dict[str, Any]:
    config = load_config(config_path)
    previous = get_repo_watch_status()
    cadence_days = int(config.get("cadence_days", 7))
    should_run = force
    if not force and previous.get("last_scan_at"):
        try:
            last = datetime.fromisoformat(previous["last_scan_at"])
            should_run = datetime.now(timezone.utc) - last >= timedelta(days=cadence_days)
        except Exception:
            should_run = True
    elif not previous.get("last_scan_at"):
        should_run = True
    if not should_run:
        previous["skipped"] = True
        previous["message"] = f"Repo watch is inside the {cadence_days}-day cadence window."
        return previous

    results = [scan_one_repo(repo) for repo in config.get("repos", [])]
    report = build_report(results, config)
    archive = repo_watch_dir() / f"repo_watch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json(latest_report_path(), report)
    write_json(archive, report)
    status = {
        "generated_at": utc_now(),
        "mode": "repo_watch_draft_only",
        "last_scan_at": report["generated_at"],
        "latest_report": str(latest_report_path()),
        "archive_path": str(archive),
        "repo_count": report["repo_count"],
        "proposal": report,
    }
    write_json(status_path(), status)
    return status


def get_repo_watch_status() -> dict[str, Any]:
    status = read_json_if_exists(status_path())
    if isinstance(status, dict):
        return status
    return {
        "generated_at": utc_now(),
        "mode": "repo_watch_draft_only",
        "last_scan_at": None,
        "latest_report": str(latest_report_path()) if latest_report_path().exists() else None,
        "proposal": read_json_if_exists(latest_report_path()),
    }


def queue_weekly_repo_watch() -> dict[str, Any]:
    import pip_scheduler

    job = pip_scheduler.add_job(
        "Weekly GitHub repo watch",
        "Run scan_repo_watch weekly and draft update suggestions for Pip's system.",
        schedule_type="weekly",
        scope="repo_watch",
    )
    return {"queued": True, "job": job}

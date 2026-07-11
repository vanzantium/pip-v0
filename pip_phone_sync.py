#!/usr/bin/env python3
"""
pip_phone_sync.py — Drop-folder watcher for S25 telemetry ingestion.

Monitors a configurable folder for new .json files from the phone.
When a file lands:
  1. Validates it against ANDROID_TELEMETRY_SCHEMA.
  2. Runs pip_phone_bridge.import_phone_usage_text() to produce a proposal.
  3. Moves the processed file to _processed/.
  4. Notifies the owner via pip_messenger if a proposal was generated.

Sync options (user picks one — all just drop files into the folder):
  • Google Drive / OneDrive — phone exports to cloud folder synced to PC.
  • Syncthing — free P2P sync between phone and PC over Wi-Fi.
  • USB / manual copy.
  • KDE Connect / Samsung Flow — direct file push.

Usage:
  python pip_phone_sync.py               # Watch mode (runs forever)
  python pip_phone_sync.py --once        # Single scan and exit
  python pip_phone_sync.py --test        # Drop a synthetic file and process it
  python pip_phone_sync.py --status      # Show drop folder status
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

# ── config ────────────────────────────────────────────────────────────────────

def _load_secrets() -> dict[str, Any]:
    secrets_path = ROOT / "pip_secrets.json"
    if not secrets_path.exists():
        return {}
    try:
        return json.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_drop_folder() -> Path:
    secrets = _load_secrets()
    rel = secrets.get("phone_drop_folder", "imports/phone_drop")
    folder = ROOT / rel
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_processed_folder() -> Path:
    folder = get_drop_folder() / "_processed"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_failed_folder() -> Path:
    folder = get_drop_folder() / "_failed"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ── core processing ──────────────────────────────────────────────────────────

def process_file(path: Path) -> dict[str, Any]:
    """Validate and ingest a single phone usage JSON file."""
    print(f"[pip_phone_sync] Processing: {path.name}")

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return _handle_failure(path, f"Could not read file: {exc}")

    # Validate
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return _handle_failure(path, f"Invalid JSON: {exc}")

    from pip_phone_bridge import validate_usage_events
    validation = validate_usage_events(raw)

    if not validation.get("ok"):
        return _handle_failure(path, f"Validation failed: {validation.get('errors', [])}")

    # Ingest
    try:
        from pip_phone_bridge import import_phone_usage_text
        status = import_phone_usage_text(text, source_name=path.name, run_optimizer=True)
    except Exception as exc:
        return _handle_failure(path, f"Ingestion error: {exc}")

    # Move to processed
    dest = get_processed_folder() / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{path.name}"
    shutil.move(str(path), str(dest))

    # Log trace
    _log_trace(path.name, "processed", validation)

    # Notify owner
    proposal = status.get("proposal")
    if proposal:
        try:
            import pip_messenger
            if pip_messenger.is_enabled():
                pip_messenger.notify_proposal(proposal)
                print(f"[pip_phone_sync] Notification sent for {path.name}")
        except Exception as exc:
            print(f"[pip_phone_sync] Notification failed: {exc}")

    result = {
        "ok": True,
        "file": path.name,
        "event_count": validation.get("event_count", 0),
        "warnings": validation.get("warnings", []),
        "proposal": proposal,
        "processed_to": str(dest),
    }
    print(f"[pip_phone_sync] Done: {path.name} ({validation.get('event_count', 0)} events)")
    return result


def _handle_failure(path: Path, error: str) -> dict[str, Any]:
    print(f"[pip_phone_sync] FAILED: {path.name} — {error}")
    dest = get_failed_folder() / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{path.name}"
    try:
        shutil.move(str(path), str(dest))
    except Exception:
        pass
    _log_trace(path.name, "failed", {"error": error})
    return {"ok": False, "file": path.name, "error": error}


def _log_trace(filename: str, status: str, details: Any = None) -> None:
    try:
        import pip_traces
        pip_traces.record_trace(
            kind="phone_sync",
            actor="pip",
            action="process_phone_drop",
            status=status,
            summary=f"Phone sync: {filename} ({status})",
            details=details or {},
            source="pip_phone_sync",
            tags=["phone_sync", "telemetry"],
        )
    except Exception:
        pass


# ── scanning ─────────────────────────────────────────────────────────────────

def scan_once() -> list[dict[str, Any]]:
    """Scan the drop folder for new .json files and process them."""
    drop = get_drop_folder()
    files = sorted(drop.glob("*.json"))
    results = []
    for path in files:
        # Skip hidden files and our own config
        if path.name.startswith("_") or path.name.startswith("."):
            continue
        result = process_file(path)
        results.append(result)
    return results


def watch(interval_seconds: int = 30) -> None:
    """Watch the drop folder continuously."""
    drop = get_drop_folder()
    print(f"[pip_phone_sync] Watching {drop} every {interval_seconds}s")
    print(f"[pip_phone_sync] Drop phone usage .json files here to ingest them.")
    print(f"[pip_phone_sync] Press Ctrl+C to stop.\n")

    while True:
        try:
            results = scan_once()
            for r in results:
                if r.get("ok"):
                    print(f"  ✓ {r['file']} — {r.get('event_count', 0)} events")
                else:
                    print(f"  ✗ {r['file']} — {r.get('error', 'unknown')}")
        except Exception as exc:
            print(f"[pip_phone_sync] Scan error: {exc}")

        time.sleep(interval_seconds)


# ── test mode ─────────────────────────────────────────────────────────────────

def generate_test_file() -> Path:
    """Generate a synthetic phone usage file for testing the pipeline."""
    from datetime import timedelta
    now = datetime.now(timezone.utc).replace(microsecond=0)
    events = []
    apps = [
        ("Messages", 8, 55, 12, 9),
        ("Instagram", 15, 180, 6, 4),
        ("YouTube", 5, 420, 3, 2),
        ("Chrome", 12, 90, 2, 1),
        ("Gmail", 6, 45, 18, 14),
    ]
    for i, (app, launches, duration, notif, dismissed) in enumerate(apps):
        for j in range(min(launches, 3)):
            ts = now - timedelta(days=6 - i, hours=j * 3)
            events.append({
                "timestamp": ts.isoformat(),
                "app_name": app,
                "event_type": "launch",
                "battery_delta": max(1, duration // 60),
                "notifications_received": notif // max(1, min(launches, 3)),
                "notifications_dismissed_unread": dismissed // max(1, min(launches, 3)),
                "session_duration_seconds": duration // min(launches, 3),
            })

    drop = get_drop_folder()
    path = drop / f"s25_test_{now.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(events, indent=2), encoding="utf-8")
    print(f"[pip_phone_sync] Generated test file: {path}")
    return path


# ── status ────────────────────────────────────────────────────────────────────

def get_status() -> dict[str, Any]:
    drop = get_drop_folder()
    processed = get_processed_folder()
    failed = get_failed_folder()
    pending = list(drop.glob("*.json"))
    pending = [p for p in pending if not p.name.startswith("_") and not p.name.startswith(".")]
    return {
        "drop_folder": str(drop),
        "pending_files": len(pending),
        "pending_names": [p.name for p in pending],
        "processed_count": len(list(processed.glob("*.json"))),
        "failed_count": len(list(failed.glob("*.json"))),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pip Phone Sync — drop-folder watcher for S25 telemetry.")
    parser.add_argument("--once", action="store_true", help="Scan once and exit.")
    parser.add_argument("--test", action="store_true", help="Generate a test file and process it.")
    parser.add_argument("--status", action="store_true", help="Show drop folder status.")
    parser.add_argument("--interval", type=int, default=30, help="Watch interval in seconds (default: 30).")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(get_status(), indent=2))
    elif args.test:
        test_path = generate_test_file()
        results = scan_once()
        for r in results:
            print(json.dumps(r, indent=2))
    elif args.once:
        results = scan_once()
        if not results:
            print("[pip_phone_sync] No files to process.")
        for r in results:
            print(json.dumps(r, indent=2))
    else:
        watch(interval_seconds=args.interval)

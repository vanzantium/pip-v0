#!/usr/bin/env python3
"""
pip_phone_relay.py — Two-way phone ↔ Pip relay via ntfy.sh.

Listens for incoming messages on your ntfy topic.
When you send a message from your phone, Pip processes it through
her Ollama brain and sends the response back via the same topic.

This gives you a text conversation with Pip from anywhere.

Usage:
  python pip_phone_relay.py               # Run the relay (foreground)
  python pip_phone_relay.py --background  # Run as a background process
  python pip_phone_relay.py --status      # Check relay status
  python pip_phone_relay.py --test        # Send a test prompt and show response

How it works:
  1. Polls ntfy.sh for new messages on your topic every few seconds.
  2. Filters out messages Pip sent herself (by checking the title prefix).
  3. Routes your message through pip_engine.generate_chat_response().
  4. Sends the response back via ntfy so it appears on your phone.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RELAY_STATE_PATH = ROOT / "imports" / "_relay_state.json"

# ── config ────────────────────────────────────────────────────────────────────

def _load_secrets() -> dict[str, Any]:
    secrets_path = ROOT / "pip_secrets.json"
    if not secrets_path.exists():
        return {}
    try:
        return json.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_topic_url() -> tuple[str, str]:
    """Returns (base_url, topic)."""
    secrets = _load_secrets()
    server = secrets.get("ntfy_server", "https://ntfy.sh").rstrip("/")
    topic = secrets.get("ntfy_topic", "")
    return server, topic


# ── state persistence (track last seen message) ──────────────────────────────

def _load_state() -> dict[str, Any]:
    if not RELAY_STATE_PATH.exists():
        return {"last_seen_id": "", "last_seen_time": 0, "is_napping": False, "seen_ids": []}
    try:
        state = json.loads(RELAY_STATE_PATH.read_text(encoding="utf-8"))
        if "is_napping" not in state:
            state["is_napping"] = False
        if "seen_ids" not in state:
            state["seen_ids"] = []
        return state
    except Exception:
        return {"last_seen_id": "", "last_seen_time": 0, "is_napping": False, "seen_ids": []}


def _save_state(state: dict[str, Any]) -> None:
    RELAY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RELAY_STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


# ── ntfy polling ──────────────────────────────────────────────────────────────

PIP_TITLE_PREFIX = "[Pip]"


def poll_messages(since: int = 0) -> list[dict[str, Any]]:
    """Poll ntfy for messages since the given Unix timestamp."""
    server, topic = _get_topic_url()
    if not topic:
        return []

    # Use the JSON poll endpoint
    since_param = since if since > 0 else int(time.time() - 60)
    url = f"{server}/{topic}/json?poll=1&since={since_param}"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            lines = resp.read().decode("utf-8").strip().split("\n")
            messages = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("event") == "message":
                        messages.append(msg)
                except json.JSONDecodeError:
                    continue
            return messages
    except Exception as exc:
        print(f"[relay] Poll error: {exc}")
        return []


def is_from_pip(msg: dict[str, Any]) -> bool:
    """Check if a message was sent by Pip (to avoid echo loops)."""
    title = msg.get("title", "")
    # Pip always prefixes her titles with [Pip]
    if title.startswith(PIP_TITLE_PREFIX):
        return True
    # Also check tags
    tags = msg.get("tags", [])
    if "fairy" in tags:
        return True
    return False


# Global Outbox Queue for handling rate limits without stalling
_outbox_queue = queue.Queue()

def _outbox_worker():
    backoff = 1.0
    while True:
        try:
            item = _outbox_queue.get()
            if item is None:
                break
                
            text = item["text"]
            server, topic = _get_topic_url()
            if not topic:
                _outbox_queue.task_done()
                continue
                
            url = f"{server}/{topic}"
            
            # Chunk the response to avoid NTFY truncation (mobile limits often visually truncate at ~500)
            import textwrap
            chunks = textwrap.wrap(text, width=400, break_long_words=False, replace_whitespace=False)
            if not chunks:
                chunks = [""]
            
            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    push_text = f"[{i+1}/{len(chunks)}]\n{chunk}"
                else:
                    push_text = chunk
                
                headers = {
                    "Title": f"{PIP_TITLE_PREFIX} Reply",
                    "Tags": "fairy,reply",
                }
                
                req = urllib.request.Request(
                    url,
                    data=push_text.encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                
                success = False
                while not success:
                    try:
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            resp.read()
                        success = True
                        backoff = 1.0 # Reset backoff on success
                    except urllib.error.HTTPError as e:
                        if e.code == 429:
                            print(f"[relay] Rate limited (429). Backing off for {backoff}s...")
                            time.sleep(backoff)
                            backoff = min(backoff * 2, 60.0) # max 60s backoff
                        else:
                            print(f"[relay] Send HTTP error: {e}")
                            break # Drop on non-429 error
                    except Exception as e:
                        print(f"[relay] Send network error: {e}")
                        break # Drop on network error
                
                # Sleep briefly between chunks so they arrive in order
                if len(chunks) > 1:
                    time.sleep(0.5)
                    
            _outbox_queue.task_done()
        except Exception as e:
            print(f"[relay] Worker unhandled error: {e}")
            time.sleep(1)

# Start worker thread
import atexit
threading.Thread(target=_outbox_worker, daemon=True).start()
atexit.register(_outbox_queue.join)

def send_response(text: str, in_reply_to: str = "") -> dict[str, Any]:
    """Queue Pip's response to be sent via ntfy."""
    server, topic = _get_topic_url()
    if not topic:
        return {"ok": False, "error": "No ntfy topic configured."}
        
    _outbox_queue.put({"text": text})
    return {"ok": True, "note": "queued"}


# ── message processing ───────────────────────────────────────────────────────

def process_message(msg: dict[str, Any]) -> str:
    """Route an incoming message through Pip's brain and return the response."""
    user_text = msg.get("message", "").strip()
    
    # Check for attachments
    attachment = msg.get("attachment")
    if attachment and isinstance(attachment, dict):
        att_url = attachment.get("url")
        att_name = attachment.get("name", "upload.file")
        if att_url:
            try:
                # Create the drop-zone directory
                brain_root = ROOT.parent.parent.parent
                drop_zone = brain_root / "99_inbox_unsorted" / "phone_uploads"
                drop_zone.mkdir(parents=True, exist_ok=True)
                
                # Download the file asynchronously so it doesn't block the relay loop
                dest_path = drop_zone / f"{int(time.time())}_{att_name}"
                
                def download_task(url, path, name):
                    try:
                        urllib.request.urlretrieve(url, path)
                        print(f"[relay] Downloaded attachment to {path}")
                    except Exception as e:
                        print(f"[relay] Failed to download attachment: {e}")
                
                threading.Thread(target=download_task, args=(att_url, dest_path, att_name), daemon=True).start()
                
                attachment_note = f"[System: User uploaded '{att_name}'. File is downloading to: {dest_path}]"
                user_text = f"{user_text}\n\n{attachment_note}".strip()
            except Exception as e:
                print(f"[relay] Failed to set up background download: {e}")

    if not user_text:
        return "I received an empty message — did you mean to say something?"

    state = _load_state()
    if state.get("is_napping") and not user_text.lower().startswith("@anti"):
        return "Zzz... Pip is currently in a deep subconscious state (background updates are being applied). She will wake up shortly!"

    print(f"[relay] Incoming: {user_text[:80]}...")

    # Log the incoming message
    _log_trace("incoming", user_text)

    # ── Delegation Hooks ──
    lower_text = user_text.lower()
    
    if lower_text.startswith("/status"):
        import pip_hardware_scanner
        try:
            hw = pip_hardware_scanner.scan_and_save()
            return f"System Status:\nCPU: {hw.get('cpu')}\nRAM: {hw.get('ram_gb')}GB\nVulkan: {hw.get('vulkan_supported')}"
        except Exception as e:
            return f"Status check failed: {e}"

    if lower_text.startswith("/evolve start"):
        def run_evolve():
            try:
                import subprocess
                brain_root = ROOT.parent.parent.parent
                engine_dir = brain_root / "02_pip_and_system_architecture" / "builds" / "learning_hub" / "evolution_engine"
                proc = subprocess.run(
                    ["python", "controller.py"],
                    cwd=str(engine_dir),
                    capture_output=True,
                    text=True
                )
                out = proc.stdout[-300:] if proc.stdout else "No output."
                send_response(f"[PipEvolve]\nFinished optimization.\n{out}")
            except Exception as e:
                send_response(f"[PipEvolve Error]\n{e}")
                
        threading.Thread(target=run_evolve, daemon=True).start()
        return "Started PipEvolve sandboxed loop in the background. I'll let you know when it finishes!"

    if "@anti" in lower_text:
        try:
            brain_root = ROOT.parent.parent.parent
            handoffs_dir = brain_root / "01_agent_context" / "handoffs"
            handoffs_dir.mkdir(parents=True, exist_ok=True)
            inbox_file = handoffs_dir / "@anti_inbox.md"
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            
            with open(inbox_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n## Request at {timestamp}\n")
                f.write(f"{user_text}\n")
                
            return "I've dropped this request into Antigravity's inbox (@anti_inbox.md) on the laptop."
        except Exception as e:
            return f"Failed to route to Antigravity: {e}"
            
    if "@claude" in lower_text:
        import re
        import subprocess
        
        match = re.search(r'@claude\s+(.*)', user_text, re.IGNORECASE | re.DOTALL)
        prompt = match.group(1).strip() if match else user_text
        
        def run_claude(p: str):
            try:
                brain_root = ROOT.parent.parent.parent
                # Claude code usually accepts the prompt directly or via -p.
                proc = subprocess.run(
                    ["claude", "-p", p],
                    capture_output=True,
                    text=True,
                    cwd=str(brain_root)
                )
                out = proc.stdout if proc.stdout else proc.stderr
                if not out.strip():
                    out = "Claude process finished silently."
                send_response(f"[Claude]\n{out}")
            except Exception as e:
                send_response(f"[Claude Error]\n{e}")
                
        threading.Thread(target=run_claude, args=(prompt,), daemon=True).start()
        return "I have invoked Claude in the background. I will relay the response when it finishes."

    # Route through Pip's chat engine
    try:
        from pip_engine import PipEngine
        memory_path = ROOT / "imports" / "_memory.json"
        engine = PipEngine(memory_path=str(memory_path))
        response = engine.generate_chat_response(user_text)
    except Exception as exc:
        response = f"My brain hit an error: {exc}"
        print(f"[relay] Engine error: {exc}")

    # Log the outgoing response
    _log_trace("outgoing", response[:200])

    return response


def _log_trace(direction: str, content: str) -> None:
    try:
        import pip_traces
        pip_traces.record_trace(
            kind="phone_relay",
            actor="pip" if direction == "outgoing" else "owner",
            action=f"relay_{direction}",
            status="ok",
            summary=content[:120],
            details={"direction": direction, "content_length": len(content)},
            source="pip_phone_relay",
            tags=["relay", "phone", direction],
        )
    except Exception:
        pass


# ── main loop ─────────────────────────────────────────────────────────────────

def _handle_msg_thread(msg: dict[str, Any], state: dict[str, Any]) -> None:
    try:
        response = process_message(msg)
        result = send_response(response)
        if result.get("ok"):
            print(f"[relay] Replied ({len(response)} chars)")
        else:
            print(f"[relay] Failed to send reply: {result.get('error')}")
    except Exception as e:
        print(f"[relay] Thread error: {e}")

def run_relay(poll_interval: int = 15) -> None:
    """Main relay loop. Streams ntfy for messages and responds."""
    server, topic = _get_topic_url()
    if not topic:
        print("[relay] ERROR: No ntfy_topic configured in pip_secrets.json. Cannot start relay.")
        return

    print(f"[relay] Pip Phone Relay starting (Streaming Mode)...")
    print(f"[relay] Listening on: {server}/{topic}")
    print(f"[relay] Send a message from your phone's ntfy app to talk to Pip.")
    print(f"[relay] Press Ctrl+C to stop.\n")

    state = _load_state()
    # Start listening from 1 hour ago to catch missed messages
    if state["last_seen_time"] == 0:
        state["last_seen_time"] = int(time.time()) - 3600
        _save_state(state)

    while True:
        try:
            since_param = state["last_seen_time"] if state.get("last_seen_time", 0) > 0 else int(time.time() - 3600)
            url = f"{server}/{topic}/json?since={since_param}"
            
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req) as resp:
                for line_bytes in resp:
                    line = line_bytes.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                        
                    if msg.get("event") == "message":
                        msg_time = msg.get("time", 0)
                        msg_id = msg.get("id", "")

                        # Skip messages we've already seen
                        if msg_id in state.get("seen_ids", []):
                            continue

                        # Skip Pip's own messages (prevent echo loop)
                        if is_from_pip(msg):
                            state["last_seen_time"] = max(state.get("last_seen_time", 0), msg_time)
                            state["last_seen_id"] = msg_id
                            if msg_id:
                                state["seen_ids"].append(msg_id)
                                state["seen_ids"] = state["seen_ids"][-50:]
                            _save_state(state)
                            continue

                        # Update state immediately so we don't re-process on reconnect
                        state["last_seen_time"] = max(state.get("last_seen_time", 0), msg_time)
                        state["last_seen_id"] = msg_id
                        if msg_id:
                            state["seen_ids"].append(msg_id)
                            state["seen_ids"] = state["seen_ids"][-50:]
                        _save_state(state)

                        # Process message in background thread so we don't block the stream
                        threading.Thread(target=_handle_msg_thread, args=(msg, state), daemon=True).start()

        except KeyboardInterrupt:
            print("\n[relay] Stopped.")
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                print(f"[relay] Streaming rate limited! Backing off for 60s...")
                time.sleep(60)
            else:
                print(f"[relay] HTTP Error: {exc}")
                time.sleep(15)
        except Exception as exc:
            print(f"[relay] Stream disconnected: {exc}. Reconnecting in 5s...")
            time.sleep(5)


# ── status ────────────────────────────────────────────────────────────────────

def get_status() -> dict[str, Any]:
    secrets = _load_secrets()
    state = _load_state()
    server, topic = _get_topic_url()
    return {
        "configured": bool(topic),
        "topic": topic,
        "server": server,
        "last_seen_time": state.get("last_seen_time", 0),
        "last_seen_id": state.get("last_seen_id", ""),
        "messaging_enabled": bool(secrets.get("messaging_enabled")),
        "is_napping": state.get("is_napping", False)
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pip Phone Relay — two-way ntfy ↔ Ollama bridge.")
    parser.add_argument("--status", action="store_true", help="Show relay configuration status.")
    parser.add_argument("--test", action="store_true", help="Send a test prompt through the relay.")
    parser.add_argument("--interval", type=int, default=15, help="Poll interval in seconds (default: 15).")
    parser.add_argument("--background", action="store_true", help="Run as a background process.")
    parser.add_argument("--nap", action="store_true", help="Put Pip in subconscious mode.")
    parser.add_argument("--wake", action="store_true", help="Wake Pip from subconscious mode.")
    args = parser.parse_args()

    if args.nap:
        state = _load_state()
        state["is_napping"] = True
        _save_state(state)
        print("[relay] Pip is now NAPPING (Subconscious mode).")
    elif args.wake:
        state = _load_state()
        state["is_napping"] = False
        _save_state(state)
        print("[relay] Pip is now AWAKE (Interactive mode).")
    elif args.status:
        print(json.dumps(get_status(), indent=2))
    elif args.test:
        print("[relay] Sending test message through Pip's brain...")
        test_msg = {"message": "Hey Pip, what are you working on right now?", "time": int(time.time()), "id": "test"}
        response = process_message(test_msg)
        print(f"\n[relay] Pip says:\n{response}")
        result = send_response(response)
        print(f"\n[relay] Sent to ntfy: {result}")
    elif args.background:
        import subprocess, sys
        import pip_platform
        log_path = ROOT / "imports" / "_relay_log.txt"
        log_file = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-u", __file__, "--interval", str(args.interval)],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **pip_platform.hidden_subprocess_kwargs(),
        )
        print(f"[relay] Started in background (PID: {proc.pid}). Logging to imports/_relay_log.txt")
    else:
        run_relay(poll_interval=args.interval)

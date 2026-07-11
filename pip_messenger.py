#!/usr/bin/env python3
"""
pip_messenger.py — Pip's outbound messaging module.

Backends:
  • Gmail SMTP  — sends email via App Password (no OAuth needed).
  • ntfy.sh     — free push notifications, zero account required.

Safety contract:
  • Only messages the owner (hardcoded recipient in pip_secrets.json).
  • Every outbound message is logged in pip_traces.
  • Rate limits are enforced in code (default: 1/hour, 5/day).
  • Disabled by default until messaging_enabled = true in secrets.
  • Content is limited to proposals, digests, and health alerts.
"""
from __future__ import annotations

import json
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SECRETS_PATH = ROOT / "pip_secrets.json"
RATE_LOG_PATH = ROOT / "imports" / "_message_rate_log.json"

# ── secrets loading ───────────────────────────────────────────────────────────

def _load_secrets() -> dict[str, Any]:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_enabled() -> bool:
    return bool(_load_secrets().get("messaging_enabled"))


# ── rate limiting ─────────────────────────────────────────────────────────────

def _load_rate_log() -> list[float]:
    if not RATE_LOG_PATH.exists():
        return []
    try:
        data = json.loads(RATE_LOG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_rate_log(timestamps: list[float]) -> None:
    RATE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep only timestamps from the last 24 hours
    cutoff = time.time() - 86400
    recent = [ts for ts in timestamps if ts > cutoff]
    RATE_LOG_PATH.write_text(json.dumps(recent), encoding="utf-8")


def _check_rate_limit(secrets: dict[str, Any]) -> tuple[bool, str]:
    max_per_hour = int(secrets.get("rate_limit_max_per_hour", 1))
    max_per_day = int(secrets.get("rate_limit_max_per_day", 5))
    now = time.time()
    log = _load_rate_log()

    hour_ago = now - 3600
    day_ago = now - 86400
    in_last_hour = sum(1 for ts in log if ts > hour_ago)
    in_last_day = sum(1 for ts in log if ts > day_ago)

    if in_last_hour >= max_per_hour:
        return False, f"Rate limit: {in_last_hour}/{max_per_hour} messages sent in last hour."
    if in_last_day >= max_per_day:
        return False, f"Rate limit: {in_last_day}/{max_per_day} messages sent in last 24 hours."
    return True, "ok"


def _record_send() -> None:
    log = _load_rate_log()
    log.append(time.time())
    _save_rate_log(log)


# ── trace logging ─────────────────────────────────────────────────────────────

def _log_trace(backend: str, subject: str, body: str, status: str, error: str = "") -> None:
    try:
        import pip_traces
        pip_traces.record_trace(
            kind="outbound_message",
            actor="pip",
            action=f"send_{backend}",
            status=status,
            summary=subject[:120],
            details={
                "backend": backend,
                "subject": subject,
                "body_preview": body[:200],
                "error": error,
            },
            source="pip_messenger",
            tags=["messenger", backend],
        )
    except Exception:
        pass


# ── Gmail SMTP backend ───────────────────────────────────────────────────────

def send_gmail(subject: str, body: str, html_body: str = "") -> dict[str, Any]:
    """Send an email via Gmail SMTP with App Password."""
    secrets = _load_secrets()
    if not secrets.get("messaging_enabled"):
        return {"ok": False, "error": "Messaging is disabled. Set messaging_enabled=true in pip_secrets.json."}

    user = secrets.get("gmail_smtp_user", "")
    app_password = secrets.get("gmail_smtp_app_password", "")
    recipient = secrets.get("gmail_recipient", "")

    if not user or not app_password:
        return {"ok": False, "error": "Gmail SMTP credentials not configured in pip_secrets.json."}
    if not recipient:
        return {"ok": False, "error": "No gmail_recipient configured in pip_secrets.json."}

    allowed, reason = _check_rate_limit(secrets)
    if not allowed:
        _log_trace("gmail", subject, body, "rate_limited", reason)
        return {"ok": False, "error": reason}

    prefixed_subject = f"[Pip] {subject}"

    msg = MIMEMultipart("alternative")
    msg["From"] = user
    msg["To"] = recipient
    msg["Subject"] = prefixed_subject

    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(user, app_password)
            server.send_message(msg)
        _record_send()
        _log_trace("gmail", prefixed_subject, body, "sent")
        return {"ok": True, "backend": "gmail", "recipient": recipient, "subject": prefixed_subject}
    except Exception as exc:
        _log_trace("gmail", prefixed_subject, body, "failed", str(exc))
        return {"ok": False, "backend": "gmail", "error": str(exc)}


# ── ntfy.sh backend ──────────────────────────────────────────────────────────

def send_ntfy(title: str, message: str, priority: str = "default") -> dict[str, Any]:
    """Send a push notification via ntfy.sh (or self-hosted ntfy server)."""
    secrets = _load_secrets()
    if not secrets.get("messaging_enabled"):
        return {"ok": False, "error": "Messaging is disabled. Set messaging_enabled=true in pip_secrets.json."}

    topic = secrets.get("ntfy_topic", "")
    server = secrets.get("ntfy_server", "https://ntfy.sh")

    if not topic:
        return {"ok": False, "error": "No ntfy_topic configured in pip_secrets.json."}

    allowed, reason = _check_rate_limit(secrets)
    if not allowed:
        _log_trace("ntfy", title, message, "rate_limited", reason)
        return {"ok": False, "error": reason}

    url = f"{server.rstrip('/')}/{topic}"
    headers = {
        "Title": f"[Pip] {title}",
        "Priority": priority,
        "Tags": "fairy",
    }

    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        _record_send()
        _log_trace("ntfy", title, message, "sent")
        return {"ok": True, "backend": "ntfy", "topic": topic, "title": title}
    except Exception as exc:
        _log_trace("ntfy", title, message, "failed", str(exc))
        return {"ok": False, "backend": "ntfy", "error": str(exc)}


# ── rhetoric monitor ──────────────────────────────────────────────────────────

def _check_rhetoric(title: str, body: str, proposal_id: str = None) -> None:
    # Exempt system traffic
    title_lower = title.lower()
    if title_lower in ["health alert", "weekly digest"] or "claude reply" in title_lower or "test message" in title_lower:
        return

    history_path = ROOT / "imports" / "_msg_history.json"
    try:
        if history_path.exists():
            history_dict = json.loads(history_path.read_text(encoding="utf-8"))
        else:
            history_dict = {}
    except Exception:
        history_dict = {}
        
    # Key by proposal ID if available, else a single default advocacy bucket
    key = str(proposal_id) if proposal_id else "default_advocacy"
    history = history_dict.get(key, [])
        
    history.append(body)
    # keep last 5
    if len(history) > 5:
        history = history[-5:]
    
    history_dict[key] = history
    history_path.write_text(json.dumps(history_dict), encoding="utf-8")
    
    if len(history) >= 2:
        try:
            import pip_rhetoric_monitor
            res = pip_rhetoric_monitor.rhetorical_escalation_score(history)
            if res.get("escalating"):
                print("[messenger] Rhetorical escalation detected! Applying metabolic penalty.")
                try:
                    import pip_bos
                    pip_bos.apply_penalty(0.3)  # Apply penalty to BOS
                except Exception as e:
                    print(f"Failed to apply penalty: {e}")
                # Log to graph memory
                try:
                    import pip_graph_memory
                    pip_graph_memory.add_edge("rhetorical_escalation_event", body, "rhetorical_warning", {"score": res, "proposal_id": key})
                except Exception:
                    pass
        except Exception:
            pass

# ── unified send ──────────────────────────────────────────────────────────────

def notify(title: str, body: str, html_body: str = "", priority: str = "default", proposal_id: str = None) -> dict[str, Any]:
    """Try all configured backends. Returns the first success or last failure."""
    _check_rhetoric(title, body, proposal_id=proposal_id)
    
    secrets = _load_secrets()
    if not secrets.get("messaging_enabled"):
        return {"ok": False, "error": "Messaging is disabled."}

    results = []

    # Try ntfy first (instant push)
    if secrets.get("ntfy_topic"):
        result = send_ntfy(title, body, priority=priority)
        results.append(result)
        if result.get("ok"):
            # Also try gmail for the email record, but don't fail if it doesn't work
            if secrets.get("gmail_smtp_app_password"):
                gmail_result = send_gmail(title, body, html_body=html_body)
                results.append(gmail_result)
            return {"ok": True, "results": results}

    # Try gmail
    if secrets.get("gmail_smtp_app_password"):
        result = send_gmail(title, body, html_body=html_body)
        results.append(result)
        if result.get("ok"):
            return {"ok": True, "results": results}

    if not results:
        return {"ok": False, "error": "No messaging backends configured. Add gmail or ntfy settings to pip_secrets.json."}

    return {"ok": False, "results": results, "error": results[-1].get("error", "All backends failed.")}


# ── convenience methods for Pip's common message types ────────────────────────

def notify_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """Notify the owner that Pip has a new proposal."""
    card = proposal.get("proposal_card") or proposal
    title = "New Proposal"
    proposal_id = card.get("id") or proposal.get("id")
    text = card.get("proposal", "Pip has a new thought.")
    evidence = card.get("evidence", "")
    body = f"{text}\n\nEvidence: {evidence}" if evidence else text
    html_body = f"""
    <div style="font-family: Georgia, serif; max-width: 480px; margin: 0 auto; padding: 20px;">
      <h2 style="color: #8b5cf6; margin-bottom: 12px;">🧚 Pip has a thought</h2>
      <div style="background: #f0fdf4; border-left: 4px solid #10b981; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
        <p style="margin: 0; font-size: 15px; line-height: 1.5;">{text}</p>
      </div>
      <p style="color: #64748b; font-size: 13px;">{evidence}</p>
      <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
      <p style="color: #94a3b8; font-size: 11px;">Open Pip's dashboard to approve, reject, or defer.</p>
    </div>
    """
    return notify(title, body, html_body=html_body, proposal_id=proposal_id)


def notify_health_alert(alert: str, details: str = "") -> dict[str, Any]:
    """Notify the owner of a system health issue."""
    body = f"{alert}\n\n{details}" if details else alert
    return notify("Health Alert", body, priority="high")


def notify_weekly_digest(summary: str) -> dict[str, Any]:
    """Send the weekly digest summary."""
    return notify("Weekly Digest", summary)


# ── status / inspection ───────────────────────────────────────────────────────

def inspect_messenger() -> dict[str, Any]:
    secrets = _load_secrets()
    log = _load_rate_log()
    now = time.time()
    return {
        "enabled": bool(secrets.get("messaging_enabled")),
        "gmail_configured": bool(secrets.get("gmail_smtp_app_password")),
        "gmail_user": secrets.get("gmail_smtp_user", ""),
        "gmail_recipient": secrets.get("gmail_recipient", ""),
        "ntfy_configured": bool(secrets.get("ntfy_topic")),
        "ntfy_topic": secrets.get("ntfy_topic", ""),
        "ntfy_server": secrets.get("ntfy_server", "https://ntfy.sh"),
        "messages_last_hour": sum(1 for ts in log if ts > now - 3600),
        "messages_last_24h": sum(1 for ts in log if ts > now - 86400),
        "rate_limit_per_hour": int(secrets.get("rate_limit_max_per_hour", 1)),
        "rate_limit_per_day": int(secrets.get("rate_limit_max_per_day", 5)),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pip Messenger")
    parser.add_argument("--test", action="store_true", help="Send a test message via all configured backends.")
    parser.add_argument("--status", action="store_true", help="Show messaging configuration status.")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(inspect_messenger(), indent=2))
    elif args.test:
        result = notify(
            "Test Message",
            "This is a test from Pip. If you received this, messaging is working!",
        )
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()

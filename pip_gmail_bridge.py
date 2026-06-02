#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config


BRIDGE_VERSION = 1
READ_ONLY_CONNECTOR_CONTRACT = {
    "mode": "gmail_read_only_awareness",
    "current_status": "not_connected",
    "allowed_future_scopes": [
        "gmail.metadata",
        "gmail.readonly",
    ],
    "disallowed_without_new_approval": [
        "gmail.modify",
        "gmail.compose",
        "gmail.send",
        "contacts access",
        "calendar write access",
    ],
    "allowed_actions": [
        "read bounded inbox snapshots",
        "summarize message metadata and snippets",
        "draft replies under Pip memory",
        "suggest labels, priorities, follow-ups, and archive candidates",
    ],
    "blocked_actions": [
        "send email",
        "delete email",
        "archive email",
        "apply labels",
        "mark read or unread",
        "create Gmail drafts directly",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def gmail_dir() -> Path:
    path = pip_config.get_memory_path() / "gmail_drafts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_import_path() -> Path:
    return gmail_dir() / "latest_inbox_summary.json"


def latest_draft_path() -> Path:
    return gmail_dir() / "latest_organization_draft.json"


def status_path() -> Path:
    return gmail_dir() / "gmail_bridge_status.json"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"error": f"Could not parse {path.name}"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "unread"}


def _message_from_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    sender = _clean(row.get("from") or row.get("sender") or row.get("email_from"))
    subject = _clean(row.get("subject") or row.get("title"))
    snippet = _clean(row.get("snippet") or row.get("body") or row.get("preview") or row.get("summary"))
    received_at = _clean(row.get("received_at") or row.get("date") or row.get("timestamp"))
    labels = row.get("labels") or []
    if isinstance(labels, str):
        labels = [part.strip() for part in labels.replace(";", ",").split(",") if part.strip()]
    if not isinstance(labels, list):
        labels = []
    return {
        "id": _clean(row.get("id") or f"manual_{index + 1:03d}"),
        "from": sender or "unknown sender",
        "subject": subject or "(no subject)",
        "snippet": snippet,
        "received_at": received_at,
        "unread": _to_bool(row.get("unread")),
        "has_attachment": _to_bool(row.get("has_attachment") or row.get("attachment")),
        "current_labels": labels,
    }


def parse_gmail_summary_text(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("gmail summary is empty")

    if raw.startswith("[") or raw.startswith("{"):
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("messages") or data.get("emails") or data.get("items") or []
        if not isinstance(data, list):
            raise ValueError("gmail summary JSON must be a list or an object with messages/emails/items")
        messages = [_message_from_row(item if isinstance(item, dict) else {}, idx) for idx, item in enumerate(data)]
    else:
        reader = csv.DictReader(io.StringIO(raw))
        if not reader.fieldnames:
            raise ValueError("gmail summary CSV needs a header row")
        messages = [_message_from_row(row, idx) for idx, row in enumerate(reader)]

    messages = [message for message in messages if message.get("from") or message.get("subject") or message.get("snippet")]
    if not messages:
        raise ValueError("gmail summary had no email rows")
    return messages


def _text_blob(message: dict[str, Any]) -> str:
    return " ".join([
        _clean(message.get("from")),
        _clean(message.get("subject")),
        _clean(message.get("snippet")),
    ]).lower()


def _suggest_labels(message: dict[str, Any]) -> list[str]:
    text = _text_blob(message)
    labels: list[str] = []
    label_rules = [
        ("Action", ["urgent", "asap", "please", "can you", "could you", "need", "deadline", "due"]),
        ("Waiting", ["waiting", "follow up", "following up", "checking in", "reminder"]),
        ("Finance", ["invoice", "receipt", "payment", "bill", "bank", "tax", "subscription"]),
        ("Calendar", ["meeting", "appointment", "schedule", "reservation", "invite", "calendar"]),
        ("Travel", ["flight", "hotel", "booking", "trip", "itinerary"]),
        ("Shopping", ["order", "shipment", "delivered", "tracking", "return"]),
        ("Account", ["password", "security", "login", "verification", "2fa", "account"]),
        ("Newsletter", ["unsubscribe", "newsletter", "digest", "weekly update"]),
    ]
    for label, keywords in label_rules:
        if any(keyword in text for keyword in keywords):
            labels.append(label)
    if message.get("has_attachment"):
        labels.append("Attachment")
    if not labels:
        labels.append("Review")
    return sorted(set(labels))


def _priority(message: dict[str, Any], labels: list[str]) -> str:
    text = _text_blob(message)
    if any(word in text for word in ["urgent", "asap", "deadline", "past due", "final notice"]):
        return "high"
    if "Action" in labels or "Finance" in labels or "Account" in labels:
        return "medium"
    if message.get("unread") and "Review" not in labels:
        return "medium"
    return "low"


def _draft_reply(message: dict[str, Any], labels: list[str]) -> str:
    text = _text_blob(message)
    if "Action" in labels or "?" in _clean(message.get("snippet")) or "please" in text:
        return "Draft reply: Thanks for sending this. I am reviewing it and will follow up with a clear answer shortly."
    if "Finance" in labels:
        return "Draft note: Verify amount/date/source before paying, filing, or archiving."
    if "Calendar" in labels:
        return "Draft note: Check calendar availability before accepting or proposing a time."
    return ""


def draft_gmail_actions(messages: list[dict[str, Any]], source_name: str = "manual_gmail_summary") -> dict[str, Any]:
    proposals: list[dict[str, Any]] = []
    label_counts: dict[str, int] = {}
    for message in messages:
        labels = _suggest_labels(message)
        priority = _priority(message, labels)
        for label in labels:
            label_counts[label] = label_counts.get(label, 0) + 1
        proposals.append({
            "message_id": message["id"],
            "from": message["from"],
            "subject": message["subject"],
            "priority": priority,
            "suggested_labels": labels,
            "suggested_action": _suggested_action(priority, labels),
            "draft_reply_or_note": _draft_reply(message, labels),
            "safety": "draft_only_no_gmail_access",
        })

    proposals.sort(key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item["priority"], 9))
    high_count = sum(1 for item in proposals if item["priority"] == "high")
    medium_count = sum(1 for item in proposals if item["priority"] == "medium")
    return {
        "version": BRIDGE_VERSION,
        "generated_at": utc_now(),
        "mode": "gmail_draft_only",
        "source_name": source_name,
        "email_count": len(messages),
        "summary": {
            "high_priority": high_count,
            "medium_priority": medium_count,
            "low_priority": len(messages) - high_count - medium_count,
            "label_counts": dict(sorted(label_counts.items())),
        },
        "proposal_card": {
            "proposal": f"Draft Gmail organization pass for {len(messages)} email summaries.",
            "evidence": f"{high_count} high-priority and {medium_count} medium-priority items found. No Gmail actions were taken.",
            "status": "proposed",
            "source_kind": "manual_summary",
            "score": round(min(1.0, 0.25 + (high_count * 0.15) + (medium_count * 0.07)), 3),
        },
        "proposals": proposals,
        "safety_contract": [
            "No Gmail OAuth is configured.",
            "No Gmail API calls are made.",
            "No emails are sent, archived, deleted, labeled, or marked read.",
            "Drafts are written only under Pip memory.",
        ],
    }


def _suggested_action(priority: str, labels: list[str]) -> str:
    if priority == "high":
        return "Review first and decide whether to reply, schedule, pay, or secure the account."
    if "Newsletter" in labels and len(labels) == 1:
        return "Consider archive or unsubscribe review if this is no longer useful."
    if "Shopping" in labels:
        return "File under shopping/order tracking after confirming no action is needed."
    if "Calendar" in labels:
        return "Check calendar and draft a response before committing."
    if priority == "medium":
        return "Batch into today's organization pass."
    return "Low-priority review or archive candidate."


def import_gmail_summary_text(text: str, source_name: str = "manual_gmail_summary.csv") -> dict[str, Any]:
    messages = parse_gmail_summary_text(text)
    draft = draft_gmail_actions(messages, source_name=source_name)
    imported = {
        "generated_at": utc_now(),
        "source_name": source_name,
        "messages": messages,
    }
    archive = gmail_dir() / f"gmail_summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json(latest_import_path(), imported)
    write_json(archive, imported)
    write_json(latest_draft_path(), draft)
    status = {
        "generated_at": utc_now(),
        "mode": "gmail_draft_only",
        "imported": True,
        "source_name": source_name,
        "latest_import": str(latest_import_path()),
        "latest_draft": str(latest_draft_path()),
        "archive_path": str(archive),
        "proposal": draft,
    }
    write_json(status_path(), status)
    return status


def import_gmail_summary_file(input_path: str | Path) -> dict[str, Any]:
    source = Path(input_path)
    return import_gmail_summary_text(source.read_text(encoding="utf-8"), source.name)


def get_gmail_status() -> dict[str, Any]:
    status = read_json_if_exists(status_path())
    if isinstance(status, dict):
        status.setdefault("connector_contract", READ_ONLY_CONNECTOR_CONTRACT)
        return status
    return {
        "generated_at": utc_now(),
        "mode": "gmail_draft_only",
        "imported": False,
        "latest_import": str(latest_import_path()) if latest_import_path().exists() else None,
        "latest_draft": str(latest_draft_path()) if latest_draft_path().exists() else None,
        "proposal": read_json_if_exists(latest_draft_path()),
        "connector_contract": READ_ONLY_CONNECTOR_CONTRACT,
    }


def inspect_connector_contract() -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "draft_bridge": {
            "mode": "gmail_draft_only",
            "status": "available",
            "summary_path": str(latest_import_path()),
            "draft_path": str(latest_draft_path()),
        },
        "read_only_connector": READ_ONLY_CONNECTOR_CONTRACT,
        "roadmap": "GMAIL_CONNECTOR_ROADMAP.md",
    }


def apply_gmail_feedback(feedback: str, note: str = "") -> dict[str, Any]:
    if feedback not in {"accepted", "rejected", "deferred", "resolved"}:
        raise ValueError("feedback must be accepted, rejected, deferred, or resolved")
    status = get_gmail_status()
    proposal = status.get("proposal") or {}
    if isinstance(proposal, dict):
        proposal.setdefault("proposal_card", {})
        proposal["proposal_card"]["status"] = feedback
        proposal["proposal_card"]["last_feedback_note"] = note
        proposal["last_feedback"] = {
            "feedback": feedback,
            "note": note,
            "recorded_at": utc_now(),
        }
        write_json(latest_draft_path(), proposal)
    status["proposal"] = proposal
    status["last_feedback"] = {"feedback": feedback, "note": note, "recorded_at": utc_now()}
    write_json(status_path(), status)
    return status

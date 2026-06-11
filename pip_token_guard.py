#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config
import pip_platform
import pip_prompt_guard


ROOT = Path(__file__).resolve().parent
BRAIN_ROOT = pip_platform.BRAIN_ROOT
SIGNAL_SIEVE_DIR = BRAIN_ROOT / "signal" / "signal-sieve"
TOKEN_GOVERNOR_SOURCE = BRAIN_ROOT / "token governor" / "token_governor_system_v0_5_0.tar.gz"

ACTION_MAPPING = {
    "verify_primary": {"priority": "CRITICAL", "max_output_tokens": 700, "energy": "full"},
    "treat_as_lead": {"priority": "NORMAL", "max_output_tokens": 500, "energy": "normal"},
    "seek_receipts": {"priority": "NORMAL", "max_output_tokens": 350, "energy": "careful"},
    "treat_as_background": {"priority": "BACKGROUND", "max_output_tokens": 220, "energy": "brief"},
    "drop": {"priority": "SPECULATIVE", "max_output_tokens": 80, "energy": "tiny"},
    "reject": {"priority": "BLOCKED", "max_output_tokens": 0, "energy": "stop"},
}

INTENT_MULTIPLIERS = {
    "chat": 1.0,
    "autonomous_goal": 3.0,
    "ambient_cycle": 2.0,
    "job": 2.5,
    "blender_recipe": 0.8,
    "skill": 1.2,
    "sieve": 0.7,
    "reword": 0.6,
}

# Builtin (in-repo) sieve patterns. Word-boundary matched so ordinary words
# like "knowledge" (contains "now") or "secretary" (contains "secret") do not
# trip a pressure hit. Used when the richer external Signal Sieve is absent.
_FALLBACK_PATTERNS = {
    "pressure": [
        r"\burgent\b", r"\bmust\b", r"\bnow\b", r"\bimmediately\b",
        r"\basap\b", r"\bhurry\b", r"\bright away\b", r"\bno time\b",
    ],
    "certainty": [
        r"\balways\b", r"\bnever\b", r"\beveryone\b", r"\bnobody\b",
        r"\bguaranteed\b", r"\bdefinitely\b", r"\bobviously\b",
    ],
    "manipulation": [
        r"\bsecret\b", r"\bexclusive\b", r"\bbreakthrough\b", r"\bmiracle\b",
        r"\bhidden\b", r"\bonly today\b", r"\blast chance\b", r"\bdon'?t tell\b",
    ],
}
_FALLBACK_COMPILED = {
    cat: [re.compile(p, re.IGNORECASE) for p in pats]
    for cat, pats in _FALLBACK_PATTERNS.items()
}

DEFAULT_STATE = {
    "version": 1,
    "day": "",
    "daily_budget_tokens": 60000,
    "daily_used_tokens": 0,
    "daily_saved_tokens": 0,
    "session_used_tokens": 0,
    "session_saved_tokens": 0,
    "events": [],
    "last_assessment": None,
    "user_nudges": [],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_key() -> str:
    # Local calendar day, so the daily budget resets at the user's midnight
    # rather than UTC midnight.
    return datetime.now().strftime("%Y-%m-%d")


def state_path() -> Path:
    return pip_config.get_memory_path() / "token_governor_state.json"


def estimate_tokens(text: str, max_output_tokens: int = 250) -> int:
    return max(1, len(text or "") // 4) + max(0, int(max_output_tokens))


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)
    merged = dict(default)
    merged.update(data if isinstance(data, dict) else {})
    return merged


def load_state() -> dict[str, Any]:
    state = _read_json(state_path(), DEFAULT_STATE)
    reset_today = False
    if state.get("day") != today_key():
        state["day"] = today_key()
        state["daily_used_tokens"] = 0
        state["daily_saved_tokens"] = 0
        state["events"] = []
        state["user_nudges"] = []
        reset_today = True
    state.setdefault("events", [])
    state.setdefault("user_nudges", [])
    if reset_today:
        save_state(state)
    return state


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file + os.replace so a concurrent reader/writer never
    sees a half-written JSON state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    state["events"] = state.get("events", [])[-200:]
    state["user_nudges"] = state.get("user_nudges", [])[-50:]
    _atomic_write(path, json.dumps(state, indent=2))


def _count_hits(text: str, category: str) -> int:
    return sum(1 for pat in _FALLBACK_COMPILED[category] if pat.search(text))


def _fallback_sieve(text: str) -> dict[str, Any]:
    """Deterministic, in-repo sieve. Used when the richer external Signal Sieve
    module is not present (e.g. a fresh public clone). Word-boundary matched to
    avoid substring false positives, and it populates the same score keys
    (manipulation_risk / certainty_bias / noise) the Flow Master reads."""
    text = text or ""
    pressure_hits = _count_hits(text, "pressure")
    certainty_hits = _count_hits(text, "certainty")
    manipulation_hits = _count_hits(text, "manipulation")

    pressure = min(1.0, pressure_hits / 3)
    certainty_bias = min(1.0, certainty_hits / 3)
    manipulation_risk = min(1.0, manipulation_hits / 3)
    noise = min(1.0, (pressure_hits + certainty_hits + manipulation_hits) / 6)

    if pressure >= 0.66 or manipulation_risk >= 0.66:
        action = "seek_receipts"
    elif pressure >= 0.33 or manipulation_risk >= 0.33 or certainty_bias >= 0.66:
        action = "treat_as_lead"
    else:
        action = "treat_as_lead"

    return {
        "recommended_action": action,
        "triage_summary": "Built-in Pip sieve heuristic (external Signal Sieve module not present).",
        "scores": {
            "pressure": round(pressure, 3),
            "manipulation_risk": round(manipulation_risk, 3),
            "certainty_bias": round(certainty_bias, 3),
            "noise": round(noise, 3),
            "signal": round(1.0 - noise, 3),
            "overall_confidence": 0.4,
        },
        "flags": [],
        "questions_to_ask": [],
        "capsule": "Built-in sieve: external signal-sieve module unavailable; using bundled heuristic.",
        "builtin": True,
    }


def analyze_signal(text: str, source_type: str = "first_hand", source_name: str = "Pip user interaction") -> dict[str, Any]:
    if not SIGNAL_SIEVE_DIR.exists():
        return _fallback_sieve(text)
    # Append (not front-insert) so the external sieve dir cannot shadow stdlib
    # or in-repo modules; the sieve's own relative imports still resolve.
    if str(SIGNAL_SIEVE_DIR) not in sys.path:
        sys.path.append(str(SIGNAL_SIEVE_DIR))
    try:
        from signal_sieve import analyze

        return analyze(text or "", source_type=source_type, source_name=source_name)
    except Exception as exc:
        result = _fallback_sieve(text)
        result["error"] = str(exc)
        return result


def _mode_for_pressure(pressure: float, remaining_ratio: float) -> str:
    if remaining_ratio <= 0.05 or pressure >= 0.85:
        return "SHED"
    if remaining_ratio <= 0.18 or pressure >= 0.65:
        return "DWELL"
    if remaining_ratio <= 0.42 or pressure >= 0.35:
        return "AUDIT"
    return "BUILD"


def _nudge_for(mode: str, action: str, intent: str, estimated: int) -> str:
    if mode == "SHED":
        return "Pip is in SHED mode. Only critical work should continue; compress, pause, or save a draft."
    if mode == "DWELL":
        return "Pip is in DWELL mode. Keep this brief, prefer summaries, and avoid new autonomous branches."
    if action in {"drop", "reject"}:
        return "Signal Sieve found low signal or high pressure. Pip should answer lightly and ask for receipts before expanding."
    if estimated > 4000:
        return "This is a large request. Pip should condense context before spending more tokens."
    if intent == "autonomous_goal":
        return "Autonomous work is higher-cost. Queue approval and keep the first job narrow."
    return "Budget looks healthy. Proceed normally, but keep outputs purposeful."


def _prompt_guard_nudge(prompt_guard: dict[str, Any]) -> str:
    verdict = prompt_guard.get("verdict", "allow")
    if verdict in {"block", "review"}:
        return pip_prompt_guard.nudge_for(verdict)
    return ""


def assess_interaction(
    text: str,
    intent: str = "chat",
    source_type: str = "first_hand",
    source_name: str = "Pip user interaction",
    signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_state()
    prompt_guard = pip_prompt_guard.check_prompt_guard(text)
    # Reuse a precomputed sieve result when the caller already ran it (the chat
    # gate does), so we don't analyze the same text twice.
    sieve = signal if signal is not None else analyze_signal(text, source_type=source_type, source_name=source_name)
    action = sieve.get("recommended_action", "treat_as_lead")
    mapping = ACTION_MAPPING.get(action, ACTION_MAPPING["treat_as_background"])
    if prompt_guard["verdict"] == "block":
        action = "reject"
        mapping = ACTION_MAPPING["reject"]
    elif prompt_guard["verdict"] == "review" and mapping["priority"] in {"BACKGROUND", "SPECULATIVE"}:
        action = "seek_receipts"
        mapping = ACTION_MAPPING["seek_receipts"]
    multiplier = INTENT_MULTIPLIERS.get(intent, 1.0)
    estimated = int(estimate_tokens(text, mapping["max_output_tokens"]) * multiplier)
    daily_budget = max(1, int(state.get("daily_budget_tokens", DEFAULT_STATE["daily_budget_tokens"])))
    projected_used = int(state.get("daily_used_tokens", 0)) + estimated
    remaining_ratio = max(0.0, 1.0 - (projected_used / daily_budget))
    pressure_score = float((sieve.get("scores") or {}).get("pressure", 0.0))
    budget_pressure = 1.0 - remaining_ratio
    combined_pressure = min(1.0, 0.55 * budget_pressure + 0.45 * pressure_score)
    mode = _mode_for_pressure(combined_pressure, remaining_ratio)

    allowed = True
    reason = "admitted"
    if prompt_guard["verdict"] == "block":
        allowed = False
        reason = "prompt_guard_block"
    elif action == "reject":
        allowed = False
        reason = "signal_sieve_reject"
    elif mode == "SHED" and mapping["priority"] not in {"CRITICAL"}:
        allowed = False
        reason = "budget_shed"
    elif mode == "DWELL" and mapping["priority"] in {"BACKGROUND", "SPECULATIVE"}:
        allowed = False
        reason = "low_priority_under_pressure"

    assessment = {
        "generated_at": utc_now(),
        "allowed": allowed,
        "reason": reason,
        "mode": mode,
        "intent": intent,
        "priority": mapping["priority"],
        "energy": mapping["energy"],
        "recommended_action": action,
        "max_output_tokens": mapping["max_output_tokens"],
        "estimated_tokens": estimated,
        "daily_budget_tokens": daily_budget,
        "daily_used_tokens": state.get("daily_used_tokens", 0),
        "remaining_ratio_after": round(remaining_ratio, 3),
        "pressure": round(combined_pressure, 3),
        "nudge": _prompt_guard_nudge(prompt_guard) or _nudge_for(mode, action, intent, estimated),
        "prompt_guard": prompt_guard,
        "signal": {
            "triage_summary": sieve.get("triage_summary", ""),
            "scores": sieve.get("scores", {}),
            "flags": sieve.get("flags", [])[:5],
            "questions_to_ask": sieve.get("questions_to_ask", [])[:5],
            "capsule": sieve.get("capsule", ""),
        },
        "source": {
            "token_governor_package": str(TOKEN_GOVERNOR_SOURCE),
            "signal_sieve_dir": str(SIGNAL_SIEVE_DIR),
        },
    }
    state["last_assessment"] = assessment
    if not allowed or mode in {"DWELL", "SHED"}:
        state.setdefault("user_nudges", []).append({"at": utc_now(), "intent": intent, "nudge": assessment["nudge"]})
    save_state(state)
    return assessment


def record_event(
    intent: str,
    estimated_tokens: int = 0,
    actual_tokens: int | None = None,
    saved_tokens: int = 0,
    note: str = "",
) -> dict[str, Any]:
    state = load_state()
    spent = max(0, int(actual_tokens if actual_tokens is not None else estimated_tokens))
    saved = max(0, int(saved_tokens))
    state["daily_used_tokens"] = max(0, int(state.get("daily_used_tokens", 0)) + spent)
    state["session_used_tokens"] = max(0, int(state.get("session_used_tokens", 0)) + spent)
    state["daily_saved_tokens"] = max(0, int(state.get("daily_saved_tokens", 0)) + saved)
    state["session_saved_tokens"] = max(0, int(state.get("session_saved_tokens", 0)) + saved)
    state.setdefault("events", []).append(
        {
            "at": utc_now(),
            "intent": intent,
            "estimated_tokens": int(estimated_tokens),
            "actual_tokens": spent,
            "saved_tokens": saved,
            "note": note,
        }
    )
    save_state(state)
    return status()


def status() -> dict[str, Any]:
    state = load_state()
    daily_budget = max(1, int(state.get("daily_budget_tokens", DEFAULT_STATE["daily_budget_tokens"])))
    used = int(state.get("daily_used_tokens", 0))
    remaining = max(0, daily_budget - used)
    remaining_ratio = remaining / daily_budget
    pressure = 1.0 - remaining_ratio
    mode = _mode_for_pressure(pressure, remaining_ratio)
    return {
        "generated_at": utc_now(),
        "mode": mode,
        "daily_budget_tokens": daily_budget,
        "daily_used_tokens": used,
        "daily_remaining_tokens": remaining,
        "daily_saved_tokens": state.get("daily_saved_tokens", 0),
        "session_used_tokens": state.get("session_used_tokens", 0),
        "session_saved_tokens": state.get("session_saved_tokens", 0),
        "remaining_ratio": round(remaining_ratio, 3),
        "pressure": round(pressure, 3),
        "last_assessment": state.get("last_assessment"),
        "recent_events": state.get("events", [])[-10:],
        "recent_nudges": state.get("user_nudges", [])[-5:],
        "signal_sieve_available": SIGNAL_SIEVE_DIR.exists(),
        "token_governor_package_present": TOKEN_GOVERNOR_SOURCE.exists(),
    }

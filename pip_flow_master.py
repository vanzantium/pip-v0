#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pip_config
import pip_platform
import pip_token_guard


ROOT = Path(__file__).resolve().parent
FLOW_MASTER_DIR = pip_platform.BRAIN_ROOT / "flow master"

FLOW_STATES = {
    "BUILD": {
        "label": "Build",
        "meaning": "Expansion is safe. Keep momentum, but keep receipts.",
        "response": "Proceed normally with purposeful output.",
    },
    "STAND": {
        "label": "Stand",
        "meaning": "Equilibrium. Stay grounded and do not over-expand.",
        "response": "Answer clearly, keep scope visible, and avoid rabbit holes.",
    },
    "AUDIT": {
        "label": "Audit",
        "meaning": "Pressure is present. Slow down and inspect the shape of the input.",
        "response": "Compress, ask for receipts, and separate claims from charge.",
    },
    "DWELL": {
        "label": "Dwell",
        "meaning": "High pressure. Pause expansion and restore agency before acting.",
        "response": "Offer a short grounding summary and defer low-value work.",
    },
    "SHED": {
        "label": "Shed",
        "meaning": "Hard contraction. Protect attention and cut non-critical branches.",
        "response": "Block or defer non-critical work, preserve only the safest next step.",
    },
}

DEFAULT_DOCTRINE = {
    "version": 1,
    "name": "Flow Master",
    "source_folder": str(FLOW_MASTER_DIR),
    "contract": "ingest -> validate -> transform -> emit",
    "purpose": "A safe local doctrine layer for attention protection, pressure recognition, and metacognitive pacing.",
    "principles": [
        "Restore agency; do not replace it.",
        "Use receipts before reaction.",
        "Compress pressure into a finite digest.",
        "Prefer user override and review over coercive blocking.",
        "Treat psyop-like language as pressure-risk, not as automatic truth judgment.",
    ],
    "states": FLOW_STATES,
    "safety_boundaries": [
        "No keyboard, mouse, microphone, biometric, browser, or app blocking features in this v0 layer.",
        "No claims that Flow Master proves whether a narrative is true or false.",
        "No unskippable DWELL or system input blocking.",
        "High-risk body features must go through Pip's permission queue later.",
    ],
}

PRESSURE_PATTERNS = {
    "urgency": [
        r"\bnow\b",
        r"\bimmediately\b",
        r"\bbefore it'?s too late\b",
        r"\blast chance\b",
        r"\bno time\b",
    ],
    "absolutes": [
        r"\balways\b",
        r"\bnever\b",
        r"\beveryone\b",
        r"\bnobody\b",
        r"\bmust\b",
        r"\bguaranteed\b",
    ],
    "tribal_pressure": [
        r"\btraitor\b",
        r"\benemy\b",
        r"\bthey want you to\b",
        r"\bus vs them\b",
        r"\bif you disagree\b",
    ],
    "scarcity_fomo": [
        r"\bsecret\b",
        r"\bhidden\b",
        r"\bexclusive\b",
        r"\bmissing out\b",
        r"\bonly today\b",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def doctrine_path() -> Path:
    return pip_config.get_memory_path() / "flow_master_doctrine.json"


def state_path() -> Path:
    return pip_config.get_memory_path() / "flow_master_state.json"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def source_files() -> list[dict[str, Any]]:
    if not FLOW_MASTER_DIR.exists():
        return []
    files = []
    for path in sorted(FLOW_MASTER_DIR.glob("*.txt")):
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
            }
        )
    return files


def load_doctrine() -> dict[str, Any]:
    path = doctrine_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = dict(DEFAULT_DOCTRINE)
                merged.update(data)
                return merged
        except Exception:
            pass
    return dict(DEFAULT_DOCTRINE)


def save_doctrine() -> dict[str, Any]:
    doctrine = dict(DEFAULT_DOCTRINE)
    doctrine["source_files"] = source_files()
    doctrine["generated_at"] = utc_now()
    path = doctrine_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doctrine, indent=2), encoding="utf-8")
    return doctrine


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return {"version": 1, "latest_assessment": None, "receipts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("receipts", [])
            data.setdefault("latest_assessment", None)
            return data
    except Exception:
        pass
    return {"version": 1, "latest_assessment": None, "receipts": []}


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["receipts"] = state.get("receipts", [])[-50:]
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _pattern_hits(text: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for category, patterns in PRESSURE_PATTERNS.items():
        category_hits = []
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                category_hits.append(pattern.replace(r"\b", "").replace("\\", ""))
        if category_hits:
            hits[category] = category_hits
    return hits


def _state_for(composite_pressure: float, token_mode: str) -> str:
    token_mode = (token_mode or "BUILD").upper()
    if token_mode == "SHED" or composite_pressure >= 0.85:
        return "SHED"
    if token_mode == "DWELL" or composite_pressure >= 0.65:
        return "DWELL"
    if token_mode == "AUDIT" or composite_pressure >= 0.35:
        return "AUDIT"
    if composite_pressure < 0.18:
        return "BUILD"
    return "STAND"


def _digest_for(flow_state: str, signal: dict[str, Any], pattern_hits: dict[str, list[str]]) -> dict[str, Any]:
    flags = signal.get("flags", [])[:4]
    pressure_clues = signal.get("pressure_clues", [])[:4]
    questions = signal.get("questions_to_ask", [])[:3]
    if flow_state in {"DWELL", "SHED"}:
        action = "Pause expansion and convert the input into receipts before acting."
    elif flow_state == "AUDIT":
        action = "Keep the response compact and inspect claims, pressure, and missing evidence."
    else:
        action = "Proceed, but keep the work bounded and evidence-aware."
    return {
        "action": action,
        "flags": flags,
        "pressure_clues": pressure_clues,
        "pattern_hits": pattern_hits,
        "questions_to_ask": questions,
    }


def assess_flow_pressure(
    content: str,
    intent: str = "chat",
    source_type: str = "first_hand",
    source_name: str = "Pip Flow Master",
    record: bool = True,
) -> dict[str, Any]:
    text = content or ""
    signal = pip_token_guard.analyze_signal(text, source_type=source_type, source_name=source_name)
    token_status = pip_token_guard.status()
    scores = signal.get("scores") or {}
    signal_pressure = float(scores.get("pressure", 0.0) or 0.0)
    manipulation = float(scores.get("manipulation_risk", 0.0) or 0.0)
    certainty_bias = float(scores.get("certainty_bias", 0.0) or 0.0)
    noise = float(scores.get("noise", 0.0) or 0.0)
    pattern_hits = _pattern_hits(text)
    pattern_pressure = _clamp(sum(len(items) for items in pattern_hits.values()) / 8)
    token_pressure = float(token_status.get("pressure", 0.0) or 0.0)
    neuro_burn_index = _clamp(
        signal_pressure * 0.42
        + manipulation * 0.22
        + certainty_bias * 0.12
        + noise * 0.10
        + pattern_pressure * 0.14
    )
    composite_threat_score = _clamp(neuro_burn_index * 0.70 + token_pressure * 0.30)
    flow_state = _state_for(composite_threat_score, token_status.get("mode", "BUILD"))
    doctrine = load_doctrine()
    state_spec = doctrine.get("states", FLOW_STATES).get(flow_state, FLOW_STATES["STAND"])
    assessment = {
        "generated_at": utc_now(),
        "intent": intent,
        "contract": doctrine.get("contract", DEFAULT_DOCTRINE["contract"]),
        "flow_state": flow_state,
        "state_label": state_spec.get("label", flow_state.title()),
        "meaning": state_spec.get("meaning", ""),
        "recommended_response": state_spec.get("response", ""),
        "neuro_burn_index": round(neuro_burn_index, 3),
        "composite_threat_score": round(composite_threat_score, 3),
        "token_mode": token_status.get("mode", "BUILD"),
        "token_pressure": token_status.get("pressure", 0.0),
        "signal": {
            "recommended_action": signal.get("recommended_action", "treat_as_lead"),
            "triage_summary": signal.get("triage_summary", ""),
            "scores": scores,
            "capsule": signal.get("capsule", ""),
        },
        "receipts_digest": _digest_for(flow_state, signal, pattern_hits),
        "safety_note": "Flow Master v0 only assesses text pressure and pacing. It does not block apps, monitor devices, or control input.",
    }

    if record:
        state = load_state()
        state["latest_assessment"] = assessment
        state.setdefault("receipts", []).append(
            {
                "at": assessment["generated_at"],
                "flow_state": flow_state,
                "pressure": assessment["composite_threat_score"],
                "summary": assessment["signal"]["triage_summary"],
                "action": assessment["receipts_digest"]["action"],
            }
        )
        save_state(state)
        try:
            import pip_traces

            pip_traces.record_trace(
                kind="flow_assessment",
                actor="pip",
                action="assess_flow_pressure",
                status=flow_state.lower(),
                summary=assessment["receipts_digest"]["action"],
                details={
                    "intent": intent,
                    "source_name": source_name,
                    "flow_state": flow_state,
                    "composite_threat_score": assessment["composite_threat_score"],
                    "neuro_burn_index": assessment["neuro_burn_index"],
                },
                source="pip_flow_master",
                tags=["flow_master", intent],
            )
        except Exception:
            pass
    return assessment


def inspect_flow_master() -> dict[str, Any]:
    doctrine = load_doctrine()
    state = load_state()
    return {
        "generated_at": utc_now(),
        "source_folder": str(FLOW_MASTER_DIR),
        "source_exists": FLOW_MASTER_DIR.exists(),
        "source_files": source_files(),
        "doctrine_path": str(doctrine_path()),
        "doctrine_exists": doctrine_path().exists(),
        "state_path": str(state_path()),
        "contract": doctrine.get("contract", DEFAULT_DOCTRINE["contract"]),
        "principles": doctrine.get("principles", []),
        "safety_boundaries": doctrine.get("safety_boundaries", []),
        "states": doctrine.get("states", FLOW_STATES),
        "latest_assessment": state.get("latest_assessment"),
        "recent_receipts": state.get("receipts", [])[-5:],
    }

#!/usr/bin/env python3
"""
pip_bos.py — Biological Operating System (Metabolic Governor) for Pip.

Maps hardware state (CPU/RAM) into a continuous metabolic phase variable φ.
This ensures Pip scales her background workloads according to the host system's viability,
preventing her from causing lag during high-stress periods.

Core Equation:
φ(t+1) = tanh(φ(t) + αM - βCR - γH)
"""
import json
import math
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

ROOT = Path(__file__).resolve().parent
BOS_STATE_PATH = ROOT / "imports" / "_bos_state.json"

# Tuning constants
ALPHA = 1.2
BETA = 1.5
GAMMA = 0.5

# CR weights
W1 = 1.0  # Stress
W2 = 1.0  # Loss
W3 = 0.8  # Low Reserve
W4 = 0.8  # Low Recovery
W5 = 0.5  # Debt

def _load_state() -> dict:
    if not BOS_STATE_PATH.exists():
        return {"phi_t": 0.0, "phi_t_minus_1": 0.0, "penalty": 0.0}
    try:
        state = json.loads(BOS_STATE_PATH.read_text(encoding="utf-8"))
        if "penalty" not in state:
            state["penalty"] = 0.0
        return state
    except Exception:
        return {"phi_t": 0.0, "phi_t_minus_1": 0.0, "penalty": 0.0}

def _save_state(state: dict) -> None:
    BOS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOS_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

def apply_penalty(amount: float) -> None:
    """Artificially increase the metabolic load (e.g. for bad rhetorical habits)."""
    state = _load_state()
    state["penalty"] += amount
    _save_state(state)

def get_hardware_metrics() -> dict:
    """Read host OS metrics via psutil and map to BOS variables (0.0 to 1.0)."""
    if not psutil:
        return {"E": 1.0, "R": 1.0, "S": 0.0, "L": 0.0, "D": 0.0}
        
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu_percent = psutil.cpu_percent(interval=0.5) / 100.0
    
    # E = Reserve (available memory fraction)
    e = mem.available / mem.total
    
    # R = Recovery capacity (idle CPU)
    r = 1.0 - cpu_percent
    
    # S = Stress (active CPU load)
    s = cpu_percent
    
    # L = Loss (memory pressure/swap usage)
    l = swap.percent / 100.0
    
    # D = Debt (could be disk IO queue or process queue, mapped simple for now)
    d = 0.0
    
    return {"E": e, "R": r, "S": s, "L": l, "D": d}

def step_oscillator() -> dict:
    """Calculate the next metabolic state and update the oscillator."""
    state = _load_state()
    metrics = get_hardware_metrics()
    
    E, R, S, L, D = metrics["E"], metrics["R"], metrics["S"], metrics["L"], metrics["D"]
    
    # M: Metabolic Viability
    M = E + R - S - L - D
    
    # CR: Cascade Risk
    CR = (W1 * S) + (W2 * L) + (W3 * max(0, 1.0 - E)) + (W4 * max(0, 1.0 - R)) + (W5 * D)
    
    # P: Penalty (decays over time)
    P = state.get("penalty", 0.0)
    new_P = P * 0.9  # 10% decay per step
    
    # H: Hysteresis (resistance to sudden change)
    phi_t = state["phi_t"]
    phi_t_minus_1 = state["phi_t_minus_1"]
    H = abs(phi_t - phi_t_minus_1)
    
    # Oscillator update (Penalty directly subtracts from viability)
    delta = (ALPHA * M) - (BETA * CR) - (GAMMA * H) - P
    phi_t_plus_1 = math.tanh(phi_t + delta)
    
    # Decode Phase
    if phi_t_plus_1 > 0.35:
        phase = "BUILD"
    elif phi_t_plus_1 >= -0.25:
        phase = "AUDIT"
    elif phi_t_plus_1 >= -0.80:
        phase = "DWELL"
    else:
        phase = "SHED"
        
    # Save state
    new_state = {
        "phi_t": phi_t_plus_1,
        "phi_t_minus_1": phi_t,
        "phase": phase,
        "M": M,
        "CR": CR,
        "H": H,
        "penalty": new_P
    }
    _save_state(new_state)
    return new_state

def get_phase() -> str:
    """Returns the current metabolic phase (BUILD, AUDIT, DWELL, SHED)."""
    return step_oscillator()["phase"]

def is_healthy_for_heavy_tasks() -> bool:
    """Helper for orchestrators to check if heavy ML tasks are permitted."""
    return get_phase() == "BUILD"

if __name__ == "__main__":
    st = step_oscillator()
    print("=== BOS Metabolic Governor State ===")
    print(f"Phase: {st['phase']} (phi: {st['phi_t']:.3f})")
    print(f"Viability (M):  {st['M']:.3f}")
    print(f"Cascade Risk:   {st['CR']:.3f}")
    print(f"Hysteresis:     {st['H']:.3f}")

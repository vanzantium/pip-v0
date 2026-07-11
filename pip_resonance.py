import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESONANCE_STATE_FILE = ROOT / "imports" / "_resonance_state.json"

def _read_state() -> dict:
    if not RESONANCE_STATE_FILE.exists():
        return {"pressures": [], "depths": [], "last_plv": 0.0}
    try:
        return json.loads(RESONANCE_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"pressures": [], "depths": [], "last_plv": 0.0}

def _write_state(state: dict):
    RESONANCE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESONANCE_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def update_resonance(pressure: float, depth: int) -> dict:
    """
    Updates the rolling history of pressure (emotion) and depth (thought),
    and calculates the Phase Locking Value (PLV) proxy.
    Returns a dict with {"plv": float, "iro_active": bool}
    """
    state = _read_state()
    pressures = state.get("pressures", [])
    depths = state.get("depths", [])
    
    pressures.append(float(pressure))
    depths.append(int(depth))
    
    # Keep last 5 interactions for momentum
    if len(pressures) > 5:
        pressures = pressures[-5:]
        depths = depths[-5:]
        
    state["pressures"] = pressures
    state["depths"] = depths
    
    plv = 0.0
    if len(pressures) >= 2:
        # Calculate momentum (gradient)
        dp = pressures[-1] - pressures[-2]
        dd = depths[-1] - depths[-2]
        
        # High resonance when emotion and thought move in tandem (both rise or both fall)
        if (dp > 0 and dd > 0) or (dp < 0 and dd < 0):
            # Normalize dp (0-1) and dd (approx 0-1000 tokens)
            plv = min(1.0, abs(dp) + (abs(dd) / 1000.0))
            
    state["last_plv"] = round(plv, 3)
    _write_state(state)
    
    return {
        "plv": state["last_plv"],
        "iro_active": state["last_plv"] > 0.5
    }

def get_current_resonance() -> dict:
    state = _read_state()
    plv = state.get("last_plv", 0.0)
    return {
        "plv": plv,
        "iro_active": plv > 0.5
    }

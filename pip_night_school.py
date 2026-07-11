#!/usr/bin/env python3
"""
pip_night_school.py - Automated nightly learning routine for Pip.

Orchestrates the reading of PDFs/docs using reads_mastery and OpenCode,
performs free-play exploration of the brain folder, and generates a morning summary.
"""
import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

import pip_platform
import pip_personas

HERE = Path(__file__).resolve().parent
BRAIN_ROOT = pip_platform.BRAIN_ROOT
MASTERY_SCRIPT = BRAIN_ROOT / "02_pip_and_system_architecture" / "builds" / "reads_mastery" / "mastery.py"
CODEX_SCRIPT = BRAIN_ROOT / "02_pip_and_system_architecture" / "builds" / "reads_mastery" / "reads_codex.py"

TARGET_ZONES = [
    BRAIN_ROOT / "08_reads_pdfs",
    BRAIN_ROOT / "12_citations",
    BRAIN_ROOT / "02_pip_and_system_architecture" / "builds" / "plm",
    BRAIN_ROOT / "04_worlds_lore_characters" / "personas",
    BRAIN_ROOT / "06_creative_media_art_music" / "video_shelf",
]

def run_cmd(cmd):
    """Run a command and return stdout."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[night_school] Command failed: {' '.join(cmd)}")
        print(e.stderr)
        return None

def process_zone(zone_path: Path) -> str:
    if not zone_path.exists():
        return f"Zone not found: {zone_path.name}"
        
    print(f"[night_school] Processing {zone_path.name}...")
    
    try:
        import pip_bos
        if not pip_bos.is_healthy_for_heavy_tasks():
            print(f"[night_school] BOS Phase is {pip_bos.get_phase()}. Yielding {zone_path.name} to prevent lag.")
            return f"Skipped {zone_path.name} due to high BOS hardware stress."
    except ImportError:
        pass
    
    # 1. Build Codex
    print(f"[night_school] Indexing codex for {zone_path.name}...")
    run_cmd([sys.executable, str(CODEX_SCRIPT), "--root", str(zone_path), "build"])
    
    # 2. Check Mastery Status
    status_out = run_cmd([sys.executable, str(MASTERY_SCRIPT), "--root", str(zone_path), "status"])
    if not status_out:
        return f"Nothing indexed in {zone_path.name}."
        
    # 3. Generate Next Task Packet
    print(f"[night_school] Emitting task packet for {zone_path.name}...")
    next_out = run_cmd([sys.executable, str(MASTERY_SCRIPT), "--root", str(zone_path), "next"])
    
    if not next_out or "already mastered" in next_out or "no indexed book" in next_out:
        return f"All books in {zone_path.name} are fully mastered!"
        
    # Parse the output to find the packet and target notes file
    packet_file = None
    for line in next_out.splitlines():
        if "packet ->" in line:
            packet_file = line.split("packet ->")[1].strip()
            
    # Read packet metadata
    import json
    meta_file = packet_file.replace(".md", ".json")
    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        meta = {}
        
    tier = meta.get("executor", "local")
    
    # 4. Route Execution based on Tier
    if tier == "strong":
        print(f"[night_school] Routing {Path(packet_file).name} (stage {meta.get('stage')}) to Claude's shift...")
        handoffs_dir = BRAIN_ROOT / "01_agent_context" / "handoffs"
        handoffs_dir.mkdir(exist_ok=True)
        
        book_name = meta.get("source", "unknown_book").replace(".pdf", "").replace(" ", "_")
        claude_file = handoffs_dir / f"@CLAUDE_Mastery_{book_name}_stage{meta.get('stage')}_{datetime.now().strftime('%Y%m%d')}.txt"
        
        notes_dest = None
        for line in next_out.splitlines():
            if "notes go to ->" in line:
                notes_dest = line.split("notes go to ->")[1].strip()
                
        instructions = (
            f"Please complete the mastery task outlined in this packet: {packet_file}\n"
            f"You will need to write the resulting notes to: {notes_dest}\n"
            f"After writing the notes, you MUST ingest them by running:\n"
            f"python {MASTERY_SCRIPT} --root {zone_path} ingest {packet_file} {notes_dest}\n"
        )
        claude_file.write_text(instructions, encoding="utf-8")
        return f"Routed {book_name} stage {meta.get('stage')} synthesis to Claude."

    # Otherwise execute Packet via Pip's native engine (Ollama) to bypass OpenCode headless hangs
    print(f"[night_school] Passing packet {Path(packet_file).name} to local Ollama engine...")
    task_prompt = (
        f"Read the task packet at {packet_file}. Execute its instructions and generate the requested notes text. "
        f"CRITICAL: Do NOT invent, guess, or include any authors, dates, or source citations that are not explicitly written in the packet content. If you are unsure, omit them entirely. "
        f"Do NOT wrap your notes in backticks or json. Output just the raw text of the notes."
    )
    
    notes_text = None
    try:
        packet_content = Path(packet_file).read_text(encoding="utf-8")[:1500]
        full_prompt = f"{task_prompt}\n\nPACKET CONTENT:\n{packet_content}"
        
        import urllib.request
        import json
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", headers={'Content-Type': 'application/json'}, method="POST")
        data = json.dumps({"model": "qwen2.5-coder:7b", "prompt": full_prompt, "stream": False}).encode("utf-8")
        with urllib.request.urlopen(req, data=data, timeout=600) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            notes_text = resp_data.get("response", "").strip()
    except Exception as e:
        notes_text = f"Error generating notes natively: {e}"

    if not notes_text or "Error" in notes_text[:20]:
        print(f"[night_school] Native engine error: {notes_text}")
        return f"OpenCode failed to produce notes for {zone_path.name}."
        
    # Provenance Gate for Stage 1 Outlines
    if meta.get("stage") == 1:
        print(f"[night_school] Running provenance gate for {zone_path.name}...")
        
        # 1. Deterministic Backstop (Regex)
        import re
        # Find 4-digit numbers (years) in notes
        years = re.findall(r'\b(1[0-9]{3}|20[0-9]{2})\b', notes_text)
        hallucinated_years = [y for y in years if y not in packet_content]
        if hallucinated_years:
            return f"Provenance Gate failed (Deterministic): Hallucinated years detected: {', '.join(set(hallucinated_years))}"
            
        # 2. LLM Gate
        gate_prompt = (
            "You are a strict fact-checker. Compare the original text to the generated outline. "
            "Does the outline invent any authors, dates, or sources not explicitly present in the original text? "
            "Reply ONLY with 'PASS' if it is strictly accurate, or 'REJECT: [reason]' if it hallucinates.\n\n"
            f"ORIGINAL TEXT:\n{packet_content}\n\n"
            f"GENERATED OUTLINE:\n{notes_text}"
        )
        try:
            req_gate = urllib.request.Request("http://127.0.0.1:11434/api/generate", headers={'Content-Type': 'application/json'}, method="POST")
            data_gate = json.dumps({"model": "qwen2.5-coder:7b", "prompt": gate_prompt, "stream": False}).encode("utf-8")
            with urllib.request.urlopen(req_gate, data=data_gate, timeout=600) as response_gate:
                gate_resp = json.loads(response_gate.read().decode("utf-8"))
                gate_result = gate_resp.get("response", "").strip()
                if gate_result.upper().startswith("REJECT"):
                    return f"Provenance Gate failed for {zone_path.name}: {gate_result}"
        except Exception as e:
            return f"Provenance Gate crashed for {zone_path.name}: {e}"
            
        # Append custody warning to separate PLM lanes
        notes_text += "\n\n> [!WARNING]\n> CUSTODY: This is a Stage 1 creative outline. Any provenance (authors/dates) is unverified and MUST NOT be ingested as factual citations."

        
    # Python writes the notes! This bypasses the --dir restriction and removes the need for --auto
    notes_file = None
    for line in next_out.splitlines():
        if "notes go to ->" in line:
            notes_file = line.split("notes go to ->")[1].strip()
            
    if notes_file:
        Path(notes_file).parent.mkdir(parents=True, exist_ok=True)
        Path(notes_file).write_text(notes_text, encoding="utf-8")
        print(f"[night_school] Ingesting notes for {zone_path.name}...")
        ingest_out = run_cmd([sys.executable, str(MASTERY_SCRIPT), "--root", str(zone_path), "ingest", packet_file, notes_file])
        return f"Advanced mastery in {zone_path.name}: {ingest_out}"
    else:
        return f"Could not determine notes file destination for {zone_path.name}."

def run_free_play() -> str:
    print("[night_school] Initiating Free Play in Brain folder...")
    
    try:
        import pip_bos
        if not pip_bos.is_healthy_for_heavy_tasks():
            return f"Skipped free play due to high BOS hardware stress ({pip_bos.get_phase()})."
    except ImportError:
        pass
    discoveries_dir = BRAIN_ROOT / "07_thought_models_research" / "pip_discoveries"
    discoveries_dir.mkdir(parents=True, exist_ok=True)
    
    out_file = discoveries_dir / f"discovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    import random
    candidate_files = []
    for root, dirs, files in os.walk(BRAIN_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith((".md", ".txt")):
                candidate_files.append(Path(root) / file)
                
    if len(candidate_files) < 3:
        return "Not enough files for free play."
        
    chosen = random.sample(candidate_files, 3)
    file_contents = []
    for f in chosen:
        try:
            content = f.read_text(encoding="utf-8")[:1500]
            file_contents.append(f"--- File: {f.name} ---\n{content}\n")
        except Exception:
            pass
            
    combined_content = "\n".join(file_contents)
    
    task_prompt = (
        f"You are exploring the brain folder. Here are 3 interesting but disconnected files:\n\n{combined_content}\n\n"
        f"Read them, find a deep conceptual connection between them, and output a short summary of this new connection. Output raw text."
    )
    
    discovery_text = None
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", headers={'Content-Type': 'application/json'}, method="POST")
        data = json.dumps({"model": "qwen2.5-coder:7b", "prompt": task_prompt, "stream": False}).encode("utf-8")
        with urllib.request.urlopen(req, data=data, timeout=600) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            discovery_text = resp_data.get("response", "").strip()
    except Exception as e:
        discovery_text = f"Error generating discovery natively: {e}"
            
    if discovery_text:
        out_file.write_text(discovery_text, encoding="utf-8")
        return f"Free play completed. Discovery saved to: {out_file.name}"
    else:
        return "Free play completed but no discovery file was written."

def run_night_school():
    print("=== Starting Pip Night School ===")
    summary_lines = [f"# Night School Summary - {datetime.now().strftime('%Y-%m-%d')}"]
    
    # Process Mastery Zones
    for zone in TARGET_ZONES:
        res = process_zone(zone)
        summary_lines.append(f"- **{zone.name}**: {res}")
        
    # Free Play
    free_play_res = run_free_play()
    summary_lines.append(f"- **Free Play**: {free_play_res}")
    
    summary_text = "\n".join(summary_lines)
    print("\n" + summary_text)
    
    # 1. Send to Phone
    try:
        import pip_phone_relay
        pip_phone_relay.send_response(f"Night School Complete!\n{summary_text}")
    except Exception as e:
        print(f"Could not send to phone: {e}")
        
    # 2. Save for Claude Accumulation
    handoffs_dir = BRAIN_ROOT / "01_agent_context" / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    
    claude_file = handoffs_dir / f"@CLAUDE_Night_School_{datetime.now().strftime('%Y%m%d')}.txt"
    claude_file.write_text(summary_text, encoding="utf-8")
    print(f"[night_school] Summary saved for Claude at {claude_file}")
    
    print("=== Night School Finished ===")

if __name__ == "__main__":
    run_night_school()

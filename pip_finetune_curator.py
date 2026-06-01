import json
from pathlib import Path
import pip_config

def get_dataset_path() -> Path:
    return pip_config.get_memory_path() / "training_data.jsonl"

def append_interaction(instruction: str, system_prompt: str, response_text: str, source: str = "goal_engine") -> None:
    """
    Appends a high-quality interaction to the local fine-tuning dataset in ShareGPT format.
    """
    p = get_dataset_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    
    entry = {
        "conversations": [
            {"from": "system", "value": system_prompt},
            {"from": "human", "value": instruction},
            {"from": "gpt", "value": response_text}
        ],
        "source": source
    }
    
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
        
    print(f"[Dataset Curator] Appended new fine-tuning sample from {source}.")

def record_accepted_proposal(proposal_text: str, evidence_text: str) -> None:
    system_prompt = "You are Pip, a localized AI assistant. Generate a high quality proposal based on the current context."
    instruction = f"Context Evidence:\n{evidence_text}\n\nDraft a proposal to assist the user."
    append_interaction(instruction, system_prompt, proposal_text, source="accepted_proposal")

def record_rejected_proposal(proposal_text: str, evidence_text: str, rejection_note: str = "") -> None:
    system_prompt = "You are Pip, a localized AI assistant. Generate a high quality proposal based on the current context."
    instruction = f"Context Evidence:\n{evidence_text}\n\nDraft a proposal to assist the user."
    response = f"[BAD PROPOSAL - DO NOT EMIT]\n{proposal_text}\n\nUser Rejection Note: {rejection_note}"
    append_interaction(instruction, system_prompt, response, source="rejected_proposal")

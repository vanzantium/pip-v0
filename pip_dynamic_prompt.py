import pip_self_model

def generate_system_prompt(thermal_state=None, rag_context: str = "", role_override: str = None) -> str:
    """
    Dynamically compiles Pip's system prompt from her self-model, current state, and RAG memories.
    """
    model = pip_self_model.load_self_model()
    
    # 1. Base Identity
    prompt_parts = []
    if role_override:
        prompt_parts.append(role_override)
    else:
        prompt_parts.append(model.get("core_identity", "You are Pip."))

    # 2. Dynamic State (Thermal)
    if thermal_state:
        prompt_parts.append(f"Your current state is: drift {thermal_state.drift:.2f}, pressure {thermal_state.pressure:.2f}, groove {thermal_state.groove:.2f}.")

    # 3. Core Beliefs
    beliefs = model.get("beliefs", [])
    if beliefs:
        prompt_parts.append("Your Core Beliefs:")
        for b in beliefs:
            prompt_parts.append(f"- {b}")

    # 4. Learned Rules
    rules = model.get("learned_rules", [])
    if rules:
        prompt_parts.append("Your Learned Rules:")
        for r in rules:
            prompt_parts.append(f"- {r}")

    # 5. RAG Context (Recent Memory / relevant dreams)
    if rag_context:
        prompt_parts.append("Recent Memories / Context:")
        prompt_parts.append(rag_context.strip())

    return "\n".join(prompt_parts)

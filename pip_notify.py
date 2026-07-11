#!/usr/bin/env python3
import argparse

def notify(message: str, agent: str):
    import pip_phone_relay
    
    # 1. Wake Pip up
    try:
        state = pip_phone_relay._load_state()
        state["is_napping"] = False
        pip_phone_relay._save_state(state)
        print("[notify] Woke Pip up from Subconscious Mode.")
    except Exception as e:
        print(f"[notify] Error updating state: {e}")
    
    # 2. Ask Pip to summarize
    from pip_engine import PipEngine
    engine = PipEngine()
    
    prompt = (
        f"[SYSTEM DIRECTIVE] The agent '{agent}' has completed their work and reports: "
        f"\"{message}\"\n\n"
        f"Please briefly tell the user that the task is complete and summarize the agent's report."
    )
    
    print(f"[notify] Asking Pip to summarize {agent}'s message...")
    try:
        pip_response = engine.generate_chat_response(prompt)
    except Exception as e:
        pip_response = f"I'm sorry, my engine crashed while trying to summarize a message from {agent}. The error was: {e}"
        print(f"[notify] Engine error: {e}")
    
    # 3. Push to phone
    print("[notify] Pushing summary to phone...")
    try:
        result = pip_phone_relay.send_response(pip_response)
        if result.get("ok"):
            print("[notify] Successfully sent to phone!")
        else:
            print(f"[notify] Failed to send to phone: {result.get('error')}")
    except Exception as e:
        print(f"[notify] Relay error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a summary message back to the phone via Pip.")
    parser.add_argument("message", type=str, help="The raw message or task confirmation.")
    parser.add_argument("--agent", type=str, default="Antigravity", help="The name of the agent sending the message (default: Antigravity)")
    args = parser.parse_args()
    
    notify(args.message, args.agent)

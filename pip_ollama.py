"""
pip_ollama.py — Direct local API hook to Ollama.
Bypasses UI automation for direct phone-to-model chats.
"""
import urllib.request
import json
import pip_threads

OLLAMA_URL = "http://localhost:11434/api/chat"

def generate_chat_response(thread_name: str, prompt: str) -> str:
    # 1. Add user message to history
    pip_threads.add_message(thread_name, "user", prompt)
    
    # 2. Get thread details
    thread = pip_threads.get_thread(thread_name)
    model = thread.get("model", "llama3.2")
    messages = thread.get("messages", [])
    
    # Format messages for Ollama API
    api_messages = []
    for m in messages:
        api_messages.append({"role": m["role"], "content": m["content"]})
        
    payload = {
        "model": model,
        "messages": api_messages,
        "stream": False
    }
    
    import socket
    import subprocess
    import time
    import os
    max_retries = 1
    
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                
            reply_content = resp_data.get("message", {}).get("content", "")
            
            # 3. Save assistant reply
            pip_threads.add_message(thread_name, "assistant", reply_content)
            return reply_content
            
        except (socket.timeout, urllib.error.URLError) as e:
            if attempt < max_retries:
                print(f"[ollama] Connection failed ({e}). Watchdog triggered: restarting ollama...")
                if os.name == "nt":
                    subprocess.run(["powershell", "-Command", "Stop-Process -Name ollama -Force -ErrorAction SilentlyContinue"], capture_output=True)
                    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                else:
                    subprocess.run(["pkill", "-9", "ollama"], capture_output=True)
                    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                print("[ollama] Waiting 60 seconds for Ollama to boot back up...")
                time.sleep(60)
                print("[ollama] Retrying generation...")
                continue
            else:
                error_msg = f"Ollama API Error (Watchdog exhausted): {e}"
                print(f"[ollama] {error_msg}")
                return error_msg
        except Exception as e:
            error_msg = f"Ollama API Error: {e}"
            print(f"[ollama] {error_msg}")
            return error_msg

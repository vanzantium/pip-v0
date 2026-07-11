"""
anti_phone_relay.py
A direct ntfy relay for Antigravity, running in the background.
It listens continuously for messages on a topic.
Instead of exiting after one message, it uses agentapi.bat to send the message
directly to the active Antigravity conversation, staying alive to catch follow-ups!
"""
import urllib.request
import json
import time
import sys
import subprocess
import os
from pathlib import Path

def listen_continuously(topic, conversation_id):
    ntfy_url = f"https://ntfy.sh/{topic}/json"
    req = urllib.request.Request(ntfy_url)
    bin_path = Path(os.environ.get("USERPROFILE", "C:\\")) / ".gemini" / "antigravity" / "bin" / "agentapi.bat"
    
    print(f"Listening continuously on {topic}...", flush=True)
    while True:
        try:
            with urllib.request.urlopen(req) as response:
                for line in response:
                    if line:
                        try:
                            data = json.loads(line.decode("utf-8"))
                            if data.get("event") == "message":
                                message = data.get("message", "")
                                attachment = data.get("attachment")
                                
                                output = f"[NEW DIRECT MESSAGE FROM USER]: {message}\n"
                                if attachment:
                                    att_url = attachment.get("url")
                                    att_name = attachment.get("name")
                                    output += f"[ATTACHMENT RECEIVED]: {att_name} - URL: {att_url}\n"
                                
                                print(f"Relaying to agent: {output.strip()}", flush=True)
                                
                                if bin_path.exists() and conversation_id:
                                    subprocess.run([str(bin_path), "send-message", conversation_id, output.strip()], 
                                                   creationflags=subprocess.CREATE_NO_WINDOW)
                                else:
                                    print("agentapi.bat not found or no conversation ID provided.", flush=True)
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "YOUR_SECRET_TOPIC"
    conv_id = sys.argv[2] if len(sys.argv) > 2 else None
    listen_continuously(topic, conv_id)

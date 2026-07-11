"""
anti_phone_relay.py
A direct ntfy relay for Antigravity, running in the background.
It listens for a single message on ntfy.sh/YOUR_SECRET_TOPIC.
Once it receives a message, it prints it and exits. This task completion
automatically wakes up Antigravity in the IDE without wasting polling tokens!
"""
import urllib.request
import json
import time
import sys

TOPIC = "YOUR_SECRET_TOPIC"
NTFY_URL = f"https://ntfy.sh/{TOPIC}/json"

def wait_for_one_message():
    req = urllib.request.Request(NTFY_URL)
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
                                
                                print(output, flush=True)
                                sys.exit(0)  # Exit immediately to trigger task completion
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    wait_for_one_message()

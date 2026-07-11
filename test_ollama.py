import urllib.request
import json
req = urllib.request.Request(
    'http://localhost:11434/api/generate',
    data=json.dumps({"model": "llama3.2:latest", "prompt": "hello", "stream": False}).encode(),
    headers={'Content-Type': 'application/json'}
)
print(urllib.request.urlopen(req).read().decode())

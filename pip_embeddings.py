import json
import math
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

import pip_config

DEFAULT_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://127.0.0.1:11434"

def pull_model(model_name: str) -> bool:
    """Uses subprocess to auto-pull an Ollama model if missing."""
    print(f"[pip_embeddings] Auto-pulling model {model_name}. This may take a minute...")
    try:
        # Run synchronous pull
        subprocess.run(["ollama", "pull", model_name], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[pip_embeddings] Failed to pull model {model_name}: {e}")
        return False
    except FileNotFoundError:
        print(f"[pip_embeddings] Ollama executable not found. Is it installed?")
        return False

def get_embedding(text: str, model: str = DEFAULT_MODEL) -> list[float]:
    """Get the embedding vector for a piece of text using Ollama."""
    url = f"{OLLAMA_URL}/api/embeddings"
    data = {"model": model, "prompt": text}
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("embedding", [])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Model likely not found, try to pull it
            if pull_model(model):
                # Try again once
                try:
                    with urllib.request.urlopen(req, timeout=30) as response:
                        result = json.loads(response.read().decode("utf-8"))
                        return result.get("embedding", [])
                except Exception as inner_e:
                    print(f"[pip_embeddings] Failed to get embedding after pull: {inner_e}")
                    return []
        print(f"[pip_embeddings] HTTP Error {e.code}: {e.reason}")
        return []
    except Exception as e:
        print(f"[pip_embeddings] Error connecting to Ollama: {e}")
        return []

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate the cosine similarity between two 1D vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot_product / (mag1 * mag2)

class PersonaMemoryStore:
    def __init__(self):
        self.memory_file = pip_config.get_memory_path() / "pip_persona_memory.json"
        self.memories = self._load()
        
    def _load(self) -> list[dict[str, Any]]:
        if not self.memory_file.exists():
            return []
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[PersonaMemoryStore] Failed to load memory: {e}")
            return []
            
    def _save(self) -> None:
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memories, f, indent=2)
        except Exception as e:
            print(f"[PersonaMemoryStore] Failed to save memory: {e}")
            
    def add_memory(self, text: str) -> bool:
        """Embeds and saves a new persona memory."""
        # Prevent duplicates
        for m in self.memories:
            if m.get("text") == text:
                return True
                
        vec = get_embedding(text)
        if not vec:
            return False
            
        self.memories.append({
            "text": text,
            "vector": vec,
            "timestamp": __import__("time").time()
        })
        self._save()
        return True
        
    def search(self, query: str, top_k: int = 3, threshold: float = 0.5) -> list[dict[str, Any]]:
        """Find the top-k most relevant memories for a query, expanded to their graph neighborhoods."""
        if not self.memories:
            return []
            
        query_vec = get_embedding(query)
        if not query_vec:
            return []
            
        # Try importing graph memory, gracefully fall back if it fails
        try:
            import pip_graph_memory
            graph_available = True
        except ImportError:
            graph_available = False
            
        results = []
        for mem in self.memories:
            vec = mem.get("vector")
            if not vec:
                continue
            sim = cosine_similarity(query_vec, vec)
            if sim >= threshold:
                base_text = mem["text"]
                # Enhance text with graph neighborhood if available
                if graph_available:
                    # Using the exact text as the node ID for now
                    enhanced_text = pip_graph_memory.format_neighborhood_for_llm(base_text, base_text)
                else:
                    enhanced_text = base_text
                    
                results.append({"text": enhanced_text, "score": sim, "timestamp": mem.get("timestamp", 0)})
                
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

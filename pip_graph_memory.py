#!/usr/bin/env python3
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import pip_platform

GRAPH_DB_PATH = pip_platform.BRAIN_ROOT / "02_pip_and_system_architecture" / "builds" / "pip" / "pip-v0" / ".graph_memory.db"

def init_db():
    conn = sqlite3.connect(str(GRAPH_DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            source_id TEXT,
            target_id TEXT,
            relation_type TEXT,
            metadata TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_id, target_id, relation_type)
        )
    """)
    conn.commit()
    conn.close()

def add_edge(source_id: str, target_id: str, relation_type: str, metadata: dict = None):
    """
    Add a directed edge between two memory items.
    relation_type could be: 'derived_from', 'contradicted_by', 'supported_by', 'reviewed_by'
    """
    if metadata is None:
        metadata = {}
        
    conn = sqlite3.connect(str(GRAPH_DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO edges (source_id, target_id, relation_type, metadata)
        VALUES (?, ?, ?, ?)
    """, (source_id, target_id, relation_type, json.dumps(metadata)))
    conn.commit()
    conn.close()

def get_neighborhood(node_id: str, depth: int = 1) -> List[Dict[str, Any]]:
    """
    Retrieve the 1-hop neighborhood for a given node.
    Returns a list of dicts: {"source_id": x, "target_id": y, "relation_type": z, "metadata": {}, "timestamp": t}
    """
    conn = sqlite3.connect(str(GRAPH_DB_PATH))
    cursor = conn.cursor()
    
    # Get outgoing edges (where node_id is source)
    cursor.execute("SELECT source_id, target_id, relation_type, metadata, timestamp FROM edges WHERE source_id = ? ORDER BY timestamp DESC", (node_id,))
    outgoing = cursor.fetchall()
    
    # Get incoming edges (where node_id is target)
    cursor.execute("SELECT source_id, target_id, relation_type, metadata, timestamp FROM edges WHERE target_id = ? ORDER BY timestamp DESC", (node_id,))
    incoming = cursor.fetchall()
    
    conn.close()
    
    neighborhood = []
    for row in outgoing + incoming:
        neighborhood.append({
            "source_id": row[0],
            "target_id": row[1],
            "relation_type": row[2],
            "metadata": json.loads(row[3]),
            "timestamp": row[4]
        })
        
    # Sort all by timestamp descending to put newest edges first
    neighborhood.sort(key=lambda x: x["timestamp"], reverse=True)
    return neighborhood

def format_neighborhood_for_llm(node_id: str, base_text: str, max_edges: int = 3) -> str:
    """
    Takes a base memory string and appends its graph relationships in a readable format.
    Caps the number of edges to `max_edges` to prevent token context blowout for 7B models,
    and includes provenance metadata/timestamps.
    """
    neighborhood = get_neighborhood(node_id)
    if not neighborhood:
        return base_text
        
    lines = [f"{base_text}"]
    
    # Apply token limit cap
    neighborhood = neighborhood[:max_edges]
    
    for edge in neighborhood:
        ts = edge["timestamp"][:10]  # Just YYYY-MM-DD
        meta = edge["metadata"]
        review_state = meta.get("review_state", "")
        meta_str = f" [{review_state}]" if review_state else ""
        
        if edge["source_id"] == node_id:
            # Outgoing edge
            target = edge['target_id']
            if len(target) > 50:
                target = target[:47] + "..."
            lines.append(f"  -> {edge['relation_type']}: {target} ({ts}){meta_str}")
        else:
            # Incoming edge
            source = edge['source_id']
            if len(source) > 50:
                source = source[:47] + "..."
            lines.append(f"  <- {edge['relation_type']} from: {source} ({ts}){meta_str}")
            
    return "\n".join(lines)

# Initialize on import
init_db()

#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
INDEX_PATTERN = re.compile(r"`([^`]*AGENTS\.md)`")


def discover_dox(root: Path = ROOT) -> list[Path]:
    return sorted(
        path for path in root.rglob("AGENTS.md")
        if "__pycache__" not in path.parts and ".git" not in path.parts
    )


def _index_entries(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    marker = "## Child DOX Index"
    if marker not in text:
        return []
    section = text.split(marker, 1)[1]
    return INDEX_PATTERN.findall(section)


def _nearest_parent_doc(path: Path, root: Path) -> Path | None:
    current = path.parent.parent
    while current == root or root in current.parents:
        candidate = current / "AGENTS.md"
        if candidate.exists():
            return candidate
        if current == root:
            break
        current = current.parent
    return None


def inspect_dox(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    docs = discover_dox(root)
    errors: list[str] = []
    entries_by_doc: dict[str, list[str]] = {}

    root_doc = root / "AGENTS.md"
    if not root_doc.exists():
        errors.append("missing root AGENTS.md")

    for doc in docs:
        relative_doc = doc.relative_to(root).as_posix()
        text = doc.read_text(encoding="utf-8")
        for section in ["Purpose", "Ownership", "Local Contracts", "Work Guidance", "Verification", "Child DOX Index"]:
            if f"## {section}" not in text:
                errors.append(f"{relative_doc}: missing section {section}")
        entries = _index_entries(doc)
        entries_by_doc[relative_doc] = entries
        for entry in entries:
            target = (doc.parent / entry).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                errors.append(f"{relative_doc}: index escapes repository: {entry}")
                continue
            if not target.exists():
                errors.append(f"{relative_doc}: indexed child missing: {entry}")

    for doc in docs:
        if doc == root_doc:
            continue
        parent_doc = _nearest_parent_doc(doc, root)
        relative_doc = doc.relative_to(root).as_posix()
        if parent_doc is None:
            errors.append(f"{relative_doc}: no parent DOX document found")
            continue
        expected = doc.relative_to(parent_doc.parent).as_posix()
        if expected not in _index_entries(parent_doc):
            errors.append(
                f"{relative_doc}: not indexed by {parent_doc.relative_to(root).as_posix()}"
            )

    return {
        "ok": not errors,
        "root": str(root),
        "document_count": len(docs),
        "documents": [doc.relative_to(root).as_posix() for doc in docs],
        "indexes": entries_by_doc,
        "errors": errors,
        "contract": "read applicable DOX chain before edits; update owning docs after meaningful changes",
    }

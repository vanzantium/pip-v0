"""
contracts.py — formal schemas for the shapes that were previously just
dict keys ("reviewed", "rejected", "source", "derived_from"...) that
every module had to remember correctly with no enforcement. A typo in a
key name used to fail silently; now it fails at construction.

Design choice: tolerant of missing keys on read (via from_dict), strict
on write (via the dataclass fields themselves). This is a "new schema
going forward, old data still readable" cut, not a hard migration --
there's no real production ledger data yet to migrate, so this is cheap
insurance, not a rescue operation.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class Thought:
    """A single entry in main.jsonl or side.jsonl."""
    text: str
    timestamp: str
    cft_score: float
    source: str = "auto"
    reviewed: bool = False
    rejected: bool = False
    derived_from: Optional[List[str]] = None  # timestamps of thoughts this was consolidated from

    @classmethod
    def from_dict(cls, d: dict) -> "Thought":
        return cls(
            text=d["text"],
            timestamp=d["timestamp"],
            cft_score=d.get("cft_score", 0.0),
            source=d.get("source", "auto"),
            reviewed=d.get("reviewed", False),
            rejected=d.get("rejected", False),
            derived_from=d.get("derived_from"),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["derived_from"] is None:
            del d["derived_from"]  # keep non-consolidated entries clean, no null clutter
        return d


@dataclass
class Receipt:
    """One line in receipts.jsonl. Event-specific fields go in `payload`
    rather than being enumerated here, since heartbeat/consolidation/skip
    events genuinely carry different shapes -- forcing one flat schema
    across all of them would just recreate the untyped-dict problem one
    level up."""
    event: str
    logged_at: str
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Receipt":
        d = dict(d)
        event = d.pop("event", "unknown")
        logged_at = d.pop("logged_at", "")
        return cls(event=event, logged_at=logged_at, payload=d)

    def to_dict(self) -> dict:
        out = {"event": self.event, "logged_at": self.logged_at}
        out.update(self.payload)
        return out


@dataclass
class ReviewDecision:
    """Result of a human checkpoint pass over one Thought."""
    thought_timestamp: str
    approved: bool
    reviewed_at: str

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewDecision":
        return cls(
            thought_timestamp=d["thought_timestamp"],
            approved=d["approved"],
            reviewed_at=d.get("reviewed_at", ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetirementRecord:
    """One logged use of a tool with a stated retirement rule."""
    tool: str
    timestamp: str
    caught_something: bool
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict, tool: str = "") -> "RetirementRecord":
        return cls(
            tool=d.get("tool", tool),
            timestamp=d["timestamp"],
            caught_something=d["caught_something"],
            note=d.get("note", ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


if __name__ == "__main__":
    # Roundtrip test against the exact old-format entries already sitting
    # in this project's test ledger, including one WITHOUT derived_from
    # and one where reviewed/rejected are set the old way.
    old_entries = [
        {"text": "The retrieval threshold may be too conservative for short notes.",
         "timestamp": "2026-07-05T10:00:00", "cft_score": 0.61,
         "source": "auto", "reviewed": True},
        {"text": "system: nothing new.", "timestamp": "2026-07-05T10:05:00",
         "cft_score": 0.55, "source": "auto", "rejected": True},
    ]

    print("=== Thought roundtrip against real old-format entries ===")
    for raw in old_entries:
        t = Thought.from_dict(raw)
        back = t.to_dict()
        print(f"in:  {raw}")
        print(f"out: {back}")
        assert back["text"] == raw["text"]
        assert "derived_from" not in back  # confirm no null clutter
        print("  OK\n")

    print("=== Thought with derived_from (new consolidation shape) ===")
    consolidated = Thought(
        text="[summary of 3 thoughts]",
        timestamp="2026-07-05T18:00:00",
        cft_score=0.5,
        source="consolidation",
        derived_from=["2026-07-01T00:00:00", "2026-07-02T00:00:00", "2026-07-03T00:00:00"],
    )
    print(consolidated.to_dict())

    print("\n=== Missing-key tolerance (old entry with NO reviewed/rejected at all) ===")
    bare = {"text": "old bare entry", "timestamp": "2026-01-01T00:00:00", "cft_score": 0.5}
    t2 = Thought.from_dict(bare)
    print(t2)
    assert t2.reviewed is False and t2.rejected is False
    print("  OK — defaults applied without error")

"""
cft_v2.py — CFT scoring rebuilt on substance_lib, not keyword presence.

WHY THE OLD ONE BROKE: it scored a thought in isolation by counting
keyword hits ("because", "correct", "?", commas). That rewards keyword
DENSITY, not substance, so it can't tell a real thought from keyword
salad, and it can't tell an echo from a genuine new thought because it
never looks at what the thought came FROM.

WHAT CHANGED: score the thought AGAINST its source context, using the
same content_words() overlap mechanism sonnet_turn_test.py already uses
to catch RESTATEMENT. Two axes instead of four invented ones:

  novelty   — how much of the thought is content NOT already in the
              context it was generated from (1 - overlap ratio).
              A verbatim echo scores 0 here, correctly, regardless of
              how many "because"s it contains.
  structure — does the new material carry argument or narrative
              structure (has_argument_content / has_narrative_content
              from substance_lib), not just new nouns dropped in.

  vacuous_penalty — filler-word density (vacuous_score), which
  subtracts rather than adds, so stacking "important, significant,
  truly, genuinely" doesn't help the way stacking "because/if/then"
  used to.

  MIN_CONTENT_WORDS floor: below this many content words, novelty is
  capped low regardless of overlap ratio, closing the short-nonsense-
  string loophole (a 4-word garbage string can hit overlap_ratio=0
  trivially; length alone shouldn't buy a high score).

composite = 0.55*novelty + 0.30*structure - 0.15*vacuous_penalty
(clamped to [0, 1])

This is a DROP-IN REPLACEMENT with a different signature: the old
cft_score(thought) becomes cft_score(thought, context). heartbeat()
must pass full_context (it already builds this string) instead of
calling cft_score(new_thought_text) alone.
"""

from substance_lib import (
    content_words,
    has_argument_content,
    has_narrative_content,
    vacuous_score,
)

MIN_CONTENT_WORDS = 6  # below this, novelty is capped -- closes the
                        # short-garbage-string loophole


def _garbage_ratio(text: str) -> float:
    """Fraction of whitespace-split tokens with no alphabetic character
    at all (bare punctuation like ',', ',,', '?'). substance_lib assumes
    real English prose on both sides of a comparison -- it has no way to
    flag a token stream that isn't language, so this is a separate,
    cheap floor rather than a substance_lib extension."""
    tokens = text.split()
    if not tokens:
        return 1.0
    garbage = sum(1 for t in tokens if not any(c.isalpha() for c in t))
    return garbage / len(tokens)


def cft_score(thought: str, context: str) -> dict:
    thought_words = content_words(thought)
    context_words = content_words(context)

    overlap_ratio = (
        len(thought_words & context_words) / len(thought_words)
        if thought_words else 1.0
    )
    novelty = 1.0 - overlap_ratio
    if len(thought_words) < MIN_CONTENT_WORDS:
        novelty = min(novelty, 0.3)  # short strings can't claim full novelty

    structure = 1.0 if (has_argument_content(thought)
                        or has_narrative_content(thought)) else 0.0

    # filler density: vacuous hits per content word, not a raw count,
    # so longer thoughts aren't unfairly penalized for one stray "truly"
    filler_density = (vacuous_score(thought) / max(1, len(thought_words)))
    vacuous_penalty = min(filler_density * 2, 1.0)

    garbage = _garbage_ratio(thought)

    composite = 0.55 * novelty + 0.30 * structure - 0.15 * vacuous_penalty
    composite = max(0.0, min(1.0, composite))
    if garbage > 0.10:
        # hard cap, not a subtraction -- a token stream that's >10% bare
        # punctuation isn't a weak thought, it's not sentence-shaped at
        # all, and no amount of novelty/structure should buy it past
        # the threshold
        composite = min(composite, 0.2)

    return {
        "composite": round(composite, 3),
        "novelty": round(novelty, 3),
        "structure": structure,
        "vacuous_penalty": round(vacuous_penalty, 3),
        "garbage_ratio": round(garbage, 3),
        "new_content_words": sorted(thought_words - context_words),
    }


if __name__ == "__main__":
    # Same three cases that broke the old scorer, run through this one.
    context = ("Hard conversations require tools, not emotional resonance. "
               "Build a raft before the flood. System collapses often come "
               "from treating a feeling as a fact. The skeptic pass checks "
               "evidentiality.")

    cases = {
        "keyword salad (old score: 0.739, wrongly promoted)":
            "because if then however since thus correct revise instead update, ,, ,, ?",
        "real substantive thought (old score: 0.039, wrongly pruned)":
            "The corpus retrieval threshold of 0.4 may be too low for short notes.",
        "verbatim echo of context (old score: undefined, silently re-promoted forever)":
            "Hard conversations require tools, not emotional resonance. Build a raft before the flood.",
    }

    for label, text in cases.items():
        result = cft_score(text, context)
        print(f"\n{label}")
        print(f"  composite: {result['composite']}  "
              f"(PROMOTE)" if result['composite'] >= 0.5 else
              f"  composite: {result['composite']}  (side/prune)")
        print(f"  novelty={result['novelty']} structure={result['structure']} "
              f"vacuous_penalty={result['vacuous_penalty']}")

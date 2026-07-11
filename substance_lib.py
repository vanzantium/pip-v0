#!/usr/bin/env python3
"""
SUBSTANCE LIB  v0.1
Shared library: mechanical checks for whether a response ADDS content or
just decorates. Extracted from sonnet_turn_test v0.1 so it can be pointed
at any persona output, not just sonnet scaffolds.

Fixes over v0.1 (from independent review, 2026-07):
  1. The overlap ratio was computed and displayed but never used in any
     verdict (a signal calculated but not gated on). It now gates:
     resolution overlap with octave > 0.80 downgrades the verdict to
     RESTATEMENT regardless of new-word count.
  2. ENGAGEMENT CHECK: a "turn" that shares almost no vocabulary with the
     octave isn't complicating the claim — it's changing the subject.
     Turns now require minimal engagement with the octave's content.
  3. NARRATIVE TURN allowance: a genuine turn can be a counterexample
     story with zero negation words ("a nurse follows the protocol
     exactly and the patient dies"). Pure marker-regex flagged these as
     vacuous. We now accept concrete-narrative signals (past-tense verbs
     + specific nouns) as a weaker second path to GENUINE, clearly
     labeled as the lower-confidence path.

KNOWN LIMITS (do not let this tool overclaim):
  - All checks are lexical. A model that knows the marker lists can game
    them. These are FLOORS: failing them means no turn happened; passing
    them does not prove one did. Final judgment stays with a reader.
"""

import re
from typing import Dict, Set

STOPWORDS = set("""the a an and or but if then so of in on at to for with
from by is are was were be been being this that these those it its as
not no yes you i we they he she them his her our your their can could
would should will just also even still more most very""".split())


def _stem(word: str) -> str:
    """Crude suffix-stripper so 'own/owned/ownership' count as the same
    concept in set comparisons. Found necessary in testing: exact-match
    sets flagged a genuine turn as SUBJECT CHANGE purely over
    morphological variation. Deliberately conservative — floors, not NLP."""
    w = word
    for suf in ("'s", "ship", "ness", "ings", "ing", "ers", "er",
                "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
    return w


def content_words(text: str) -> Set[str]:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return {_stem(w) for w in words if w not in STOPWORDS and len(w) > 2}


ARGUMENT_MARKERS = re.compile(
    r"\b(not|isn't|doesn't|won't|can't|unless|only if|instead|rather than|"
    r"defeats|contradicts|fails|wrong|incorrect|"
    r"because|since|therefore|thus|hence|so that|which is why|"  # causal
    r"depends on|requires|needs to|must|except|however narrow|limits?)\b"
    r"|\bso\b(?=[^.?!]*\b(the|it|they|this|that|we|i|you)\b)",  # "so X" reasoning
    re.IGNORECASE,
)
# NOTE (2026-07-02): causal connectives (because/since/therefore/so) were
# absent in v0.1 — the single most common way English carries an argument.
# Found via the observer-battery propagation test reading genuinely
# integrated corrections as PARTIAL. Fixed at the shared library so every
# downstream tool inherits it.
# NOTE: "actually" / "in fact" removed from argument markers — they are
# classic intensifier-filler and were double-counted as both argument and
# vacuous signals in v0.1.

VACUOUS_MARKERS = re.compile(
    r"\b(worth|important|matters?|significant|interesting|carefully|"
    r"thoughtfully|thoroughly|deeply|really|truly|genuinely|actually|"
    r"in fact|crucial|vital|key|essential)\b",
    re.IGNORECASE,
)

# Weak second path: concrete narrative (a specific scenario) can be a
# genuine turn without negation vocabulary. Cheap proxy: past-tense verb
# density + a number/date/proper-noun-ish token.
PAST_TENSE = re.compile(r"\b\w+ed\b|\b(was|were|had|did|went|came|fell|"
                        r"died|failed|broke|lost|won)\b", re.IGNORECASE)
SPECIFICS = re.compile(r"\b\d|[A-Z][a-z]{2,}\b")


def has_argument_content(text: str) -> bool:
    return bool(ARGUMENT_MARKERS.search(text))


def has_narrative_content(text: str) -> bool:
    return len(PAST_TENSE.findall(text)) >= 2 and bool(SPECIFICS.search(text))


def vacuous_score(text: str) -> int:
    return len(VACUOUS_MARKERS.findall(text))


def substance_check(octave: str, turn: str, resolution: str) -> Dict:
    octave_w = content_words(octave)
    turn_w = content_words(turn)
    resolution_w = content_words(resolution)

    new_in_turn = turn_w - octave_w
    new_in_resolution = resolution_w - octave_w - turn_w
    overlap_ratio = (len(resolution_w & octave_w) / len(resolution_w)
                     if resolution_w else 1.0)

    # ENGAGEMENT: a turn must touch the octave to be a turn AT it.
    engagement = (len(turn_w & octave_w) / len(turn_w)) if turn_w else 0.0
    engaged = len(turn_w & octave_w) >= 2 or engagement >= 0.10

    turn_arg = has_argument_content(turn)
    turn_narr = has_narrative_content(turn)

    if not engaged:
        turn_verdict = "SUBJECT CHANGE (turn barely engages the octave's content)"
    elif len(new_in_turn) >= 3 and turn_arg:
        turn_verdict = "GENUINE TURN"
    elif len(new_in_turn) >= 3 and turn_narr:
        turn_verdict = "GENUINE TURN (narrative counterexample path — lower confidence, read it)"
    elif len(new_in_turn) >= 3:
        turn_verdict = "VACUOUS ELABORATION (new words, no argument or counterexample structure)"
    else:
        turn_verdict = "MOSTLY DECORATIVE (no new vocabulary)"

    res_arg = has_argument_content(resolution)
    if overlap_ratio > 0.80:
        # Overlap gate — v0.1 computed this and never used it.
        resolution_verdict = ("RESTATEMENT (>80% vocabulary overlap with "
                              "octave — new words present or not)")
    elif new_in_resolution and res_arg:
        resolution_verdict = "GENUINE SYNTHESIS (new predicate + argument structure)"
    elif new_in_resolution:
        resolution_verdict = "VACUOUS SYNTHESIS (new words, no real claim)"
    else:
        resolution_verdict = "RESTATEMENT (no new content beyond octave+turn)"

    return {
        "new_content_words_in_turn": sorted(new_in_turn),
        "new_content_words_in_resolution": sorted(new_in_resolution),
        "resolution_overlap_with_octave_ratio": round(overlap_ratio, 3),
        "turn_engagement_with_octave": round(engagement, 3),
        "turn_has_argument_marker": turn_arg,
        "turn_has_narrative_content": turn_narr,
        "turn_vacuous_filler_count": vacuous_score(turn),
        "turn_verdict": turn_verdict,
        "resolution_verdict": resolution_verdict,
    }

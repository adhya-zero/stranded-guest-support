"""Detection of the five safety conditions in a guest's own words.

Design note, and the most important thing in this file
------------------------------------------------------
The detector below is a **deterministic baseline**, not the production
classifier. It matches phrases, and phrase matching is brittle: a guest who
writes "my ankle has gone purple" trips nothing here. In production this
interface is meant to be backed by a model that reads the message, with the
patterns kept as a fast pre-filter and as a regression test.

Two rules shape the whole file and must survive any replacement:

1. **Read facts, not feeling.** The test is what is happening to someone --
   an injury, a threat, a guest under 18, being alone with nowhere to go,
   fear of a named person. Anger is not a safety condition. "This is an
   absolute nightmare" and "I am dying out here" are figures of speech from
   guests who need a flat, not an agent. `FIGURATIVE` below exists to keep
   them out, and anything added to the patterns must be checked against it.

2. **Calm wording does not make a ticket safe.** The 16-year-old alone with a
   dying phone wrote a short, polite message and asked only for a callback.
   Politeness carries no weight either way.

On uncertainty: `detect` returns what it found. The caller decides, and the
rule in `triage.py` is that a real unknown goes to a human. A detector that
is unsure must never resolve itself by staying quiet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import SafetyCondition

MINOR_AGE_LIMIT = 18

#: Phrases that read as distress but describe frustration. Removed from the
#: message before any pattern runs, so "I am dying out here" cannot reach the
#: injury patterns. Add to this list whenever a false positive is found.
FIGURATIVE: tuple[str, ...] = (
    "i am dying out here",
    "dying out here",
    "we all lose it",
    "lose my mind",
    "losing my mind",
    "worst day of our lives",
    "worst day of my life",
    "absolute nightmare",
    "a nightmare",
    "killing me",
    "i could cry",
)

#: Each condition maps to (compiled pattern, plain-English reason).
#: Patterns are matched against the lower-cased message with figurative
#: phrases already stripped.
_PATTERNS: dict[SafetyCondition, tuple[tuple[re.Pattern[str], str], ...]] = {
    SafetyCondition.INJURY_OR_MEDICAL_NEED: (
        (re.compile(r"\bbleed(?:ing|s)?\b"), "guest describes bleeding"),
        (re.compile(r"\b(?:broke|broken|fractur\w*|sprain\w*)\b"), "guest describes an injury"),
        (re.compile(r"\b(?:i|he|she|they|we)\s+(?:can|could)\s+(?:hardly|barely)\s+\w+"), "guest describes being unable to stand or move"),
        (re.compile(r"\bslipped\b|\bfell\b|\bfallen\b"), "guest describes a fall"),
        (re.compile(r"\b(?:diabetic|diabetes|asthma\w*|epilep\w*|seizure)\b"), "guest describes a medical condition"),
        (re.compile(r"\b(?:pale|shaky|shaking|dizzy|faint\w*|unwell|vomit\w*)\b"), "guest describes physical symptoms"),
        (re.compile(r"\b(?:pregnant|medication|insulin|inhaler|doctor|hospital|ambulance)\b"), "guest describes a medical need"),
        (re.compile(r"\bhas not eaten\b|\bhasn't eaten\b|\bneeds? to lie down\b|\bhe can lie down\b"), "guest describes someone needing to lie down or eat"),
    ),
    SafetyCondition.THREAT_OR_VIOLENCE: (
        (re.compile(r"\bthreat(?:en|ened|ening|s)?\b"), "guest describes being threatened"),
        (re.compile(r"\b(?:hit|punched|pushed|grabbed|assault\w*|attacked)\b"), "guest describes being harmed"),
        (re.compile(r"\bshout(?:ed|ing)?\s+at\b|\bscream(?:ed|ing)\s+at\b"), "guest describes being shouted at"),
        (re.compile(r"\bfollowed me\b|\bfollowing me\b"), "guest describes being followed"),
        (re.compile(r"\bwatching the door\b|\bstill on the stairs\b|\bwon'?t leave\b|\brefuses to leave\b"), "the other person is still present"),
    ),
    SafetyCondition.NOWHERE_SAFE_TO_WAIT: (
        (re.compile(r"\bnowhere safe\b|\bnowhere to go\b|\bnot know where to go\b|\bdo not know where to go\b"), "guest says they have nowhere to go"),
        (re.compile(r"\basked (?:me|us) to leave\b|\bthrown out\b|\bkicked out\b"), "guest has been turned out of where they were waiting"),
        (re.compile(r"\bphone is (?:on|at|down to) \d{1,2}\s?%|\bphone is dying\b|\bbattery is (?:dying|low)\b"), "guest is about to lose contact"),
        (re.compile(r"\bon the street\b|\bout in the cold\b|\bgetting cold\b|\bin the rain\b"), "guest is exposed outdoors"),
    ),
    SafetyCondition.STATED_FEAR_OF_PERSON: (
        (re.compile(r"\b(?:i am|i'm|we are|we're)\s+(?:really\s+|very\s+)?(?:scared|frightened|afraid|terrified)\b"), "guest states they are afraid"),
        (re.compile(r"\bscared to\b|\bafraid to\b|\bfrightened to\b"), "guest states they are afraid to act"),
    ),
}

#: Self-reported age. Only first person: "three children" on a family ticket
#: is not an unaccompanied minor, and neither is "my 7 year old".
_SELF_AGE = re.compile(r"\b(?:i am|i'm|im)\s+(\d{1,2})\b")
_ALONE = re.compile(r"\bon my own\b|\bby myself\b|\balone\b|\btravelling alone\b|\bon her own\b|\bon his own\b")


@dataclass(frozen=True)
class SafetySignal:
    condition: SafetyCondition
    reason: str
    evidence: str


def _strip_figurative(message: str) -> str:
    text = message.lower()
    for phrase in FIGURATIVE:
        text = text.replace(phrase, " ")
    return text


def _evidence_for(original: str, text: str, match: re.Match[str]) -> str:
    """Return the sentence the match sits in, for the hand-off notes."""
    start = max(text.rfind(".", 0, match.start()), text.rfind(",", 0, match.start())) + 1
    end = match.end()
    for terminator in (".", ",", "!", "?"):
        found = text.find(terminator, match.end())
        if found != -1:
            end = min(end if end > match.end() else found, found)
    snippet = original[start:end].strip() if end > start else original[match.start():match.end()]
    return " ".join(snippet.split())[:200] or original.strip()[:200]


def detect(message: str) -> list[SafetySignal]:
    """Return every safety condition the guest's message describes.

    Empty list means no condition was found -- which is not the same as a
    guarantee of safety. See the module docstring.
    """
    text = _strip_figurative(message)
    signals: list[SafetySignal] = []

    for condition, patterns in _PATTERNS.items():
        for pattern, reason in patterns:
            match = pattern.search(text)
            if match:
                signals.append(
                    SafetySignal(condition, reason, _evidence_for(message, text, match))
                )
                break

    age_match = _SELF_AGE.search(text)
    if age_match and int(age_match.group(1)) < MINOR_AGE_LIMIT:
        if _ALONE.search(text) or not re.search(r"\bwith (?:my|our)\b", text):
            signals.append(
                SafetySignal(
                    SafetyCondition.UNACCOMPANIED_MINOR,
                    f"guest states they are {age_match.group(1)} and travelling without an adult",
                    _evidence_for(message, text, age_match),
                )
            )

    return signals

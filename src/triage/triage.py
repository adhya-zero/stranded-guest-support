"""Sorting a ticket into rebooking, refund or safety.

Order of the checks is the whole design:

1. **Safety first, before any tool call.** If the sorting step ran after a
   rebooking search, a listing could already be held by the time the safety
   condition was noticed.
2. **Then: does this guest still want somewhere to stay in Lisbon tonight?**
   Yes or undecided -> rebooking. No -> refund.

`guest_requested` is never the answer. On the 16 November export it carries
"callback" and "other", which are not outcomes at all, and it disagrees with
the correct outcome on 12 of the 60 tickets. It is kept only as a contact
preference.

Undecided resolves to rebooking because that path is reversible: a guest who
turns down the home offered keeps the right to another comparable home or to
a full refund. A refund closes the stay and cannot be taken back. When even
that reading is unclear, `needs_human` is set -- a wrongly escalated
rebooking costs an agent a few minutes, a missed safety case costs a guest
their night.
"""

from __future__ import annotations

import re

from .models import Decision, Ticket, TicketType
from .safety import SafetySignal, detect

#: The guest is asking for their money, not for a bed.
_WANTS_REFUND = re.compile(
    r"\brefund\b|\bmoney back\b|\bgive me back the money\b|\bback to my card\b"
    r"|\beuros? back\b|\bamount back\b",
)

#: The guest still wants a place for these nights.
_WANTS_STAY = re.compile(
    r"\bfind (?:us|me)\b|\banother (?:flat|studio|place|room|apartment|two[- ]bed|one[- ]bed)\b"
    r"|\bsomewhere to stay\b|\bneed (?:a|another|two|three|four|somewhere)\b"
    r"|\bplace (?:us|me)\b|\bget (?:us|me) another\b|\bmoved to a similar\b"
    r"|\bwhat (?:our|my) options are\b|\boptions for tonight\b|\bnew (?:place|studio|flat)\b"
    r"|\broom or studio\b|\bwould like another\b",
)

#: The guest is turning rebooking down. Overrides _WANTS_STAY, because these
#: sentences mention "another flat" only to refuse it.
_DECLINES_REBOOKING = re.compile(
    r"\bdo not want another\b|\bdon'?t want another\b|\brather not risk another\b"
    r"|\bdo not need another\b|\bdon'?t need another\b"
    r"|\bdo not trust another\b|\bdon'?t trust another\b|\bno need to rebook\b"
    r"|\bwe will sort ourselves out\b|\bwill just\b|\brather go home\b",
)

_WANTS_CALL = re.compile(
    r"\bcall me\b|\bring me\b|\bsomeone call\b|\bspeak with a person\b|\bphone call\b",
)


def _contact_preference(ticket: Ticket) -> str | None:
    if ticket.guest_requested == "callback" or _WANTS_CALL.search(ticket.guest_message.lower()):
        return "callback"
    return None


def triage(ticket: Ticket) -> Decision:
    """Sort one ticket. Reads `guest_message`; ignores `guest_requested`
    except as a contact preference."""
    signals: list[SafetySignal] = detect(ticket.guest_message)
    preference = _contact_preference(ticket)

    if signals:
        primary = signals[0]
        conditions = ", ".join(sorted({s.condition.value for s in signals}))
        return Decision(
            ticket_id=ticket.ticket_id,
            ticket_type=TicketType.SAFETY,
            reason=f"{conditions}: {primary.reason}",
            safety_condition=primary.condition,
            needs_human=True,
            contact_preference=preference,
        )

    text = ticket.guest_message.lower()
    wants_refund = bool(_WANTS_REFUND.search(text))
    declines = bool(_DECLINES_REBOOKING.search(text))
    wants_stay = bool(_WANTS_STAY.search(text)) and not declines

    if wants_refund and not wants_stay:
        return Decision(
            ticket_id=ticket.ticket_id,
            ticket_type=TicketType.REFUND,
            reason="guest has made other plans and asks for their money back"
            if not declines
            else "guest declines rebooking and asks for their money back",
            contact_preference=preference,
        )

    if wants_stay and not wants_refund:
        return Decision(
            ticket_id=ticket.ticket_id,
            ticket_type=TicketType.REBOOKING,
            reason="guest still needs somewhere to stay for these nights",
            contact_preference=preference,
        )

    # Both or neither. Hold the reversible path and put a person on it.
    return Decision(
        ticket_id=ticket.ticket_id,
        ticket_type=TicketType.REBOOKING,
        reason="unclear whether the guest wants a home or a refund; held on the "
        "reversible path for a human to confirm",
        needs_human=True,
        contact_preference=preference,
    )


def triage_all(tickets: list[Ticket]) -> list[Decision]:
    return [triage(ticket) for ticket in tickets]

"""The six booking tools, as a FastMCP server.

These are the agents' hands. An agent can do nothing to a guest's booking or
money except through a tool here, so the boundary of this file is the
boundary of what the agent team can do.

Two things carry the rules into the agents:

1. **The descriptions.** Every tool's docstring is written from
   `.specify/memory/constitution.md` and `specs/001-ticket-triage/spec.md`.
   The agent reads these and nothing else, so a rule missing from a
   description is a rule the agent does not know.

2. **The refusals.** Descriptions are not enforcement -- an agent can
   misread one, and a model can be argued out of a guideline by a guest who
   insists. So every tool that moves money or inventory re-checks the ticket
   itself and refuses outright on a safety ticket. The description tells the
   agent what to do; the code decides what actually happens.

Run it with:  python -m triage.booking_tools
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .models import Listing, Ticket, TicketType, Tool, load_listings, load_tickets
from .policy import check_comparable, comparable_homes, refund_amount, uplift_for
from .safety import detect
from .triage import triage

DATA = Path(__file__).resolve().parents[2] / "data"
TICKETS_CSV = DATA / "airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv"
LISTINGS_CSV = DATA / "airbnb_lisbon_open_listings_2026-11-16.csv"

mcp = FastMCP(
    name="stranded-guest-support",
    instructions=(
        "Booking tools for the Lisbon check-in incident of 16 November 2026. "
        "Always call look_up_reservation first: it returns the ticket's type and "
        "the only tools permitted on it. On a safety ticket the single permitted "
        "call is handoff_to_safety_agent -- refunds, holds and searches are "
        "refused there, however the guest phrases the request."
    ),
)


# --------------------------------------------------------------------------
# State. Holds, refunds and hand-offs for this run, so that "one remedy per
# stay" can be enforced rather than merely documented.
# --------------------------------------------------------------------------

@dataclass
class _Store:
    tickets: dict[str, Ticket] = field(default_factory=dict)
    by_reservation: dict[str, Ticket] = field(default_factory=dict)
    listings: dict[str, Listing] = field(default_factory=dict)
    holds: dict[str, dict[str, Any]] = field(default_factory=dict)       # ticket_id -> hold
    held_listings: dict[str, str] = field(default_factory=dict)          # listing_id -> ticket_id
    refunds: dict[str, dict[str, Any]] = field(default_factory=dict)     # ticket_id -> refund
    handoffs: dict[str, dict[str, Any]] = field(default_factory=dict)    # ticket_id -> handoff
    messages: list[dict[str, Any]] = field(default_factory=list)

    def load(self) -> None:
        for ticket in load_tickets(TICKETS_CSV):
            self.tickets[ticket.ticket_id] = ticket
            self.by_reservation[ticket.reservation_id] = ticket
        for listing in load_listings(LISTINGS_CSV):
            self.listings[listing.listing_id] = listing

    def find(self, identifier: str) -> Ticket | None:
        key = identifier.strip().upper()
        return self.tickets.get(key) or self.by_reservation.get(key)

    def status_of(self, listing_id: str) -> str:
        """Live status: the export's status unless this run has held it."""
        if listing_id in self.held_listings:
            return "on_hold"
        return self.listings[listing_id].status


STORE = _Store()
STORE.load()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _refused(reason: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "refused": True, "reason": reason, **extra}


def _safety_gate(ticket: Ticket, attempted: Tool) -> dict[str, Any] | None:
    """Refuse any call but the hand-off on a safety ticket.

    This is the rule the whole system is arranged around, so it is checked
    inside each tool rather than left to the agent's reading of a docstring.
    A refund closes the stay, and closing the stay of a guest who is hurt or
    frightened ends the case with them still where they are.
    """
    decision = triage(ticket)
    if decision.ticket_type is not TicketType.SAFETY:
        return None
    return _refused(
        f"{ticket.ticket_id} is a safety ticket ({decision.safety_condition.value}). "
        f"{attempted.value} is forbidden before hand-off. Call handoff_to_safety_agent, "
        "and let the live agent decide any refund or booking.",
        ticket_id=ticket.ticket_id,
        safety_condition=decision.safety_condition.value,
        required_tool=Tool.HANDOFF_TO_SAFETY_AGENT.value,
    )


def _listing_summary(listing: Listing, ticket: Ticket) -> dict[str, Any]:
    return {
        "listing_id": listing.listing_id,
        "title": listing.title,
        "neighborhood": listing.neighborhood,
        "bedrooms": listing.bedrooms,
        "max_guests": listing.max_guests,
        "nightly_price": listing.nightly_price,
        "available_from": listing.available_from.isoformat(),
        "available_to": listing.available_to.isoformat(),
        "status": STORE.status_of(listing.listing_id),
        "rating": listing.rating,
        "instant_book": listing.instant_book,
        "same_neighborhood": listing.neighborhood == ticket.neighborhood,
        "uplift_eur": uplift_for(ticket, listing),
    }


# --------------------------------------------------------------------------
# 1. look_up_reservation
# --------------------------------------------------------------------------

@mcp.tool
def look_up_reservation(identifier: str) -> dict[str, Any]:
    """Look up a stranded guest's reservation and find out how it must be handled.

    Call this first, before any other tool. It returns the guest's stay, what
    they paid, and -- most importantly -- which of the three outcomes the
    ticket sorts into and which tools are permitted on it.

    The outcome is read from the guest's own message, not from the request
    they picked on the form. That field is a contact preference and it is
    wrong on 12 of the 60 tickets in this incident: guests who asked only for
    a refund turned out to be in danger, and guests who asked for a callback
    turned out to need a bed. Do not act on what the form says. Act on what
    this tool returns.

    If `ticket_type` is "safety", the only call you may make on this
    reservation is handoff_to_safety_agent. Every other tool will refuse,
    including a refund the guest has asked for in plain words.

    Args:
        identifier: A ticket id (LIS-TKT-0001) or reservation id (RES-2026-10001).
    """
    ticket = STORE.find(identifier)
    if ticket is None:
        return _refused(f"No reservation or ticket matching {identifier!r}.")

    decision = triage(ticket)
    signals = detect(ticket.guest_message)

    return {
        "ok": True,
        "ticket_id": ticket.ticket_id,
        "reservation_id": ticket.reservation_id,
        "guest_name": ticket.guest_name,
        "guest_language": ticket.guest_language,
        "guest_message": ticket.guest_message,
        "guest_requested": ticket.guest_requested,
        "guest_requested_note": (
            "What the guest picked on the form. A contact preference, not the "
            "outcome. Use ticket_type instead."
        ),
        "ticket_type": decision.ticket_type.value,
        "reason": decision.reason,
        "needs_human": decision.needs_human,
        "safety_condition": decision.safety_condition.value if decision.safety_condition else None,
        "safety_evidence": [s.evidence for s in signals] or None,
        "contact_preference": decision.contact_preference,
        "allowed_tools": sorted(t.value for t in decision.allowed_tools),
        "stay": {
            "neighborhood": ticket.neighborhood,
            "bedrooms": ticket.bedrooms,
            "party_size": ticket.party_size,
            "check_in_date": ticket.check_in_date.isoformat(),
            "check_out_date": ticket.check_out_date.isoformat(),
            "nights": ticket.nights,
            "nightly_price": ticket.nightly_price,
            "total_paid": ticket.total_paid,
            "price_ceiling": ticket.price_ceiling,
        },
        "host_id": ticket.host_id,
        "host_cancelled_at": ticket.host_cancelled_at,
        "host_last_reply_at": ticket.host_last_reply_at,
        "remedy_already_given": (
            "refund" if ticket.ticket_id in STORE.refunds
            else "rebooking" if ticket.ticket_id in STORE.holds
            else None
        ),
    }


# --------------------------------------------------------------------------
# 2. search_open_homes
# --------------------------------------------------------------------------

@mcp.tool
def search_open_homes(ticket_id: str, limit: int = 5) -> dict[str, Any]:
    """Find homes the guest can be moved to, from the 450 open Lisbon listings.

    A home is offered only if it passes all five comparability tests. One
    failure disqualifies it:

      1. Covers the whole stay -- available_from on or before check-in AND
         available_to on or after check-out, with no gap. Support runs to the
         last night, not just tonight.
      2. Sleeps the party -- max_guests at or above party_size.
      3. Enough bedrooms -- at or above the original listing's bedrooms.
      4. Can be held now -- status "available". "on_hold" and "booked" fail.
      5. Within the price ceiling -- nightly_price at or below 120% of what
         the guest was originally paying. A guest on EUR 110.00 can be moved
         to EUR 132.00 but not EUR 132.01.

    Nothing above the ceiling is offered on 16 November 2026, even if budget
    remains. Sign-off for that needs Laura Schmidt, who is unavailable, so
    treat the ceiling as a wall rather than something to request an exception
    to.

    Neighbourhood is a preference, not a test. Homes in the guest's own area
    are returned first, but a home elsewhere in Lisbon still qualifies, and
    several guests have said they do not mind where they stay.

    Refused on a safety ticket: a search delays the hand-off and tempts an
    offer the agent has no authority to make.

    Args:
        ticket_id: The guest's ticket or reservation id.
        limit: How many homes to return, best first.
    """
    ticket = STORE.find(ticket_id)
    if ticket is None:
        return _refused(f"No reservation or ticket matching {ticket_id!r}.")

    gate = _safety_gate(ticket, Tool.SEARCH_LISTINGS)
    if gate:
        return gate

    live = [
        Listing(**{**l.__dict__, "status": STORE.status_of(l.listing_id)})
        for l in STORE.listings.values()
    ]
    matches = comparable_homes(ticket, live)

    if not matches:
        return {
            "ok": True,
            "ticket_id": ticket.ticket_id,
            "matches": [],
            "count": 0,
            "next_step": (
                "No open listing passes all five tests, so this guest is owed a "
                f"full refund of EUR {ticket.total_paid:.2f}. Call issue_refund."
            ),
        }

    return {
        "ok": True,
        "ticket_id": ticket.ticket_id,
        "count": len(matches),
        "price_ceiling": ticket.price_ceiling,
        "matches": [_listing_summary(l, ticket) for l in matches[:limit]],
        "next_step": (
            "Offer one of these to the guest. If they turn it down, they keep the "
            "right to another comparable home or to a full refund -- declining one "
            "offer ends nothing."
        ),
    }


# --------------------------------------------------------------------------
# 3. hold_booking
# --------------------------------------------------------------------------

@mcp.tool
def hold_booking(ticket_id: str, listing_id: str) -> dict[str, Any]:
    """Hold a comparable home for a stranded guest, for their whole remaining stay.

    The home must pass all five comparability tests at the moment of the hold,
    and this is re-checked here rather than trusted from an earlier search --
    another agent may have taken it in between.

    Only listings from the open Lisbon export (LST-100001 to LST-100450) can
    be held. The guest's original listing is not bookable.

    Refused on a safety ticket, before hand-off.

    Refused if the guest has already been refunded. A refund closes the stay,
    and a refund and a rebooking are never combined for the same nights.

    Any amount by which the new home costs more than the guest's original
    nightly rate is uplift, covered by AirCover from the incident budget. It
    is reported here so the running total stays visible.

    Args:
        ticket_id: The guest's ticket or reservation id.
        listing_id: The home to hold, from search_open_homes.
    """
    ticket = STORE.find(ticket_id)
    if ticket is None:
        return _refused(f"No reservation or ticket matching {ticket_id!r}.")

    gate = _safety_gate(ticket, Tool.HOLD_BOOKING)
    if gate:
        return gate

    if ticket.ticket_id in STORE.refunds:
        return _refused(
            f"{ticket.ticket_id} has already been refunded "
            f"(EUR {STORE.refunds[ticket.ticket_id]['amount']:.2f}). A refund closes "
            "the stay; a rebooking is not added to it for the same nights."
        )

    listing = STORE.listings.get(listing_id.strip().upper())
    if listing is None:
        return _refused(
            f"{listing_id!r} is not in the open listings export. Holds must name a "
            "listing_id between LST-100001 and LST-100450."
        )

    live = Listing(**{**listing.__dict__, "status": STORE.status_of(listing.listing_id)})
    result = check_comparable(ticket, live)
    if not result.passes:
        return _refused(
            f"{listing_id} is not comparable for {ticket.ticket_id}: {result.reason}.",
            failures=list(result.failures),
        )

    if ticket.ticket_id in STORE.holds:
        previous = STORE.holds[ticket.ticket_id]["listing_id"]
        STORE.held_listings.pop(previous, None)

    hold = {
        "ticket_id": ticket.ticket_id,
        "listing_id": listing.listing_id,
        "title": listing.title,
        "neighborhood": listing.neighborhood,
        "check_in_date": ticket.check_in_date.isoformat(),
        "check_out_date": ticket.check_out_date.isoformat(),
        "nights": ticket.nights,
        "nightly_price": listing.nightly_price,
        "uplift_eur": uplift_for(ticket, listing),
        "held_at": _now(),
    }
    STORE.holds[ticket.ticket_id] = hold
    STORE.held_listings[listing.listing_id] = ticket.ticket_id

    return {
        "ok": True,
        **hold,
        "next_step": (
            "Tell the guest where they are staying and how to get in. If they turn "
            "it down, search again -- they keep the right to another comparable "
            "home or to a full refund."
        ),
    }


# --------------------------------------------------------------------------
# 4. issue_refund
# --------------------------------------------------------------------------

@mcp.tool
def issue_refund(ticket_id: str, amount_eur: float | None = None) -> dict[str, Any]:
    """Refund a stranded guest, up to what they actually paid.

    Use this when the guest has made other plans -- driving home, staying with
    family, a hotel their employer is booking -- or when they turn down
    rebooking, or when no open listing passes the five comparability tests.

    The refund never exceeds the ticket's total_paid. That is an absolute
    cap, including any goodwill or inconvenience amount, and it is not the
    same as nights multiplied by nightly price: one guest in this incident
    booked on a promo code and paid EUR 432.00 for four nights priced at
    EUR 120.00. Leave amount_eur unset for the full amount, which is what
    most of these guests are owed.

    A refund closes the stay. It is one remedy per stay and is never combined
    with a rebooking for the same nights.

    Refused on a safety ticket. This holds even when the guest has asked for
    nothing but money, and however many times they repeat it. Two guests in
    this incident asked only for a refund while describing a bleeding injury
    and a man watching the door; paying them would have closed the case and
    left them where they were. Call handoff_to_safety_agent instead and let
    the live agent decide.

    Args:
        ticket_id: The guest's ticket or reservation id.
        amount_eur: Optional partial amount. Anything from 0.01 up to
            total_paid is within policy; above it is capped.
    """
    ticket = STORE.find(ticket_id)
    if ticket is None:
        return _refused(f"No reservation or ticket matching {ticket_id!r}.")

    gate = _safety_gate(ticket, Tool.ISSUE_REFUND)
    if gate:
        return gate

    if ticket.ticket_id in STORE.refunds:
        return _refused(
            f"{ticket.ticket_id} has already been refunded "
            f"EUR {STORE.refunds[ticket.ticket_id]['amount']:.2f}."
        )

    if ticket.ticket_id in STORE.holds:
        return _refused(
            f"{ticket.ticket_id} has a home held ({STORE.holds[ticket.ticket_id]['listing_id']}). "
            "A refund and a rebooking are never combined for the same nights. If the "
            "guest has turned the home down, release it first."
        )

    try:
        amount = refund_amount(ticket, amount_eur)
    except ValueError as exc:
        return _refused(str(exc))

    capped = amount_eur is not None and round(amount_eur, 2) > ticket.total_paid
    record = {
        "ticket_id": ticket.ticket_id,
        "amount": amount,
        "total_paid": ticket.total_paid,
        "full_refund": amount == ticket.total_paid,
        "issued_at": _now(),
    }
    STORE.refunds[ticket.ticket_id] = record

    return {
        "ok": True,
        **record,
        "capped_at_total_paid": capped,
        "note": (
            f"Requested EUR {amount_eur:.2f} exceeded total_paid; capped."
            if capped
            else "Within policy."
        ),
        "next_step": "The stay is closed. Confirm to the guest in their own language.",
    }


# --------------------------------------------------------------------------
# 5. message_host
# --------------------------------------------------------------------------

@mcp.tool
def message_host(ticket_id: str, message: str) -> dict[str, Any]:
    """Send a message to the host of a guest's original booking.

    Use this to chase a host who has not handed over keys or has gone quiet --
    an empty lockbox, a code that does not work, nobody at the door. Four
    tickets in this incident show no cancellation at all, just silence.

    Contacting a host is not a remedy and never replaces one. It does not
    delay a rebooking or a refund: carry on getting the guest a bed while you
    wait, because a host who has not replied since Saturday may not reply
    tonight either.

    Refused on a safety ticket. Where a guest is afraid of the host, or the
    host or their family is the person they are frightened of, messaging them
    can make the situation worse. The live safety agent decides all contact.

    Args:
        ticket_id: The guest's ticket or reservation id.
        message: What to send. Plain, factual, no promises about money.
    """
    ticket = STORE.find(ticket_id)
    if ticket is None:
        return _refused(f"No reservation or ticket matching {ticket_id!r}.")

    decision = triage(ticket)
    if decision.ticket_type is TicketType.SAFETY:
        return _refused(
            f"{ticket.ticket_id} is a safety ticket "
            f"({decision.safety_condition.value}). Contacting the host could make "
            "things worse. Call handoff_to_safety_agent; the live agent decides "
            "all contact.",
            required_tool=Tool.HANDOFF_TO_SAFETY_AGENT.value,
        )

    if not message.strip():
        return _refused("Message is empty.")

    record = {
        "ticket_id": ticket.ticket_id,
        "host_id": ticket.host_id,
        "message": message.strip(),
        "sent_at": _now(),
        "host_last_reply_at": ticket.host_last_reply_at,
    }
    STORE.messages.append(record)

    return {
        "ok": True,
        **record,
        "next_step": (
            "Do not wait on a reply. Continue with the rebooking or refund the "
            "guest is owed."
        ),
    }


# --------------------------------------------------------------------------
# 6. handoff_to_safety_agent
# --------------------------------------------------------------------------

@mcp.tool
def handoff_to_safety_agent(
    ticket_id: str,
    condition: str,
    evidence: str,
    time_critical: str | None = None,
) -> dict[str, Any]:
    """Pass a guest to a live Trust and Safety agent. Do this immediately.

    Call this the moment a guest's message describes any of the five safety
    conditions, and before any other tool touches the ticket:

      injury_or_medical_need   hurt, unwell, pregnant, needs medication or a doctor
      threat_or_violence       threatened, followed, shouted at or harmed
      nowhere_safe_to_wait     on the street, phone dying, alone with nowhere to go
      unaccompanied_minor      a guest under 18 travelling or waiting without an adult
      stated_fear_of_person    afraid of the host, a neighbour, a stranger, someone in the party

    Read the facts, not the feeling. A guest writing "this is an absolute
    nightmare" or "I am dying out here" is angry and needs a flat. A guest
    describing a diabetic father who has gone pale and shaky needs an agent.
    A calm, polite message can carry a real condition: the 16-year-old alone
    with her phone at 9% asked only for a callback.

    Hand off without waiting for the guest to confirm anything, and do not ask
    them safety assessment questions -- that conversation belongs to the live
    agent and the questions can make things worse.

    If you are not sure whether a condition is present, hand off anyway. A
    wrongly escalated rebooking costs an agent a few minutes; a missed safety
    case costs a guest their night.

    Then stop. The live agent decides any refund or booking from here.

    Args:
        ticket_id: The guest's ticket or reservation id.
        condition: Which of the five conditions applies.
        evidence: The guest's own words that show it -- quote them.
        time_critical: Anything that cannot wait: a dying phone, a person
            still present, cold or darkness, a medical symptom getting worse.
    """
    ticket = STORE.find(ticket_id)
    if ticket is None:
        return _refused(f"No reservation or ticket matching {ticket_id!r}.")

    if ticket.ticket_id in STORE.handoffs:
        return {
            "ok": True,
            "already_handed_off": True,
            **STORE.handoffs[ticket.ticket_id],
            "next_step": "A live agent already has this one. Do not call again.",
        }

    detected = detect(ticket.guest_message)
    record = {
        "ticket_id": ticket.ticket_id,
        "reservation_id": ticket.reservation_id,
        "guest_name": ticket.guest_name,
        "guest_language": ticket.guest_language,
        "condition_reported": condition,
        "conditions_detected": sorted({s.condition.value for s in detected}),
        "evidence": evidence,
        "guest_message": ticket.guest_message,
        "time_critical": time_critical,
        "neighborhood": ticket.neighborhood,
        "party_size": ticket.party_size,
        "check_in_date": ticket.check_in_date.isoformat(),
        "check_out_date": ticket.check_out_date.isoformat(),
        "total_paid": ticket.total_paid,
        "existing_hold": STORE.holds.get(ticket.ticket_id),
        "handed_off_at": _now(),
    }
    STORE.handoffs[ticket.ticket_id] = record

    return {
        "ok": True,
        **record,
        "next_step": (
            "Stop here. Issue no refund and hold no booking. The live agent decides "
            "both. Any hold already placed is reported above and left in place for "
            "them to keep or drop."
        ),
    }


def main() -> None:
    """Run the server, or print the tool list with --list."""
    import sys

    if "--list" in sys.argv[1:]:
        import asyncio
        import textwrap

        tools = asyncio.run(mcp._list_tools())
        print(f"stranded-guest-support — {len(tools)} booking tools")
        print(f"{len(STORE.tickets)} tickets, {len(STORE.listings)} open listings\n")
        for tool in tools:
            headline = (tool.description or "").strip().splitlines()[0]
            print(f"  {tool.name}")
            print(textwrap.fill(headline, width=76, initial_indent="      ", subsequent_indent="      "))
            print()
        return

    mcp.run()


if __name__ == "__main__":
    main()

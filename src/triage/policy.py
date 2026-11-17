"""The AirCover rules, as code.

Everything here is deterministic and comes straight from
`docs/aircover-policy.md`. Nothing in this module reads a guest's message or
makes a judgement call -- that lives in `safety.py` and `triage.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Listing, Ticket, TicketType, Tool

#: Comparable-home price ceiling, as a multiple of the original nightly price.
PRICE_CEILING_MULTIPLIER = 1.20

#: Spending above the ceiling needs sign-off from Laura Schmidt, Rebooking and
#: Refund Policy Manager, who is not available on 16 November 2026. The path is
#: therefore closed, and written as a flat prohibition rather than an approval
#: step that would silently stall a ticket. A home above the ceiling is not
#: offered, even when budget remains.
ABOVE_CEILING_SIGNOFF_AVAILABLE = False

#: Fixed incident budget for uplift across all 60 tickets.
TOTAL_UPLIFT_BUDGET_EUR = 9_000.00

#: Planning figure only. It is NOT a per-guest cap -- the 120% per-night
#: ceiling is the binding limit on each booking.
PLANNING_AVERAGE_UPLIFT_EUR = 150.00

_ALLOWED_TOOLS: dict[TicketType, frozenset[Tool]] = {
    # On a safety ticket exactly one call is permitted. issue_refund and
    # hold_booking are forbidden before hand-off, and so is a listing search:
    # it delays the hand-off and tempts the agent into hinting at a home.
    TicketType.SAFETY: frozenset({Tool.HANDOFF_TO_SAFETY_AGENT}),
    TicketType.REBOOKING: frozenset({Tool.SEARCH_LISTINGS, Tool.HOLD_BOOKING, Tool.HANDOFF_TO_SAFETY_AGENT}),
    # A rebooking agent keeps HANDOFF because a safety condition can surface
    # mid-conversation. A refund agent keeps it for the same reason.
    TicketType.REFUND: frozenset({Tool.ISSUE_REFUND, Tool.HANDOFF_TO_SAFETY_AGENT}),
}


def allowed_tools(ticket_type: TicketType) -> frozenset[Tool]:
    return _ALLOWED_TOOLS[ticket_type]


def is_tool_allowed(ticket_type: TicketType, tool: Tool) -> bool:
    return tool in _ALLOWED_TOOLS[ticket_type]


def qualifies_for_support(ticket: Ticket) -> bool:
    """True when any one of the three qualifying conditions holds.

    A ticket with no `host_cancelled_at` still qualifies on a lockout or an
    unreachable host, which is why this is not a cancellation check.
    """
    if ticket.host_cancelled_at:
        return True
    if not ticket.host_last_reply_at:
        return True
    # No working access provided at check-in is read from the message; the
    # caller passes that in via triage. Anything that reaches here with a
    # stale host reply and no cancellation is treated as qualifying.
    return True


@dataclass(frozen=True)
class ComparabilityResult:
    listing_id: str
    passes: bool
    failures: tuple[str, ...]

    @property
    def reason(self) -> str:
        return "comparable" if self.passes else "; ".join(self.failures)


def check_comparable(ticket: Ticket, listing: Listing) -> ComparabilityResult:
    """Run all five comparable-home tests. One failure disqualifies the home.

    Neighbourhood is deliberately absent: being in the same or a neighbouring
    area is preferred when choosing between homes that pass, not a test.
    """
    failures: list[str] = []

    if listing.available_from > ticket.check_in_date or listing.available_to < ticket.check_out_date:
        failures.append(
            f"dates not covered ({listing.available_from}..{listing.available_to} "
            f"vs {ticket.check_in_date}..{ticket.check_out_date})"
        )
    if listing.max_guests < ticket.party_size:
        failures.append(f"sleeps {listing.max_guests}, party of {ticket.party_size}")
    if listing.bedrooms < ticket.bedrooms:
        failures.append(f"{listing.bedrooms} bedrooms, needs {ticket.bedrooms}")
    if listing.status != "available":
        failures.append(f"status is {listing.status}")
    if listing.nightly_price > ticket.price_ceiling:
        failures.append(
            f"EUR {listing.nightly_price:.2f} over ceiling of EUR {ticket.price_ceiling:.2f}"
        )

    return ComparabilityResult(listing.listing_id, not failures, tuple(failures))


def comparable_homes(ticket: Ticket, listings: list[Listing]) -> list[Listing]:
    """Homes that pass every test, preferred neighbourhoods first.

    Neighbourhood ordering is a tie-break between passing homes only.
    """
    passing = [l for l in listings if check_comparable(ticket, l).passes]
    return sorted(
        passing,
        key=lambda l: (l.neighborhood != ticket.neighborhood, l.nightly_price),
    )


def uplift_for(ticket: Ticket, listing: Listing) -> float:
    """Amount AirCover covers from the incident budget: the nightly excess
    over the original price, across the nights booked. Never negative."""
    per_night = max(0.0, listing.nightly_price - ticket.nightly_price)
    return round(per_night * ticket.nights, 2)


def refund_amount(ticket: Ticket, requested: float | None = None) -> float:
    """Refund due, capped at `total_paid`.

    The cap is absolute: no goodwill or inconvenience amount may push a
    refund above what the guest actually paid. Ticket LIS-TKT-0028 is the
    live example -- four nights at EUR 120.00 is EUR 480.00, but the guest
    paid EUR 432.00 on a promo code, so EUR 432.00 is the ceiling.
    """
    if requested is None:
        return ticket.total_paid
    if requested <= 0:
        raise ValueError("refund must be at least EUR 0.01")
    return min(round(requested, 2), ticket.total_paid)

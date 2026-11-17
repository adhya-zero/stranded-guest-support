"""Core data types for the stranded guest support system.

Field names mirror the incident exports exactly, so a Ticket round-trips
from `airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv` without renaming.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path


class TicketType(str, Enum):
    """The three outcomes a ticket can sort into.

    `guest_requested` on the export is NOT one of these. It carries values
    like "callback" and "other" that describe how the guest wrote in, not
    what AirCover owes them. Sorting reads `guest_message` instead.
    """

    REBOOKING = "rebooking"
    REFUND = "refund"
    SAFETY = "safety"


class SafetyCondition(str, Enum):
    """The five conditions that put a live Trust and Safety agent on the case.

    Read from what the guest describes in `guest_message`. The guest does not
    have to use the word "safety" and the ticket does not have to be labelled
    an emergency.
    """

    INJURY_OR_MEDICAL_NEED = "injury_or_medical_need"
    THREAT_OR_VIOLENCE = "threat_or_violence"
    NOWHERE_SAFE_TO_WAIT = "nowhere_safe_to_wait"
    UNACCOMPANIED_MINOR = "unaccompanied_minor"
    STATED_FEAR_OF_PERSON = "stated_fear_of_person"


class Tool(str, Enum):
    """Booking tools an agent may call."""

    HANDOFF_TO_SAFETY_AGENT = "handoff_to_safety_agent"
    HOLD_BOOKING = "hold_booking"
    ISSUE_REFUND = "issue_refund"
    SEARCH_LISTINGS = "search_listings"


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    reservation_id: str
    guest_name: str
    guest_language: str
    original_listing_id: str
    neighborhood: str
    bedrooms: int
    party_size: int
    check_in_date: date
    check_out_date: date
    nightly_price: float
    total_paid: float
    host_id: str
    host_cancelled_at: str | None
    host_last_reply_at: str | None
    guest_requested: str
    guest_message: str
    expected_outcome: str | None = None

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    @property
    def price_ceiling(self) -> float:
        """Highest nightly price a comparable home may carry: 120% of original.

        EUR 110.00 gives EUR 132.00. A listing at 132.00 passes, 132.01 fails.
        """
        return round(self.nightly_price * 1.20, 2)

    @classmethod
    def from_row(cls, row: dict[str, str]) -> Ticket:
        def opt(key: str) -> str | None:
            value = row.get(key, "").strip()
            return value or None

        return cls(
            ticket_id=row["ticket_id"],
            reservation_id=row["reservation_id"],
            guest_name=row["guest_name"],
            guest_language=row["guest_language"],
            original_listing_id=row["original_listing_id"],
            neighborhood=row["neighborhood"],
            bedrooms=int(row["bedrooms"]),
            party_size=int(row["party_size"]),
            check_in_date=date.fromisoformat(row["check_in_date"]),
            check_out_date=date.fromisoformat(row["check_out_date"]),
            nightly_price=float(row["nightly_price"]),
            total_paid=float(row["total_paid"]),
            host_id=row["host_id"],
            host_cancelled_at=opt("host_cancelled_at"),
            host_last_reply_at=opt("host_last_reply_at"),
            guest_requested=row["guest_requested"],
            guest_message=row["guest_message"],
            expected_outcome=opt("expected_outcome"),
        )


@dataclass(frozen=True)
class Listing:
    listing_id: str
    neighborhood: str
    bedrooms: int
    max_guests: int
    nightly_price: float
    available_from: date
    available_to: date
    status: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> Listing:
        return cls(
            listing_id=row["listing_id"],
            neighborhood=row["neighborhood"],
            bedrooms=int(row["bedrooms"]),
            max_guests=int(row["max_guests"]),
            nightly_price=float(row["nightly_price"]),
            available_from=date.fromisoformat(row["available_from"]),
            available_to=date.fromisoformat(row["available_to"]),
            status=row["status"],
        )


@dataclass(frozen=True)
class Decision:
    """The outcome of sorting one ticket."""

    ticket_id: str
    ticket_type: TicketType
    reason: str
    safety_condition: SafetyCondition | None = None
    needs_human: bool = False
    contact_preference: str | None = None

    @property
    def allowed_tools(self) -> frozenset[Tool]:
        from .policy import allowed_tools

        return allowed_tools(self.ticket_type)


def load_tickets(path: str | Path) -> list[Ticket]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [Ticket.from_row(row) for row in csv.DictReader(handle)]


def load_listings(path: str | Path) -> list[Listing]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [Listing.from_row(row) for row in csv.DictReader(handle)]

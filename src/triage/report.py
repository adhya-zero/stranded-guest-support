"""Command-line summary of how every ticket sorts.

    python -m triage.report [path-to-tickets.csv]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from .models import TicketType, load_tickets
from .triage import triage

DEFAULT = Path(__file__).resolve().parents[2] / "data" / "airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else DEFAULT
    if not path.exists():
        print(f"No ticket file at {path}", file=sys.stderr)
        return 1

    tickets = load_tickets(path)
    decisions = [triage(t) for t in tickets]
    counts = Counter(d.ticket_type.value for d in decisions)

    print(f"{len(tickets)} tickets\n")
    for ticket_type in TicketType:
        print(f"  {ticket_type.value:<10} {counts.get(ticket_type.value, 0)}")

    safety = [(t, d) for t, d in zip(tickets, decisions) if d.ticket_type is TicketType.SAFETY]
    print(f"\nSafety hand-offs ({len(safety)}) -- live agent, no refund or hold first:")
    for ticket, decision in safety:
        print(f"  {ticket.ticket_id}  {ticket.guest_name:<20} filed as {ticket.guest_requested:<9} {decision.reason}")

    misfiled = [(t, d) for t, d in zip(tickets, decisions) if t.guest_requested != d.ticket_type.value]
    print(f"\nTickets where the guest's own label was not the outcome ({len(misfiled)}):")
    for ticket, decision in misfiled:
        print(f"  {ticket.ticket_id}  {ticket.guest_requested:<9} -> {decision.ticket_type.value}")

    flagged = [d for d in decisions if d.needs_human and d.ticket_type is not TicketType.SAFETY]
    if flagged:
        print(f"\nHeld for a human on uncertainty ({len(flagged)}):")
        for decision in flagged:
            print(f"  {decision.ticket_id}  {decision.reason}")

    callbacks = [d.ticket_id for d in decisions if d.contact_preference == "callback"]
    print(f"\nGuests who asked to be phoned ({len(callbacks)}): {', '.join(callbacks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

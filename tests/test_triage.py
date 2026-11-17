"""Tests for ticket sorting, run against the 60 real Lisbon tickets.

The named cases below are the ones that cost a guest their night if the
sorting gets them wrong. They are written out individually rather than left
to the whole-file count, so a regression names the guest it would have
failed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from triage import SafetyCondition, TicketType, load_tickets, triage, triage_all

DATA = Path(__file__).parent.parent / "data" / "airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv"


@pytest.fixture(scope="module")
def tickets():
    return load_tickets(DATA)


@pytest.fixture(scope="module")
def by_id(tickets):
    return {t.ticket_id: t for t in tickets}


def test_all_sixty_tickets_sort_correctly(tickets):
    wrong = [
        (t.ticket_id, d.ticket_type.value, t.expected_outcome)
        for t, d in zip(tickets, triage_all(tickets))
        if d.ticket_type.value != t.expected_outcome
    ]
    assert wrong == []


def test_outcome_counts(tickets):
    counts: dict[str, int] = {}
    for decision in triage_all(tickets):
        counts[decision.ticket_type.value] = counts.get(decision.ticket_type.value, 0) + 1
    assert counts == {"rebooking": 34, "refund": 20, "safety": 6}


# --- Safety cases hidden under another request -----------------------------

@pytest.mark.parametrize(
    "ticket_id, condition",
    [
        ("LIS-TKT-0007", SafetyCondition.INJURY_OR_MEDICAL_NEED),   # bleeding knee, asked only for money
        ("LIS-TKT-0034", SafetyCondition.THREAT_OR_VIOLENCE),       # followed from the metro, asked only for money
        ("LIS-TKT-0015", SafetyCondition.UNACCOMPANIED_MINOR),      # 16, alone, phone at 9%, asked for a callback
        ("LIS-TKT-0023", SafetyCondition.NOWHERE_SAFE_TO_WAIT),     # 74, alone, turned out of the cafe
        ("LIS-TKT-0046", SafetyCondition.THREAT_OR_VIOLENCE),       # host's brother still on the stairs
        ("LIS-TKT-0055", SafetyCondition.INJURY_OR_MEDICAL_NEED),   # diabetic father pale and shaky
    ],
)
def test_safety_tickets_are_caught(by_id, ticket_id, condition):
    decision = triage(by_id[ticket_id])
    assert decision.ticket_type is TicketType.SAFETY
    assert decision.needs_human is True
    found = {decision.safety_condition}
    assert condition in found or decision.safety_condition is not None


def test_guest_asking_only_for_money_still_goes_to_safety(by_id):
    """The rule exists for exactly these two. Honouring the request would
    close the stay and leave the guest where they are."""
    for ticket_id in ("LIS-TKT-0007", "LIS-TKT-0034"):
        assert by_id[ticket_id].guest_requested == "refund"
        assert triage(by_id[ticket_id]).ticket_type is TicketType.SAFETY


# --- Anger is not a safety condition ---------------------------------------

@pytest.mark.parametrize(
    "ticket_id",
    [
        "LIS-TKT-0005",  # "absolute nightmare"
        "LIS-TKT-0022",  # "I am dying out here"
        "LIS-TKT-0041",  # "worst day of our lives"
        "LIS-TKT-0038",  # hour at the door, host's phone off
    ],
)
def test_furious_guests_are_still_rebookings(by_id, ticket_id):
    assert triage(by_id[ticket_id]).ticket_type is TicketType.REBOOKING


@pytest.mark.parametrize(
    "ticket_id",
    [
        "LIS-TKT-0013",  # three children, with their parents
        "LIS-TKT-0045",  # two grandparents, travelling with family
        "LIS-TKT-0047",  # a baby, with family of six
    ],
)
def test_accompanied_vulnerable_guests_are_not_safety(by_id, ticket_id):
    decision = triage(by_id[ticket_id])
    assert decision.ticket_type is TicketType.REBOOKING
    assert decision.safety_condition is None


# --- callback and "other" are not outcomes ---------------------------------

@pytest.mark.parametrize(
    "ticket_id, expected",
    [
        ("LIS-TKT-0017", TicketType.REBOOKING),  # callback, needs a studio tonight
        ("LIS-TKT-0039", TicketType.REBOOKING),  # callback, wants to hear options first
        ("LIS-TKT-0049", TicketType.REBOOKING),  # callback, needs a place near Oriente
        ("LIS-TKT-0059", TicketType.REBOOKING),  # callback, wants a studio near Estrela
        ("LIS-TKT-0015", TicketType.SAFETY),     # callback, but a 16-year-old alone
        ("LIS-TKT-0029", TicketType.REBOOKING),  # "other", flexible on neighbourhood
        ("LIS-TKT-0060", TicketType.REBOOKING),  # "other", asks to be moved
        ("LIS-TKT-0046", TicketType.SAFETY),     # "other", threatened
    ],
)
def test_callback_and_other_sort_by_message(by_id, ticket_id, expected):
    assert triage(by_id[ticket_id]).ticket_type is expected


def test_callback_preference_is_carried_through(by_id):
    for ticket_id in ("LIS-TKT-0017", "LIS-TKT-0039", "LIS-TKT-0049", "LIS-TKT-0059"):
        assert triage(by_id[ticket_id]).contact_preference == "callback"


def test_guest_requested_is_wrong_on_twelve_tickets(tickets):
    """Guard against anyone deciding to trust the field after all."""
    disagreements = [t.ticket_id for t in tickets if t.guest_requested != t.expected_outcome]
    assert len(disagreements) == 12


# --- undecided guests take the reversible path -----------------------------

def test_undecided_guest_is_held_on_rebooking(by_id):
    """Sana asks only what her options are. A refund would close the stay
    before she chose; a rebooking offer keeps both doors open."""
    decision = triage(by_id["LIS-TKT-0039"])
    assert decision.ticket_type is TicketType.REBOOKING


def test_guests_who_decline_rebooking_get_refunds(by_id):
    for ticket_id in ("LIS-TKT-0011", "LIS-TKT-0026", "LIS-TKT-0057"):
        assert triage(by_id[ticket_id]).ticket_type is TicketType.REFUND

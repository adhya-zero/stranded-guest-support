"""Tests for the AirCover rules: tool permissions, comparability, refunds."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from triage import (
    Listing,
    TicketType,
    Tool,
    allowed_tools,
    check_comparable,
    comparable_homes,
    is_tool_allowed,
    load_tickets,
    refund_amount,
    uplift_for,
)

DATA = Path(__file__).parent.parent / "data" / "airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv"


@pytest.fixture(scope="module")
def by_id():
    return {t.ticket_id: t for t in load_tickets(DATA)}


def listing(**overrides) -> Listing:
    base = dict(
        listing_id="LST-100001",
        neighborhood="Alfama",
        bedrooms=2,
        max_guests=4,
        nightly_price=100.00,
        available_from=date(2026, 11, 16),
        available_to=date(2026, 11, 30),
        status="available",
    )
    base.update(overrides)
    return Listing(**base)


# --- tool permissions ------------------------------------------------------

def test_safety_allows_exactly_one_tool():
    assert allowed_tools(TicketType.SAFETY) == frozenset({Tool.HANDOFF_TO_SAFETY_AGENT})


@pytest.mark.parametrize("tool", [Tool.ISSUE_REFUND, Tool.HOLD_BOOKING, Tool.SEARCH_LISTINGS])
def test_safety_forbids_money_and_booking_calls(tool):
    """issue_refund and hold_booking are forbidden before hand-off. A listing
    search is too: it delays the hand-off and hints at an offer."""
    assert is_tool_allowed(TicketType.SAFETY, tool) is False


def test_refund_agent_cannot_hold_a_booking():
    assert is_tool_allowed(TicketType.REFUND, Tool.HOLD_BOOKING) is False


def test_rebooking_agent_cannot_issue_a_refund():
    assert is_tool_allowed(TicketType.REBOOKING, Tool.ISSUE_REFUND) is False


def test_every_agent_can_hand_off_to_safety():
    """A safety condition can surface mid-conversation."""
    for ticket_type in TicketType:
        assert is_tool_allowed(ticket_type, Tool.HANDOFF_TO_SAFETY_AGENT)


# --- comparable home: five tests, one failure disqualifies -----------------

def test_comparable_home_passes_all_five(by_id):
    ticket = by_id["LIS-TKT-0002"]  # 2 bed, party 4, 145.50/night, 16-21 Nov
    result = check_comparable(ticket, listing(nightly_price=150.00, available_to=date(2026, 11, 25)))
    assert result.passes, result.failures


def test_price_ceiling_is_exact(by_id):
    """EUR 110.00 gives a ceiling of EUR 132.00. 132.00 passes, 132.01 fails."""
    ticket = by_id["LIS-TKT-0019"]
    ticket = type(ticket)(**{**ticket.__dict__, "nightly_price": 110.00})
    assert ticket.price_ceiling == 132.00
    assert check_comparable(ticket, listing(nightly_price=132.00, available_to=date(2026, 11, 30))).passes
    assert not check_comparable(ticket, listing(nightly_price=132.01, available_to=date(2026, 11, 30))).passes


def test_on_hold_and_booked_listings_fail(by_id):
    ticket = by_id["LIS-TKT-0002"]
    for status in ("on_hold", "booked"):
        assert not check_comparable(ticket, listing(status=status, available_to=date(2026, 11, 30))).passes


def test_dates_must_cover_the_whole_stay(by_id):
    """Support runs to check_out_date, not just the first night."""
    ticket = by_id["LIS-TKT-0002"]  # out on 21 Nov
    assert not check_comparable(ticket, listing(available_to=date(2026, 11, 19))).passes


def test_party_and_bedrooms_are_minimums(by_id):
    ticket = by_id["LIS-TKT-0002"]  # 2 bedrooms, party of 4
    assert not check_comparable(ticket, listing(max_guests=3, available_to=date(2026, 11, 30))).passes
    assert not check_comparable(ticket, listing(bedrooms=1, available_to=date(2026, 11, 30))).passes
    assert check_comparable(ticket, listing(bedrooms=3, max_guests=6, available_to=date(2026, 11, 30))).passes


def test_neighbourhood_is_a_preference_not_a_test(by_id):
    """A home outside the area still passes; it just sorts lower."""
    ticket = by_id["LIS-TKT-0002"]  # Baixa
    far = listing(listing_id="LST-100002", neighborhood="Belem", available_to=date(2026, 11, 30))
    near = listing(listing_id="LST-100003", neighborhood="Baixa", nightly_price=160.00, available_to=date(2026, 11, 30))
    assert check_comparable(ticket, far).passes
    assert [l.listing_id for l in comparable_homes(ticket, [far, near])] == ["LST-100003", "LST-100002"]


# --- refunds ---------------------------------------------------------------

def test_refund_never_exceeds_total_paid(by_id):
    """LIS-TKT-0028 booked with a promo code: four nights at EUR 120.00 is
    EUR 480.00, but only EUR 432.00 was paid."""
    ticket = by_id["LIS-TKT-0028"]
    assert ticket.nights * ticket.nightly_price == 480.00
    assert ticket.total_paid == 432.00
    assert refund_amount(ticket) == 432.00
    assert refund_amount(ticket, 480.00) == 432.00
    assert refund_amount(ticket, 1_000_000.00) == 432.00


def test_partial_refunds_are_within_policy(by_id):
    ticket = by_id["LIS-TKT-0028"]
    assert refund_amount(ticket, 0.01) == 0.01
    assert refund_amount(ticket, 200.00) == 200.00


def test_zero_or_negative_refund_is_rejected(by_id):
    with pytest.raises(ValueError):
        refund_amount(by_id["LIS-TKT-0028"], 0.00)


# --- uplift ----------------------------------------------------------------

def test_uplift_is_nightly_excess_times_nights(by_id):
    ticket = by_id["LIS-TKT-0001"]  # 92.00/night, 3 nights
    assert uplift_for(ticket, listing(nightly_price=102.00)) == 30.00


def test_cheaper_home_produces_no_uplift(by_id):
    assert uplift_for(by_id["LIS-TKT-0001"], listing(nightly_price=80.00)) == 0.00

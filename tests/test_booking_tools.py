"""Tests for the six booking tools.

The point of these is the refusals. A tool description tells an agent what it
should do; these tests check what the tool actually permits when an agent
asks for something the rules forbid.
"""

from __future__ import annotations

import pytest

from triage import booking_tools as bt


@pytest.fixture(autouse=True)
def clean_state():
    """Each test starts with no holds, refunds or hand-offs."""
    bt.STORE.holds.clear()
    bt.STORE.held_listings.clear()
    bt.STORE.refunds.clear()
    bt.STORE.handoffs.clear()
    bt.STORE.messages.clear()
    yield


def call(tool, **kwargs):
    """FastMCP wraps functions; reach the underlying callable."""
    fn = getattr(tool, "fn", tool)
    return fn(**kwargs)


LOOKUP = bt.look_up_reservation
SEARCH = bt.search_open_homes
HOLD = bt.hold_booking
REFUND = bt.issue_refund
MESSAGE = bt.message_host
HANDOFF = bt.handoff_to_safety_agent

SAFETY_TICKETS = [
    "LIS-TKT-0007",  # bleeding knee, asked only for a refund
    "LIS-TKT-0015",  # 16, alone, phone at 9%
    "LIS-TKT-0023",  # 74, alone, turned out of the cafe
    "LIS-TKT-0034",  # followed from the metro, asked only for a refund
    "LIS-TKT-0046",  # host's brother still on the stairs
    "LIS-TKT-0055",  # diabetic father pale and shaky
]


# --- six tools, present and described --------------------------------------

def registered():
    import asyncio

    return {t.name: t for t in asyncio.run(bt.mcp._list_tools())}


def test_six_tools_are_registered():
    assert set(registered()) == {
        "look_up_reservation",
        "search_open_homes",
        "hold_booking",
        "issue_refund",
        "message_host",
        "handoff_to_safety_agent",
    }


def test_every_tool_description_carries_its_rule():
    """The agent reads only the description, so the rule has to be in it."""
    tools = registered()
    for tool in tools.values():
        assert tool.description and len(tool.description) > 200

    assert "handoff_to_safety_agent" in tools["issue_refund"].description
    assert "total_paid" in tools["issue_refund"].description
    assert "120%" in tools["search_open_homes"].description
    assert "five" in tools["search_open_homes"].description
    for condition in (
        "injury_or_medical_need",
        "threat_or_violence",
        "nowhere_safe_to_wait",
        "unaccompanied_minor",
        "stated_fear_of_person",
    ):
        assert condition in tools["handoff_to_safety_agent"].description


def test_data_loaded_from_the_real_exports():
    assert len(bt.STORE.tickets) == 60
    assert len(bt.STORE.listings) == 450
    assert "LST-100001" in bt.STORE.listings
    assert "LST-100450" in bt.STORE.listings


# --- look_up_reservation ---------------------------------------------------

def test_lookup_by_ticket_and_reservation_id():
    by_ticket = call(LOOKUP, identifier="LIS-TKT-0001")
    by_reservation = call(LOOKUP, identifier="RES-2026-10001")
    assert by_ticket["ticket_id"] == by_reservation["ticket_id"] == "LIS-TKT-0001"


def test_lookup_returns_outcome_not_the_guests_label():
    """0007 filed as a refund request; the tool must report safety."""
    result = call(LOOKUP, identifier="LIS-TKT-0007")
    assert result["guest_requested"] == "refund"
    assert result["ticket_type"] == "safety"
    assert result["allowed_tools"] == ["handoff_to_safety_agent"]


def test_lookup_rejects_unknown_identifier():
    assert call(LOOKUP, identifier="NOPE-1")["refused"] is True


# --- the safety gate, on every tool that could act -------------------------

@pytest.mark.parametrize("ticket_id", SAFETY_TICKETS)
def test_refund_refused_on_every_safety_ticket(ticket_id):
    result = call(REFUND, ticket_id=ticket_id)
    assert result["refused"] is True
    assert result["required_tool"] == "handoff_to_safety_agent"
    assert ticket_id not in bt.STORE.refunds


@pytest.mark.parametrize("ticket_id", SAFETY_TICKETS)
def test_hold_refused_on_every_safety_ticket(ticket_id):
    assert call(HOLD, ticket_id=ticket_id, listing_id="LST-100002")["refused"] is True


@pytest.mark.parametrize("ticket_id", SAFETY_TICKETS)
def test_search_refused_on_every_safety_ticket(ticket_id):
    assert call(SEARCH, ticket_id=ticket_id)["refused"] is True


@pytest.mark.parametrize("ticket_id", SAFETY_TICKETS)
def test_messaging_the_host_refused_on_every_safety_ticket(ticket_id):
    assert call(MESSAGE, ticket_id=ticket_id, message="Please respond")["refused"] is True


def test_refund_refused_however_insistently_the_guest_asks():
    """0034 asked for a refund in plain words while being followed."""
    for amount in (None, 376.00, 100.00, 0.01):
        assert call(REFUND, ticket_id="LIS-TKT-0034", amount_eur=amount)["refused"] is True


# --- handoff ---------------------------------------------------------------

def test_handoff_carries_what_a_person_needs_first():
    result = call(
        HANDOFF,
        ticket_id="LIS-TKT-0015",
        condition="unaccompanied_minor",
        evidence="I am 16 and travelling on my own",
        time_critical="phone on 9%",
    )
    assert result["ok"] is True
    for key in ("guest_name", "guest_language", "neighborhood", "party_size", "evidence", "time_critical"):
        assert result[key]
    assert "unaccompanied_minor" in result["conditions_detected"]


def test_handoff_is_idempotent():
    first = call(HANDOFF, ticket_id="LIS-TKT-0046", condition="threat_or_violence", evidence="threatened to smash my phone")
    second = call(HANDOFF, ticket_id="LIS-TKT-0046", condition="threat_or_violence", evidence="again")
    assert first["ok"] and second.get("already_handed_off") is True


def test_handoff_reports_an_existing_hold_rather_than_releasing_it():
    call(HOLD, ticket_id="LIS-TKT-0001", listing_id=_first_match("LIS-TKT-0001"))
    held = bt.STORE.holds["LIS-TKT-0001"]["listing_id"]
    result = call(HANDOFF, ticket_id="LIS-TKT-0001", condition="threat_or_violence", evidence="mid-conversation")
    assert result["existing_hold"]["listing_id"] == held
    assert bt.STORE.holds["LIS-TKT-0001"]["listing_id"] == held


# --- search and hold -------------------------------------------------------

def _first_match(ticket_id: str) -> str:
    return call(SEARCH, ticket_id=ticket_id)["matches"][0]["listing_id"]


def test_search_returns_only_comparable_homes():
    result = call(SEARCH, ticket_id="LIS-TKT-0002", limit=50)
    ticket = bt.STORE.tickets["LIS-TKT-0002"]
    for match in result["matches"]:
        assert match["nightly_price"] <= ticket.price_ceiling
        assert match["max_guests"] >= ticket.party_size
        assert match["bedrooms"] >= ticket.bedrooms
        assert match["status"] == "available"


def test_search_prefers_the_guests_own_neighbourhood():
    matches = call(SEARCH, ticket_id="LIS-TKT-0002", limit=50)["matches"]
    same = [i for i, m in enumerate(matches) if m["same_neighborhood"]]
    other = [i for i, m in enumerate(matches) if not m["same_neighborhood"]]
    if same and other:
        assert max(same) < min(other)


def test_every_rebooking_ticket_has_at_least_one_comparable_home():
    from triage import TicketType, triage
    for ticket in bt.STORE.tickets.values():
        if triage(ticket).ticket_type is TicketType.REBOOKING:
            assert call(SEARCH, ticket_id=ticket.ticket_id)["count"] > 0, ticket.ticket_id


def test_hold_rechecks_comparability_and_refuses_an_overpriced_home():
    """LST-100002 is EUR 417.84 a night -- far above most guests' ceilings."""
    result = call(HOLD, ticket_id="LIS-TKT-0001", listing_id="LST-100002")
    assert result["refused"] is True
    assert any("ceiling" in f for f in result["failures"])


def test_hold_refuses_a_listing_outside_the_open_export():
    result = call(HOLD, ticket_id="LIS-TKT-0001", listing_id="LST-200001")
    assert result["refused"] is True
    assert "LST-100001" in result["reason"]


def test_holding_a_home_marks_it_unavailable_to_the_next_guest():
    listing_id = _first_match("LIS-TKT-0001")
    assert call(HOLD, ticket_id="LIS-TKT-0001", listing_id=listing_id)["ok"] is True
    assert bt.STORE.status_of(listing_id) == "on_hold"
    assert call(HOLD, ticket_id="LIS-TKT-0050", listing_id=listing_id)["refused"] is True


# --- one remedy per stay ---------------------------------------------------

def test_refund_refused_after_a_home_is_held():
    call(HOLD, ticket_id="LIS-TKT-0001", listing_id=_first_match("LIS-TKT-0001"))
    assert call(REFUND, ticket_id="LIS-TKT-0001")["refused"] is True


def test_hold_refused_after_a_refund():
    assert call(REFUND, ticket_id="LIS-TKT-0004")["ok"] is True
    assert call(HOLD, ticket_id="LIS-TKT-0004", listing_id="LST-100002")["refused"] is True


# --- the refund cap --------------------------------------------------------

def test_refund_defaults_to_the_full_amount_paid():
    result = call(REFUND, ticket_id="LIS-TKT-0004")
    assert result["amount"] == 168.00 and result["full_refund"] is True


def test_refund_is_capped_at_total_paid_not_nights_times_price():
    """0028: four nights at EUR 120.00 is EUR 480.00, but EUR 432.00 was paid."""
    result = call(REFUND, ticket_id="LIS-TKT-0028", amount_eur=480.00)
    assert result["amount"] == 432.00
    assert result["capped_at_total_paid"] is True


def test_partial_refund_is_allowed():
    assert call(REFUND, ticket_id="LIS-TKT-0008", amount_eur=100.00)["amount"] == 100.00


def test_zero_refund_is_rejected():
    assert call(REFUND, ticket_id="LIS-TKT-0008", amount_eur=0.0)["refused"] is True


def test_refund_cannot_be_issued_twice():
    assert call(REFUND, ticket_id="LIS-TKT-0008")["ok"] is True
    assert call(REFUND, ticket_id="LIS-TKT-0008")["refused"] is True


# --- message_host ----------------------------------------------------------

def test_message_host_works_on_a_lockout_with_no_cancellation():
    """0038: empty lockbox, host's phone off, nothing cancelled in the app."""
    result = call(MESSAGE, ticket_id="LIS-TKT-0038", message="Guest waiting at the door.")
    assert result["ok"] is True and result["host_id"]


def test_empty_message_is_rejected():
    assert call(MESSAGE, ticket_id="LIS-TKT-0038", message="   ")["refused"] is True

# Stranded Guest Support

Ticket sorting and AirCover policy rules for the Lisbon check-in incident of
16 November 2026 — 60 guests who could not get into their stay.

Every ticket sorts into one of three outcomes, each handled by its own agent
with its own tools:

| Outcome | Count | Tools that agent may call |
|---|---|---|
| **Rebooking** | 34 | `search_listings`, `hold_booking`, `handoff_to_safety_agent` |
| **Refund** | 20 | `issue_refund`, `handoff_to_safety_agent` |
| **Safety** | 6 | `handoff_to_safety_agent` — and nothing else |

## The rule that matters most

**A guest in danger never gets an automated refund.**

Two of the six safety tickets asked for nothing but their money. One guest was
bleeding and could hardly stand; another had been followed from the metro by a
man standing across the street watching the door. Processing those refunds
would have closed both stays — a refund is one remedy per stay — and ended the
conversation with each guest exactly where she was.

So on a safety ticket the only permitted call is `handoff_to_safety_agent`.
`issue_refund` and `hold_booking` are forbidden before hand-off, and so is a
listing search, which only delays the hand-off and hints at an offer the agent
has no authority to make.

The full ground rules are in [`.specify/memory/constitution.md`](.specify/memory/constitution.md),
and the specification in [`specs/001-ticket-triage/spec.md`](specs/001-ticket-triage/spec.md).

## What the data showed

`guest_requested` is not an outcome. It disagrees with the correct handling on
**12 of the 60 tickets**, and carries two values that are not outcomes at all:

- **6 hidden safety cases.** Two filed as refunds, two as rebookings, one as a
  callback, one as "other".
- **6 callback or "other" tickets that are really rebookings.** Four guests
  asked for a phone call while saying they still needed a bed; two asked a
  question rather than making a demand.

Traps that must *not* change the outcome:

- **Fury is not danger.** "An absolute nightmare", "I am dying out here" and
  "the worst day of our lives" are all rebookings.
- **Vulnerable but accompanied.** Three children, two grandparents and a baby
  — all travelling with family, all rebookings.
- **The promo-code refund.** One ticket's nights × nightly price comes to
  EUR 480.00, but EUR 432.00 was paid. The refund is capped at what was paid.
- **Lockouts with no cancellation.** Four tickets show nothing cancelled in the
  app. They qualify on no working access or an unreachable host.

## Install and run

```bash
git clone https://github.com/adhya-zero/stranded-guest-support.git
cd stranded-guest-support
pip install -e ".[dev]"
pytest
```

Sort the tickets and print a summary:

```bash
python -m triage.report
```

## Using it

```python
from triage import load_tickets, triage

tickets = load_tickets("data/airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv")
decision = triage(tickets[6])   # LIS-TKT-0007, filed as a refund request

decision.ticket_type      # TicketType.SAFETY
decision.safety_condition # SafetyCondition.INJURY_OR_MEDICAL_NEED
decision.needs_human      # True
decision.allowed_tools    # frozenset({Tool.HANDOFF_TO_SAFETY_AGENT})
```

Checking a home against the five comparability tests:

```python
from triage import check_comparable

result = check_comparable(ticket, listing)
result.passes    # False
result.failures  # ('EUR 160.00 over ceiling of EUR 132.00',)
```

## Layout

This is a [GitHub Spec Kit](https://github.com/github/spec-kit) project. The
rules live as a constitution and a spec; the code implements them.

```
.specify/memory/
  constitution.md    Ground rules every agent follows
specs/001-ticket-triage/
  spec.md            Requirements, acceptance scenarios, success criteria
src/triage/
  models.py   Ticket, Listing, Decision, TicketType, SafetyCondition, Tool
  safety.py   The five safety conditions, read from the guest's own words
  triage.py   Sorting: safety first, then does the guest still want a bed
  policy.py   AirCover rules — tool permissions, comparability, refund caps
  report.py   Command-line summary of all 60 tickets
docs/
  aircover-policy.md The Policy and Payments ruling this implements
data/
  airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv
tests/
  test_triage.py  Sorting, with the six safety cases named individually
  test_policy.py  Tool permissions, comparability, refund caps, uplift
```

## A caveat worth reading

The classifier in `safety.py` matches phrases, and phrase matching is brittle.
A guest who writes "my ankle has gone purple" trips nothing in it today. It
scores 60/60 on the tickets it was built against, which is exactly the kind of
result that should not be trusted on its own.

It is written as a deterministic baseline behind a stable interface. The
production classifier should be a model that reads the message, with these
patterns kept as a fast pre-filter and the 60 labelled tickets kept as the
regression set. The two rules that must survive any replacement are in the
module docstring: read facts rather than feeling, and treat calm wording as
carrying no weight either way.

## Status

Sorting and the policy rules are implemented and tested. Still to build: the
three agents themselves, the listing search against the 450 open Lisbon
listings, and the hand-off payload sent to Trust and Safety.

Next in the Spec Kit workflow, from Claude Code in this repo:

```
/speckit-plan      # tech stack and approach for the agents
/speckit-tasks     # break the plan into steps
/speckit-implement # build them
```

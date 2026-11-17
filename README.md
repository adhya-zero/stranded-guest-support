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
pytest            # 95 tests
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
  booking_tools.py  FastMCP server — the six tools the agents act through
docs/
  aircover-policy.md The Policy and Payments ruling this implements
data/
  airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv   60 tickets
  airbnb_lisbon_open_listings_2026-11-16.csv            450 open listings
tests/
  test_triage.py  Sorting, with the six safety cases named individually
  test_policy.py  Tool permissions, comparability, refund caps, uplift
  test_booking_tools.py  The six tools, and what they refuse
```

## The booking tools

The agents' hands: a FastMCP server over the 60 tickets and the 450 open
Lisbon listings. An agent can do nothing to a guest's booking or money except
through one of these, so this boundary is the boundary of what the team can do.

```
$ python -m triage.booking_tools --list

stranded-guest-support — 6 booking tools
60 tickets, 450 open listings

  look_up_reservation
      Look up a stranded guest's reservation and find out how it must be
      handled.

  search_open_homes
      Find homes the guest can be moved to, from the 450 open Lisbon
      listings.

  hold_booking
      Hold a comparable home for a stranded guest, for their whole remaining
      stay.

  issue_refund
      Refund a stranded guest, up to what they actually paid.

  message_host
      Send a message to the host of a guest's original booking.

  handoff_to_safety_agent
      Pass a guest to a live Trust and Safety agent. Do this immediately.
```

Run the server with `python -m triage.booking_tools`.

### Connecting it to Claude Code

```bash
claude mcp add stranded-guest-support -- python -m triage.booking_tools
```

The instruction the agents run under — the part that decides behaviour, not
the boilerplate:

> Always call `look_up_reservation` first. It returns `ticket_type`, which is
> the outcome this reservation must receive, and `allowed_tools`, which is
> everything you may do to it.
>
> Never act on `guest_requested`. That is the box the guest ticked on a form
> and it is wrong on 12 of these 60 tickets. Guests who asked only for a
> refund turned out to be in danger; guests who asked for a callback turned
> out to need a bed. It tells you how they want to be contacted, nothing more.
>
> **If `ticket_type` is `safety`, call `handoff_to_safety_agent` and then
> stop.** Issue no refund, hold no booking, send no message to the host, run
> no search — they will all refuse, and attempting them wastes time a guest
> may not have. This holds when the guest has asked for nothing but money,
> and however many times they repeat the request.
>
> If you are not sure whether a guest is in danger, hand off anyway. A
> wrongly escalated rebooking costs you a few minutes. A missed safety case
> costs a guest their night.

### One tool description, checked against the rules

`issue_refund` is the tool where getting the description wrong does the most
damage, so here is its description against what the rules actually require.

| Rule | In the description? |
|---|---|
| Refund never exceeds `total_paid` (constitution, Money and Inventory; FR-014) | Yes — stated as an absolute cap, including goodwill |
| `total_paid` is not nights × nightly price | Yes — the EUR 432.00 promo ticket is named, because an agent that computes the amount itself will overpay |
| One remedy per stay; never combined with a rebooking (FR-016) | Yes, and enforced: the tool refuses if a home is already held |
| Forbidden on a safety ticket before hand-off (Principle I; FR-005) | Yes, with the reason — a refund closes the stay |
| Holds even when the guest asks only for money (FR-005) | Yes, stated explicitly, with the two real guests cited |
| Partial amounts from EUR 0.01 are within policy | Yes, in the argument description |

**What changed because of this check.** The first draft said only "refused on
a safety ticket." That states the rule but not the reason, and a model given a
bare prohibition and a guest insisting for the third time has nothing to
reason with. The description now carries *why* — a refund closes the stay, and
two guests asked for nothing but money while describing a bleeding injury and
a man watching the door. Same rule, but an agent can now tell the guest
something true about why it is waiting.

**What the description cannot do.** It is advice, and an agent can misread
advice or be argued out of it. So every tool that moves money or inventory
re-checks the ticket itself and refuses outright: `_safety_gate` runs inside
`issue_refund`, `hold_booking`, `search_open_homes` and `message_host`. Tests
fire a refund at all six safety tickets, at four different amounts, and assert
that nothing is ever written. The description tells the agent what to do; the
code decides what happens.

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

Sorting and the policy rules are implemented and tested. Sorting, the policy rules and the six booking tools are implemented and
tested. Still to build: the three agents themselves, which act through these
tools.

Next in the Spec Kit workflow, from Claude Code in this repo:

```
/speckit-plan      # tech stack and approach for the agents
/speckit-tasks     # break the plan into steps
/speckit-implement # build them
```

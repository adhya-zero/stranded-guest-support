# Stranded Guest Support Constitution

Ground rules for every agent, tool and feature in this repository. Where a
spec, plan or implementation disagrees with this document, this document wins.

Scope: the Lisbon check-in incident of 16 November 2026 — 60 guests who could
not get into their stay. The policy these rules implement is
`docs/aircover-policy.md`.

## Core Principles

### I. A Guest in Danger Never Gets an Automated Answer (NON-NEGOTIABLE)

If a guest's message describes any of the five safety conditions, the ticket
goes to a live Trust and Safety agent and nothing else happens first. The only
permitted call on such a ticket is `handoff_to_safety_agent`. `issue_refund`
and `hold_booking` are forbidden before hand-off, and so is a listing search,
which only delays the hand-off and hints at an offer the agent has no
authority to make.

The reason is in the refund rules: a refund is one remedy per stay, and it
closes the stay. An automatic refund does not merely pay someone out — it ends
the case and ends the conversation. Two guests on 16 November asked for
nothing but their money while describing a bleeding injury and a man watching
the door. Paying them would have been the fastest way to abandon them.

The rule is absolute. An agent that refunds "when the guest really insists"
will eventually refund the guest it exists to protect.

The five conditions, read from what the guest describes rather than from any
label on the ticket: `injury_or_medical_need`, `threat_or_violence`,
`nowhere_safe_to_wait`, `unaccompanied_minor`, `stated_fear_of_person`.

### II. Sort on What the Guest Describes, Never on What the Form Says

`guest_requested` is a contact preference, not an outcome. On the 16 November
export it carries values that are not outcomes at all — "callback" and "other"
— and it disagrees with the correct handling on 12 of the 60 tickets.

Sorting reads `guest_message`, in a fixed order:

1. Check the five safety conditions. This runs **before any tool call**, so no
   listing is ever held on a ticket that turns out to be a safety case.
2. Then ask: does this guest still want somewhere to stay for these nights?
   Yes or undecided → rebooking. No → refund.

### III. Facts, Not Feeling

A safety condition is a thing happening to a person: an injury or symptom, a
threat, a guest under 18, being alone with nowhere to go, fear of someone
specific.

Anger is not a safety condition. "An absolute nightmare", "I am dying out
here" and "the worst day of our lives" came from guests who needed a flat, not
an agent. Escalating on tone floods the safety queue and pushes real cases
behind people who are merely furious.

Calm wording carries no weight either: the 16-year-old alone with a phone at
9% wrote a short, polite message and asked only for a callback. Nor does
sounding vulnerable — a guest with three children, one with grandparents and
one with a baby were all accompanied adults asking for a flat.

### IV. Prefer the Reversible Path

A guest who has not decided is sorted as a rebooking. Turning down a home
keeps their right to another comparable home or to a full refund. A refund
closes the stay and cannot be undone.

### V. Real Uncertainty Goes to a Human (NON-NEGOTIABLE)

When an agent cannot tell whether a safety condition is present, or whether a
guest wants a home or their money, it stops and asks a person.

The costs are not symmetric. A wrongly escalated rebooking costs an agent a
few minutes. A missed safety case costs a guest their night, against the
commitment that every guest has a bed, a refund or a live agent before
midnight on 16 November 2026. An agent that is unsure must never resolve the
doubt by staying quiet.

## Money and Inventory Constraints

**Refunds are capped, always.** No refund exceeds the ticket's `total_paid`,
including any goodwill or inconvenience amount. One ticket was booked on a
promo code: four nights at EUR 120.00 is EUR 480.00, but EUR 432.00 was paid,
so EUR 432.00 is the ceiling. Any amount from EUR 0.01 up to `total_paid` is
within policy. A refund and a rebooking are never combined for the same nights.

**The above-ceiling path is closed, not slow.** A home above 120% of the
guest's original nightly price is never offered on 16 November 2026. Sign-off
from Laura Schmidt, Rebooking and Refund Policy Manager, is unavailable that
day, so this is written as a prohibition rather than an approval step that
would leave a ticket waiting on a signature that is not coming. Remaining
budget is not a reason to exceed it; the EUR 150 average is a planning figure,
not a per-guest cap.

**Comparability is five tests, all pass or fail.** Dates covering the whole
stay, `max_guests` ≥ party size, bedrooms ≥ the original, status `available`
at the time of the hold, and nightly price ≤ 120% of the original. One failure
disqualifies the home. Neighbourhood orders homes that already pass; it never
qualifies or disqualifies one. Support runs from `check_in_date` to
`check_out_date`, not just the first night. If no open listing passes, the
guest receives a full refund of `total_paid`.

**Qualification is broader than cancellation.** A guest qualifies on any one
of: no working access at check-in, an unreachable host, or a host cancellation
within 30 days of check-in. Four tickets show no cancellation at all — empty
lockboxes and silent hosts. A check written against `host_cancelled_at` alone
would have turned them away.

## Development Workflow

**Every decision explains itself.** A decision carries the reason it was
reached and, for a safety ticket, the condition and the guest's own words that
triggered it. A hand-off carries what a person needs in the first ten seconds:
the condition, the evidence, where the guest is, the party, their language,
and anything time-critical such as a dying phone or a threat still present.

**Tested against the real tickets.** Sorting is tested against all 60 tickets
from 16 November 2026 and must reproduce 34 rebookings, 20 refunds and 6
safety hand-offs. Each safety case is also tested by name, so a regression
says which guest it would have failed. Tool permissions are enforced in code
and asserted in tests, not merely documented.

**Classifiers are replaceable and honest about their limits.** The
phrase-matching detector in `src/triage/safety.py` is a baseline behind a
stable interface, documented as brittle. A perfect score on the tickets it was
built against is not evidence of correctness. The 60 labelled tickets are the
regression set that keeps any replacement honest.

## Governance

This constitution supersedes all other practices in this repository. Any
amendment must be recorded here with a version bump and a dated note, and must
state its effect on the agents already built.

Principles I and V are non-negotiable: no feature, performance target or
convenience may weaken them, and a change to either requires sign-off from
Trust and Safety rather than engineering alone.

All reviews verify compliance. A change that makes an agent act with less
information, or escalate less often, carries the burden of proof.

**Version**: 1.0.0 | **Ratified**: 2026-11-17 | **Last Amended**: 2026-11-17

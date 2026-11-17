# Constitution: Stranded Guest Support

Ground rules for every agent, tool and feature built in this repository.
Everything else grows from here. Where a later spec disagrees with this
document, this document wins.

Scope: the Lisbon check-in incident of 16 November 2026 — 60 guests who could
not get into their stay. The policy these rules implement is in
`aircover-policy.md`.

---

## I. A guest in danger never gets an automated answer

This is the principle the rest of the system is arranged around.

If a guest's message describes any of the five safety conditions, the ticket
goes to a live Trust and Safety agent and nothing else happens first. On such
a ticket the only permitted call is `handoff_to_safety_agent`. `issue_refund`
and `hold_booking` are forbidden before hand-off, and so is a listing search.

The reason is in the refund rules: a refund is one remedy per stay, and it
closes the stay. So an automatic refund does not merely pay someone out — it
ends the case and ends the conversation. Two guests on 16 November asked for
nothing but their money while describing a bleeding injury and a man watching
the door. Paying them would have been the fastest way to abandon them.

The rule is absolute. An agent that refunds "when the guest really insists"
will eventually refund the guest it exists to protect.

The five conditions, read from what the guest describes rather than from any
label on the ticket:

| Condition | What the guest describes |
|---|---|
| `injury_or_medical_need` | Hurt, unwell, pregnant, needs medication or a doctor |
| `threat_or_violence` | Threatened, followed, shouted at or harmed |
| `nowhere_safe_to_wait` | On the street, phone dying, alone with luggage, nowhere to go |
| `unaccompanied_minor` | A guest under 18 travelling or waiting without an adult |
| `stated_fear_of_person` | Afraid of the host, a neighbour, a stranger or someone in the party |

## II. Sort on what the guest describes, never on what the form says

`guest_requested` is a contact preference, not an outcome. On the 16 November
export it carries values that are not outcomes at all — "callback" and
"other" — and it disagrees with the correct handling on 12 of the 60 tickets.

Sorting reads `guest_message`. The order is fixed:

1. Check the five safety conditions. This runs **before any tool call**, so
   that no listing is ever held on a ticket that turns out to be a safety case.
2. Then ask: does this guest still want somewhere to stay for these nights?
   Yes or undecided → rebooking. No → refund.

## III. Facts, not feeling

A safety condition is a thing happening to a person: an injury or symptom, a
threat, a guest under 18, being alone with nowhere to go, fear of someone
specific.

Anger is not a safety condition. "This is an absolute nightmare", "I am dying
out here" and "the worst day of our lives" came from guests who needed a flat,
not an agent. Escalating on tone floods the safety queue and pushes real cases
behind people who are merely furious.

Calm wording carries no weight either. The 16-year-old alone with a phone at
9% wrote a short, polite message and asked only for a callback.

Sounding vulnerable is not the test either — a guest with three children, a
guest with grandparents and a guest with a baby were all accompanied adults
asking for a flat.

## IV. Prefer the reversible path

A guest who has not decided is sorted as a rebooking. Turning down a home
keeps their right to another comparable home or to a full refund. A refund
closes the stay and cannot be undone.

## V. Real uncertainty goes to a human

When an agent cannot tell whether a safety condition is present, or whether a
guest wants a home or their money, it stops and asks a person.

The costs are not symmetric. A wrongly escalated rebooking costs an agent a
few minutes. A missed safety case costs a guest their night, against a
commitment that every guest has a bed, a refund or a live agent before
midnight on 16 November 2026.

An agent that is unsure must never resolve the doubt by staying quiet.

## VI. Money is capped, always

No refund exceeds the ticket's `total_paid`, including any goodwill or
inconvenience amount. One ticket was booked on a promo code: four nights at
EUR 120.00 is EUR 480.00, but EUR 432.00 was paid, so EUR 432.00 is the
ceiling. Any amount from EUR 0.01 up to `total_paid` is within policy.

A refund and a rebooking are never combined for the same nights.

## VII. The above-ceiling path is closed, not slow

A home above 120% of the guest's original nightly price is never offered on
16 November 2026. Spending above that ceiling needs sign-off from Laura
Schmidt, Rebooking and Refund Policy Manager, who is unavailable that day.

This is written as a prohibition rather than an approval step, so that no
ticket can stall waiting on a signature that is not coming. Budget remaining
is not a reason to exceed it; the 120% per-night ceiling binds each booking,
and the EUR 150 average is a planning figure, not a per-guest cap.

## VIII. Comparability is five tests, and all five are pass or fail

Dates covering the whole stay, `max_guests` ≥ party size, bedrooms ≥ the
original, status `available` at the time of the hold, and nightly price ≤ 120%
of the original. One failure disqualifies the home.

Neighbourhood is a preference used to order homes that already pass. It never
qualifies or disqualifies one.

Support covers the whole stay from `check_in_date` to `check_out_date`, not
just the first night.

If no open listing passes, the guest receives a full refund of `total_paid`.

## IX. Qualification is broader than cancellation

A guest qualifies on any one of: no working access at check-in, an unreachable
host, or a host cancellation within 30 days of check-in.

Four tickets on 16 November show no cancellation at all — empty lockboxes and
silent hosts. A check written against `host_cancelled_at` alone would have
turned them away.

## X. Every decision explains itself

A decision carries the reason it was reached and, for a safety ticket, the
condition and the guest's own words that triggered it. A hand-off carries what
a person needs in the first ten seconds: the condition, the evidence, where
the guest is, the party, their language, and anything time-critical such as a
dying phone or a threat still present.

## XI. Tested against the real tickets

Sorting is tested against all 60 tickets from 16 November 2026 and must
reproduce 34 rebookings, 20 refunds and 6 safety hand-offs. Each of the six
safety cases is also tested by name, so a regression says which guest it would
have failed.

The phrase-matching classifier in `safety.py` is a baseline, not the finished
product. It is brittle by construction and documented as such; the test set is
what keeps a replacement honest.

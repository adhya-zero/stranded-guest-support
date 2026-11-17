# Feature Specification: Stranded Guest Ticket Triage

**Feature Branch**: `001-ticket-triage`

**Created**: 2026-11-17

**Status**: Implemented (sorting and policy rules); agents outstanding

**Input**: Sort every stranded guest ticket from the Lisbon check-in incident
of 16 November 2026 into rebooking, refund or safety, decide which warning
signs send a ticket straight to a human, and make sure a guest in danger never
receives an automatic refund.

**Source policy**: `docs/aircover-policy.md` (Policy and Payments ruling)
**Ground rules**: `.specify/memory/constitution.md`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A guest in danger reaches a person, not a refund (Priority: P1)

A guest who is hurt, threatened, alone with nowhere to go, under 18, or afraid
of someone is taken off the automated path entirely and handed to a live Trust
and Safety agent. This holds even when the guest asks only for money, and even
when nothing on the ticket is labelled an emergency.

**Why this priority**: Getting this wrong is the only failure in the system
that can leave someone in physical danger. A refund closes the stay, so
honouring the request would end the case and the conversation with the guest
still where they are. Every other story is worth less than this one.

**Independent Test**: Run the six safety tickets from 16 November through
sorting. Each must come back as a safety hand-off with the condition named and
the guest's own words attached, and no refund or booking call may be permitted
on them.

**Acceptance Scenarios**:

1. **Given** LIS-TKT-0007, filed as a refund request, whose message describes
   a bleeding knee and being barely able to stand, **When** the ticket is
   sorted, **Then** it is a safety ticket with `injury_or_medical_need` and
   `issue_refund` is not among the permitted calls.
2. **Given** LIS-TKT-0034, filed as a refund request, whose message describes
   a man who followed her from the metro and is watching the door, **When** the
   ticket is sorted, **Then** it is a safety ticket and no refund is issued.
3. **Given** LIS-TKT-0015, filed as a callback, written politely by a guest who
   states she is 16, travelling alone, with her phone at 9%, **When** the
   ticket is sorted, **Then** it is a safety ticket with `unaccompanied_minor`.
4. **Given** any safety ticket, **When** an agent attempts `issue_refund`,
   `hold_booking` or a listing search, **Then** the call is refused.
5. **Given** a safety condition that surfaces mid-conversation on a ticket
   already sorted as a rebooking, **When** it is detected, **Then** the agent
   stops and hands off, and any existing hold is reported rather than released.

---

### User Story 2 - A guest who still needs a bed is offered a comparable home (Priority: P2)

A guest who has not got in and still wants to stay in Lisbon is sorted as a
rebooking and offered a home that passes all five comparability tests, for the
whole remaining stay.

**Why this priority**: This is the largest group — 34 of 60 — and the incident
commitment is that every guest has a bed, a refund or a live agent before
midnight.

**Independent Test**: Sort the 34 rebooking tickets and confirm each is
matched against the open listings using all five tests, with the whole stay
covered rather than the first night.

**Acceptance Scenarios**:

1. **Given** a qualifying guest who asks to be moved, **When** the ticket is
   sorted, **Then** it is a rebooking and the search covers `check_in_date`
   through `check_out_date`.
2. **Given** an open listing priced above 120% of the guest's original nightly
   price, **When** comparability is checked, **Then** it fails and is never
   offered, regardless of remaining budget.
3. **Given** a listing whose status is `on_hold` or `booked`, **When**
   comparability is checked, **Then** it fails.
4. **Given** a guest who turns down the first home offered, **When** they ask
   again, **Then** they retain the right to another comparable home or a full
   refund.
5. **Given** a rebooking ticket for which no open listing passes all five
   tests, **When** the search completes, **Then** the guest receives a full
   refund of `total_paid`.

---

### User Story 3 - A guest who has made other plans gets their money back (Priority: P2)

A guest who has somewhere else to go, or who declines rebooking, is refunded
up to what they actually paid.

**Why this priority**: Equal in standing to rebooking — both are remedies the
guest is entitled to — but simpler to deliver and smaller in volume (20 of 60).

**Independent Test**: Sort the 20 refund tickets and confirm each is capped at
`total_paid` and closes the stay without a parallel rebooking.

**Acceptance Scenarios**:

1. **Given** a guest who says they will drive home, stay with family, or have
   a company hotel, **When** the ticket is sorted, **Then** it is a refund.
2. **Given** LIS-TKT-0028, where four nights at EUR 120.00 comes to EUR 480.00
   but EUR 432.00 was paid on a promo code, **When** a refund is issued,
   **Then** the amount is EUR 432.00.
3. **Given** any refund request above `total_paid`, including goodwill,
   **When** it is processed, **Then** it is capped at `total_paid`.
4. **Given** a guest who has been refunded, **When** the same nights are
   considered, **Then** no rebooking is offered for them.

---

### User Story 4 - An ambiguous ticket reaches a human (Priority: P3)

A ticket whose message does not reveal whether the guest wants a home or their
money, or whether a safety condition is present, is held for a person rather
than guessed.

**Why this priority**: Lower volume, but it is what stops the other three
stories from failing quietly.

**Independent Test**: Confirm ambiguous tickets are flagged for a human and
held on the reversible path rather than refunded.

**Acceptance Scenarios**:

1. **Given** a message that both asks for a refund and asks for another flat,
   **When** the ticket is sorted, **Then** it is flagged for a human and held
   as a rebooking.
2. **Given** a message that asks only for a phone call with no stated need,
   **When** the ticket is sorted, **Then** it is flagged for a human and no
   refund is issued.

---

### Edge Cases

- **A furious guest who is not in danger.** "An absolute nightmare", "I am
  dying out here", "the worst day of our lives" — all rebookings. Tone must
  not route a ticket.
- **A vulnerable-sounding guest travelling with family.** Three children, two
  grandparents, a baby — all accompanied, all rebookings.
- **A lockout with no cancellation in the app.** Four tickets show nothing
  cancelled. They qualify on no working access or an unreachable host.
- **A guest who mentions another flat only to refuse it.** "I do not trust
  another flat now, refund the 1168 euros" is a refund, not a rebooking.
- **A ticket with no `host_last_reply_at` and no `host_cancelled_at`.** Still
  qualifies.
- **A guest whose stay runs past every listing's availability window.** No
  comparable home exists; full refund.
- **A safety condition stated in a language other than English.** The ticket
  carries `guest_language`; detection must not assume English.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST sort every ticket into exactly one of `rebooking`,
  `refund` or `safety`.
- **FR-002**: System MUST derive the outcome from `guest_message`, and MUST
  NOT treat `guest_requested` as the outcome. `guest_requested` is retained
  only as a contact preference.
- **FR-003**: System MUST check the five safety conditions before any tool
  call on a ticket.
- **FR-004**: System MUST permit exactly one call on a safety ticket:
  `handoff_to_safety_agent`.
- **FR-005**: System MUST refuse `issue_refund`, `hold_booking` and listing
  searches on a safety ticket, regardless of what the guest requested.
- **FR-006**: System MUST allow any agent to hand off to safety at any point,
  because a safety condition can surface mid-conversation.
- **FR-007**: System MUST attach to every safety hand-off the condition
  matched, the guest's own words that matched it, the guest's location, party
  size, `guest_language`, and any time-critical detail.
- **FR-008**: System MUST sort an undecided guest as a rebooking.
- **FR-009**: System MUST flag a ticket for human review when the outcome is
  genuinely unclear, and MUST NOT resolve the doubt by choosing silently.
- **FR-010**: System MUST treat a guest as qualifying on any one of: no
  working access at check-in, an unreachable host, or a host cancellation
  within 30 days of check-in.
- **FR-011**: System MUST apply all five comparability tests and reject a
  listing that fails any one of them.
- **FR-012**: System MUST use neighbourhood only to order listings that
  already pass, never to qualify or disqualify one.
- **FR-013**: System MUST cover the whole stay from `check_in_date` to
  `check_out_date`.
- **FR-014**: System MUST cap every refund at the ticket's `total_paid`.
- **FR-015**: System MUST NOT offer a home priced above 120% of the guest's
  original nightly price on 16 November 2026, and MUST NOT create a pending
  approval state for one.
- **FR-016**: System MUST NOT combine a refund and a rebooking for the same
  nights.
- **FR-017**: System MUST issue a full refund of `total_paid` when no open
  listing passes all five tests, or when the guest declines rebooking.
- **FR-018**: System MUST record, for every decision, the reason it was
  reached.
- **FR-019**: System MUST restrict a rebooking to a `listing_id` in the open
  listings export (LST-100001–LST-100450). `original_listing_id` values are
  not bookable.
- **FR-020**: System MUST NOT ask a guest safety assessment questions before
  hand-off; that conversation belongs to the live agent.

### Key Entities

- **Ticket**: One stranded guest. Carries the reservation, the original
  listing's size and price, party size, stay dates, `total_paid`, host
  cancellation and reply timestamps, the guest's stated request, and the
  guest's own message.
- **Listing**: An open Lisbon home. Carries availability window, capacity,
  bedrooms, nightly price and bookable status.
- **Decision**: The outcome of sorting one ticket — the type, the reason, any
  safety condition matched, whether a human is needed, and the contact
  preference.
- **Safety signal**: One matched condition, with the reason and the guest's
  words that triggered it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 60 tickets from 16 November 2026 sort to the correct
  outcome: 34 rebookings, 20 refunds, 6 safety hand-offs.
- **SC-002**: All six safety tickets are caught, including the two that asked
  only for money and the one that asked only for a callback. Zero misses is
  the only acceptable result.
- **SC-003**: Zero refunds are issued on a safety ticket before hand-off,
  under any phrasing or repetition of the request.
- **SC-004**: Zero refunds exceed the ticket's `total_paid`.
- **SC-005**: Zero homes above 120% of the original nightly price are offered.
- **SC-006**: No ticket sorts on tone alone: the four tickets using dramatic
  language without a safety condition remain rebookings.
- **SC-007**: Every guest has a bed, a refund or a live agent before midnight
  on 16 November 2026.

## Assumptions

- Guest messages are available as text; no audio or image intake is in scope.
- The open listings export is a point-in-time snapshot, so a listing's
  `available` status is re-checked at the moment of the hold.
- Laura Schmidt remains unavailable on 16 November 2026, so the above-ceiling
  path stays closed for the duration of this incident.
- Live Trust and Safety agents have capacity to take every hand-off; the
  system does not queue or triage within safety.
- Guests are contactable by the channel already on the ticket, and a stated
  callback preference is honoured without changing the outcome.
- Scope is this incident only. Nothing here is a general AirCover
  implementation, and the 120% ceiling and closed sign-off path are
  incident-specific.

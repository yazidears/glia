# Hackathon runbook

## Before leaving

- Finish the Entire browser sign-in, then verify `entire status` in this repo.
- Open the Luma ticket on the phone and keep it available offline.
- Join the organizer Discord from the public event page and scan announcements.
- Charge the MacBook, phone, and power bank.
- Pack: laptop charger, USB-C cable/dongle, phone cable, power bank, headphones, ID, water bottle, light layer, and any medication.
- Bring a small snack if you need one; lunch, dinner, fruit, snacks, beer, and soft drinks are listed as provided.

Weather is expected to be hot and sunny, around 30°C at the high. Dress light and bring water.

## Arrival

Be at the building by **09:10**. The event is limited to 60 people and the organizer says admission is first-come, first-served even with an approved ticket.

The exact attendee address is in `.private/event.md` and in the registration email.

## Official schedule

| Time | Event | Your move |
|---|---|---|
| 09:30 | Doors and networking | Check in, get Wi-Fi/credits, meet one engineer and one designer/data person. |
| 10:00 | Opening and matchmaking | Capture the actual brief and judging criteria verbatim. Form a team only if roles are complementary. |
| 12:30 | Lunch | Have the happy path running locally before eating. |
| 17:30 | Internal feature freeze | Fix reliability, visuals, copy, and latency only. |
| 18:00 | Rehearsal | Time the full demo three times. Record a backup. |
| 19:00 | Competition opt-in deadline and dinner | Submit by 18:40; verify confirmation. |
| 20:00 | Live demos | Lead with the result, then show how it works. |
| 20:45 | Awards | Keep the app and repo ready for judge follow-ups. |

## First 30 minutes after opening

Write the answers in `PROJECT_BRIEF.md`:

1. What exact problem or track is being judged?
2. Who feels the pain, and what do they do today?
3. What is the single before/after moment the judges will see?
4. Which scoring criterion does that moment prove?
5. What can be real by lunch, and what can be mocked honestly?
6. What will still work if Wi-Fi or an API fails?

Do not begin a broad build until these fit on one screen.

## Build gates

### Gate 1 — by 11:00

- Project selected and pitch sentence written.
- Repo instructions, environment names, and sample fixture in place.
- One command starts the app.

### Gate 2 — by 12:30

- End-to-end happy path works locally with a fixture.
- Primary model/provider call works once, or the mock is explicit.
- First Entire checkpoint is committed locally.

### Gate 3 — by 15:30

- Real provider integration is stable.
- Errors, empty state, and retry path exist.
- UI clearly explains input, progress, evidence, and result.

### Gate 4 — by 17:30

- Feature freeze.
- Fresh-machine setup steps are correct.
- Aikido/security and secret checks are clean.
- Demo data resets in one action.

### Gate 5 — by 18:40

- Submission completed and verified.
- 90-second and 3-minute pitches rehearsed.
- Screen recording and static screenshots saved locally.

## Team rule

Use a team only if responsibilities are crisp: one person owns the demo product, one owns the core data/model path, and one owns story/presentation. If that cannot be established by 10:30, run the solo plan and keep scope small.

## Failure protocol

- API slow: switch to the saved fixture while saying it is the deterministic demo mode.
- Wi-Fi down: run everything locally and show the recorded provider-backed result afterward.
- Model gives a bad answer: use structured output validation and a pre-tested input.
- Integration breaks after 17:30: disable it behind a flag; do not rewrite the architecture.
- Demo machine issue: keep the recording and screenshots one click away.

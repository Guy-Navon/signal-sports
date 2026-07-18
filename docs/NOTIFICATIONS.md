# Telegram Push Pilot — Notification Contract (Milestone 7)

**Status:** authoritative living contract for M7-5/#151 (story identity + outbox),
M7-6/#152 (planner), M7-7/#153 (delivery).
**ACTIVE IN PRODUCTION since 2026-07-18 (M7-10 #156):** the guarded watermark
initialization (`scripts/init_notification_watermark.py`) ran at 2026-07-18T12:43:48Z
suppressing the 7 historical PUSH stories, then the production `backend/.env` enabled
`TELEGRAM_NOTIFICATIONS_ENABLED=true` with `TELEGRAM_REQUEST_TIMEOUT_SECONDS=20`.
The `.env.example` default stays false; enabling without a watermark is fail-closed.
First deliveries: controlled probe (Telegram message 5) and a genuine Israel Hayom
story (message 6), both exactly once — see `docs/qa/M7_ACCEPTANCE_155.md`.

## The delivery-semantics statement (exact required language)

> Signal enforces durable story-level notification uniqueness and conservative
> at-most-one retry semantics. Telegram network delivery may produce an unknown
> outcome, which is not retried automatically.

Telegram's `sendMessage` has no client-supplied idempotency key, so exactly-once
network delivery cannot be claimed and is not. The product policy is:

> At most one attempted user-visible notification per story is more important
> than guaranteed eventual delivery.

A rare missed notification is deliberately preferred over a duplicate one.

## Pipeline position

```
ingestion (articles committed) → anchors → clustering → PLANNER (M7-6)
  → DISPATCHER (M7-7, own sessions, never in the ingestion transaction)
  → retention cleanup (M7-3, after planning so planning sees the full window)
```

Planner and dispatcher failures degrade the cycle to `succeeded_with_warnings`
and never roll back or fail ingestion. A Telegram outage never marks the
ingestion system dead (health keeps them apart — M7-8).

## Story notification identity (M7-5) — why member lineage

Cluster ids are stable under append but **not** under evolution: an anchor
change or a component merge retires an id and mints a new one
(`reconcile_scope` preserves ids only through overlap), and the anchor
reference is nullable under pruning. Article ids (`rss_` + sha1(url)) are
immutable forever — a republished URL maps back to the same id.

So a notified story's identity is its **member lineage**:
`notification_story_members` with the database constraint
`UNIQUE(profile_id, policy_version, article_id)`. Creating an event inserts
every current component member; any conflict proves the story was already
notified. Application `exists()` checks are explicitly **not** the mechanism.

Consequences, all test-locked (`test_notification_identity_151.py`):

| Story evolution | Behavior |
|---|---|
| Second source joins / component expands | New member attaches to the existing lineage (`expansion`); **no new event** |
| Cluster id churns (anchor change, backfill) | Members prove identity; suppressed |
| Canonical article changes | No new members; suppressed; the event keeps its creation-time snapshot |
| Two previously-notified components merge | **No message**; members attach to the OLDEST event; `component_merge_observed` notes on every involved event |
| Retention deletes old member articles | Lineage rows have no FK and survive — they are the notification system's memory |
| Same source republishes a URL | Same article id → same lineage row |
| Policy version bump | A deliberate NEW identity space, requiring its own guarded watermark initialization |

## Activation watermark — no historical flood

The planner **refuses to plan** for a (profile, policy) with no
`notification_watermarks` row. Only the M7-10 guarded initialization sets one,
and the same initialization plants `suppressed_watermark` events (with
lineage) for every story already PUSH-eligible at activation — so enabling
Telegram cannot send the backlog, and the suppression itself is auditable.

## Planning rules (M7-6)

- **Guy only** (`TELEGRAM_NOTIFICATION_PROFILE=guy`), **PUSH tier only**.
- Feed eligibility is the source of truth: the planner invokes exactly the
  canonical path behind `GET /api/feed/guy` (learned profile, dismissed
  filtering, `include_hidden=False`, cluster collapse) and reads story-level
  card decisions. No second ruleset.
- **Freshness is inherited, not reimplemented** (M8, #173): `build_feed`
  applies the shared 36h window (`docs/FEED_FRESHNESS.md`), so expired
  stories never create events, restarting the planner cannot notify about
  old PUSH stories, and an expired canonical replaced by a fresh duplicate
  stays already-notified (lineage covers expired members). There is no
  Telegram-specific age rule — a source-guard test locks this.
- Identity snapshots use **full component membership from the DB** (not just
  the card's visible members) so hidden members can never resurface as a
  "new" story.
- A story rising to PUSH later (genuinely new facts) creates one event iff it
  was never notified. A canonical change without an eligibility change creates
  nothing. Material-update pairs follow production story separation — there is
  no Telegram-specific collapse.
- Disabling Telegram **pauses planning** (not just delivery): re-enabling does
  not flood a stale pending backlog; a story from the gap notifies only if it
  is still push-visible in the feed and was never notified.

## Delivery semantics (M7-7)

Claim-then-send: each event is durably marked `claimed` (attempt count,
timestamp) and committed **before** the network attempt.

| Outcome | Status | Behavior |
|---|---|---|
| Telegram confirms (`ok` + message_id) | `sent` | Message id persisted; never resent |
| Connect error before transmission, 429, 5xx | `failed_retryable` | Exponential backoff (`TELEGRAM_RETRY_BACKOFF_SECONDS` × 2^attempts), capped at `TELEGRAM_MAX_ATTEMPTS`, then `failed_final` |
| 400/401/403/404 (bad request/token/blocked/chat) | `failed_final` | Terminal; sanitized error class recorded |
| Timeout after transmission may have begun; interrupted mid-request; any unprovable case | `unknown` | **Never automatically resent.** Surfaced for manual review. The lineage already exists, so no replacement event can be created either |
| Crash after claim, before result | stays `claimed` | Diagnosable via `claimed_at`; deliberately NOT auto-reset to pending — the send may have gone out |

Message contract (pilot): **plain text** — canonical headline, source name,
original-article link. Plain text deliberately: Markdown/HTML escaping is a
failure class with zero product value here. The link points to the canonical
article selected at notification creation; a later canonical change does not
trigger another message.

## Secrets

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` live only in the git-ignored
`backend/.env`. The token appears in the Bot API URL — therefore the URL is
never logged, exceptions are reduced to class names, and no API/health/ops
surface returns either value (test-locked). The `httpx` and `httpcore`
loggers are additionally capped at WARNING when the adapter is imported:
httpx logs every request URL at INFO, and the worker runs root logging at
INFO, so without the cap the first real send would print the token
(test-locked in `test_telegram_dispatch_153.py`).

## One-time setup (Guy's human-only steps)

1. In Telegram, talk to **@BotFather** → `/newbot` → choose a name/username →
   copy the token.
2. Put the token in `backend/.env` as `TELEGRAM_BOT_TOKEN=...` (never commit).
3. Open the new bot's chat and send it **one message** (anything).
4. Run `backend> .venv\Scripts\python.exe scripts/resolve_telegram_chat_id.py`
   and copy the printed private chat id into `TELEGRAM_CHAT_ID`.
5. Leave `TELEGRAM_NOTIFICATIONS_ENABLED=false` — activation is M7-10's
   controlled step (watermark initialization → enable → live acceptance).

No webhooks are registered; the bot receives no commands; the pilot is
one-way delivery to one private chat.

## Rollback

- **Disable Telegram without touching the scheduler:** set
  `TELEGRAM_NOTIFICATIONS_ENABLED=false` (planning and delivery both pause;
  ingestion unaffected; outbox history preserved).
- The outbox is append-only audit history — never cleared on restart or
  rollback.

# MVP journey audit — a new non-admin user on a phone (2026-10-25)

**Question.** Can Guy's father use Signal daily within a week: sign up or log in on a phone,
choose preferences, read a personalized Hebrew feed, open the source articles?

**Answer.** The journey works end to end on a local copy, and the feed itself is good: Hebrew,
RTL, personalized, no horizontal overflow, working source links. What blocks daily use is not
in the walked journey but around it: there is no always-on host, and password signup needs an
email provider that does not exist yet. Inside the journey, three defects badly degraded it;
each now has a focused PR (§4). The rest are listed with reproductions (§3).

## 1. How this was run

Manual-desktop validation in an isolated environment. Nothing here was checked on a real phone.

| Item | Value |
|---|---|
| Code | `origin/main` at `74541ab` (fix branches from the same base) |
| Database | a verified copy made with `backend/scripts/backup_db.py --src <live corpus> <worktree>/backend/data/journey/journey.db` (3,225 articles; 93 published in the last 36 h). The live corpus was only read by the backup |
| API | `uvicorn app.main:app` on **127.0.0.1:8010**, `DEPLOY_ENV=dev`, `SCHEDULER_ENABLED=false`, `CLASSIFICATION_PROVIDER=disabled`, `TELEGRAM_NOTIFICATIONS_ENABLED=false` (token and chat id empty), `RESULTS_SYNC_ENABLED=false`, `RETENTION_CLEANUP_ENABLED=false`, `FEED_FRESHNESS_ENABLED=true` (36 h, as in production), `CLUSTERING_ENABLED=true`, `MAIL_BACKEND=console` |
| Web | Vite on **127.0.0.1:5180**, `VITE_DATA_MODE=backend`, `/api` proxied to 8010 through a scratch config outside the tracked tree (`vite.config.js` unchanged) |
| Browser | Playwright (Python, scratch venv, not a repo dependency) driving installed Chrome, headless. Phone **390×844** (DPR 2, touch, mobile), desktop **1440×1000**, the dock also at 320×640. Requests to any non-local host were aborted, so no publisher page was fetched |
| User | `father.test@example.com`, display name "אבא", created through the real signup and emailed-link flow |

Interests chosen: basketball and football; NBA, EuroLeague, Ligat Ha'Al; Maccabi Tel Aviv and
Deni Avdija. Calibration: 8 of 18 headlines rated, then "save to profile".

## 2. What works (verified)

- **Signup → verification → first landing.** Client validation is Hebrew and inline. The
  console mailer logged the link; opening it asked for the password and activated the account,
  landing on `/welcome` ([m04](mvp-journey-2026-10-25/m04_signup_submitted.png),
  [m06](mvp-journey-2026-10-25/m06_after_verify.png)).
- **Login.** A wrong password gives "אימייל או סיסמה שגויים"; the right one lands on the feed.
- **Onboarding.** Welcome → interests in 4 steps → calibration → feed, with no overflow at 390.
- **Feed.** 63 stories (9 important, 17 normal, 37 low), Hebrew RTL, long headlines wrap, no
  horizontal overflow at 390 or 1440 ([m12](mvp-journey-2026-10-25/m12_feed_phone_top.png),
  [d01](mvp-journey-2026-10-25/d_01_feed_top.png)). The loading skeleton is intentional
  ([f07](mvp-journey-2026-10-25/f_07_loading.png)).
- **Opening the original article.** "קרא את הדיווח" carries the source URL
  (`https://www.sport5.co.il/articles.aspx?...`) with `target="_blank"` and
  `rel="noopener noreferrer"`; every queue card has a direct "פתח את הדיווח" link too.
- **Queue → centre.** Tapping a queue story puts the same story in the centre field and scrolls
  to it on the phone.
- **Feedback.** "יותר כמו זה" posts `/api/me/feedback` (201).
- **Logout.** The account menu's "התנתקות" lands on `/login`, and `/` afterwards redirects to
  `/login` (the session is gone).

## 3. Defects, by priority

Severity: **P0** blocks daily use; **P1** badly degrades it; **P2** friction.

| # | Sev | Defect | Status |
|---|---|---|---|
| D1 | P0 | No always-on host | owner decision (milestone 13) |
| D2 | P0 | Password signup needs an email provider that does not exist | owner configuration |
| D3 | P1 | A stopped worker looks like a quiet day | **fix open: #356** (closes #249) |
| D4 | P1 | Feedback says "saved" when the save failed | **fix open: #358** (feedback half of #197) |
| D5 | P1 | A failed feed load shows the empty state and an English error | open |
| D6 | P1 | "Why you see this" exposes engine internals | open, copy decision |
| D7 | P1 | Touch targets under 44 px across the journey | open (#19) |
| D8 | P2 | Regular users' mobile dock shows "קונסולה", which only bounces back | **fix open: #357** (related to #20) |
| D9 | P2 | The thumbs-down menu cannot be closed by Escape or an outside tap | open |
| D10 | P2 | "מקורות מחו״ל" filter is always 0 | open |
| D11 | P2 | Internal identifiers on Preferences; English team names on Results | open |
| D12 | P2 | Calibration is long and dense on a phone | open |

### D1 (P0) — No always-on host

Nothing starts or restarts the API, Vite or the worker
([CURRENT_PROJECT_STATE.md](../CURRENT_PROJECT_STATE.md) §10). The father's phone can only
reach the app while Guy's PC runs all three, behind Tailscale. **Repro:** stop the API, open
the app from the phone. **Path:** milestone 13 (#267 decisions, #268 provision, #269
cutover), all waiting on owner decisions.

### D2 (P0) — Password signup needs an email provider

With `MAIL_BACKEND` unset, `POST /api/auth/signup` answers 503 and the page says
"לא ניתן לשלוח אימיילים כרגע, ולכן ההרשמה לא זמינה". `MAIL_BACKEND=console` (used here)
only writes the link into the API log, which works for a developer, not for the father. A host
needs `MAIL_BACKEND=smtp` with real `SMTP_*`, `MAIL_FROM` and an https `APP_PUBLIC_URL`
([DEPLOYMENT.md](../DEPLOYMENT.md), "Verification email"). Google sign-in is the other path and
is also off (no OAuth client configured). **Repro:** start the API without `MAIL_BACKEND` and
submit `/signup`. **Not fixed here, by design:** adding a mail service is out of scope. Until
a provider exists, the only no-new-service path on the PC is to run the API with
`MAIL_BACKEND=console` for the signup and hand the father the link from the API log (it is
valid for 24 hours and needs his password). No script creates a password account directly;
`backend/scripts/set_user_password.py` only resets an existing one.

### D3 (P1) — A stopped worker looks like a quiet day (#249)

The feed had no age line. When the worker stops, the 36 h window empties the feed and the empty
state says "המערכת סורקת את המקורות ברקע" — false. **Repro:** on the copy, the worker heartbeat
went stale 20 minutes after the backup; `/api/scheduler/health` (admin) said not running, while
the reader saw nothing ([m12](mvp-journey-2026-10-25/m12_feed_phone_top.png)).
**Fix (#356, open):** `GET /api/me/feed/freshness` plus one line over the feed, and a warning when ingestion
is not running ([after, stopped](mvp-journey-2026-10-25/fr_phone_stopped.png),
[after, empty and stopped](mvp-journey-2026-10-25/fr_phone_empty_stopped.png),
[after, running](mvp-journey-2026-10-25/fr_phone_running.png),
[desktop](mvp-journey-2026-10-25/fr_desktop_running.png)).

### D4 (P1) — Feedback says "saved" when the save failed (#197)

`FeedbackControls` showed "נשמר" on tap, and `AppContext.addFeedback` swallowed the failure.
**Repro:** answer `POST /api/me/feedback` with 500 (request interception) and tap "יותר כמו זה":
the card says "נשמר" ([before](mvp-journey-2026-10-25/f_05_feedback_failed_card.png)).
**Fix (#358, open):** "שומר…", then "נשמר" only on success; otherwise "לא נשמר" with "נסו שוב", which
retries the same action ([after, failed](mvp-journey-2026-10-25/fb_phone_failed.png),
[after, retried](mvp-journey-2026-10-25/fb_phone_retried.png)). Re-run in the browser: a
retry while the API still fails stays "לא נשמר"; after recovery it posts (201) and says
"נשמר". A failing "never show" is reported the same way.

### D5 (P1) — A failed feed load shows the empty state and an English error

**Repro:** answer `GET /api/me/feed` with 500. A red banner says
"שגיאה בחיבור לשרת …feed failed (500): boom" (raw English detail) and "נסה שוב", while the body
below shows the normal empty state, "אין סיגנלים חדשים — המערכת סורקת את המקורות ברקע"
([f08](mvp-journey-2026-10-25/f_08_error.png)). The reader is told both "error" and
"nothing new". **Suggested fix:** when the feed request failed, render an error body instead
of `EditionEmptyState`, and map the error to Hebrew copy without the raw detail.

### D6 (P1) — "Why you see this" exposes engine internals

The collapsed line reads "למה אצלך: ניקוד: 3 → חשוב". Expanded, it shows
"בסיס: עוקב (high) אחרי EuroLeague (via_team_membership: comp:euroleague) → 2 נק'",
"ישות במעקב בכתבה (Maccabi Tel Aviv Basketball) → +1" and "ראה קונסולת דיבאג לפירוט מלא"
([p02](mvp-journey-2026-10-25/p_02_why_expanded.png)). For the father this is noise, in two
languages. **Repro:** tap "למה אצלך" on any story. **Suggested fix:** a consumer phrasing
("כי את/ה עוקב/ת אחרי מכבי תל אביב") and the trace kept for Debug. A copy decision for the owner.

### D7 (P1) — Touch targets under 44 px (#19)

Measured with `getBoundingClientRect` at 390 px:

| Element | Size |
|---|---|
| Feed thumbs and "פתח את הדיווח" | 40×40 (26×26 and 28×28 on desktop) |
| Masthead account button | 32×32 |
| Thumbs-down menu "פחות כאלה" | 156×40 |
| "עוד 22 במסלול" | 332×42 |
| Login and signup inputs and submit | 342×36 |
| Interest chips (competitions, teams) | 28 px tall |
| Calibration answers, event presets | 26 px tall |
| "דלגו על הבחירה" | 76×16 |

The feed's primary action (44 px) and the dock rows (47 px) pass. **Suggested fix:** #19's
scope plus the onboarding and auth controls, which #19 does not list.

### D8 (P2) — "קונסולה" in a regular user's mobile dock (related to #20)

The product dock always ended with "קונסולה". For a non-admin, `RequireOpsRole` sends
`/sources` straight back to `/`, so the button did nothing visible
([before](mvp-journey-2026-10-25/m07_interests_step1.png)). The desktop masthead already hid it
(#54). **Fix (#357, open):** the dock uses the same `canEnterOpsShell` check
([after](mvp-journey-2026-10-25/dock_after_390.png)).

### D9 (P2) — The thumbs-down menu does not close

Once open, the "פחות כאלה / אל תראה לי יותר כאלה" menu stays open after Escape and after a tap
elsewhere, and it covers the button that opened it
([f06](mvp-journey-2026-10-25/f_06_suppress_popover.png)). **Repro:** tap the thumbs-down on a
queue card, press Escape, tap the page. **Suggested fix:** close on Escape and outside pointer
down, and keep the toggle reachable.

### D10 (P2) — "מקורות מחו״ל" is always 0

English sources are off in the Hebrew-only MVP, so the chip always filters to nothing
([p01](mvp-journey-2026-10-25/p_01_foreign_chip.png)). **Suggested fix:** hide a topic chip
whose count is 0.

### D11 (P2) — Internal identifiers and mixed languages

Preferences shows "פרופיל: אבא · סוג: self_serve". Results mixes Hebrew and English team names
in one fixture ("מכבי חיפה" against "Hapoel Be'er Sheva").

### D12 (P2) — Calibration is long and dense on a phone

18 headlines × 5 answers at 26 px, plus status jargon ("טיוטה", "גרסת מאגר 3")
([m11](mvp-journey-2026-10-25/m11_calibration_rated.png)). The teams step of onboarding is a
wall of about 70 chips ([step 3](mvp-journey-2026-10-25/m09_interests_step3.png)). Skipping
works and the feed is useful without calibration.

## 4. Fixes (one open PR each, branched from `origin/main`)

| PR | Branch | Fixes | Tests |
|---|---|---|---|
| #356 (closes #249) | `feat/feed-freshness-249` | D3 | backend `test_feed_freshness_signal_249.py` (401, two fields only, newest *successful* cycle, stale heartbeat, parity with `/api/scheduler/health` across five worker states) and the authz inventory; frontend `feedFreshnessModel.test.js` |
| #358 (related to #197) | `fix/honest-feedback-saves-197` | D4 (the feedback half of #197; the results-sync lease stays open) | `feedbackSaveModel.test.js` (a rejected save never reports "saved"; retry semantics) |
| #357 (related to #20) | `fix/mobile-dock-console-entry` | D8 | `navConfig.test.js` (new case; existing cases unchanged) |

All three: `npm run lint`, `typecheck`, `test` and `build` pass in `frontend/`. The backend
suite passed on the #249 branch (3,060 passed, 2 skipped) and on `origin/main`'s backend tree,
which the other two leave unchanged (3,051 passed, 2 skipped). None of them is merged.

## 5. What remains for the father's daily use

1. **A host that is always on** (D1): milestone 13, owner decisions first.
2. **An email provider or Google sign-in** (D2), or a one-off console-mailer signup on the PC.
3. **Honest error state** (D5) and **consumer "why" copy** (D6).
4. **Touch targets** (D7, #19), most of all in onboarding and on the auth forms.
5. **A real-phone pass** (#16): nothing in this audit ran on a physical device, Safari or
   Android Chrome.

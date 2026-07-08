# Calibration Apply — Design Notes

> **DEPRECATED (2026-07-08, issue #33):** superseded by `CALIBRATION_V2.md` — the frontend-only flow described here was removed.

## What This Is

PR 3 adds the ability to convert a calibration draft into a real (but isolated) user profile called the **sandbox profile**, and apply it to the feed without touching the existing Guy or Casual Deni Fan profiles.

## Why a Sandbox First

The calibration inference engine produces a best-guess profile from a limited number of ratings. That guess may be partially wrong:

- A user who rated 5 NBA headlines may not represent their full NBA preferences.
- The inferred mode (`followed_entities_only`, `titles_only`, `all`) is heuristic and may need correction.
- Muting decisions (e.g. muting all football) should be reviewed before being applied to a permanent profile.

The sandbox profile lets the user try the inferred profile against the real feed without committing to it. It is:

- Stored in React state only (no persistence)
- Never applied to Guy or Casual Deni Fan
- Easily reset with one click
- Automatically shown in the profile switcher when it exists

## Conversion Logic

`convertCalibrationDraftToUserProfile(draft)` in `src/engine/draftToProfile.js`:

1. Iterates over `draft.inferredTopics`
2. For each topic: maps `topicKey → topicId`, `league → leagues[]`, builds `eventRules` and `entityEventRules`
3. Sets `userId: "calibrated_sandbox"`, `profileType: "calibration_generated"`
4. Passes `draft.mutedCandidates` directly into `mutedTopics` (conservative — see below)
5. Passes `draft.followedEntities` directly into the profile

### entityEventRules Generation

For `followed_entities_only` topics (topics where the user positively rated entity-specific articles but negatively rated non-entity articles of the same sport/league):

- High-priority event rules (`push`, `high_feed`) are extracted into `entityEventRules[entityName]`
- This means: "for this entity specifically, apply these stronger decisions"
- Lower-priority rules (`feed`, `low_feed`, `hidden`) remain only in `eventRules` as fallbacks
- This is identical in structure to `entityEventRules` on Guy's NBA topic (introduced in PR 2.6)

Example: user rates Deni trade as push, Deni injury as interesting, Hornets/Wizards as not_interesting:

```json
{
  "topicId": "calibrated_basketball_nba",
  "mode": "followed_entities_only",
  "eventRules": {
    "major_trade": "push",
    "injury": "high_feed",
    "regular_season_result": "hidden"
  },
  "entityEventRules": {
    "Deni Avdija": {
      "major_trade": "push",
      "injury": "high_feed"
    },
    "Portland Trail Blazers": {
      "major_trade": "push"
    }
  }
}
```

For `all` mode topics: no `entityEventRules` are generated. The generic `eventRules` handle all filtering.

### Why No Legacy Keys

The old `deni_avdija_trade` and `deni_avdija_news` key pattern (removed in PR 2.6) is never generated. All entity-specific overrides live in `entityEventRules[entityName][eventType]`, which is explicit, composable, and doesn't couple event-type eligibility to naming conventions.

## Conservative Muting

Muting is only applied when:

1. **All ratings for a topic are negative** (`not_interesting` or `never_show`) — the user expressed zero interest in any article from this topic
2. **At least one `never_show` rating** — the user explicitly said "don't show me this"

The calibration engine handles this gate. `convertCalibrationDraftToUserProfile` passes `draft.mutedCandidates` directly into `mutedTopics` without any additional logic. This is intentionally conservative — we never add mutes beyond what the inference engine already flagged.

Muting is by **sport** (e.g. "football"), not by league. So rating all football articles negatively mutes the whole football sport for the sandbox profile.

## Profile Switcher Integration

The sandbox profile appears in the profile switcher only when it exists (after the user clicks "החל על פרופיל בדיקה"). It is marked with a "(בדיקה)" badge.

`AppContext` exposes:
- `sandboxProfile` — the current sandbox, or `null`
- `profileList` — dynamic list including sandbox when present
- `applySandboxProfile(profile)` — sets sandbox and switches to it
- `resetSandboxProfile()` — removes sandbox and switches back to Guy

`comparisonItems` in the debug/comparison view also includes the sandbox profile scores when it exists.

## Calibration Page UX

After rating headlines, the `InferenceDraftPanel` shows:
- Inferred topics with event rules
- Entity-specific rules preview for `followed_entities_only` topics
- Followed entities
- Muted candidates
- **"החל על פרופיל בדיקה"** button — enabled when topics were inferred, disabled otherwise
- On success: green confirmation + "עבור לפיד" link (note: Guy and Casual Deni Fan are unchanged)
- **"אפס פרופיל בדיקה"** button — shown whenever a sandbox exists

Re-rating headlines after apply resets `justApplied` state so the user can apply again.

## Limitations

- **No persistence** — sandbox is lost on page refresh
- **No editing** — the inferred profile cannot be manually tuned in the UI yet
- **Single sandbox** — re-applying overwrites the previous sandbox
- **No real article scoring validation** — the user cannot yet see why specific articles were scored for their sandbox profile before committing
- **No partial application** — the entire draft is applied as-is; individual topics cannot be accepted or rejected

## Next Steps

- Add persistence (localStorage) for the sandbox profile
- Allow manual editing of inferred event rules before applying
- Add per-article explanation in the feed for sandbox profile scores
- Allow promoting sandbox → named profile
- Support multiple saved calibration sessions

# Signal Sports — Synthetic Headline Calibration v0

## What it is

Synthetic headline calibration is a user onboarding mechanism that builds a personalized preference profile without asking the user to fill out structured forms or edit rule sets.

Instead, the system shows the user a set of realistic but fictional sports headlines. Each headline is pre-tagged internally with metadata: sport, league, entities, event type, importance. The user rates each headline. The system then infers a structured preference draft from the rating pattern.

The insight is that users do not think in terms of "topic priorities" or "event rules." They do know whether they find a given headline interesting. By collecting enough ratings, the system can reverse-engineer the rules that explain the pattern.

## Why it matters to the product

The main blocker to a personalized feed is the "cold start problem": the system does not know what a new user cares about. Without a preference profile, every article scores as noise.

Two wrong solutions:
1. Ask the user to fill out a settings form (most users will not do this)
2. Show a generic feed and hope (defeats the product's purpose)

Synthetic headline calibration solves the cold start without imposing a data entry burden. It turns preference elicitation into a quick rating task — closer to swiping than to form filling.

It also makes the system's logic visible: the user can see what the system inferred and correct it if wrong.

## Rating model

| Rating key | Hebrew label | Inferred decision | Meaning |
|---|---|---|---|
| `push` | תעדכן אותי מיד | `push` | I want to know immediately when this happens |
| `interesting` | מעניין | `high_feed` | I find this type of story interesting |
| `neutral` | סבבה, לא קריטי | `low_feed` | Fine to see occasionally, not critical |
| `not_interesting` | לא מעניין | `hidden` | I'd rather not see this |
| `never_show` | אל תראה לי כאלה | `hidden` + mute candidate | Strong suppression — this topic is not for me |

Users can also deselect a rating (toggle off) to return a headline to unrated state.

## How ratings map to inferred rules

### Event rules

For each rated headline, the inference engine extracts its `(sport, league, eventType)` and maps the rating to a decision level. When multiple headlines share the same topic and eventType, the highest-ranking rating wins (push > high_feed > feed > low_feed > hidden).

Example:
- Headline: "מכבי ת״א בשלבי מו״מ עם גארד יורוליגי" → rated `push`
- Inferred rule: `eventRules.negotiation = "push"` for EuroLeague basketball topic

### Topic mode

The engine detects structural patterns across the ratings for each topic:

**`followed_entities_only`**: Detected when positively-rated articles in a topic exclusively mention entities that do not appear in any negatively-rated articles. This indicates entity-focused rather than broad topic interest.

Example: "Deni Avdija trade" rated push + "Hornets vs Wizards" rated not_interesting → NBA topic in `followed_entities_only` mode, `followedEntities` includes Deni Avdija.

**`titles_only`**: Detected when all positively-rated articles are major-event types (grand_slam_winner, title_win, finals_result, star_trade) and all negatively-rated articles are non-major types.

Example: "Alcaraz wins Roland Garros" rated interesting + "Alcaraz first round" rated not_interesting → tennis in `titles_only` mode.

**`all`** (default): When the pattern is mixed or only one direction of ratings is present. Filtering is handled by event rules, not by mode restriction.

### Priority inference

Topic priority (0–100) is derived from the ratio of positively-rated articles:

| Positive ratio | Priority |
|---|---|
| ≥ 80% | 85 |
| 60–80% | 70 |
| 40–60% | 50 |
| 20–40% | 30 |
| < 20% | 15 |

### Followed entities

Entities are added to `followedEntities` when they appear in positively-rated articles but never in negatively-rated articles for the same topic. This identifies entities that explain the user's interest pattern.

### Muted candidates

A sport is flagged as a muted candidate when:
- All rated headlines for that sport are negative (`not_interesting` or `never_show`), OR
- At least one headline in that sport is rated `never_show`

Muted candidates are advisory suggestions — they do not automatically mute anything.

## Calibration headline dataset

28 synthetic headlines in `src/data/calibrationHeadlines.js`, covering:

| Sport | Scenarios |
|---|---|
| Basketball — Maccabi TLV | negotiation, signing, injury, candidate, interview, friendly match |
| Basketball — EuroLeague (non-Maccabi) | major signing, regular result, Final Four |
| Basketball — Israeli League (non-Maccabi) | title win, regular result preview |
| Basketball — NBA | Hornets/Wizards result, Deni trade, Deni injury, star trade, Finals, generic preview, record |
| Basketball — European domestic | ACB playoff, Greek derby, French LNB signing, Italian preview |
| Tennis | Grand Slam winner, early-round result, generic news |
| Football | Mbappe-level transfer, small Israeli result, schedule |

Each headline includes: id, title (Hebrew), sport, league, entities, eventType, importance, tags.

## What is implemented in v0

- Calibration headline dataset (28 headlines)
- Full rating model: 5 levels (push / interesting / neutral / not_interesting / never_show)
- Pure inference function: `inferPreferenceDraftFromCalibration(ratings, headlines)`
  - Event rule extraction per topic
  - Mode detection (followed_entities_only, titles_only, all)
  - Priority calculation
  - Followed entity inference
  - Muted candidate detection
- Calibration page (`/calibration`):
  - Hebrew RTL headline cards with metadata chips
  - 5 rating buttons per card (toggle on/off)
  - Sport filter chips (basketball / football / tennis / all)
  - Live progress bar (rated X / total)
  - Live inference preview panel (updates as user rates)
  - Rating legend
  - Reset button
- Navigation item: "כיוונון" (Sliders icon) between Preferences and Sources
- 16 Vitest test cases covering all inference scenarios

## What is intentionally not implemented yet

- **Apply button is disabled.** The draft is a preview only. Applying inferred preferences to a real profile requires additional UX to let the user review and confirm before overwriting.
- **No persistence.** Ratings are stored in React local state. Refreshing the page clears them.
- **No profile-awareness.** The calibration is not tied to a specific profile yet. Applying the draft to Guy vs. Casual Deni Fan requires a merge/replace strategy.
- **No entity disambiguation.** Team entities (e.g., Portland Trail Blazers) may appear in `followedEntities` alongside player entities (Deni Avdija) when they co-appear in positively-rated articles. A future version should distinguish player vs. team entities.
- **Single eventType per topic.** If the same eventType appears in multiple headlines for the same topic with different ratings, the higher rating wins. A weighted average could be more accurate but adds complexity.
- **No cluster/deduplication.** Multiple headlines covering the same story (e.g., two sources reporting the same Maccabi negotiation) are treated as independent data points.
- **No LLM.** All inference is rule-based. This is intentional for v0 — the logic is fully testable, deterministic, and auditable.

## Inference function contract

```js
inferPreferenceDraftFromCalibration(
  ratings:   { [headlineId: string]: RatingKey },
  headlines: CalibrationHeadline[]
) → InferenceDraft

InferenceDraft = {
  inferredTopics: Array<{
    topicKey: string,       // "sport::league"
    label: string,          // Hebrew display name
    sport: string,
    league: string | null,
    priority: number,       // 0–100
    mode: string,           // "all" | "followed_entities_only" | "titles_only"
    entities: string[],     // entities from positively-rated articles
    eventRules: { [eventType]: decision },
    reasoning: string[]     // Hebrew explanation lines
  }>,
  followedEntities: string[],
  mutedCandidates: string[],
  reasoning: string[]       // top-level Hebrew reasoning
}
```

## Future next steps

1. **Apply draft with confirmation UX.** Show the inferred topics side-by-side with the current profile and let the user approve, reject, or tweak each rule before applying.

2. **Persist ratings.** Store ratings in localStorage so the calibration survives page refresh and can be resumed across sessions.

3. **Expand headline dataset.** Add more headlines to reduce ambiguity. 28 headlines may not cover enough combinations for reliable mode detection on niche interests.

4. **Entity disambiguation.** Track player vs. team entities separately to avoid adding team names to `followedEntities` when only a player is of interest.

5. **Iterative refinement.** After the initial calibration, use ongoing feed feedback (more like this / not interesting) to continue updating the preference profile.

6. **LLM-assisted preference extraction.** Eventually, the inferred draft can be sent to an LLM to produce a more nuanced and natural-language-explained preference profile. The rule-based v0 serves as both the MVP and the baseline to compare against.

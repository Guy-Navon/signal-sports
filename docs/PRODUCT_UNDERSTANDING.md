# Signal Sports — Product Understanding

## What Signal Sports Is Trying to Become

Signal Sports is a personalized sports news intelligence feed. The key word is *intelligence*. This is not a sports news aggregator that collects articles from multiple sources and shows them all. It is a system that understands what a specific person cares about, and surfaces only the subset of sports news that is actually worth their time.

The product answer one question: **"What sports news is worth this user's attention right now?"** Not "what sports news exists," and not "what sports news is objectively important."

The distinction matters. A blockbuster NFL trade is objectively important news. It may reach front pages everywhere. But for a user who follows only Israeli basketball and Deni Avdija, it is noise. The same article — "Deni Avdija negotiating a contract extension" — would be urgent for a Deni fan, moderately interesting for a basketball power user, and invisible to a football-only follower.

The product is successful only when the feed feels like it was curated specifically for that user, and not one article more than what that user genuinely wants to see.

## Why It Is Different From a Generic Sports News Feed

A generic sports feed aggregates. It collects articles from sources and shows them, perhaps ranked by recency or global importance. The user sees everything and filters manually by visiting specific sections or using search.

Signal Sports inverts this model. The filter happens before delivery, not after. The user never has to open 7 sports websites, scan through 40 headlines, and manually identify the 3 that matter. The system does that filtering automatically, per person.

Differences from existing alternatives:

| Generic feed | Signal Sports |
|---|---|
| Same feed for all users | Unique feed per user profile |
| Sorted by recency or "importance" | Sorted by personal relevance |
| User must filter manually | System filters before showing |
| Every article has the same status | Each article has a decision: hidden, low, normal, high, or push |
| No explanation for why an item appears | Each item can explain why it was shown |
| No deduplication logic | Clustered duplicate stories shown as one |
| User has no way to tune the feed | Feed adapts from feedback, calibration, preferences |

The deeper difference is the relevance engine. Signal Sports separates three concerns that generic feeds collapse into one:

1. **Article classification** — what is this article about? (sport, league, entities, event type, importance)
2. **User preference matching** — does this user care about this topic?
3. **Final relevance decision** — and if they do, how much? push, high_feed, feed, low_feed, or hidden?

These are different problems. Mixing them makes the system brittle. Keeping them separate makes it testable, explainable, and tunable.

## What the Personalization Engine Must Eventually Do

The personalization engine is the core product. Everything else is infrastructure around it.

### Article Understanding

Every article must be classified. Not just "sport = football" but:
- Which sport, which league, which teams, which players
- What type of event is this? A signing, a negotiation, a rumor, a result, a major trade, an interview, a Grand Slam winner, an injury?
- How important is this event, globally speaking?
- How confident is the system in this classification?

This classification is the input to scoring. Without correct classification, even perfect user preferences produce wrong feed decisions.

### User Interest Representation

User interests must be structured, not flat. A user does not just "follow basketball." They may follow Maccabi Tel Aviv basketball at near-maximum priority, follow the NBA broadly but not obsessively, care about EuroLeague in general, and want to hear only about Grand Slam tennis winners.

Each topic in a user's profile needs:
- A priority level
- A mode (show everything, show only major events, show only if entity is involved, etc.)
- A list of specific event rules (signing → push, pre-match → hidden, etc.)
- Entity lists (which teams or players elevate the significance of an article)

The preference model must be expressive enough to encode these nuanced, topic-specific rules.

### Dynamic, Per-User Scoring

The same article must be able to produce different decisions for different users. This is non-negotiable. If an article has a single "relevance score" that is user-independent, the system is not doing its job.

The scoring pipeline must:
1. Take an article's classification
2. Take a user's preference profile
3. Return a decision (hidden / low_feed / feed / high_feed / push) with a full explanation

Push must be rare. It means "stop what you are doing and read this." If more than a handful of articles per day reach push, push loses meaning.

### How User Interests Are Collected

User preferences should not require users to fill out structured forms. People do not think in JSON. Three paths must eventually exist:

**Path 1: Natural Language Input**
A user writes: "I care a lot about Maccabi Tel Aviv basketball, especially signings and negotiations. I broadly follow the NBA. I care about tennis only when a Grand Slam is won. Football is noise for me."
The system converts this free text into a structured preference profile using an LLM.

**Path 2: Synthetic Headline Calibration**
The user is shown a set of pre-tagged synthetic headlines and rates them (push / interesting / not interesting / never show this). Because the headlines are already tagged with metadata internally, the system can infer preferences from the ratings.

Example: if the user marks "Maccabi Tel Aviv signs a new guard" as push-worthy, the system learns negotiation/signing events for Maccabi basketball should be push. If they mark "Alcaraz wins Roland Garros" as interesting but "Alcaraz reaches third round" as not interesting, the system infers titles_only mode for tennis.

**Path 3: Ongoing Feedback Loop**
After onboarding, every item in the feed should support actions: "more like this," "never show this again," "mute this source," "this should have been push." These feedback events should update the user's profile over time.

The key product insight is that a user should never need to manually edit JSON-style topic rules. The system should infer them from behavior.

## What the Current MVP Should Prove

The MVP does not need real sources, real scraping, backend persistence, or production-ready infrastructure. What it needs to prove is:

1. **The scoring model is correct.** Given an article's metadata, the engine produces the right decision for the right user. The same article scores differently for different profiles. Push is rare and intentional. Hidden articles are genuinely irrelevant.

2. **The debug view is honest.** Every decision must come with a complete, accurate explanation. The reasoning chain must reflect the actual scoring logic, not a post-hoc story.

3. **Profile diversity works.** The Guy profile and the Casual Deni Fan profile should produce meaningfully different feeds from the same article set. If both profiles see roughly the same articles, the personalization is not working.

4. **The preference model is expressive.** The user profile structure must be rich enough to encode topics like "EuroLeague at high priority, but for Maccabi-related stories treat it as push, not just high_feed." 

5. **The feed is low noise.** If the feed shows 40 out of 41 articles as feed-or-above, the engine is not filtering. The feed should surface the articles that actually matter and aggressively hide the rest.

## What Should Not Be Built Yet (as of the original MVP scoping)

The following were explicitly out of scope when this document was first written. **Status update — most of this has since been built; see `docs/CURRENT_PROJECT_STATE.md` for current, authoritative state:**

- ~~Real RSS or scraping from live sources~~ — **done.** Walla Sport + Israel Hayom Sport are live RSS sources; Sport5 is a working HTML-scraping pilot (disabled by default).
- ~~Backend server, database, or API layer~~ — **done.** FastAPI + SQLite, `backend/app/`.
- User authentication or accounts — **built (User Platform, 2026-07-10):** email/password accounts, cookie sessions, session-derived `/api/me/*`, fail-closed admin gating. The two seeded demo profiles remain permanent QA fixtures alongside real accounts.
- Push notifications to devices — **still not built.** `push` is a decision level only; no device delivery.
- ~~Natural language processing / LLM-based classification~~ — **done.** Deterministic classifier + optional LLM overlay (Gemini/Ollama) with 7 merge guardrails; see `docs/LLM_CLASSIFICATION.md`.
- Natural language preference input (free text → structured profile) — **still not built.** This is Option 1 from the personalization section above; only Option 2 (synthetic headline calibration) has a working screen (`Calibration.jsx`) and Option 3 (feedback loop) records events but doesn't yet mutate profiles.
- Production deployment — **still not applicable.** Local dev only.
- ~~Multi-language translation engine~~ — **built, but intentionally disabled.** `backend/app/translation/` is intact (Claude/Fake/Noop providers); `TRANSLATION_PROVIDER=disabled` is correct for the current Hebrew-only MVP. Re-enable when English sources (Eurohoops, Sportando) return.
- Real clustering algorithm (TF-IDF, semantic similarity, time windowing) — **still not built.** Dedup is URL-only; `cluster_id` exists on the model but nothing populates it. This is the most-cited "still fake" gap across every audit pass.

The original reasoning still holds for what's left: don't build feedback-driven learning or fuzzy clustering on top of an unvalidated scoring engine. The scoring engine and classification pipeline are now validated (1081 backend tests); the remaining gaps (auth, push delivery, NL preference input, feedback→profile mutation, real clustering) are genuine product features, not scaffolding risk.

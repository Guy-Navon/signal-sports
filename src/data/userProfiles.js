// User preference profiles
// Guy = basketball power user
// Casual Deni Fan = follows NBA only when Deni Avdija is involved

export const userProfiles = {
  guy: {
    userId: "guy",
    displayName: "Guy",
    language: "he",
    profileType: "basketball_power_user",
    topics: [
      // ── Maccabi TLV Basketball (highest priority) ─────────────
      // push: official signing, confirmed negotiation/serious interest, major injury, title win
      // high_feed: candidates/rumors, playoff results
      // feed: match summaries, interviews, analysis
      // low_feed: friendly matches
      {
        topicId: "maccabi_tel_aviv_basketball",
        label: "מכבי ת״א כדורסל",
        sport: "basketball",
        priority: 100,
        mode: "all",
        leagues: ["Israeli Basketball League", "EuroLeague"],
        entities: ["Maccabi Tel Aviv Basketball", "Oded Katash"],
        eventRules: {
          // push: confirmed actions only
          signing: "push",             // official signing confirmed
          major_signing: "push",       // official signing confirmed
          negotiation: "push",         // confirmed serious negotiation (not rumor)
          injury: "push",              // player injury
          title_win: "push",           // championship win
          // high_feed: strong interest but not confirmed
          candidate: "high_feed",      // interest/monitoring — NOT push
          rumor: "high_feed",          // rumor level — NOT push
          playoff_result: "high_feed",
          // feed: regular content
          match_result: "feed",
          match_summary: "feed",
          regular_season_result: "feed",
          interview: "feed",
          analysis: "feed",
          opinion: "feed",
          // low_feed / hidden
          friendly_match: "low_feed",
          pre_match: "hidden",
          schedule: "hidden",
          generic_preview: "hidden"
        }
      },

      // ── NBA ───────────────────────────────────────────────────
      // push: Deni trade, confirmed blockbuster star trade, title win
      // high_feed: finals, major injury, playoff
      // feed: regular season result, record (unless Deni-related)
      // low_feed: generic preview
      // hidden: nothing by default
      {
        topicId: "nba",
        label: "NBA",
        sport: "basketball",
        priority: 90,
        mode: "all",
        leagues: ["NBA"],
        entities: ["Deni Avdija"],
        eventRules: {
          // push — only the most significant events
          star_trade: "push",              // blockbuster NBA star trade
          deni_avdija_trade: "push",       // any trade involving Deni Avdija — always push for Guy
          major_trade: "high_feed",        // major trade (non-star, non-Deni) — high_feed, not push
          title_win: "push",               // NBA champion
          // high_feed
          finals_result: "high_feed",
          playoff_result: "high_feed",
          injury: "feed",                  // generic NBA injury — feed not high_feed
          signing: "feed",
          major_signing: "high_feed",
          record: "high_feed",
          // feed
          regular_season_result: "feed",
          match_result: "feed",
          match_summary: "feed",
          interview: "feed",
          analysis: "feed",
          // low_feed / hidden
          generic_preview: "low_feed",
          schedule: "hidden"
        }
      },

      // ── EuroLeague ────────────────────────────────────────────
      // push: Maccabi-related major transfer (handled by entity boost in engine)
      //       EuroLeague title win
      // high_feed: other major EuroLeague signings/transfers, playoffs, Final Four
      // feed: regular results, match summaries, interviews
      // low_feed: generic previews
      {
        topicId: "euroleague",
        label: "יורוליג",
        sport: "basketball",
        priority: 95,
        mode: "all",
        leagues: ["EuroLeague"],
        entities: ["Maccabi Tel Aviv Basketball"],
        eventRules: {
          // Maccabi-specific push rules are handled by maccabi_tel_aviv_basketball topic above
          // For non-Maccabi EuroLeague:
          signing: "high_feed",
          major_signing: "high_feed",
          negotiation: "high_feed",
          major_transfer: "high_feed",      // general EL major transfer = high_feed (not push)
          candidate: "feed",
          injury: "feed",
          match_result: "feed",
          match_summary: "feed",
          regular_season_result: "feed",
          playoff_result: "high_feed",
          final_four: "high_feed",
          title_win: "push",
          interview: "feed",
          analysis: "feed",
          opinion: "feed",
          generic_preview: "low_feed",
          schedule: "hidden"
        }
      },

      // ── Israeli Basketball League ─────────────────────────────
      // Non-Maccabi Israeli basketball
      {
        topicId: "israeli_basketball",
        label: "כדורסל ישראלי",
        sport: "basketball",
        priority: 85,
        mode: "all",
        leagues: ["Israeli Basketball League"],
        entities: [],
        eventRules: {
          signing: "feed",
          major_signing: "high_feed",
          negotiation: "feed",
          candidate: "feed",
          injury: "feed",
          match_result: "feed",
          regular_season_result: "feed",
          match_summary: "feed",
          playoff_result: "high_feed",
          title_win: "high_feed",          // non-Maccabi title = high_feed, not push
          interview: "feed",
          analysis: "feed",
          opinion: "feed",
          friendly_match: "low_feed",
          generic_preview: "low_feed",
          schedule: "hidden"
        }
      },

      // ── European Domestic Basketball ──────────────────────────
      // Spanish ACB, Turkish BSL, Greek, Italian, French
      // high_importance_only: only titles, playoff finals, EuroLeague-related moves
      // Generic regular season = always hidden
      {
        topicId: "major_european_domestic_basketball",
        label: "ליגות כדורסל בכירות באירופה",
        sport: "basketball",
        priority: 65,
        mode: "high_importance_only",
        leagues: ["Spanish ACB", "Turkish BSL", "Greek Basket League", "Italian LBA", "French LNB"],
        entities: [],
        eventRules: {
          major_match_result: "feed",       // major derby, etc.
          playoff_result: "feed",
          title_win: "high_feed",
          major_signing: "feed",
          euroleague_related_transfer: "high_feed",
          // all these are explicitly hidden
          regular_season_result: "hidden",
          generic_regular_season_result: "hidden",
          match_result: "hidden",
          generic_preview: "hidden",
          schedule: "hidden"
        }
      },

      // ── Football ─────────────────────────────────────────────
      // major_only mode: only big events surface at all
      // No football ever reaches push for Guy
      {
        topicId: "football",
        label: "כדורגל",
        sport: "football",
        priority: 20,
        mode: "major_only",
        leagues: [],
        entities: [],
        eventRules: {
          major_transfer: "feed",
          title_win: "feed",
          major_match_result: "low_feed",
          match_summary: "low_feed",
          // all below are hidden
          regular_season_result: "hidden",
          generic_regular_season_result: "hidden",
          match_result: "hidden",
          generic_preview: "hidden",
          schedule: "hidden",
          interview: "hidden",
          opinion: "hidden",
          analysis: "hidden"
        }
      },

      // ── Tennis ────────────────────────────────────────────────
      // titles_only mode: Grand Slam winner = high_feed, everything else hidden
      {
        topicId: "tennis",
        label: "טניס",
        sport: "tennis",
        priority: 25,
        mode: "titles_only",
        leagues: [],
        entities: [],
        eventRules: {
          grand_slam_winner: "high_feed",
          grand_slam_final: "feed",
          early_round_result: "hidden",
          generic_news: "hidden",
          match_result: "hidden",
          regular_season_result: "hidden",
          analysis: "hidden",
          schedule: "hidden"
        }
      }
    ],
    mutedTopics: [],
    mutedSources: [],
    followedEntities: ["Maccabi Tel Aviv Basketball", "Deni Avdija", "Oded Katash"]
  },

  casual_deni_fan: {
    userId: "casual_deni_fan",
    displayName: "אוהד דני קז׳ואל",
    language: "he",
    profileType: "casual_entity_follower",
    topics: [
      // ── Only NBA, only when Deni is involved ─────────────────
      // push: Deni trade (confirmed)
      // high_feed: Deni strong performance, Deni news
      // feed: Deni-adjacent (NBA finals, if Deni's team involved)
      // Everything else = hidden
      {
        topicId: "nba",
        label: "NBA",
        sport: "basketball",
        priority: 45,
        mode: "followed_entities_only",
        leagues: ["NBA"],
        entities: ["Deni Avdija"],
        eventRules: {
          // Deni-specific entity rules
          deni_avdija_trade: "push",
          deni_avdija_news: "high_feed",
          // Generic event rules (apply after entity check)
          regular_season_result: "feed",     // Deni's game result
          match_result: "feed",
          match_summary: "feed",
          injury: "high_feed",               // if Deni is injured = high_feed
          major_trade: "push",               // if Deni involved in major trade
          star_trade: "high_feed",           // if entity-matched (Deni's team trade)
          finals_result: "feed",
          playoff_result: "feed",
          record: "high_feed",
          interview: "feed",
          analysis: "feed",
          generic_preview: "hidden",
          schedule: "hidden",
          signing: "hidden",
          // catch-all for any Deni-related news
          followed_entity_news: "high_feed"
        }
      }
    ],
    mutedTopics: [],
    mutedSources: [],
    followedEntities: ["Deni Avdija"]
  }
};

export const profileList = [
  { id: "guy", label: "Guy" },
  { id: "casual_deni_fan", label: "אוהד דני קז׳ואל" }
];
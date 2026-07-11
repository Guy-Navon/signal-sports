// Pure logic for the explicit-interest picker (issues #82/#83,
// docs/INTERESTS.md). No React, no fetch — node-testable like
// onboardingFlow.js. Components stay thin over this module.
//
// A "follow" is { scope, target_id, starred } — the exact wire shape of
// PUT /api/me/interests (tier→level mapping is server-side, #77).

// ── Follow-set operations ─────────────────────────────────────────────────────

export function followKey(follow) {
  return `${follow.scope}:${follow.target_id}`;
}

export function isFollowed(follows, scope, targetId) {
  return follows.some((f) => f.scope === scope && f.target_id === targetId);
}

// Tap gesture: add at Follow tier, or remove if already present.
// NEVER adds parent scopes (the no-implicit-parents contract).
export function toggleFollow(follows, scope, targetId) {
  if (isFollowed(follows, scope, targetId)) {
    return follows.filter((f) => !(f.scope === scope && f.target_id === targetId));
  }
  return [...follows, { scope, target_id: targetId, starred: false }];
}

// Star gesture: flips starred on an existing follow; a star on an
// unfollowed scope follows it starred (one gesture, no dead taps).
export function toggleStar(follows, scope, targetId) {
  if (!isFollowed(follows, scope, targetId)) {
    return [...follows, { scope, target_id: targetId, starred: true }];
  }
  return follows.map((f) =>
    f.scope === scope && f.target_id === targetId
      ? { ...f, starred: !f.starred }
      : f,
  );
}

export function buildPutPayload(follows, eventPreferences) {
  return {
    follows: follows.map(({ scope, target_id, starred }) => ({
      scope, target_id, starred: Boolean(starred),
    })),
    eventPreferences: Object.fromEntries(
      Object.entries(eventPreferences || {}).filter(([, v]) => v !== "normal"),
    ),
  };
}

// ── Catalog projections (progressive disclosure) ──────────────────────────────

export function competitionsForSport(catalog, sportId) {
  const sport = (catalog?.sports || []).find((s) => s.id === sportId);
  return sport ? sport.competitions : [];
}

// Teams shown on step 3: members of any followed competition, plus every
// team of a followed sport that has no followed competition yet (so a
// sport-only user still sees teams to pick).
export function teamsForSelection(catalog, follows) {
  const teams = catalog?.teams || [];
  const followedComps = new Set(
    follows.filter((f) => f.scope === "competition").map((f) => f.target_id),
  );
  const followedSports = new Set(
    follows.filter((f) => f.scope === "sport").map((f) => f.target_id),
  );
  const sportsWithComps = new Set();
  for (const team of teams) {
    if (team.memberships.some((m) => followedComps.has(m))) {
      sportsWithComps.add(team.sport);
    }
  }
  return teams.filter((team) => {
    if (!team.selectable) return false;
    if (team.memberships.some((m) => followedComps.has(m))) return true;
    return followedSports.has(team.sport) && !sportsWithComps.has(team.sport);
  });
}

export function peopleForSelection(catalog, follows) {
  const followedSports = new Set(
    follows.filter((f) => f.scope === "sport").map((f) => f.target_id),
  );
  const followedComps = new Set(
    follows.filter((f) => f.scope === "competition").map((f) => f.target_id),
  );
  const teamsById = new Map((catalog?.teams || []).map((t) => [t.id, t]));
  return (catalog?.people || []).filter((p) => {
    if (!p.selectable) return false;
    if (followedSports.has(p.sport)) return true;
    const team = p.team_id ? teamsById.get(p.team_id) : null;
    return Boolean(team && team.memberships.some((m) => followedComps.has(m)));
  });
}

// ── Global search (all selectable items, Hebrew + English) ────────────────────

function matches(query, item) {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return false;
  const haystacks = [
    item.display_he, item.display_en, ...(item.aliases || []),
  ];
  return haystacks.some((h) => h && h.toLowerCase().includes(q));
}

// Flat search across sports, selectable competitions, teams, and people —
// independent of the disclosure state (a user can follow Hapoel TLV bb
// without ever selecting basketball). Returns picker-ready entries.
export function searchCatalog(catalog, query) {
  if (!catalog || !query || query.trim().length < 2) return [];
  const results = [];
  for (const sport of catalog.sports || []) {
    if (matches(query, sport)) {
      results.push({ scope: "sport", item: sport });
    }
    for (const comp of sport.competitions) {
      if (comp.selectable && matches(query, comp)) {
        results.push({ scope: "competition", item: comp, sport: sport.id });
      }
    }
  }
  for (const team of catalog.teams || []) {
    if (team.selectable && matches(query, team)) {
      results.push({ scope: "team", item: team });
    }
  }
  for (const person of catalog.people || []) {
    if (person.selectable && matches(query, person)) {
      results.push({ scope: "player", item: person });
    }
  }
  return results.slice(0, 12);
}

// ── Parent suggestions (suggest, NEVER auto-create) ───────────────────────────

// After following a narrow scope, suggest its parents as one-tap chips.
// Returns suggestions NOT already followed; mutates nothing.
export function parentSuggestions(catalog, follows) {
  const suggestions = new Map();
  const teamsById = new Map((catalog?.teams || []).map((t) => [t.id, t]));
  const compMeta = new Map();
  for (const sport of catalog?.sports || []) {
    for (const comp of sport.competitions) {
      compMeta.set(comp.id, { comp, sport: sport.id });
    }
  }

  const addComp = (compId) => {
    const meta = compMeta.get(compId);
    if (meta && meta.comp.selectable && !isFollowed(follows, "competition", compId)) {
      suggestions.set(`competition:${compId}`,
        { scope: "competition", item: meta.comp });
    }
  };
  const addSport = (sportId) => {
    const sport = (catalog?.sports || []).find((s) => s.id === sportId);
    if (sport && !isFollowed(follows, "sport", sportId)) {
      suggestions.set(`sport:${sportId}`, { scope: "sport", item: sport });
    }
  };

  for (const follow of follows) {
    if (follow.scope === "team") {
      const team = teamsById.get(follow.target_id);
      if (team) {
        if (team.domestic_competition) addComp(team.domestic_competition);
        addSport(team.sport);
      }
    } else if (follow.scope === "player") {
      const person = (catalog?.people || []).find((p) => p.id === follow.target_id);
      const team = person?.team_id ? teamsById.get(person.team_id) : null;
      if (team?.domestic_competition) addComp(team.domestic_competition);
      if (person) addSport(person.sport);
    } else if (follow.scope === "competition") {
      const meta = compMeta.get(follow.target_id);
      if (meta) addSport(meta.sport);
    }
  }
  return [...suggestions.values()].slice(0, 4);
}

// ── Event preset groups (mirrors interests_service.EVENT_PRESET_GROUPS) ──────

export const EVENT_PRESET_GROUPS = [
  { id: "transfers_rumors", label: "העברות ושמועות" },
  { id: "injuries", label: "פציעות" },
  { id: "results", label: "תוצאות משחקים" },
  { id: "interviews_features", label: "ראיונות וכתבות עומק" },
  { id: "schedules_previews", label: "לוחות זמנים ותצוגות מקדימות" },
];

export const PRESET_STATES = [
  { id: "less", label: "פחות" },
  { id: "normal", label: "רגיל" },
  { id: "more", label: "יותר" },
];

// ── Provenance display (issue #83) ────────────────────────────────────────────

export const SOURCE_LABELS = { calibration: "מכויל", learned: "נלמד" };

export const LEVEL_LABELS = {
  "-2": "לא לראות בכלל",
  "-1": "עניין נמוך",
  0: "עניין בינוני",
  1: "עניין גבוה",
  2: "עניין מאוד גבוה",
};

// Scope affinities the interests surface does NOT manage: calibration- and
// learning-derived entries, plus negative explicit levels (seed nuance).
// Shown read-only with provenance labels — never silently editable as
// explicit (docs/INTERESTS.md managed-subset contract).
export function nonExplicitEntries(profileV2) {
  return (profileV2?.scope_affinities || []).filter(
    (a) => a.source !== "explicit" || a.level < 0,
  );
}

export function displayNameFor(catalog, scope, targetId) {
  if (scope === "sport") {
    const sport = (catalog?.sports || []).find((s) => s.id === targetId);
    return sport?.display_he || targetId;
  }
  if (scope === "competition") {
    for (const sport of catalog?.sports || []) {
      const comp = sport.competitions.find((c) => c.id === targetId);
      if (comp) return comp.display_he;
    }
    return targetId;
  }
  const pool = scope === "team" ? catalog?.teams : catalog?.people;
  const item = (pool || []).find((e) => e.id === targetId);
  return item?.display_he || targetId;
}

// ── Document ↔ picker state ───────────────────────────────────────────────────

export function documentToState(doc) {
  return {
    follows: (doc?.follows || []).map(({ scope, target_id, starred }) => ({
      scope, target_id, starred: Boolean(starred),
    })),
    eventPreferences: { ...(doc?.event_preferences || {}) },
  };
}

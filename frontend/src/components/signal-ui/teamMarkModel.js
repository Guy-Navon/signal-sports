// Which team a story row's mark shows (#592). Pure: built on teamIdentity()
// (#591) over the article's own entity list. The mark never infers a team from
// headline text; when the entities don't name one or two coloured teams it
// falls back to a neutral sport glyph, and abstains when the sport is unknown.
import { contrast } from "./contrastMath";
import { teamIdentity } from "./teamIdentity";

/** Two jerseys fit the slot; three or more read as a league story. */
const MAX_TEAMS = 2;

/**
 * @typedef {{
 *   teamId: string,
 *   sport: string,
 *   displayHe: string,
 *   primary: string,
 *   secondary: string,
 *   number: string|null,
 *   personDisplayHe: string|null,
 * }} MarkTeam
 * @typedef {{ kind: "teams", teams: MarkTeam[] } | { kind: "sport", sport: "basketball"|"football" } | null} TeamMarkModel
 */

/**
 * @param {{ entities?: string[], sport?: string }} article
 * @returns {TeamMarkModel}
 */
export function teamMarkFor(article) {
  /** @type {Map<string, Omit<MarkTeam, "primary"|"secondary"> & { primary: string|null, secondary: string|null }>} */
  const teams = new Map();
  for (const ref of article?.entities ?? []) {
    const identity = typeof ref === "string" ? teamIdentity(ref) : null;
    if (!identity) continue;
    const person = identity.personDisplayHe;
    const known = teams.get(identity.teamId);
    if (known) {
      // The club already appears (as itself or through another player): keep
      // one jersey and carry the first named player's number onto it.
      if (person && !known.personDisplayHe) {
        known.personDisplayHe = person;
        known.number = identity.number;
      }
      continue;
    }
    teams.set(identity.teamId, {
      teamId: identity.teamId,
      sport: identity.sport,
      displayHe: identity.displayHe,
      primary: identity.primary,
      secondary: identity.secondary,
      number: identity.number,
      personDisplayHe: person,
    });
  }

  const chosen = [...teams.values()];
  if (chosen.length >= 1 && chosen.length <= MAX_TEAMS && chosen.every((team) => team.primary && team.secondary)) {
    return { kind: "teams", teams: /** @type {MarkTeam[]} */ (chosen) };
  }
  const sport = article?.sport;
  return sport === "basketball" || sport === "football" ? { kind: "sport", sport } : null;
}

/**
 * The colour the jersey number is drawn in: the team's secondary when it
 * contrasts at least 3:1 with the body (non-text graphic, WCAG 1.4.11),
 * otherwise whichever of white and black contrasts more.
 * @param {string} primary
 * @param {string|null} secondary
 * @returns {string}
 */
export function numberInk(primary, secondary) {
  if (secondary && contrast(primary, secondary) >= 3) return secondary;
  return contrast(primary, "#FFFFFF") >= contrast(primary, "#000000") ? "#FFFFFF" : "#000000";
}

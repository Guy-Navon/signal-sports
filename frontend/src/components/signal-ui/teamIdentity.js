// Team identity lookup for the feed's team mark (#591, drawn by #592).
// Data: teamIdentity.generated.json, written by
// backend/scripts/generate_taxonomy_export.py. Colours are facts and are never
// adjusted here; visibility on each ground belongs to the mark.
import identity from "../../data/teamIdentity.generated.json";

/**
 * @typedef {{ sport: string, display_he: string, primary: string|null, secondary: string|null, code: string|null }} TeamEntry
 * @typedef {{ kind: string, display_he: string, team_id: string, number: string|null }} PersonEntry
 */

/** @type {Record<string, TeamEntry>} */
const TEAMS = identity.teams;
/** @type {Record<string, PersonEntry>} */
const PEOPLE = identity.people;
/** @type {Record<string, string>} */
const LEGACY = identity.legacy_name_to_id;

/**
 * Resolve an entity id or legacy name to the identity of the team it belongs to.
 * @param {string} ref
 * @returns {{ teamId: string, sport: string, displayHe: string, primary: string|null, secondary: string|null, code: string|null, number: string|null, personId: string|null, personDisplayHe: string|null } | null}
 */
export function teamIdentity(ref) {
  const id = Object.hasOwn(TEAMS, ref) || Object.hasOwn(PEOPLE, ref) ? ref : LEGACY[ref];
  if (!id) return null;
  const person = Object.hasOwn(PEOPLE, id) ? PEOPLE[id] : null;
  const teamId = person ? person.team_id : id;
  const team = Object.hasOwn(TEAMS, teamId) ? TEAMS[teamId] : null;
  if (!team) return null;
  return {
    teamId,
    sport: team.sport,
    displayHe: team.display_he,
    primary: team.primary,
    secondary: team.secondary,
    code: team.code ?? null,
    number: person ? person.number : null,
    personId: person ? id : null,
    personDisplayHe: person ? person.display_he : null,
  };
}

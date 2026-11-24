import React, { useId } from "react";
import { numberInk } from "./teamMarkModel";

// Team mark (#592, design Guy 2026-11-24 "C + jersey"): three parts drawn from
// one teamMarkFor() model, all for the first team only.
//   TeamEdge  a two-colour bar on the row's inline-start edge;
//   TeamMark  a jersey beside the headline, drawn by us (never an image or a
//             logo): tank top for basketball, sleeved shirt for football, with
//             side panels, trim, shading and the player number or team code;
//   TeamChip  a colour dot and the player's or team's name at the start of the
//             meta line, then "· גם <second team>".
// Each renders nothing when the model abstains. The outlines use
// --sg-mark-edge, so the shapes show on every ground whatever the colours are.
// See docs/FRONTEND_DESIGN_SYSTEM.md, "Team mark (#592)".

/**
 * Shapes in a 40×44 box: the outline, the neckline and armhole trim, and the
 * side panels (x, y, width, height), which are clipped to the body.
 */
const TANK = {
  body: "M11 2.5h5.2c.6 4.6 2 6.6 3.8 6.6s3.2-2 3.8-6.6H29v3.4c.5 6.3 3 9.4 8 10.1V40a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V16c5-.7 7.5-3.8 8-10.1z",
  trim: "M16.2 2.5c.6 4.6 2 6.6 3.8 6.6s3.2-2 3.8-6.6M29 5.9c.5 6.3 3 9.4 8 10.1M11 5.9c-.5 6.3-3 9.4-8 10.1",
  panels: [[3, 16, 3.2, 26], [33.8, 16, 3.2, 26]],
};
const SHIRT = {
  body: "M14 2.5c1.5 3.2 3.5 4.6 6 4.6s4.5-1.4 6-4.6l12 6-3.5 9-4.5-2V40a2 2 0 0 1-2 2H12a2 2 0 0 1-2-2V15.5l-4.5 2-3.5-9z",
  trim: "M14 2.5c1.5 3.2 3.5 4.6 6 4.6s4.5-1.4 6-4.6M38 8.5l-3.5 9M2 8.5l3.5 9",
  panels: [[10, 15.5, 3.2, 27], [26.8, 15.5, 3.2, 27]],
};

/** @typedef {import("./teamMarkModel").TeamMarkModel} TeamMarkModel */
/** @typedef {import("./teamMarkModel").MarkTeam} MarkTeam */

/** @param {MarkTeam} team */
function teamName(team) {
  return team.number ? `${team.displayHe} · ${team.number}` : team.displayHe;
}

/** @param {MarkTeam} team */
function teamColours(team) {
  return /** @type {React.CSSProperties} */ ({ "--sg-team-p": team.primary, "--sg-team-s": team.secondary });
}

/**
 * The jersey beside the headline: the first team's, with its number when one
 * is known, otherwise its code, otherwise a plain chest.
 * @param {{ mark: TeamMarkModel, className?: string }} props
 */
export default function TeamMark({ mark, className = "" }) {
  const id = useId().replace(/:/g, "");
  if (!mark) return null;
  const [team] = mark.teams;
  const football = team.sport === "football";
  const shape = football ? SHIRT : TANK;
  const label = team.number ?? team.code;
  const name = teamName(team);
  return (
    <svg
      className={`sg-mark ${className}`.trim()}
      role="img"
      aria-label={name}
      viewBox="0 0 40 44"
      width="38"
      height="42"
    >
      <title>{name}</title>
      <defs>
        <linearGradient id={`${id}-shade`} x1="0" x2="1">
          <stop offset="0" stopColor="#000" stopOpacity="0.18" />
          <stop offset="0.25" stopColor="#000" stopOpacity="0" />
          <stop offset="0.75" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.18" />
        </linearGradient>
        <clipPath id={`${id}-body`}>
          <path d={shape.body} />
        </clipPath>
      </defs>
      <g data-shape={football ? "shirt" : "tank"}>
        <path d={shape.body} fill={team.primary} />
        <g clipPath={`url(#${id}-body)`}>
          {shape.panels.map(([x, y, width, height]) => (
            <rect key={x} x={x} y={y} width={width} height={height} fill={team.secondary} />
          ))}
          <rect x="0" y="0" width="40" height="44" fill={`url(#${id}-shade)`} />
        </g>
        <path d={shape.trim} fill="none" stroke={team.secondary} strokeWidth="3" />
        {label && (
          <text
            x="20"
            y="31"
            textAnchor="middle"
            fontSize={label.length > 2 ? "10.5" : "15"}
            fontWeight="800"
            letterSpacing="0.3"
            fill={numberInk(team.primary, team.secondary)}
            direction="ltr"
          >
            {label}
          </text>
        )}
        <path className="sg-mark__edge" d={shape.body} fill="none" strokeWidth="1" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

/**
 * The colour bar on the row's inline-start edge: primary, then secondary.
 * Decorative; the jersey and the chip carry the name.
 * @param {{ mark: TeamMarkModel }} props
 */
export function TeamEdge({ mark }) {
  if (!mark) return null;
  return <span className="sg-edge" aria-hidden={true} style={teamColours(mark.teams[0])} />;
}

/**
 * The name at the start of the meta line: the followed player's name when the
 * story is about one, otherwise the team's; a second team follows by name.
 * @param {{ mark: TeamMarkModel }} props
 */
export function TeamChip({ mark }) {
  if (!mark) return null;
  const [team, second] = mark.teams;
  return (
    <span className="sg-chip">
      <span className="sg-chip__dot" aria-hidden={true} style={teamColours(team)} />
      <bdi>{team.personDisplayHe ?? team.displayHe}</bdi>
      {second && <span className="sg-chip__also">· גם {second.displayHe}</span>}
    </span>
  );
}

import React from "react";
import { numberInk } from "./teamMarkModel";

// Team mark (#592): a jersey drawn by us, never an image or a logo. A tank top
// for basketball, a sleeved shirt for football; body in the team's primary,
// neckline and arm trim in its secondary, the outline in --sg-mark-edge so the
// shape shows on every ground whatever the team colours are. With no team to
// show it is a neutral sport glyph; with no sport either it renders nothing.
// See docs/FRONTEND_DESIGN_SYSTEM.md, "Team mark (#592)".

/** Jerseys are drawn in a 40×44 box. */
const TANK = {
  body: "M9 2H15Q15 10 20 10Q25 10 25 2H31Q31 13 36 16V40.5Q36 42 34.5 42H5.5Q4 42 4 40.5V16Q9 13 9 2Z",
  trim: ["M15 2Q15 10 20 10Q25 10 25 2", "M31 2Q31 13 36 16", "M9 2Q9 13 4 16"],
};
const SHIRT = {
  body: "M14 2Q20 7 26 2L38 8.5L34.5 17.5L30 15.5V40.5Q30 42 28.5 42H11.5Q10 42 10 40.5V15.5L5.5 17.5L2 8.5Z",
  trim: ["M14 2Q20 7 26 2", "M38 8.5L34.5 17.5", "M2 8.5L5.5 17.5"],
};

const SPORT_HE = { basketball: "כדורסל", football: "כדורגל" };

/** @param {{ teamId: string, displayHe: string, number: string|null }} team */
function teamName(team) {
  return team.number ? `${team.displayHe} · ${team.number}` : team.displayHe;
}

/** @param {{ team: import("./teamMarkModel").MarkTeam, transform?: string }} props */
function Jersey({ team, transform = undefined }) {
  const shape = team.sport === "football" ? SHIRT : TANK;
  return (
    <g transform={transform} data-shape={team.sport === "football" ? "shirt" : "tank"}>
      <path d={shape.body} fill={team.primary} />
      {shape.trim.map((d) => (
        <path key={d} d={d} fill="none" stroke={team.secondary} strokeWidth="2.5" strokeLinecap="round" />
      ))}
      {team.number && (
        <text
          x="20"
          y="33"
          textAnchor="middle"
          fontSize="14"
          fontWeight="800"
          fill={numberInk(team.primary, team.secondary)}
          direction="ltr"
        >
          {team.number}
        </text>
      )}
      <path className="sg-mark__edge" d={shape.body} fill="none" strokeWidth="1.25" strokeLinejoin="round" />
    </g>
  );
}

/** Neutral 24 px glyphs, Lucide-style (2 px stroke, round caps), in --sg-dim. */
function SportGlyph({ sport }) {
  return (
    <g fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      {sport === "football" ? (
        <path d="M12 7l4.75 3.45-1.8 5.6h-5.9l-1.8-5.6ZM12 7V2M16.75 10.45l4.75-1.55M14.95 16.05l2.9 4M9.05 16.05l-2.9 4M7.25 10.45 2.5 8.9" />
      ) : (
        <path d="M12 2v20M2 12h20M5.6 4.3c2.3 2 3.4 4.6 3.4 7.7s-1.1 5.7-3.4 7.7M18.4 4.3c-2.3 2-3.4 4.6-3.4 7.7s1.1 5.7 3.4 7.7" />
      )}
    </g>
  );
}

/**
 * @param {{ mark: import("./teamMarkModel").TeamMarkModel, className?: string }} props
 */
export default function TeamMark({ mark, className = "" }) {
  if (!mark) return null;
  if (mark.kind === "sport") {
    const label = SPORT_HE[mark.sport];
    return (
      <svg className={`sg-mark sg-mark--glyph ${className}`.trim()} role="img" aria-label={label} viewBox="0 0 24 24" width="24" height="24">
        <title>{label}</title>
        <SportGlyph sport={mark.sport} />
      </svg>
    );
  }
  const label = mark.teams.map(teamName).join(" ו");
  const [first, second] = mark.teams;
  return (
    <svg
      className={`sg-mark ${second ? "sg-mark--pair" : ""} ${className}`.replace(/\s+/g, " ").trim()}
      role="img"
      aria-label={label}
      viewBox={second ? "0 0 44 44" : "0 0 40 44"}
      width={second ? 44 : 40}
      height="44"
    >
      <title>{label}</title>
      {second ? (
        // Two 30 px jerseys overlapping. The first-named team sits on the
        // right and in front, where an RTL reader starts.
        <>
          <Jersey team={second} transform="translate(0 14) scale(0.68)" />
          <Jersey team={first} transform="translate(16.8 0) scale(0.68)" />
        </>
      ) : (
        <Jersey team={first} />
      )}
    </svg>
  );
}

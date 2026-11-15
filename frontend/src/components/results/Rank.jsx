import React from "react";

// "(17)" after a team name: the parentheses stay in the RTL context, only the digits are isolated.
export default function Rank({ value }) {
  if (value == null) return null;
  return <span className="sr-rank">(<bdi dir="ltr">{value}</bdi>)</span>;
}

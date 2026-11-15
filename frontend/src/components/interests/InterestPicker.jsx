import React, { useMemo } from "react";
import { Check, Sparkles } from "lucide-react";
import "./interests.css";
import FollowChip from "@/components/interests/FollowChip";
import CatalogSearch from "@/components/interests/CatalogSearch";
import {
  competitionsForSport,
  isFollowed,
  parentSuggestions,
  peopleForSelection,
  teamsForSelection,
  toggleFollow,
  toggleStar,
} from "@/components/interests/interestsModel";

// The shared interest picker (issues #82/#83). All logic lives in
// interestsModel.js; this component renders chips over it.
//
// variant="onboarding": renders ONE step at a time (step prop: sports |
// competitions | teams). variant="manage" (#83): renders all sections flat.
// Both share the global search and the parent-suggestion strip.
//
// Contract: selections NEVER create parent scopes implicitly — parents are
// suggested as one-tap chips only.

function Section({ title, children }) {
  return (
    <div className="sg-interest-section">
      {title && <h3>{title}</h3>}
      <div className="sg-interest-options">{children}</div>
    </div>
  );
}

function SportCards({ catalog, follows, onToggle }) {
  return (
    <div className="sg-sport-options">
      {(catalog?.sports || []).map((sport) => {
        const followed = isFollowed(follows, "sport", sport.id);
        return (
          <button
            key={sport.id}
            type="button"
            onClick={() => onToggle("sport", sport.id)}
            className="sg-sport-option"
            aria-pressed={followed}
          >
            <bdi dir="auto">{sport.display_he}</bdi>
            {followed && <Check size={18} aria-hidden="true" />}
          </button>
        );
      })}
    </div>
  );
}

export default function InterestPicker({
  catalog,
  follows,
  onFollowsChange,
  variant = "manage",
  step = null, // onboarding: "sports" | "competitions" | "teams"
}) {
  const handleToggle = (scope, targetId) =>
    onFollowsChange(toggleFollow(follows, scope, targetId));
  const handleStar = (scope, targetId) =>
    onFollowsChange(toggleStar(follows, scope, targetId));

  const followedSports = follows.filter((f) => f.scope === "sport");
  const teams = useMemo(
    () => teamsForSelection(catalog, follows),
    [catalog, follows],
  );
  const people = useMemo(
    () => peopleForSelection(catalog, follows),
    [catalog, follows],
  );
  const suggestions = useMemo(
    () => parentSuggestions(catalog, follows),
    [catalog, follows],
  );

  const showSports = variant === "manage" || step === "sports";
  const showComps = variant === "manage" || step === "competitions";
  const showTeams = variant === "manage" || step === "teams";

  const compSports = showComps
    ? (variant === "manage"
        ? (catalog?.sports || []).map((s) => s.id)
        : followedSports.map((f) => f.target_id))
    : [];

  return (
    <div className="sg-interest-picker">
      <CatalogSearch catalog={catalog} follows={follows} onPick={handleToggle} />

      {suggestions.length > 0 && (
        <div className="sg-interest-suggestions">
          <Sparkles size={16} aria-hidden="true" />
          <span>אולי תרצו לעקוב גם:</span>
          {suggestions.map(({ scope, item }) => (
            <button
              key={`${scope}:${item.id}`}
              type="button"
              onClick={() => handleToggle(scope, item.id)}
              className="sg-form-button"
            >
              + <bdi dir="auto">{item.display_he}</bdi>
            </button>
          ))}
        </div>
      )}

      {showSports && (
        <SportCards catalog={catalog} follows={follows} onToggle={handleToggle} />
      )}

      {showComps &&
        compSports.map((sportId) => {
          const sport = (catalog?.sports || []).find((s) => s.id === sportId);
          if (!sport) return null;
          return (
            <Section key={sportId} title={sport.display_he}>
              {competitionsForSport(catalog, sportId).map((comp) => {
                const followed = follows.find(
                  (f) => f.scope === "competition" && f.target_id === comp.id,
                );
                return (
                  <FollowChip
                    key={comp.id}
                    label={comp.display_he}
                    selectable={comp.selectable}
                    followed={Boolean(followed)}
                    starred={Boolean(followed?.starred)}
                    onToggle={() => handleToggle("competition", comp.id)}
                    onStar={() => handleStar("competition", comp.id)}
                  />
                );
              })}
            </Section>
          );
        })}
      {showComps && compSports.length === 0 && <p className="sg-form-empty">בחרו ענף כדי לראות ליגות, או חפשו ליגה ישירות.</p>}

      {showTeams && (
        <>
          {teams.length === 0 && people.length === 0 && <p className="sg-form-empty">בחרו ענף או ליגה כדי לראות קבוצות ושחקנים. אפשר גם לחפש ישירות.</p>}
          {teams.length > 0 && (
            <Section title="קבוצות">
              {teams.map((team) => {
                const followed = follows.find(
                  (f) => f.scope === "team" && f.target_id === team.id,
                );
                return (
                  <FollowChip
                    key={team.id}
                    label={team.display_he}
                    followed={Boolean(followed)}
                    starred={Boolean(followed?.starred)}
                    onToggle={() => handleToggle("team", team.id)}
                    onStar={() => handleStar("team", team.id)}
                  />
                );
              })}
            </Section>
          )}
          {people.length > 0 && (
            <Section title="שחקנים ואנשים">
              {people.map((person) => {
                const followed = follows.find(
                  (f) => f.scope === "player" && f.target_id === person.id,
                );
                return (
                  <FollowChip
                    key={person.id}
                    label={person.display_he}
                    followed={Boolean(followed)}
                    starred={Boolean(followed?.starred)}
                    onToggle={() => handleToggle("player", person.id)}
                    onStar={() => handleStar("player", person.id)}
                  />
                );
              })}
            </Section>
          )}
        </>
      )}
    </div>
  );
}

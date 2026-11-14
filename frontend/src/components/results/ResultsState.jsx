import React from "react";

export default function ResultsState({ icon: Icon, title, hint, action = null, role = undefined }) {
  return (
    <section className="sg-results-page__state" role={role}>
      <Icon size={20} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{hint}</p>
      {action}
    </section>
  );
}

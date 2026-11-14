import React from "react";
import "./personalization.css";

// Consumer-only wrappers. Shared console primitives keep their own appearance.
export function PersonalizationHeader({ title, subtitle, icon: Icon, level = 1 }) {
  const Heading = level === 2 ? "h2" : "h1";
  return (
    <header className="sg-personalization__header">
      {level === 1 && <p className="sg-personalization__eyebrow">הפיד שלך, לפי מה שחשוב לך</p>}
      <Heading>{Icon && <Icon size={22} aria-hidden="true" />}{title}</Heading>
      {subtitle && <p>{subtitle}</p>}
    </header>
  );
}

export function PersonalizationSection({ title = null, icon: Icon = null, children }) {
  return (
    <section className="sg-form-section">
      {title && <h2>{Icon && <Icon size={18} aria-hidden="true" />}{title}</h2>}
      {children}
    </section>
  );
}

export function PersonalizationStat({ label, value }) {
  return <div className="sg-form-stat"><b><bdi dir="auto">{value}</bdi></b><span>{label}</span></div>;
}

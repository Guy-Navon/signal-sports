/**
 * Debug: story-cluster evidence (#104) — docs/CLUSTERING.md §10.
 *
 * Makes a wrong cluster VISIBLE. Three roles can be three different articles, and Debug is
 * the only place that shows all of them plus the members the user's preferences suppressed:
 *
 *   corpus representative — global, user-independent (§9.1 ladder)
 *   displayed member      — the representative if visible, else the best visible member
 *   priority member       — the visible member whose decision SET the card decision
 *   suppressed members    — hidden for this user; NEVER present in the consumer payload
 *
 * It also proves the core invariant: the card's decision (MAX over visible members) is
 * shown alongside the displayed ARTICLE's own decision, which clustering never changes.
 */

import { clusterDebugRoles } from "@/components/feed/clusterModel";

function Row({ label, children }) {
  return (
    <div className="flex items-start gap-2 py-0.5">
      <span className="w-28 shrink-0 text-text-dim">{label}</span>
      <span className="min-w-0 text-text-secondary break-words">{children}</span>
    </div>
  );
}

function MemberList({ members, testid, muted = false }) {
  if (!members?.length) return <span className="text-text-dim">—</span>;
  return (
    <ul data-testid={testid} className="space-y-0.5">
      {members.map(m => (
        <li key={m.articleId} className={muted ? "text-text-dim" : undefined}>
          <span className="tabular-nums">{m.decision}</span>
          {" · "}
          <span>{m.sourceDisplayName}</span>
          {" · "}
          <span>{m.title}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ClusterEvidence({ item }) {
  const roles = clusterDebugRoles(item);
  if (!roles) return null;

  return (
    <div
      data-testid="cluster-evidence"
      className="mt-3 rounded-lg border border-border/60 bg-surface-1/40 p-3 text-xs leading-relaxed"
    >
      <div className="mb-2 font-semibold text-text-secondary">אשכול סיפור</div>

      <Row label="מזהה אשכול">
        <code data-testid="cluster-id">{roles.clusterId}</code>
      </Row>
      <Row label="גרסת חוק">
        {roles.ruleVersion ?? "—"}
        {roles.eventState ? ` · ${roles.eventState}` : ""}
      </Row>

      <Row label="נציג קורפוס">
        <code data-testid="cluster-representative">{roles.representativeArticleId ?? "—"}</code>
      </Row>
      <Row label="חבר מוצג">
        <code data-testid="cluster-displayed">{roles.displayedArticleId}</code>
        {" — "}
        {roles.displayedReasonLabel}
      </Row>
      <Row label="חבר מכריע">
        <code data-testid="cluster-priority">{roles.priorityArticleId}</code>
      </Row>

      <Row label="החלטת כרטיס">
        <span data-testid="cluster-card-decision">{roles.cardDecision}</span>
        <span className="text-text-dim"> (מקסימום מבין החברים הגלויים)</span>
      </Row>
      <Row label="החלטת כתבה">
        <span data-testid="cluster-article-decision">{roles.articleDecision}</span>
        <span className="text-text-dim"> (ללא שינוי מהאשכול)</span>
      </Row>

      <Row label={`חברים גלויים (${roles.visibleMembers.length})`}>
        <MemberList members={roles.visibleMembers} testid="cluster-visible-members" />
      </Row>
      <Row label="חברים מוסתרים">
        <MemberList members={roles.suppressedMembers} testid="cluster-suppressed-members" muted />
      </Row>
    </div>
  );
}

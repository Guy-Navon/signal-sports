import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { canEnterOpsShell } from "@/context/dataRouting";
import { consumerDockItems } from "@/components/shell/productShellModel";

// Phone navigation of the consumer product (under 768px, where the top bar
// drops its links): a bottom bar within thumb reach, every destination one tap
// away, 56px tall targets. Hidden from 768px up by shell.css.
export default function ProductDock({ isBackendMode }) {
  const location = useLocation();
  const auth = useAuth();
  const showConsoleEntry = canEnterOpsShell({
    isBackendMode,
    authEnforced: auth.authEnforced,
    user: auth.user,
  });
  const items = consumerDockItems({ isBackendMode, showConsoleEntry });

  return (
    <nav aria-label="ניווט ראשי" className="signal-ui sg-dock">
      <div className="sg-dock__list">
        {items.map(({ path, label, icon: Icon }) => (
          <Link
            key={path}
            to={path}
            aria-current={location.pathname === path ? "page" : undefined}
            className="sg-dock__link"
          >
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
          </Link>
        ))}
      </div>
    </nav>
  );
}

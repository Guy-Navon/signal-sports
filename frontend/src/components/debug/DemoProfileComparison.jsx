import React, { useMemo } from "react";
import { useApp } from "@/context/AppContext";
import { computeProfileComparison } from "@/context/localDemo";
import ProfileComparisonTable from "@/components/debug/ProfileComparisonTable";

// Debug's compare tab in local (demo) mode: mock articles across the demo
// profiles. Computed only while the tab is open (#199).
export default function DemoProfileComparison() {
  const { allProfiles, profiles, disabledSourceIds } = useApp();
  const items = useMemo(
    () => computeProfileComparison(allProfiles, disabledSourceIds),
    [allProfiles, disabledSourceIds]
  );
  return <ProfileComparisonTable items={items} profiles={profiles} />;
}

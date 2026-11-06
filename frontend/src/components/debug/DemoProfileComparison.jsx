import React, { useMemo } from "react";
import { useApp } from "@/context/AppContext";
import { computeProfileComparison, userProfiles } from "@/context/localDemo";
import ProfileComparisonTable from "@/components/debug/ProfileComparisonTable";

// Debug's compare tab. Mock articles and the seed profiles in both data modes, as
// it always was; loaded and computed only while the tab is open (#199).
export default function DemoProfileComparison() {
  const { allProfiles, profiles, disabledSourceIds } = useApp();
  const items = useMemo(
    () => computeProfileComparison({ ...userProfiles, ...allProfiles }, disabledSourceIds),
    [allProfiles, disabledSourceIds]
  );
  return <ProfileComparisonTable items={items} profiles={{ ...userProfiles, ...profiles }} />;
}

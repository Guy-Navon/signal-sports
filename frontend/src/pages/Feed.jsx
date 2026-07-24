import React, { useState, useMemo } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { SlidersHorizontal } from "lucide-react";
import { useApp } from "@/context/AppContext";
import EditionHeader from "@/components/feed/EditionHeader";
import SignalSpectrum from "@/components/feed/SignalSpectrum";
import SignalBoard from "@/components/feed/SignalBoard";
import TopicFilters from "@/components/feed/TopicFilters";
import LeadStory from "@/components/feed/LeadStory";
import BulletinStrip from "@/components/feed/BulletinStrip";
import EditorialTier from "@/components/feed/EditorialTier";
import StreamRow from "@/components/feed/StreamRow";
import BriefsDigest from "@/components/feed/BriefsDigest";
import SectionHeading from "@/components/feed/SectionHeading";
import EditionSkeleton from "@/components/feed/EditionSkeleton";
import EmptyState from "@/components/shared/EmptyState";
import EditionEmptyState from "@/components/feed/EditionEmptyState";
import { useAuth } from "@/context/AuthContext";
import { showCalibrateEmptyState } from "@/context/onboardingFlow";
import MonoValue from "@/components/shared/MonoValue";
import { composeEdition } from "@/components/feed/editionComposer";
import { editionVariants, rowPresence } from "@/components/feed/motionPresets";
import {
  getVisibleItems,
  filterFeedItems,
  toggleFilterSet,
} from "@/components/feed/feedFilters";

// The Feed as an edition: the ranked visible items are partitioned into
// editorial tiers (lead "הסיפור המרכזי" / bulletins / "במוקד" / "עוד מהפיד" /
// "קריאה נוספת") so the page's *shape* encodes relevance. Desktop composition:
// the lead is a full-width front page; below it the editorial column runs
// beside a sticky desk index (lg+). Filtering collapses the edition
// into a flat level-annotated list; clearing it recomposes the edition.
export default function Feed() {
  const { feedItems, debugItems, activeProfileId, activeProfile, isBackendMode, isLoading } =
    useApp();
  const auth = useAuth();
  // PR 4 (#52): uncalibrated consumer sessions get the calibrate CTA species
  // instead of the generic quiet-sources moment.
  const emptyStateVariant = showCalibrateEmptyState(auth) ? "calibrate" : "default";
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));
  const reduce = useReducedMotion();
  const v = useMemo(() => editionVariants(reduce), [reduce]);

  const visibleItems = useMemo(() => getVisibleItems(feedItems), [feedItems]);

  const decisionCounts = useMemo(() => {
    const c = { push: 0, high_feed: 0, feed: 0, low_feed: 0 };
    for (const item of visibleItems) {
      const d = item.score?.decision;
      if (d in c) c[d] += 1;
    }
    return c;
  }, [visibleItems]);

  const edition = useMemo(() => composeEdition(visibleItems), [visibleItems]);

  const isUnfiltered = activeFilters.has("all");
  const filteredItems = useMemo(
    () => filterFeedItems(visibleItems, activeFilters),
    [visibleItems, activeFilters]
  );

  const toggleFilter = (id) => setActiveFilters((prev) => toggleFilterSet(prev, id));
  const resetFilters = () => setActiveFilters(new Set(["all"]));

  // Loading state (backend mode, first fetch)
  if (isBackendMode && isLoading && visibleItems.length === 0) {
    return (
      <div className="mx-auto max-w-[1320px]">
        <EditionSkeleton />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1320px] min-w-0 overflow-hidden">
      {/* Keyed by profile: switching readers re-composes and re-reveals the edition. */}
      <motion.div
        key={activeProfileId || "none"}
        variants={v.container}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={v.item}>
          <EditionHeader
            profileName={activeProfile?.displayName}
            total={visibleItems.length}
            scanned={debugItems.length}
          />
        </motion.div>

        {/* The edition meter is always above the fold: hierarchy is a primary
            navigation surface, not a wide-screen-only dashboard. */}
        <motion.div
          variants={v.item}
          className="mt-5 border-y border-foreground/25 py-3 md:flex md:items-start md:justify-between md:gap-8"
        >
          <SignalSpectrum
            counts={decisionCounts}
            activeFilters={activeFilters}
            onToggle={toggleFilter}
            className="md:min-w-[360px] md:flex-1"
          />
          <TopicFilters
            activeFilters={activeFilters}
            onToggle={toggleFilter}
            onReset={resetFilters}
            className="mt-3 md:mt-0 md:max-w-[44%] md:justify-end"
          />
        </motion.div>

        {visibleItems.length === 0 ? (
          <motion.div variants={v.item}>
            <EditionEmptyState variant={emptyStateVariant} />
          </motion.div>
        ) : (
          <AnimatePresence mode="wait" initial={false}>
            {isUnfiltered ? (
              <motion.div
                key="edition"
                variants={v.container}
                initial="hidden"
                animate="show"
                exit={{ opacity: 0, transition: { duration: 0.15 } }}
              >
                {/* Full-width hero band */}
                {edition.lead && (
                  <motion.div variants={v.headline} className="mt-4 md:mt-6">
                    <LeadStory item={edition.lead} />
                  </motion.div>
                )}

                {edition.bulletins.length > 0 && (
                  <motion.div variants={v.item} className="mt-4 space-y-1.5">
                    {edition.bulletins.map((item) => (
                      <BulletinStrip key={item.id} item={item} />
                    ))}
                  </motion.div>
                )}

                {/* Editorial column + signal board (xl) */}
                <div className="mt-9 lg:grid lg:grid-cols-[minmax(0,1fr)_280px] lg:gap-12 xl:gap-16">
                  <div className="min-w-0">
                    {edition.editorial.length > 0 && (
                      <EditorialTier
                        items={edition.editorial}
                        variants={v.item}
                        headingVariants={v.item}
                      />
                    )}

                    {edition.stream.length > 0 && (
                      <motion.section
                        variants={v.item}
                        aria-label="עוד מהפיד"
                        className={edition.editorial.length > 0 ? "mt-10 md:mt-14" : ""}
                      >
                        <SectionHeading className="mb-2">עוד מהפיד</SectionHeading>
                        <div className="divide-y divide-border/40">
                          {edition.stream.map((item) => (
                            <StreamRow key={item.id} item={item} />
                          ))}
                        </div>
                      </motion.section>
                    )}

                    {edition.briefs.length > 0 && (
                      <motion.div variants={v.item} className="mt-10 md:mt-14">
                        <BriefsDigest items={edition.briefs} />
                      </motion.div>
                    )}
                  </div>

                  <motion.aside variants={v.item} className="hidden lg:block">
                    <div className="sticky top-24">
                      <SignalBoard
                        items={visibleItems}
                        scanned={debugItems.length}
                      />
                    </div>
                  </motion.aside>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="filtered"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, transition: { duration: 0.15 } }}
                className="mt-8 max-w-4xl"
              >
                {/* On xl the spectrum lives in the signal board, which belongs
                    to the edition view — surface it here so levels can still
                    be toggled while filtering. */}
                <SectionHeading
                  count={filteredItems.length}
                  className="mb-3"
                  action={
                    <button
                      onClick={resetFilters}
                      className="text-xs text-signal-high hover:text-signal-high/80 transition-colors flex-shrink-0"
                    >
                      חזרה למהדורה המלאה
                    </button>
                  }
                >
                  מסונן
                </SectionHeading>

                {filteredItems.length === 0 ? (
                  <EmptyState
                    icon={SlidersHorizontal}
                    title="אין פריטים תואמים לסינון"
                    hint="נסה להסיר חלק מהמסננים כדי לראות יותר סיפורים."
                    action={
                      <button
                        onClick={resetFilters}
                        className="text-sm text-signal-high hover:text-signal-high/80 transition-colors"
                      >
                        הצג הכל
                      </button>
                    }
                  />
                ) : (
                  <div className="divide-y divide-border/40">
                    <AnimatePresence mode="popLayout" initial={false}>
                      {filteredItems.map((item) => (
                        <motion.div key={item.id} layout {...rowPresence(reduce)}>
                          <StreamRow item={item} showLevelDot />
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                )}

                <p className="mt-6 text-xs text-text-dim">
                  מציג <MonoValue>{filteredItems.length}</MonoValue> מתוך{" "}
                  <MonoValue>{visibleItems.length}</MonoValue> סיפורים במהדורה
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </motion.div>
    </div>
  );
}

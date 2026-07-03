import React from "react";
import { Flame } from "lucide-react";
import ArticleCard from "@/components/feed/ArticleCard";

// The lead story: an eyebrow label above an enlarged ArticleCard. Used for the
// single most relevant item (top push, else top high_feed) at the top of the feed.
export default function FeedHero({ item }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5 text-xs font-medium text-signal-push">
        <Flame size={13} />
        הסיפור המוביל עבורך
      </div>
      <ArticleCard item={item} hero index={0} />
    </div>
  );
}

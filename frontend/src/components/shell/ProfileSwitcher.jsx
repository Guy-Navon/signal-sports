import React from "react";
import { ChevronDown, User } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { SANDBOX_PROFILE_ID } from "@/context/AppContext";
import { cn } from "@/lib/utils";
import PulseDot from "@/components/shared/PulseDot";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";

export default function ProfileSwitcher({ inverted = false }) {
  const { activeProfileId, setActiveProfileId, activeProfile, profileList } = useApp();

  return (
    <DropdownMenu dir="rtl">
      <DropdownMenuTrigger asChild>
        <button
          className={cn(
            "flex items-center gap-2 border px-2.5 py-1.5 text-sm transition-colors",
            inverted
              ? "border-background/20 bg-transparent text-background hover:border-background/50"
              : "border-border bg-surface-2 text-foreground hover:bg-surface-3"
          )}
        >
          <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center bg-signal-high/15">
            <User size={11} className={inverted ? "text-background" : "text-signal-high"} />
          </div>
          <span className="hidden sm:inline">{activeProfile?.displayName}</span>
          <ChevronDown size={13} className={inverted ? "text-background/55" : "text-text-secondary"} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[190px] bg-surface-2 border-border">
        <DropdownMenuLabel className="text-xs text-text-dim font-normal">
          החלף פרופיל
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="bg-border" />
        {profileList.map((profile) => {
          const isActive = activeProfileId === profile.id;
          const isSandbox = profile.id === SANDBOX_PROFILE_ID;
          return (
            <DropdownMenuItem
              key={profile.id}
              onSelect={() => setActiveProfileId(profile.id)}
              className={cn(
                "gap-2 cursor-pointer",
                isActive ? "text-signal-high focus:text-signal-high" : "text-foreground"
              )}
            >
              <PulseDot tone={isActive ? "high" : "neutral"} />
              <span className="flex-1">{profile.label}</span>
              {isSandbox && (
                <span className="text-[9px] bg-signal-ai/10 border border-signal-ai/30 text-signal-ai rounded px-1.5 py-0.5">
                  בדיקה
                </span>
              )}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

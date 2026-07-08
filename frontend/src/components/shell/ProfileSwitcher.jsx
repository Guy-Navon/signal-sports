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

export default function ProfileSwitcher() {
  const { activeProfileId, setActiveProfileId, activeProfile, profileList } = useApp();

  return (
    <DropdownMenu dir="rtl">
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 bg-surface-2 hover:bg-surface-3 border border-border rounded-lg px-3 py-1.5 text-sm transition-colors">
          <div className="w-5 h-5 rounded-full bg-signal-high/15 border border-signal-high/30 flex items-center justify-center flex-shrink-0">
            <User size={11} className="text-signal-high" />
          </div>
          <span className="text-foreground">{activeProfile?.displayName}</span>
          <ChevronDown size={13} className="text-text-secondary" />
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

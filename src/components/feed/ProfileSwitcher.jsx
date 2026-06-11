import React, { useState, useRef, useEffect } from "react";
import { ChevronDown, User } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { profileList } from "@/data/userProfiles";

export default function ProfileSwitcher() {
  const { activeProfileId, setActiveProfileId, activeProfile } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-1.5 text-sm transition-colors"
      >
        <div className="w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
          <User size={11} className="text-emerald-400" />
        </div>
        <span className="text-gray-200">{activeProfile?.displayName}</span>
        <ChevronDown size={13} className={`text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl overflow-hidden z-50 min-w-[180px]">
          <div className="px-3 py-2 border-b border-gray-700">
            <p className="text-xs text-gray-500">החלף פרופיל</p>
          </div>
          {profileList.map(profile => (
            <button
              key={profile.id}
              onClick={() => { setActiveProfileId(profile.id); setOpen(false); }}
              className={`w-full text-right px-3 py-2.5 text-sm transition-colors flex items-center gap-2 ${
                activeProfileId === profile.id
                  ? "bg-emerald-500/10 text-emerald-300"
                  : "text-gray-300 hover:bg-gray-700"
              }`}
            >
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                activeProfileId === profile.id ? "bg-emerald-400" : "bg-gray-600"
              }`} />
              {profile.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
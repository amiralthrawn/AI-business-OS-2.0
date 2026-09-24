"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { setSelectedProfile } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { ROLE_LABEL } from "@/lib/objects";
import type { MeRead, UserProfileRead } from "@/lib/types";

// Who am I using the OS as (V2 roles). Selecting a profile stores its id in
// a cookie read by every API call (lib/api.ts); the whole UI -- navigation,
// allowed actions, approvals -- follows that role. There is no password in
// this MVP: this chooses a declared profile, it does not authenticate
// (brain/permissions.md).
export default function ProfileSwitcher({ me, users, fallbackLabel }: { me: MeRead | null; users: UserProfileRead[]; fallbackLabel: string }) {
  const router = useRouter();
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const name = me?.profile?.name ?? fallbackLabel;
  const initials = name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  function choose(id: string | null) {
    setSelectedProfile(id);
    setOpen(false);
    router.refresh();
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full"
        aria-label={t("topbar.profile")}
        title={me?.profile ? `${me.profile.name} · ${me.role_label}` : t("topbar.no_profile")}
      >
        <span className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-accent text-[12px] font-semibold text-white">{initials || "OS"}</span>
        <span className="hidden text-left leading-tight lg:block">
          <span className="block text-[12.5px] font-semibold text-text">{me?.profile?.name ?? t("topbar.profile")}</span>
          <span className="block text-[11px] text-text-faint">{me?.profile ? me.role_label : t("topbar.no_profile")}</span>
        </span>
      </button>
      {open && (
        <div className="animate-pop absolute right-0 z-50 mt-2 w-64 rounded-xl border border-border bg-surface p-1.5 shadow-card">
          {users.map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => choose(u.id)}
              className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-[13px] hover:bg-surface-sunken ${me?.profile?.id === u.id ? "font-semibold text-accent-strong" : "text-text"}`}
            >
              <span className="truncate">{u.name}</span>
              <span className="text-[11.5px] text-text-faint">{ROLE_LABEL[u.role]}</span>
            </button>
          ))}
          <button type="button" onClick={() => choose(null)} className="mt-1 w-full rounded-lg px-3 py-2 text-left text-[12.5px] text-text-soft hover:bg-surface-sunken">
            {t("topbar.no_profile")}
          </button>
          <a href="/settings#profils" className="block rounded-lg px-3 py-2 text-[12.5px] text-accent-strong hover:bg-surface-sunken">
            Gérer les profils et rôles
          </a>
        </div>
      )}
    </div>
  );
}

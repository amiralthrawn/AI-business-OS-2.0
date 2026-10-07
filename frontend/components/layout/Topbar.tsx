"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import AssistantDrawer from "@/components/ai/AssistantDrawer";
import ProfileSwitcher from "@/components/layout/ProfileSwitcher";
import { type LabelKey, useLocale } from "@/lib/i18n";
import type { MeRead, UserProfileRead } from "@/lib/types";

const TITLE_KEYS: Record<string, LabelKey> = {
  "/": "nav.command_center",
  "/business/finance": "nav.finance",
  "/business/procurement": "nav.procurement",
  "/business/sales": "nav.sales",
  "/data": "nav.catalog",
  "/data/products": "nav.catalog",
  "/data/customers": "nav.sales",
  "/data/suppliers": "nav.procurement",
  "/data/transactions": "nav.finance",
  "/communications": "nav.communications",
  "/documents": "nav.documents",
  "/people": "nav.people",
  "/direction": "nav.direction",
  "/intelligence/risks": "nav.risks",
  "/intelligence/opportunities": "nav.opportunities",
  "/intelligence/decision-intelligence": "nav.decision_intelligence",
  "/actions/tasks": "nav.tasks",
  "/actions/activity": "nav.activity",
  "/ai/ask-ai": "nav.ask_ai",
  "/settings": "nav.configuration",
};

function titleFor(pathname: string, t: (key: LabelKey) => string): string {
  if (TITLE_KEYS[pathname]) return t(TITLE_KEYS[pathname]);
  const parent = "/" + pathname.split("/").slice(1, 3).join("/");
  if (TITLE_KEYS[parent]) return t(TITLE_KEYS[parent]);
  const root = "/" + pathname.split("/")[1];
  return TITLE_KEYS[root] ? t(TITLE_KEYS[root]) : "AI Business OS";
}

export default function Topbar({
  companyName,
  pendingCount,
  me,
  users,
  onMenuClick,
}: {
  companyName: string | null;
  pendingCount: number;
  me: MeRead | null;
  users: UserProfileRead[];
  onMenuClick: () => void;
}) {
  const pathname = usePathname();
  const { t } = useLocale();

  return (
    <header className="grid h-[72px] shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-border bg-surface px-5 md:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label={t("topbar.open_menu")}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-text-soft hover:bg-surface-sunken md:hidden"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <line x1="4" y1="7" x2="20" y2="7" /><line x1="4" y1="12" x2="20" y2="12" /><line x1="4" y1="17" x2="20" y2="17" />
          </svg>
        </button>
        <div className="flex min-w-0 items-center gap-2 text-[13.5px]">
          <span className="hidden truncate text-text-faint lg:inline">{companyName ?? "AI Business OS"}</span>
          <span className="hidden text-border-strong lg:inline">/</span>
          <span className="truncate font-semibold text-text">{titleFor(pathname, t)}</span>
        </div>
      </div>

      {/* The OS assistant, centred and reachable from every page. */}
      <Suspense fallback={null}>
        <AssistantDrawer />
      </Suspense>

      <div className="flex items-center justify-end gap-3.5">
        <Link
          href="/actions/tasks"
          className="relative flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-surface-sunken text-text-soft"
          aria-label={`${pendingCount} ${t("topbar.pending")}`}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
          {pendingCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-[15px] w-[15px] items-center justify-center rounded-full bg-danger text-[9px] font-bold text-white">
              {pendingCount}
            </span>
          )}
        </Link>
        <ProfileSwitcher me={me} users={users} fallbackLabel={companyName ?? "OS"} />
      </div>
    </header>
  );
}

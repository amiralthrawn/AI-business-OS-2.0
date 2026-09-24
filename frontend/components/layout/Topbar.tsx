"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import LanguageSwitcher from "@/components/layout/LanguageSwitcher";
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
    <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-border bg-surface px-5 md:px-10">
      <div className="flex items-center gap-3">
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
        <div className="flex items-center gap-2 text-[13.5px]">
          <span className="hidden text-text-faint sm:inline">{companyName ?? "AI Business OS"}</span>
          <span className="hidden text-border-strong sm:inline">/</span>
          <span className="font-semibold text-text">{titleFor(pathname, t)}</span>
        </div>
      </div>

      <div className="flex items-center gap-3.5">
        <LanguageSwitcher />
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
        <Link
          href="/ai/ask-ai"
          className="hidden items-center gap-1.5 rounded-[10px] border-[1.5px] border-border-strong px-3.5 py-2 text-[13px] font-semibold text-text hover:border-text-faint sm:inline-flex"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z" /></svg>
          {t("nav.ask_ai")}
        </Link>
        <ProfileSwitcher me={me} users={users} fallbackLabel={companyName ?? "OS"} />
      </div>
    </header>
  );
}

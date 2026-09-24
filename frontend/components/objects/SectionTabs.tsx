import WorkspaceTabs from "@/components/objects/WorkspaceTabs";

// V2 merge (brain/navigation_v2.md): Risks, Opportunities and Decisions are
// one "Intelligence" workspace; Tasks and Activity are one "Actions"
// workspace. Their pages stay where they were (links keep working); the
// navigation shows one entry and these tabs.
const SECTIONS = {
  intelligence: [
    { key: "risks", label: "Risques", href: "/intelligence/risks" },
    { key: "opportunities", label: "Opportunités", href: "/intelligence/opportunities" },
    { key: "decisions", label: "Décisions", href: "/intelligence/decision-intelligence" },
  ],
  actions: [
    { key: "tasks", label: "Tâches & validations", href: "/actions/tasks" },
    { key: "activity", label: "Activité de l'entreprise", href: "/actions/activity" },
    // V2.1: compliance is Tasks + experts + linked documents, not a module.
    { key: "compliance", label: "Conformité & juridique", href: "/actions/compliance" },
  ],
} as const;

export default function SectionTabs({ section, active }: { section: keyof typeof SECTIONS; active: string }) {
  return <WorkspaceTabs tabs={[...SECTIONS[section]]} active={active} />;
}

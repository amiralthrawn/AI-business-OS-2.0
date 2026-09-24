"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Button from "@/components/ui/Button";
import { addSkillNeed, publishSkillGaps } from "@/lib/api";

// Declare a need, or push uncovered needs into Intelligence as Opportunities
// ("Recruter ou former : X") -- the same list the Command Center reads.
export default function SkillsGapActions() {
  const router = useRouter();
  const [skill, setSkill] = useState("");
  const [keywords, setKeywords] = useState("");
  const [priority, setPriority] = useState("medium");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<string>) {
    setBusy(true);
    try {
      setMessage(await fn());
      router.refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-[13px]">
      <input value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="Besoin (ex. Data / automatisation)" className="rounded-xl border-[1.5px] border-border-strong px-3 py-2 outline-none focus:border-accent" />
      <input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="Mots-clés (python, sql…)" className="rounded-xl border-[1.5px] border-border-strong px-3 py-2 outline-none focus:border-accent" />
      <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-xl border-[1.5px] border-border-strong px-3 py-2 outline-none focus:border-accent">
        <option value="high">Priorité haute</option>
        <option value="medium">Priorité moyenne</option>
        <option value="low">Priorité basse</option>
      </select>
      <Button variant="ghost" disabled={!skill.trim() || busy} onClick={() => run(async () => { await addSkillNeed({ skill: skill.trim(), keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean), priority }); setSkill(""); setKeywords(""); return "Besoin ajouté."; })}>
        Déclarer le besoin
      </Button>
      <Button disabled={busy} onClick={() => run(async () => `${(await publishSkillGaps()).opportunities_created} opportunité(s) créée(s) dans Intelligence.`)}>
        Signaler les manques à l&rsquo;Intelligence
      </Button>
      {message && <span className="text-[12px] text-text-soft">{message}</span>}
    </div>
  );
}

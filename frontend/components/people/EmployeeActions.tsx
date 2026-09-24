"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { assignEmployeeTask, proposeEmployeeDecision } from "@/lib/api";

const field = "rounded-xl border-[1.5px] border-border-strong px-3 py-2 text-[13px] outline-none focus:border-accent";

// Manager actions on an employee. Assigning a task is immediate (a human
// decision). A promotion / raise / evolution is only PROPOSED: it waits for
// a director's validation in Actions, and nothing changes before.
export default function EmployeeActions({ employeeId, canWrite, canCost }: { employeeId: string; canWrite: boolean; canCost: boolean }) {
  const router = useRouter();
  const [taskTitle, setTaskTitle] = useState("");
  const [due, setDue] = useState("");
  const [kind, setKind] = useState("promotion");
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState("");
  const [rationale, setRationale] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!canWrite) return null;

  async function run(fn: () => Promise<string>) {
    setBusy(true);
    setMessage(null);
    try {
      setMessage(await fn());
      router.refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="space-y-2 p-5">
        <p className="text-[13px] font-semibold text-text">Envoyer une tâche</p>
        <input className={`${field} w-full`} placeholder="Intitulé" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} />
        <div className="flex gap-2">
          <input type="date" className={field} value={due} onChange={(e) => setDue(e.target.value)} />
          <Button disabled={!taskTitle.trim() || busy} onClick={() => run(async () => { await assignEmployeeTask(employeeId, { title: taskTitle.trim(), due_at: due ? new Date(due).toISOString() : undefined }); setTaskTitle(""); return "Tâche assignée."; })}>
            Assigner
          </Button>
        </div>
      </Card>
      <Card className="space-y-2 p-5">
        <p className="text-[13px] font-semibold text-text">Proposer une décision</p>
        <div className="flex flex-wrap gap-2">
          <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="promotion">Promotion</option>
            <option value="evolution">Évolution</option>
            {canCost && <option value="raise">Augmentation</option>}
            <option value="decision">Autre décision</option>
          </select>
          {kind === "promotion" && <input className={`${field} flex-1`} placeholder="Nouveau poste" value={title} onChange={(e) => setTitle(e.target.value)} />}
          {kind === "raise" && <input className={`${field} flex-1`} placeholder="Nouveau salaire brut annuel (€)" value={salary} onChange={(e) => setSalary(e.target.value)} />}
        </div>
        <textarea className={`${field} w-full`} rows={2} placeholder="Justification" value={rationale} onChange={(e) => setRationale(e.target.value)} />
        <Button
          variant="ghost"
          disabled={!rationale.trim() || busy}
          onClick={() => run(async () => (await proposeEmployeeDecision(employeeId, { kind, rationale: rationale.trim(), new_job_title: title || undefined, new_salary: salary ? Number(salary.replace(",", ".")) : undefined })).note)}
        >
          Soumettre à la direction
        </Button>
      </Card>
      {message && <p className="text-[12.5px] text-text-soft md:col-span-2">{message}</p>}
    </div>
  );
}

"use client";

import { useState } from "react";
import TaskActionButtons from "@/components/actions/TaskActionButtons";
import Button from "@/components/ui/Button";
import { askAI } from "@/lib/api";
import type { AskAIResponse } from "@/lib/types";
import { valueLabel } from "@/lib/labels";

// The same Ask AI entry point as /ai/ask-ai, embedded compactly on the
// Command Center -- calls the same POST /ai/ask (the AI Orchestrator), not a
// second chat system. Any proposed action still goes through the shared
// TaskActionButtons; nothing here executes anything on its own.
export default function HomeAskAI() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskAIResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await askAI(question));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={handleSubmit} className="flex gap-2.5">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Posez une question sur votre activité…"
          className="flex-1 rounded-xl border-[1.5px] border-border-strong bg-surface px-4 py-2.5 text-[13.5px] outline-none focus:border-accent"
        />
        <Button type="submit" loading={loading} disabled={!question.trim()}>
          Demander
        </Button>
      </form>

      {error && <p className="text-[12.5px] text-danger">{error}</p>}

      {result && (
        <div className="space-y-2.5 rounded-xl bg-surface-sunken p-4">
          <p className="whitespace-pre-wrap text-[13.5px] text-text">{result.answer}</p>
          <p className="text-[11.5px] text-text-faint">
            Secteur{result.agent.includes(",") ? "s" : ""} consulté{result.agent.includes(",") ? "s" : ""}&nbsp;: {result.agent.split(",").map((a) => valueLabel("domain", a.trim())).join(", ")}
            {result.agent.includes(",") && " (raisonnement cross-domaine)"}
          </p>
          {result.requires_human_validation && result.action_result && (
            <TaskActionButtons taskId={result.action_result.task_id} taskTitle={result.action_result.title} />
          )}
        </div>
      )}
    </div>
  );
}

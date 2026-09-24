"use client";

import { useState } from "react";
import SectionLabel from "@/components/objects/SectionLabel";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { askAI } from "@/lib/api";

// Ask AI *about this object*: the question is sent with the object on
// screen, so "cette commande" needs no number -- the Orchestrator traverses
// its relations (deals agent) instead of guessing.
export default function ObjectAskAI({ objectType, objectId, suggestions }: { objectType: string; objectId: string; suggestions: string[] }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(q: string) {
    if (!q.trim()) return;
    setQuestion(q);
    setLoading(true);
    setError(null);
    try {
      const res = await askAI(q.trim(), { objectType, objectId });
      setAnswer(res.answer);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <SectionLabel>Demander à l&rsquo;IA</SectionLabel>
      <Card className="p-5">
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button key={s} type="button" onClick={() => ask(s)} className="rounded-lg border border-border bg-surface-alt px-3 py-1.5 text-[12.5px] text-text-soft hover:border-border-strong hover:text-text">
              {s}
            </button>
          ))}
        </div>
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(question); }}>
          <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Votre question sur cet objet…" className="flex-1 rounded-xl border-[1.5px] border-border-strong bg-surface px-4 py-2.5 text-[13.5px] outline-none focus:border-accent" />
          <Button type="submit" loading={loading} disabled={!question.trim()}>Demander</Button>
        </form>
        {error && <p className="mt-2 text-[12.5px] text-danger">{error}</p>}
        {answer && <p className="mt-4 whitespace-pre-line rounded-xl bg-surface-alt px-4 py-3 text-[13.5px] leading-relaxed text-text">{answer}</p>}
      </Card>
    </section>
  );
}

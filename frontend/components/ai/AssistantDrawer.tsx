"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import TaskActionButtons from "@/components/actions/TaskActionButtons";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { askAI, getObjectContext } from "@/lib/api";
import { valueLabel } from "@/lib/labels";
import type { AskAIResponse, ObjectSummary, ObjectType } from "@/lib/types";

type PageObject = { type: ObjectType; id: string };
type Exchange = { question: string; result?: AskAIResponse; error?: string; context?: string };

// Objects the Orchestrator reads directly from the screen (object_type /
// object_id on POST /ai/ask). Customers and suppliers are recognised by
// their NAME in the question -- the suggestions carry it.
const SENT_AS_CONTEXT: ObjectType[] = ["commercial_document", "product"];

function pageObject(pathname: string, messageId: string | null): PageObject | null {
  const m = pathname.match(/^\/(documents|data\/customers|data\/suppliers|data\/products)\/([0-9a-f-]{32,36})$/i);
  if (m) {
    const type = ({ documents: "commercial_document", "data/customers": "customer", "data/suppliers": "supplier", "data/products": "product" } as const)[m[1] as "documents"];
    return { type, id: m[2] };
  }
  if (pathname === "/communications" && messageId) return { type: "communication", id: messageId };
  return null;
}

function suggestionsFor(pathname: string, obj: ObjectSummary | null): string[] {
  if (obj?.type === "commercial_document") return ["Où en est ce document ?", "Quels risques concernent cette affaire ?", "Pourquoi cette marge ?"];
  if (obj?.type === "product") return ["Quelle est la marge de ce produit ?", "Quels fournisseurs pour ce produit ?"];
  if (obj?.type === "customer") return [`Que faut-il savoir sur ${obj.title} ?`, `Le chiffre d'affaires de ${obj.title} évolue-t-il ?`];
  if (obj?.type === "supplier") return [`Que faut-il savoir sur ${obj.title} ?`, `Les délais de ${obj.title} se dégradent-ils ?`];
  if (pathname.startsWith("/business/finance")) return ["Pourquoi la marge baisse-t-elle ?", "Quels encaissements sont en retard ?"];
  if (pathname.startsWith("/business/procurement")) return ["Quels fournisseurs posent problème ?", "Où faut-il agir côté achats ?"];
  if (pathname.startsWith("/business/sales")) return ["Quels clients sont à risque ?", "Quelles affaires faire avancer ?"];
  if (pathname.startsWith("/intelligence")) return ["Que dois-je traiter en priorité ?", "Pourquoi ce risque est-il important ?"];
  return ["Que dois-je traiter en priorité aujourd'hui ?", "Pourquoi la marge baisse-t-elle ?", "Quels fournisseurs posent problème ?"];
}

// The OS assistant, one click away from every page (topbar). Same
// Orchestrator as the "Demander à l'IA" page (POST /ai/ask) -- no second AI
// system. The page's object is sent when the Orchestrator can use it; an
// action it proposes is only a Task awaiting human validation (HITL).
export default function AssistantDrawer() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<Exchange[]>([]);
  const [objectInfo, setObjectInfo] = useState<{ key: string; summary: ObjectSummary | null } | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const target = pageObject(pathname, searchParams.get("message"));
  const targetKey = target ? `${target.type}:${target.id}` : null;
  const summary = objectInfo && objectInfo.key === targetKey ? objectInfo.summary : null;

  // Name of the object on screen, read from the contextual API when the panel opens.
  useEffect(() => {
    if (!open || !target || objectInfo?.key === targetKey) return;
    let cancelled = false;
    getObjectContext(target.type, target.id)
      .then((ctx) => !cancelled && setObjectInfo({ key: targetKey!, summary: ctx.object }))
      .catch(() => !cancelled && setObjectInfo({ key: targetKey!, summary: null }));
    return () => {
      cancelled = true;
    };
  }, [open, target, targetKey, objectInfo?.key]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [history, loading]);

  async function ask(q: string) {
    const text = q.trim();
    if (!text || loading) return;
    setQuestion("");
    setLoading(true);
    const sendContext = target && SENT_AS_CONTEXT.includes(target.type) ? { objectType: target.type, objectId: target.id } : undefined;
    const contextLabel = sendContext && summary ? `${summary.kind_label} ${summary.title}` : undefined;
    try {
      const result = await askAI(text, sendContext);
      setHistory((h) => [...h, { question: text, result, context: contextLabel }]);
    } catch (err) {
      setHistory((h) => [...h, { question: text, error: err instanceof Error ? err.message : "Une erreur est survenue." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="assistant-ia"
        title="Assistant IA (Échap pour fermer)"
        className={`group relative flex h-[38px] items-center gap-2 rounded-full border-[1.5px] px-3.5 text-[13px] font-semibold transition-all duration-200 ${
          open ? "border-accent bg-accent text-white shadow-card" : "border-border-strong bg-surface text-text hover:-translate-y-px hover:border-accent hover:text-accent hover:shadow-card"
        }`}
      >
        <span className={`relative flex h-5 w-5 items-center justify-center ${open ? "" : "animate-ai-glow"} rounded-full`}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" className="transition-transform duration-300 group-hover:rotate-45">
            <path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z" />
            <path d="M19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z" opacity=".7" />
          </svg>
        </span>
        <span className="hidden sm:inline">Assistant IA</span>
      </button>

      {open && (
        <div className="fixed inset-x-0 bottom-0 top-[72px] z-40 flex justify-end" role="presentation">
          <button type="button" aria-label="Fermer l'assistant" className="animate-fade-in absolute inset-0 bg-text/20" onClick={() => setOpen(false)} />
          <aside id="assistant-ia" role="dialog" aria-modal="true" aria-label="Assistant IA" className="animate-drawer-in relative flex h-full w-full max-w-[440px] flex-col border-l border-border bg-surface shadow-card">
            <header className="flex items-center gap-3 border-b border-border px-5 py-4">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-white">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z" /></svg>
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-semibold text-text">Assistant IA</p>
                <p className="truncate text-[11.5px] text-text-faint">
                  {summary ? (
                    <>Contexte : {summary.kind_label} <span className="font-medium text-text-soft">{summary.title}</span></>
                  ) : (
                    "Question sur l'ensemble de l'entreprise"
                  )}
                </p>
              </div>
              <button type="button" onClick={() => setOpen(false)} aria-label="Fermer" className="flex h-8 w-8 items-center justify-center rounded-lg text-text-faint hover:bg-surface-sunken hover:text-text">
                ✕
              </button>
            </header>

            <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
              {history.length === 0 && (
                <div className="space-y-3">
                  <p className="text-[13px] leading-relaxed text-text-soft">
                    Posez une question sur ce que vous voyez ou sur l&rsquo;entreprise. L&rsquo;assistant lit les données réelles, explique son raisonnement et ne
                    déclenche rien seul : toute action proposée attend votre validation.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {suggestionsFor(pathname, summary).map((s) => (
                      <button key={s} type="button" onClick={() => ask(s)} className="rounded-lg border border-border bg-surface-alt px-3 py-1.5 text-left text-[12.5px] text-text-soft transition-colors hover:border-accent hover:text-text">
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {history.map((x, i) => (
                <div key={i} className="animate-reveal space-y-2">
                  <p className="ml-8 rounded-2xl rounded-tr-sm bg-accent-soft px-3.5 py-2 text-[13px] text-text">{x.question}</p>
                  {x.error ? (
                    <p className="text-[12.5px] text-danger">{x.error}</p>
                  ) : (
                    x.result && (
                      <div className="mr-4 space-y-2 rounded-2xl rounded-tl-sm border border-border bg-surface-alt px-3.5 py-2.5">
                        <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-text">{x.result.answer}</p>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {x.result.agent.split(",").map((a) => (
                            <Badge key={a} label={valueLabel("domain", a.trim())} tone="accent" />
                          ))}
                          {x.context && <span className="text-[11px] text-text-faint">· sur {x.context}</span>}
                        </div>
                        {x.result.requires_human_validation && x.result.action_result && (
                          <div className="border-t border-border pt-2">
                            <p className="mb-1.5 text-[11.5px] text-text-faint">Action proposée — rien n&rsquo;est exécuté sans votre validation :</p>
                            <TaskActionButtons taskId={x.result.action_result.task_id} taskTitle={x.result.action_result.title} />
                          </div>
                        )}
                      </div>
                    )
                  )}
                </div>
              ))}
              {loading && (
                <p className="flex items-center gap-2 text-[12.5px] text-text-faint">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> L&rsquo;assistant analyse les données…
                </p>
              )}
              <div ref={endRef} />
            </div>

            <form
              className="space-y-2 border-t border-border px-5 py-4"
              onSubmit={(e) => {
                e.preventDefault();
                ask(question);
              }}
            >
              <textarea
                ref={inputRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    ask(question);
                  }
                }}
                rows={2}
                placeholder="Votre question… (Entrée pour envoyer)"
                className="w-full resize-none rounded-xl border-[1.5px] border-border-strong bg-surface px-3 py-2 text-[13px] outline-none focus:border-accent"
              />
              <div className="flex items-center justify-between gap-3">
                <Link href="/ai/ask-ai" onClick={() => setOpen(false)} className="text-[12px] text-text-faint hover:text-text hover:underline">
                  Ouvrir la page IA complète
                </Link>
                <Button type="submit" loading={loading} disabled={!question.trim()}>
                  Demander
                </Button>
              </div>
            </form>
          </aside>
        </div>
      )}
    </>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";
import TaskActionButtons from "@/components/actions/TaskActionButtons";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { SECTOR_LABEL_FR, formatDateFR } from "@/lib/labels";
import { submitTaskForValidation, updateTaskStatus } from "@/lib/api";
import { entityHref } from "@/lib/related-entity";
import type { TaskRead, TaskStatus } from "@/lib/types";

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending_validation: "en attente de validation",
  open: "à faire",
  in_progress: "en cours",
  done: "terminée",
  cancelled: "annulée",
  rejected: "rejetée",
  executed: "exécutée",
};

function statusTone(status: TaskStatus): BadgeTone {
  if (status === "pending_validation") return "warning";
  if (status === "executed" || status === "done") return "success";
  if (status === "rejected" || status === "cancelled") return "neutral";
  return "accent";
}

// The Tasks tab's "click to open" detail (Step 29 points 12-15): real
// context (description), a real related-entity link when there is one, and
// only the state transitions the backend actually supports -- never a
// button that looks actionable but does nothing (see
// app.actions.service.ActionsService's allowed transitions).
export default function TaskDetailPanel({
  task,
  entityName,
  onClose,
  onChange,
}: {
  task: TaskRead;
  entityName: string | null;
  onClose: () => void;
  onChange: (updated: TaskRead) => void;
}) {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const href = task.related_entity_type && task.related_entity_id ? entityHref(task.related_entity_type, task.related_entity_id) : null;

  async function runStatusChange(action: string, run: () => Promise<TaskRead>) {
    setLoadingAction(action);
    setError(null);
    try {
      const updated = await run();
      onChange(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setLoadingAction(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-text/30" onClick={onClose}>
      <div
        className="animate-reveal flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-border bg-surface p-7"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {task.domain && <Badge label={SECTOR_LABEL_FR[task.domain] ?? task.domain} tone="neutral" />}
            <Badge label={STATUS_LABEL[task.status]} tone={statusTone(task.status)} />
            {task.requires_decision && <Badge label="Décision requise" tone="warning" />}
          </div>
          <button type="button" onClick={onClose} aria-label="Fermer" className="text-text-faint hover:text-text">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <h2 className="mt-4 font-display text-[20px] italic text-text">{task.title}</h2>
        <p className="mt-1 text-[11.5px] text-text-faint">Créée le <span className="num">{formatDateFR(task.created_at)}</span></p>

        {task.description && (
          <div className="mt-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-text-faint">Contexte</p>
            <p className="mt-1 text-[13.5px] leading-relaxed text-text-soft">{task.description}</p>
          </div>
        )}

        {href && (entityName || task.related_entity_type === "communication" || task.related_entity_type === "commercial_document") && (
          <Link href={href} className="mt-3 inline-block text-[12.5px] font-medium text-accent-strong hover:underline">
            {entityName ? `Voir ${entityName} →` : task.related_entity_type === "communication" ? "Voir le message à valider →" : "Voir le document →"}
          </Link>
        )}

        {task.requires_decision && task.status === "open" && (
          <div className="mt-4 rounded-xl border-[1.5px] border-warning-soft bg-warning-soft/30 p-3.5 text-[12.5px] text-text">
            Cette action nécessite une analyse et une décision avant d&rsquo;être considérée comme exécutable.
          </div>
        )}

        <div className="mt-6">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-faint">Actions</p>

          {error && <p className="mb-2 text-[12.5px] text-danger">{error}</p>}

          {task.status === "pending_validation" && task.pending_action ? (
            <TaskActionButtons taskId={task.id} taskTitle={task.title} />
          ) : (
            <div className="flex flex-wrap gap-2">
              {task.status === "open" && (
                <>
                  <Button
                    variant="ghost"
                    loading={loadingAction === "in_progress"}
                    onClick={() => runStatusChange("in_progress", () => updateTaskStatus(task.id, "in_progress"))}
                  >
                    Marquer en cours
                  </Button>
                  <Button
                    variant="ghost"
                    loading={loadingAction === "submit"}
                    onClick={() => runStatusChange("submit", () => submitTaskForValidation(task.id))}
                  >
                    Soumettre pour validation
                  </Button>
                  <Button
                    variant="ghost"
                    loading={loadingAction === "done"}
                    onClick={() => runStatusChange("done", () => updateTaskStatus(task.id, "done"))}
                  >
                    Marquer comme traité
                  </Button>
                  <Button
                    variant="danger-ghost"
                    loading={loadingAction === "cancelled"}
                    onClick={() => runStatusChange("cancelled", () => updateTaskStatus(task.id, "cancelled"))}
                  >
                    Annuler
                  </Button>
                </>
              )}
              {task.status === "in_progress" && (
                <>
                  <Button
                    variant="ghost"
                    loading={loadingAction === "done"}
                    onClick={() => runStatusChange("done", () => updateTaskStatus(task.id, "done"))}
                  >
                    Marquer comme traité
                  </Button>
                  <Button
                    variant="ghost"
                    loading={loadingAction === "open"}
                    onClick={() => runStatusChange("open", () => updateTaskStatus(task.id, "open"))}
                  >
                    Reporter
                  </Button>
                  <Button
                    variant="danger-ghost"
                    loading={loadingAction === "cancelled"}
                    onClick={() => runStatusChange("cancelled", () => updateTaskStatus(task.id, "cancelled"))}
                  >
                    Annuler
                  </Button>
                </>
              )}
              {(task.status === "done" || task.status === "executed" || task.status === "cancelled" || task.status === "rejected") && (
                <p className="text-[12.5px] text-text-faint">Cette tâche est {STATUS_LABEL[task.status]} ; aucune action supplémentaire.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

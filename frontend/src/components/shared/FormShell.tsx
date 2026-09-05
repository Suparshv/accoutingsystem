import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// SPEC.md §13.2 — the mockup's state pipeline, shown left to right with the
// document's current state highlighted. Step keys match SPEC.md §7.1's
// budget_state enum verbatim (draft, confirmed, revised, cancelled) so a
// real page can pass its `state` field straight through. "Cancelled" is a
// terminal branch rather than a true fourth step, but the mockup draws it
// in this sequence.
const PIPELINE_STEPS = ["draft", "confirmed", "revised", "cancelled"] as const;
type PipelineStep = (typeof PIPELINE_STEPS)[number];

const PIPELINE_LABELS: Record<PipelineStep, string> = {
  draft: "Draft",
  confirmed: "Confirm",
  revised: "Revised",
  cancelled: "Cancelled",
};

export type FormShellAction = {
  label: string;
  onClick: () => void;
  variant?: "default" | "outline" | "destructive" | "ghost";
  disabled?: boolean;
};

type FormShellProps = {
  title: string;
  // Omit for records with no document lifecycle (masters like Contacts,
  // Products, Analytic Accounts) — the pipeline strip only renders when
  // a state is given.
  state?: string;
  actions: FormShellAction[];
  children: ReactNode;
  onBack?: () => void;
};

export function FormShell({ title, state, actions, children, onBack }: FormShellProps) {
  const currentIndex = state ? PIPELINE_STEPS.indexOf(state as PipelineStep) : -1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          {onBack && (
            <Button type="button" variant="ghost" size="icon" onClick={onBack} aria-label="Back">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          )}
          <h1 className="text-2xl font-semibold text-text_primary">{title}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {actions.map((action) => (
            <Button
              key={action.label}
              type="button"
              variant={action.variant ?? "default"}
              disabled={action.disabled}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>

      {state && (
        <ol className="flex flex-wrap items-center gap-2 text-sm">
          {PIPELINE_STEPS.map((step, i) => (
            <li key={step} className="flex items-center gap-2">
              <span
                className={cn(
                  "rounded-full px-3 py-1 font-medium",
                  i === currentIndex
                    ? "bg-primary text-primary-foreground"
                    : "bg-surface text-text_secondary",
                )}
              >
                {PIPELINE_LABELS[step]}
              </span>
              {i < PIPELINE_STEPS.length - 1 && (
                <span aria-hidden="true" className="text-text_secondary">
                  &rsaquo;
                </span>
              )}
            </li>
          ))}
        </ol>
      )}

      <div className="rounded-lg border border-border bg-background p-5">{children}</div>
    </div>
  );
}

import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { BudgetState, DocumentState, JournalEntryState } from "@/types/api";

// SPEC.md §13.2 — the mockup's state pipeline, shown left to right with the
// document's current state highlighted. Two different lifecycles share this
// component: most documents (sales/purchase orders, bills, invoices) use
// document_state (draft/confirmed/cancelled — 3 steps), while budgets use
// budget_state (draft/confirmed/revised/cancelled — 4 steps, "revised" being
// a real, reachable stage there). `variant` picks which step list to draw;
// it must NOT be hardcoded to one enum the way this used to be, or every
// non-budget document grows a "Revised" step it can never reach.
type FormShellVariant = "document" | "budget";

const DOCUMENT_STEPS = ["draft", "confirmed", "cancelled"] as const;
const BUDGET_STEPS = ["draft", "confirmed", "revised", "cancelled"] as const;

const STEPS_BY_VARIANT: Record<FormShellVariant, readonly string[]> = {
  document: DOCUMENT_STEPS,
  budget: BUDGET_STEPS,
};

const STEP_LABELS: Record<string, string> = {
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
  // a state is given. Typed as a union of the real state enums (rather than
  // a loose `string`) so passing the wrong one is a compile error, not a
  // silent wrong stepper.
  state?: DocumentState | BudgetState | JournalEntryState;
  // Which step list to draw. Defaults to "document" (draft/confirmed/
  // cancelled), the lifecycle every non-budget caller here actually has.
  // Budgets must pass "budget" explicitly to get their real "Revised" step.
  variant?: FormShellVariant;
  actions: FormShellAction[];
  children: ReactNode;
  onBack?: () => void;
};

export function FormShell({
  title,
  state,
  variant = "document",
  actions,
  children,
  onBack,
}: FormShellProps) {
  const steps = STEPS_BY_VARIANT[variant];
  const currentIndex = state ? steps.indexOf(state) : -1;

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
          {steps.map((step, i) => (
            <li key={step} className="flex items-center gap-2">
              <span
                className={cn(
                  "rounded px-3 py-1 font-medium",
                  i === currentIndex
                    ? "bg-primary text-primary-foreground"
                    : "bg-surface text-text_secondary",
                )}
              >
                {STEP_LABELS[step]}
              </span>
              {i < steps.length - 1 && (
                <span aria-hidden="true" className="text-text_secondary">
                  &rsaquo;
                </span>
              )}
            </li>
          ))}
        </ol>
      )}

      <div className="rounded border border-border bg-background p-5">{children}</div>
    </div>
  );
}

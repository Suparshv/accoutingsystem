import type { ReactNode } from "react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// SPEC.md §13.2. getItemId, emptyMessage, error and onRetry aren't in the
// spec's literal prop list but are needed so Kanban — now a real second view
// over the same fetched data as DataTable, not a mock — can show the same
// loading/error/empty/success states DataTable does, per AGENTS.md §5's
// "loading, error and empty states all render" rule.
export type KanbanGridProps<T> = {
  items: T[];
  renderCard: (item: T) => ReactNode;
  loading?: boolean;
  error?: { message: string } | null;
  onRetry?: () => void;
  onCardClick?: (item: T) => void;
  getItemId: (item: T) => string | number;
  emptyMessage?: string;
};

export function KanbanGrid<T>({
  items,
  renderCard,
  loading = false,
  error = null,
  onRetry,
  onCardClick,
  getItemId,
  emptyMessage = "Nothing to show yet.",
}: KanbanGridProps<T>) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-border bg-surface"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border px-4 py-10 text-center">
        <p className="text-sm text-danger">{error.message}</p>
        {onRetry && (
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            <RotateCcw className="mr-2 h-4 w-4" />
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-text_secondary">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <div
          key={getItemId(item)}
          onClick={() => onCardClick?.(item)}
          className={cn(
            "rounded-lg border border-border bg-background p-4 shadow-sm transition-shadow hover:shadow-md",
            onCardClick && "cursor-pointer",
          )}
        >
          {renderCard(item)}
        </div>
      ))}
    </div>
  );
}

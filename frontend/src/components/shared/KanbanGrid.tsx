import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// SPEC.md §13.2. getItemId and emptyMessage aren't in the spec's literal
// prop list but are needed to render stable keys and a real empty state —
// the same small additions DataTable makes for the same reasons.
export type KanbanGridProps<T> = {
  items: T[];
  renderCard: (item: T) => ReactNode;
  loading?: boolean;
  onCardClick?: (item: T) => void;
  getItemId: (item: T) => string | number;
  emptyMessage?: string;
};

export function KanbanGrid<T>({
  items,
  renderCard,
  loading = false,
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

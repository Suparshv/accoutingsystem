import { LayoutGrid, List } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ViewMode = "list" | "kanban";

type ViewSwitcherProps = {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
};

// SPEC.md §13.2 — pure client-side toggle over one API response. The page
// fetches once; this only decides which of DataTable/KanbanGrid renders it.
export function ViewSwitcher({ value, onChange }: ViewSwitcherProps) {
  return (
    <div className="inline-flex rounded-md border border-border p-0.5">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-pressed={value === "list"}
        onClick={() => onChange("list")}
        className={cn(value === "list" && "bg-surface")}
      >
        <List className="mr-2 h-4 w-4" />
        List
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-pressed={value === "kanban"}
        onClick={() => onChange("kanban")}
        className={cn(value === "kanban" && "bg-surface")}
      >
        <LayoutGrid className="mr-2 h-4 w-4" />
        Kanban
      </Button>
    </div>
  );
}

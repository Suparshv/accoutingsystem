import { cn } from "@/lib/utils";

// SPEC.md §13.2 StatusBadge mapping.
export type Status =
  | "draft"
  | "confirmed"
  | "posted"
  | "cancelled"
  | "paid"
  | "partial"
  | "not_paid"
  | "revised";

const STATUS_STYLES: Record<Status, string> = {
  draft: "bg-draft text-white",
  confirmed: "bg-accent text-accent-foreground",
  posted: "bg-success text-white",
  cancelled: "bg-danger text-white",
  paid: "bg-success text-white",
  partial: "bg-warning text-white",
  not_paid: "bg-danger text-white",
  revised: "bg-accent text-accent-foreground",
};

const STATUS_LABELS: Record<Status, string> = {
  draft: "Draft",
  confirmed: "Confirmed",
  posted: "Posted",
  cancelled: "Cancelled",
  paid: "Paid",
  partial: "Partial",
  not_paid: "Not Paid",
  revised: "Revised",
};

type StatusBadgeProps = {
  status: Status;
  className?: string;
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium",
        STATUS_STYLES[status],
        className,
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

import { cn } from "@/lib/utils";

// Indian digit grouping (₹1,00,000.00) via Intl — formatting only. Never do
// money arithmetic in JS (SPEC.md §13.1/§13.5, AGENTS.md R2): the value
// passed in must already be the server-computed figure.
const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

type MoneyDisplayProps = {
  value: string | number;
  className?: string;
};

export function MoneyDisplay({ value, className }: MoneyDisplayProps) {
  const numeric = typeof value === "string" ? Number(value) : value;
  const formatted = Number.isFinite(numeric) ? inrFormatter.format(numeric) : "—";

  return (
    <span className={cn("font-medium tabular-nums text-text_primary", className)}>
      {formatted}
    </span>
  );
}

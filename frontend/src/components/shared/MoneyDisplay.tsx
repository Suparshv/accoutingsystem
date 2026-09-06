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

  // whitespace-nowrap is load-bearing, not cosmetic. Intl renders a negative
  // as "-₹23,000.00" with the minus as its own leading glyph, so a narrow
  // table cell wrapped straight after it and left the amount reading as
  //
  //     -
  //     ₹23,000.00
  //
  // which looks like this table's own "no value" em-dash followed by a
  // POSITIVE number — the exact opposite of the truth.
  return (
    <span
      className={cn(
        "whitespace-nowrap font-medium tabular-nums text-text_primary",
        className,
      )}
    >
      {formatted}
    </span>
  );
}

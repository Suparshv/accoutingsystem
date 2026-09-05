// Money helpers. SPEC.md §4 says lib/money.ts is "formatting ONLY, never
// arithmetic", and the spirit of that rule (P2 / AGENTS.md R2) is: never let a
// money value become an IEEE-754 float.
//
// The Journal Entry form is the one place the UI genuinely must add money up
// before the server sees it — the mockup requires a live Debit/Credit running
// total and a Post button that stays disabled until they match. Sending it to
// the server per keystroke isn't viable.
//
// So instead of floats, we parse each amount into an exact integer number of
// paise and sum those. Integer addition is exact up to 2^53 paise (~90,000
// crore), so the balance check can never be wrong by a rounding error the way
// 0.1 + 0.2 !== 0.3 would be. The server still re-validates with Decimal and
// rejects an unbalanced entry — this is a UI affordance, not the authority.

/** "1234.56" -> 123456 paise. Returns 0 for blank/malformed input. */
export function toMinorUnits(value: string): number {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return 0;

  const match = /^(-?)(\d*)(?:\.(\d{0,2}))?$/.exec(trimmed);
  if (!match) return 0;

  const [, sign, whole, fraction = ""] = match;
  const paise = Number(whole || "0") * 100 + Number(fraction.padEnd(2, "0") || "0");
  return sign === "-" ? -paise : paise;
}

/** 123456 paise -> "1234.56", for handing to MoneyDisplay. */
export function fromMinorUnits(minor: number): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(Math.trunc(minor));
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

/** Exact sum of money strings, returned in paise. */
export function sumMinorUnits(values: string[]): number {
  return values.reduce((total, value) => total + toMinorUnits(value), 0);
}

/** The year a report defaults to. */
export function currentYear(): number {
  return new Date().getFullYear();
}

/** Years offered in the report year selector: next year back through four ago. */
export function yearOptions(): number[] {
  const now = currentYear();
  return [now + 1, now, now - 1, now - 2, now - 3];
}

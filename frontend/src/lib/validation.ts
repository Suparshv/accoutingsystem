// Required-field checks for the forms that are NOT react-hook-form.
//
// The document forms (sales/purchase orders, invoices, bills, journal entries,
// budgets) hold their state in plain useState because their fields arrive from
// a fetched document and their Save/Confirm buttons live in FormShell's header
// rather than inside a <form>. They used to express "this field is required"
// only by grabbing the Save button out from under the user — no message, no
// mark on the label, nothing saying which field was at fault.
//
// The message wording matches what zod produces on the react-hook-form pages
// ("Name is required"), so the whole app says the same thing.

export type FieldErrors = Record<string, string>;

/**
 * `{ field: [value, "Label"] }` -> a message for each blank value.
 *
 * Call it during render, not on submit: the message then disappears as soon
 * as the user fills the field in, with no error state to clear by hand. The
 * page decides *when* to show what comes back — normally only after the first
 * save attempt, so a fresh form is not red before it has been touched.
 */
export function requiredErrors(
  fields: Record<string, [value: string, label: string]>,
): FieldErrors {
  const errors: FieldErrors = {};
  for (const [name, [value, label]] of Object.entries(fields)) {
    if (!value.trim()) errors[name] = `${label} is required`;
  }
  return errors;
}

export function hasErrors(errors: FieldErrors): boolean {
  return Object.keys(errors).length > 0;
}

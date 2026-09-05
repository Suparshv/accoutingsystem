import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import type { ApiError } from "@/lib/api";

type ServerFieldError = { loc: (string | number)[]; msg: string };

// SPEC.md §13.5 — "Server 422 field errors map back onto the form fields by
// name." A VALIDATION_ERROR's details.fields come straight from FastAPI's
// RequestValidationError (each with a `loc` path ending in the field name).
// A business-rule conflict (409 LOGIN_ID_TAKEN, EMAIL_TAKEN, ...) isn't
// field-shaped on the wire, so callers pass a code -> field map for those;
// anything neither of these recognises is left for the caller to show as a
// banner instead. Returns true if at least one field error was set.
export function applyServerErrors<T extends FieldValues>(
  error: ApiError,
  setError: UseFormSetError<T>,
  codeFieldMap: Partial<Record<string, Path<T>>> = {},
): boolean {
  if (error.code === "VALIDATION_ERROR" && error.details) {
    const fields = (error.details as { fields?: ServerFieldError[] }).fields ?? [];
    let applied = false;
    for (const field of fields) {
      const name = field.loc[field.loc.length - 1];
      if (typeof name === "string") {
        setError(name as Path<T>, { type: "server", message: field.msg });
        applied = true;
      }
    }
    return applied;
  }

  const mappedField = codeFieldMap[error.code];
  if (mappedField) {
    setError(mappedField, { type: "server", message: error.message });
    return true;
  }

  return false;
}

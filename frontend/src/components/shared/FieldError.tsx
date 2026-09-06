// One rendering of "this field is wrong", so every form in the app reports a
// missing value the same way (SPEC.md §13.5). Renders nothing when there is
// no message, so it can sit unconditionally under a control.
//
// `role="alert"` makes a screen reader announce the message when it appears
// after a failed save, rather than leaving it as silent red text.
export function FieldError({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1 text-xs text-danger">
      {message}
    </p>
  );
}

import { useEffect, useState } from "react";

// One definition of "the user has stopped typing", shared by every search box
// (SPEC.md §13.2 DataTable). Thirteen pages had hand-rolled copies of this
// effect; a search box that fires per keystroke is the bug it prevents.
export const SEARCH_DEBOUNCE_MS = 400;

/**
 * The latest `value` once it has held still for `delay` milliseconds.
 *
 * Each change restarts the timer, so a run of keystrokes — or of backspaces —
 * settles into exactly one update after the last one.
 */
export function useDebouncedValue<T>(value: T, delay = SEARCH_DEBOUNCE_MS): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

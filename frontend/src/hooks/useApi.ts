import { useCallback, useEffect, useState } from "react";
import { api, normaliseError, type ApiError } from "@/lib/api";

// SPEC.md §13.4 — the entire state-management story. No query library (see §3 explicitly_excluded).
//
// `enabled` (default true) lets a caller that already knows a fetch is
// pointless for the current user — e.g. Dashboard.tsx skipping /dashboard
// entirely for a contact role, which the API would 403 anyway — skip it
// without ever issuing the request. Hooks can't be called conditionally, so
// this is a flag rather than an early return around the whole hook.
export function useApi<T>(path: string, deps: unknown[] = [], enabled: boolean = true) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<ApiError | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<T>(path));
    } catch (e) {
      setError(normaliseError(e));
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  return { data, loading, error, refetch };
}

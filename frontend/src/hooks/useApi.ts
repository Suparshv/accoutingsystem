import { useCallback, useEffect, useState } from "react";
import { api, normaliseError, type ApiError } from "@/lib/api";

// SPEC.md §13.4 — the entire state-management story. No query library (see §3 explicitly_excluded).
export function useApi<T>(path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
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
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, refetch };
}

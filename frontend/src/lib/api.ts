const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

// Mirrors the error envelope in SPEC.md §12.1 — every backend error response has this shape.
export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown> | null;
    correlation_id: string;
  };
};

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown> | null;
  correlationId: string;
  status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.details = body.error.details;
    this.correlationId = body.error.correlation_id;
  }
}

// The JWT lives in memory only, never localStorage — a page reload logs the
// user out, which is the deliberate tradeoff for not persisting a bearer
// token somewhere an XSS payload could read it. useAuth (src/hooks/useAuth.tsx)
// is the only caller of setAuthToken; every other module just reads through
// api.* and gets the header attached automatically.
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const body = (await response.json()) as ApiErrorBody;
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

import { getMockResponse } from "./mockData";

let demoMode =
  typeof window !== "undefined" &&
  window.sessionStorage.getItem("urban_demo_mode") === "true";

export function setDemoMode(active: boolean): void {
  demoMode = active;
  if (typeof window !== "undefined") {
    if (active) {
      window.sessionStorage.setItem("urban_demo_mode", "true");
    } else {
      window.sessionStorage.removeItem("urban_demo_mode");
    }
  }
}

export function isDemoMode(): boolean {
  return demoMode;
}

export const api = {
  get: async <T>(path: string): Promise<T> => {
    if (demoMode) {
      const mock = getMockResponse<T>(path);
      if (mock !== undefined) {
        return mock;
      }
    }
    return request<T>(path, { method: "GET" });
  },
  post: async <T>(path: string, body?: unknown): Promise<T> => {
    if (demoMode) {
      return { success: true, id: 99 } as unknown as T;
    }
    return request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
  },
  put: async <T>(path: string, body?: unknown): Promise<T> => {
    if (demoMode) {
      return { success: true } as unknown as T;
    }
    return request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined });
  },
  patch: async <T>(path: string, body?: unknown): Promise<T> => {
    if (demoMode) {
      return { success: true } as unknown as T;
    }
    return request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined });
  },
  delete: async <T>(path: string): Promise<T> => {
    if (demoMode) {
      return undefined as T;
    }
    return request<T>(path, { method: "DELETE" });
  },
};

export function normaliseError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError(500, {
    error: {
      code: "UNKNOWN_ERROR",
      message: e instanceof Error ? e.message : "An unexpected error occurred.",
      details: null,
      correlation_id: "",
    },
  });
}

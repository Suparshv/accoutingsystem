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

function getAuthToken(): string | null {
  // Placeholder — wired up once auth (useAuth) lands. Reads the stored JWT, if any.
  return localStorage.getItem("auth_token");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
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

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
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

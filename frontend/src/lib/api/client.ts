// Thin fetch wrapper for the backend API.
//
// - Always sends cookies (credentials: "include") so the httpOnly auth
//   cookies set by /auth/login travel with every request.
// - Normalizes errors into ApiError with a status + human-readable detail.
// - Base URL comes from NEXT_PUBLIC_API_URL (e.g. http://localhost:8000/api/v1).

import { ApiError } from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type Json = Record<string, unknown> | unknown[];

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: Json;
  // For endpoints that return no content (204).
  expectNoContent?: boolean;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, expectNoContent = false } = opts;

  const headers: Record<string, string> = {};
  let serializedBody: string | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    serializedBody = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: serializedBody,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "Network error — is the backend running?");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (data && typeof data.detail === "string") {
        detail = data.detail;
      } else if (Array.isArray(data?.detail)) {
        // FastAPI validation errors: array of {msg, loc, ...}
        detail = data.detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join("; ") || detail;
      }
    } catch {
      // response body not JSON; keep default detail
    }
    throw new ApiError(response.status, detail);
  }

  if (expectNoContent || response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: Json) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: Json) => request<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body?: Json) => request<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE", expectNoContent: true }),
};

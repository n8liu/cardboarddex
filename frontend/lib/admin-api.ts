import { resolveApiUrl } from "@/lib/api";
import type { StatsReport } from "@/types/analytics";

export class AdminApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${resolveApiUrl()}/admin${path}`, {
    ...init, credentials: "include", cache: "no-store",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const message = response.status === 401 ? "Login required or session expired."
      : response.status === 403 ? "Admin access is disabled or this origin is not allowed."
      : response.status === 429 ? "Too many requests. Please wait a minute."
      : response.status === 422 ? "Select a valid date range within the last 90 days (UTC)."
      : `Statistics unavailable (HTTP ${response.status}). Please try again.`;
    throw new AdminApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export function getStats(start: string, end: string, signal?: AbortSignal) {
  return adminRequest<StatsReport>(`/stats?${new URLSearchParams({ start, end })}`, { signal });
}

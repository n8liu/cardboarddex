import { resolveApiUrl } from "@/lib/api";

const VISITOR_KEY = "cardboarddex_visitor";
export const OPT_OUT_KEY = "cardboarddex_analytics_opt_out";
const PUBLIC_PATH = /^\/(?:catalog|pokedex|market-movers|grading-profit|sealed-signals|top-volume|live-updates|binder|cards\/[A-Za-z0-9_-]{1,64}|pokemon\/[A-Za-z0-9_-]{1,64})?$/;
let lastPath: string | null = null;

export function analyticsOptedOut(): boolean {
  try {
    return localStorage.getItem(OPT_OUT_KEY) === "1" || navigator.doNotTrack === "1";
  } catch (error) {
    console.warn("Analytics preferences unavailable", error);
    return true;
  }
}

export function setAnalyticsOptOut(value: boolean): void {
  try {
    localStorage.setItem(OPT_OUT_KEY, value ? "1" : "0");
    if (value) localStorage.removeItem(VISITOR_KEY);
  } catch (error) {
    console.warn("Could not save analytics preference", error);
  }
}

export async function trackPageView(path: string): Promise<void> {
  // Keep the previous path even for excluded pages so A -> admin -> A is a revisit.
  if (path === lastPath) return;
  lastPath = path;
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  if ((process.env.NODE_ENV !== "production" || local) && process.env.NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL !== "true") return;
  if (process.env.NEXT_PUBLIC_ANALYTICS_ENABLED !== "true" || !PUBLIC_PATH.test(path) || analyticsOptedOut()) return;
  try {
    let visitor = localStorage.getItem(VISITOR_KEY);
    if (!visitor || !/^[0-9a-f-]{36}$/i.test(visitor)) {
      visitor = crypto.randomUUID();
      localStorage.setItem(VISITOR_KEY, visitor);
    }
    const body = JSON.stringify({ event_id: crypto.randomUUID(), visitor_id: visitor, path });
    for (let attempt = 0; attempt < 2; attempt++) {
      if (analyticsOptedOut()) return;
      try {
        const response = await fetch(`${resolveApiUrl()}/telemetry/page-view`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body, keepalive: true, credentials: "omit", cache: "no-store",
          signal: AbortSignal.timeout(5000),
        });
        if (response.ok) return;
        if (response.status < 500) {
          console.warn(`Page tracking rejected: HTTP ${response.status}`);
          return;
        }
        throw new Error(`HTTP ${response.status}`);
      } catch (error) {
        console.warn(`Page tracking attempt ${attempt + 1} failed`, error);
      }
    }
  } catch (error) {
    console.warn("Page tracking unavailable", error);
  }
}

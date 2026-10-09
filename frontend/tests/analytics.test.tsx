import { StrictMode } from "react";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

let pathname = "/catalog";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));
vi.mock("@/lib/api", () => ({ resolveApiUrl: () => "https://api.example.com" }));
const fetchMock = vi.fn();

beforeEach(() => {
  vi.resetModules(); localStorage.clear(); pathname = "/catalog";
  vi.stubEnv("NEXT_PUBLIC_ANALYTICS_ENABLED", "true");
  vi.stubEnv("NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL", "true");
  fetchMock.mockReset().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

it("counts navigation and revisits once, including Strict Mode effect replay", async () => {
  const { AnalyticsTracker } = await import("@/components/analytics-tracker");
  const view = render(<StrictMode><AnalyticsTracker /></StrictMode>);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  view.rerender(<StrictMode><AnalyticsTracker /></StrictMode>);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  pathname = "/pokedex"; view.rerender(<StrictMode><AnalyticsTracker /></StrictMode>);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  pathname = "/catalog"; view.rerender(<StrictMode><AnalyticsTracker /></StrictMode>);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  const bodies = fetchMock.mock.calls.map((call) => JSON.parse(call[1].body));
  expect(new Set(bodies.map((body) => body.visitor_id)).size).toBe(1);
  expect(new Set(bodies.map((body) => body.event_id)).size).toBe(3);
  view.unmount();
});

it("excludes admin pages, query strings, opt-outs and disabled environments", async () => {
  const { trackPageView, setAnalyticsOptOut } = await import("@/lib/analytics");
  await trackPageView("/admin/stats"); await trackPageView("/catalog?q=private");
  setAnalyticsOptOut(true); await trackPageView("/catalog");
  setAnalyticsOptOut(false); vi.stubEnv("NEXT_PUBLIC_ANALYTICS_ENABLED", "false");
  await trackPageView("/pokedex");
  expect(fetchMock).not.toHaveBeenCalled();
});

it("retries transient delivery failure with the same event ID and no credentials", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  fetchMock.mockRejectedValueOnce(new Error("offline"));
  const { trackPageView } = await import("@/lib/analytics");
  await trackPageView("/catalog");
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock.mock.calls[0][1].body).toBe(fetchMock.mock.calls[1][1].body);
  expect(fetchMock.mock.calls[0][1].credentials).toBe("omit");
});

it("does not retry rate limits or throw when browser storage is unavailable", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  fetchMock.mockResolvedValue(new Response(null, { status: 429 }));
  const { trackPageView } = await import("@/lib/analytics");
  await trackPageView("/catalog");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); } });
  await expect(trackPageView("/pokedex")).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});


it("excludes development traffic unless explicitly enabled", async () => {
  vi.stubEnv("NEXT_PUBLIC_ANALYTICS_ALLOW_LOCAL", "false");
  const { trackPageView } = await import("@/lib/analytics");
  await trackPageView("/catalog");
  expect(fetchMock).not.toHaveBeenCalled();
});

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useLiveStats } from "@/lib/use-live-stats";
import { getLiveStats } from "@/lib/api";
import type { LiveStatsResponse } from "@/types/card";

vi.mock("@/lib/api", () => ({ getLiveStats: vi.fn() }));
const snapshot = (): LiveStatsResponse => ({ total_items: 0, graded_updates_count: 0,
  total_ebay_updates: 0, total_tcg_updates: 0, total_ppt_updates: 0,
  generated_at: new Date().toISOString(), is_stale: false });
function Probe() {
  const { stats, stale, loading, error, retry } = useLiveStats();
  return <><p>{stats ? `Count ${stats.total_items}` : loading ? "Loading" : "Unavailable"}</p>
    <p>{stale ? "Stale" : "Fresh"}</p>{error && <p>Error</p>}<button onClick={retry}>Retry</button></>;
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(getLiveStats).mockReset();
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

it("distinguishes real zero from unavailable and retries independently", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(getLiveStats).mockRejectedValueOnce(new Error("offline")).mockResolvedValue(snapshot());
  render(<Probe />);
  await act(async () => {});
  expect(screen.getByText("Unavailable")).toBeVisible();
  fireEvent.click(screen.getByText("Retry"));
  await act(async () => {});
  expect(screen.getByText("Count 0")).toBeVisible();
});

it("preserves stale values on refresh failure, then expires them at thirty minutes", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(getLiveStats).mockResolvedValueOnce(snapshot()).mockRejectedValue(new Error("offline"));
  render(<Probe />);
  await act(async () => {});
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(screen.getByText("Count 0")).toBeVisible();
  expect(screen.getByText("Stale")).toBeVisible();
  await act(async () => { await vi.advanceTimersByTimeAsync(29 * 60_000); });
  expect(screen.getByText("Unavailable")).toBeVisible();
});

it("avoids overlapping polls and aborts on hide and unmount", async () => {
  vi.mocked(getLiveStats).mockImplementation(() => new Promise(() => {}));
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  const view = render(<Probe />);
  await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
  expect(getLiveStats).toHaveBeenCalledTimes(1);
  const signal = vi.mocked(getLiveStats).mock.calls[0][0]?.abortSignal;
  hidden.mockReturnValue(true);
  fireEvent(document, new Event("visibilitychange"));
  expect(signal?.aborted).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
  expect(getLiveStats).toHaveBeenCalledTimes(1);
  hidden.mockReturnValue(false);
  fireEvent(document, new Event("visibilitychange"));
  expect(getLiveStats).toHaveBeenCalledTimes(2);
  const next = vi.mocked(getLiveStats).mock.calls[1][0]?.abortSignal;
  view.unmount();
  expect(next?.aborted).toBe(true);
});

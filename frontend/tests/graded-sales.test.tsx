import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GradedSalesActivityPanel } from "@/components/graded-sales-activity-panel";
import { getGradedSalesActivity } from "@/lib/api";
import type { GradedSalesActivity } from "@/types/market-data";

vi.mock("@/lib/api", () => ({ getGradedSalesActivity: vi.fn(), cardImageUrl: (src: string) => src }));
vi.mock("@/components/card-image", () => ({ default: () => null }));
const empty: GradedSalesActivity = { status: "not_synced", coverage: "Provider-reported coverage; not a selected-period total.", synced_at: null, products_with_sales_data: 0, items: [] };
const ready: GradedSalesActivity = { ...empty, status: "ready", products_with_sales_data: 1, items: [{
  card_id: "card", name: "Pikachu", set_name: "Example", image_url: null, sales: 0,
  grades: [{ grade: "psa10", sales: 0, last_sale_date: null }], last_sale_date: null,
  synced_at: "2026-10-01T00:00:00Z", stale: true,
}] };
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

it.each([
  ["provider_disabled", /not enabled yet/],
  ["not_synced", /No graded sales counts have been synced/],
  ["no_matches", /No synced graded sales counts match/],
] as const)("explains %s without inventing zero sales", async (status, message) => {
  vi.mocked(getGradedSalesActivity).mockResolvedValue({ ...empty, status });
  render(<GradedSalesActivityPanel />);
  expect(await screen.findByText(message)).toBeVisible();
  expect(screen.queryByText(/0 reported graded sales/)).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});

it("shows explicit zero, grade labels, coverage and stale sync dates", async () => {
  vi.mocked(getGradedSalesActivity).mockResolvedValue(ready);
  render(<GradedSalesActivityPanel />);
  expect(await screen.findByText("0 reported graded sales")).toBeVisible();
  expect(screen.getByText("psa10: 0")).toBeVisible();
  expect(screen.getByText(/Stale snapshot.*2026-10-01/)).toBeVisible();
  expect(screen.getByText("Latest sale unknown")).toBeVisible();
  expect(screen.getByText(/not a selected-period total/)).toBeVisible();
  expect(screen.getByRole("link")).toHaveAttribute("href", "/cards/card?ref=trending");
});

it("retries a failed request", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(getGradedSalesActivity).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(ready);
  try {
    render(<GradedSalesActivityPanel />);
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Retry graded sales" }));
    expect(await screen.findByText("Pikachu")).toBeVisible();
    expect(log).toHaveBeenCalledWith("Graded sales activity request failed:", expect.any(Error));
  } finally { log.mockRestore(); }
});

it("aborts obsolete searches and ignores their responses", async () => {
  let finish!: (data: GradedSalesActivity) => void;
  vi.mocked(getGradedSalesActivity).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce(empty);
  const { rerender } = render(<GradedSalesActivityPanel query="old" />);
  await waitFor(() => expect(getGradedSalesActivity).toHaveBeenCalledTimes(1));
  const signal = vi.mocked(getGradedSalesActivity).mock.calls[0][1];
  rerender(<GradedSalesActivityPanel query="new" />);
  expect(signal?.aborted).toBe(true);
  await screen.findByText(/No graded sales counts have been synced/);
  await act(async () => finish(ready));
  expect(screen.queryByText("Pikachu")).not.toBeInTheDocument();
  expect(getGradedSalesActivity).toHaveBeenLastCalledWith("new", expect.any(AbortSignal));
});

it("limits overview to 15 cards and the full view to 50", async () => {
  vi.mocked(getGradedSalesActivity).mockResolvedValue({ ...ready, items: Array.from({ length: 50 }, (_, i) => ({ ...ready.items[0], card_id: String(i) })) });
  const { rerender } = render(<GradedSalesActivityPanel compact />);
  await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(15));
  rerender(<GradedSalesActivityPanel />);
  expect(screen.getAllByRole("link")).toHaveLength(50);
});

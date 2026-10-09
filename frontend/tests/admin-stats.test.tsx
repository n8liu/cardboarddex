import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StatsDashboard } from "@/components/admin/stats-dashboard";
import { AdminLogin } from "@/components/admin/admin-login";
import { AdminApiError, adminRequest, getStats } from "@/lib/admin-api";
import type { StatsReport } from "@/types/analytics";

vi.mock("@/lib/admin-api", async (original) => {
  const actual = await original<typeof import("@/lib/admin-api")>();
  return { ...actual, adminRequest: vi.fn(), getStats: vi.fn() };
});
vi.mock("recharts", () => {
  const Empty = () => null;
  return { ResponsiveContainer: Empty, CartesianGrid: Empty, Legend: Empty, Line: Empty, LineChart: Empty, Tooltip: Empty, XAxis: Empty, YAxis: Empty };
});
const report: StatsReport = {
  start: "2026-10-03", end: "2026-10-09", timezone: "UTC", updated_at: "2026-10-09T12:00:00Z",
  tracking_started_at: "2026-10-08T12:00:00Z", tracking_enabled: true,
  earliest_report_date: "2026-07-12", total_views: 10, total_visitors: 2,
  current: { views: 10, visitors: 2, sessions: 3 }, previous: { views: 0, visitors: 0, sessions: 0 },
  daily: [{ day: "2026-10-09", views: 10, visitors: 2, sessions: 3 }],
  countries: [{ country: "ZZ", views: 10, visitors: 2, sessions: 3 }],
  pages: [{ path: "/catalog", views: 10, visitors: 2, sessions: 3 }],
};
beforeEach(() => { vi.mocked(getStats).mockReset(); vi.mocked(adminRequest).mockReset(); });
afterEach(cleanup);

it("shows login after unauthorized response, without private metrics", async () => {
  vi.mocked(getStats).mockRejectedValue(new AdminApiError(401, "Login required"));
  render(<StatsDashboard />);
  expect(await screen.findByLabelText("Admin secret")).toBeInTheDocument();
  expect(screen.queryByText("Lifetime visitors")).not.toBeInTheDocument();
});

it("renders reporting and clears private data on logout", async () => {
  vi.mocked(getStats).mockResolvedValue(report);
  vi.mocked(adminRequest).mockResolvedValue({ status: "ok" });
  render(<StatsDashboard />);
  expect(await screen.findByText("Lifetime visitors")).toBeInTheDocument();
  expect(screen.getByText("Unknown")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Sign out"));
  await screen.findByLabelText("Admin secret");
  expect(screen.queryByText("Lifetime visitors")).not.toBeInTheDocument();
  expect(adminRequest).toHaveBeenCalledWith("/logout", { method: "POST" });
});

it("distinguishes unavailable reports from zero traffic", async () => {
  vi.mocked(getStats).mockRejectedValue(new AdminApiError(503, "Statistics unavailable"));
  render(<StatsDashboard />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Statistics unavailable");
  expect(screen.queryByText("Lifetime views")).not.toBeInTheDocument();
});

it("refreshes with requested dates and handles session expiration", async () => {
  vi.mocked(getStats).mockResolvedValueOnce(report).mockRejectedValueOnce(new AdminApiError(401, "Expired"));
  render(<StatsDashboard />);
  await screen.findByText("Lifetime visitors");
  fireEvent.click(screen.getByText("Today"));
  await screen.findByLabelText("Admin secret");
  const [start, end] = vi.mocked(getStats).mock.calls[1];
  expect(start).toBe(end);
  expect(screen.queryByText("Lifetime visitors")).not.toBeInTheDocument();
});

it("does not save the admin secret in browser storage", async () => {
  const onLogin = vi.fn();
  vi.mocked(adminRequest).mockResolvedValue({ status: "ok" });
  const local = vi.spyOn(localStorage, "setItem");
  const session = vi.spyOn(sessionStorage, "setItem");
  render(<AdminLogin onLogin={onLogin} />);
  fireEvent.change(screen.getByLabelText("Admin secret"), { target: { value: "secret" } });
  fireEvent.click(screen.getByText("Sign in"));
  await waitFor(() => expect(onLogin).toHaveBeenCalled());
  expect(screen.getByLabelText("Admin secret")).toHaveValue("");
  expect(local).not.toHaveBeenCalled(); expect(session).not.toHaveBeenCalled();
  local.mockRestore(); session.mockRestore();
});

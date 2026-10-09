"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AdminLogin } from "@/components/admin/admin-login";
import { AdminApiError, adminRequest, getStats } from "@/lib/admin-api";
import type { StatsReport, TrafficCounts } from "@/types/analytics";

function isoDay(value: Date) { return value.toISOString().slice(0, 10); }
function range(days: number) {
  const end = new Date();
  const start = new Date(end); start.setUTCDate(start.getUTCDate() - days + 1);
  return { start: isoDay(start), end: isoDay(end) };
}
const number = (value: number) => value.toLocaleString();
function change(current: number, previous: number) {
  if (!previous) return current ? "No previous-period baseline" : "No change";
  const delta = ((current - previous) / previous) * 100;
  return `${delta > 0 ? "+" : ""}${delta.toFixed(1)}% vs previous period`;
}
function countryName(code: string) {
  if (code === "ZZ") return "Unknown";
  return new Intl.DisplayNames(["en"], { type: "region" }).of(code) || code;
}

export function StatsDashboard() {
  const [selected, setSelected] = useState(() => range(7));
  const [draft, setDraft] = useState(selected);
  const [data, setData] = useState<StatsReport | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [logoutBusy, setLogoutBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError(""); setData(null);
    getStats(selected.start, selected.end, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setData(result); setNeedsLogin(false); }
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      if (error instanceof AdminApiError && error.status === 401) setNeedsLogin(true);
      else setError(error instanceof Error ? error.message : "Unable to load statistics.");
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [selected, refresh]);

  if (needsLogin) return <AdminLogin onLogin={() => { setNeedsLogin(false); setRefresh((value) => value + 1); }} />;
  const minimum = range(90).start;
  return <div className="mt-8 space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap gap-2">{[[1, "Today"], [7, "7 days"], [30, "30 days"]].map(([days, label]) => <button key={days} disabled={busy} onClick={() => {
        const next = range(Number(days)); setSelected(next); setDraft(next);
      }} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">{label}</button>)}</div>
      <div className="flex gap-3">
        <button disabled={busy} onClick={() => setRefresh((value) => value + 1)} className="text-sm font-semibold text-emerald-800 disabled:opacity-50">Refresh</button>
        {data && <button disabled={logoutBusy} className="text-sm text-slate-600" onClick={async () => {
          setLogoutBusy(true);
          try { await adminRequest("/logout", { method: "POST" }); setData(null); setNeedsLogin(true); }
          catch (error) {
            if (error instanceof AdminApiError && error.status === 401) { setData(null); setNeedsLogin(true); }
            else setError(error instanceof Error ? error.message : "Logout failed.");
          } finally { setLogoutBusy(false); }
        }}>Sign out</button>}
      </div>
    </div>
    <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); setSelected({ ...draft }); }}>
      <label className="text-sm">From (UTC)<input aria-label="From date" type="date" required min={minimum} max={draft.end} value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} className="mt-1 block rounded-lg border border-slate-300 bg-white p-2" /></label>
      <label className="text-sm">Through (UTC)<input aria-label="Through date" type="date" required min={draft.start} max={range(1).end} value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} className="mt-1 block rounded-lg border border-slate-300 bg-white p-2" /></label>
      <button disabled={busy} className="rounded-lg bg-emerald-800 px-4 py-2 text-white disabled:opacity-50">Apply dates</button>
    </form>
    {busy && <p role="status">Loading private statistics…</p>}
    {error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error}</p>}
    {data && <>
      {!data.tracking_enabled && <p className="rounded-lg bg-amber-50 p-4 text-amber-900">Tracking is currently disabled. Previously collected statistics remain available.</p>}
      {!data.tracking_started_at && <p className="rounded-lg bg-slate-100 p-4">No visits recorded yet. Statistics begin when browser tracking is enabled and visitors arrive.</p>}
      <p className="text-sm text-slate-500">{data.start} — {data.end} · UTC · Updated {new Date(data.updated_at).toLocaleTimeString()}{data.tracking_started_at && ` · Tracking since ${isoDay(new Date(data.tracking_started_at))}`}</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {([['views', 'Page views'], ['visitors', 'Unique visitors'], ['sessions', 'Sessions']] as const).map(([key, label]) => <Metric key={key} label={label} value={data.current[key]} note={data.previous ? change(data.current[key], data.previous[key]) : "Previous period outside retention window"} />)}
        <Metric label="Lifetime views" value={data.total_views} note="Since tracking began" />
        <Metric label="Lifetime visitors" value={data.total_visitors} note="Distinct browser identifiers" />
      </div>
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="mb-5 text-lg font-semibold">Daily traffic</h2>
        <div className="h-80" role="img" aria-label="Daily page views, unique visitors, and sessions. Exact values are available in the table below.">
          <ResponsiveContainer width="100%" height="100%"><LineChart data={data.daily}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="day" tickFormatter={(day: string) => day.slice(5)} /><YAxis allowDecimals={false} width={45} /><Tooltip /><Legend />
            <Line type="monotone" dataKey="views" name="Page views" stroke="#047857" strokeWidth={2} dot={data.daily.length === 1} />
            <Line type="monotone" dataKey="visitors" name="Unique visitors" stroke="#4f46e5" strokeWidth={2} dot={data.daily.length === 1} />
            <Line type="monotone" dataKey="sessions" name="Sessions" stroke="#d97706" dot={data.daily.length === 1} />
          </LineChart></ResponsiveContainer>
        </div>
        <details className="mt-4"><summary className="cursor-pointer text-sm text-emerald-800">View daily numbers</summary><TrafficTable label="Date" rows={data.daily.map((row) => ({ ...row, label: row.day }))} /></details>
      </section>
      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold">Countries</h2><p className="mt-1 text-xs text-slate-500">Approximate location. Visitors can appear in more than one country.</p><TrafficTable label="Country" rows={data.countries.map((row) => ({ ...row, label: countryName(row.country) }))} /></section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold">Top 20 pages</h2><TrafficTable label="Page" rows={data.pages.map((row) => ({ ...row, label: row.path }))} /></section>
      </div>
      <p className="max-w-4xl text-xs leading-5 text-slate-500">Visitors are browser identifiers, not verified people. Clearing browser storage or using another device creates a new visitor. Sessions restart after 30 minutes without a tracked page view; sessions shown were active in the selected period. Daily unique counts should not be added together. Blockers, opt-outs, and delivery failures can reduce recorded traffic. Detailed reports cover the last 90 days.</p>
    </>}
  </div>;
}

function Metric({ label, value, note }: { label: string; value: number; note: string }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-sm text-slate-500">{label}</h2><p className="mt-2 text-3xl font-semibold tracking-tight">{number(value)}</p><p className="mt-2 text-xs text-slate-500">{note}</p></div>;
}
function TrafficTable({ label, rows }: { label: string; rows: (TrafficCounts & { label: string })[] }) {
  if (!rows.length) return <p className="py-8 text-sm text-slate-500">No recorded visits in this period.</p>;
  return <div className="mt-4 overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-3 pr-4">{label}</th><th className="px-2 text-right">Views</th><th className="px-2 text-right">Visitors</th><th className="px-2 text-right">Sessions</th></tr></thead><tbody>{rows.map((row) => <tr key={row.label} className="border-b border-slate-100"><td className="max-w-64 break-words py-3 pr-4">{row.label}</td><td className="px-2 text-right">{number(row.views)}</td><td className="px-2 text-right">{number(row.visitors)}</td><td className="px-2 text-right">{number(row.sessions)}</td></tr>)}</tbody></table></div>;
}

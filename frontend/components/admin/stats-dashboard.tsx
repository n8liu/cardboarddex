"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CatalogHealth } from "@/components/admin/catalog-health";
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
      <div className="flex flex-wrap gap-2">{[[1, "Today"], [7, "7 days"], [30, "30 days"]].map(([days, label]) => <button key={days} disabled={busy} aria-pressed={selected.start === range(Number(days)).start && selected.end === range(Number(days)).end} onClick={() => {
        const next = range(Number(days)); setSelected(next); setDraft(next);
      }} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold transition-colors hover:border-emerald-600 aria-pressed:border-emerald-800 aria-pressed:bg-emerald-800 aria-pressed:text-white disabled:opacity-50">{label}</button>)}</div>
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
    <form className="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200 bg-white p-4" onSubmit={(event) => { event.preventDefault(); setSelected({ ...draft }); }}>
      <label className="text-sm">From (UTC)<input aria-label="From date" type="date" required min={minimum} max={draft.end} value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} className="mt-1 block rounded-lg border border-slate-300 bg-white p-2" /></label>
      <label className="text-sm">Through (UTC)<input aria-label="Through date" type="date" required min={draft.start} max={range(1).end} value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} className="mt-1 block rounded-lg border border-slate-300 bg-white p-2" /></label>
      <button disabled={busy} className="rounded-lg bg-emerald-800 px-4 py-2 text-white disabled:opacity-50">Apply dates</button>
    </form>
    {busy && <p role="status">Loading private statistics…</p>}
    {error && <p role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error}</p>}
    {data && <>
      <CatalogHealth />
      {!data.tracking_enabled && <p className="rounded-lg bg-amber-50 p-4 text-amber-900">Tracking is currently disabled. Previously collected statistics remain available.</p>}
      {!data.tracking_started_at && <p className="rounded-lg bg-slate-100 p-4">No visits recorded yet. Statistics begin when browser tracking is enabled and visitors arrive.</p>}
      <p className="text-sm text-slate-500">{data.start} — {data.end} · UTC · Updated {new Date(data.updated_at).toLocaleTimeString()}{data.tracking_started_at && ` · Tracking since ${isoDay(new Date(data.tracking_started_at))}`}</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total visits" value={data.current.views} description="Every page view, including reloads and revisits" note={data.previous ? change(data.current.views, data.previous.views) : "Previous period unavailable"} accent />
        <Metric label="Unique visitors" value={data.current.visitors} description="Each browser counted once in this date range" note={data.previous ? change(data.current.visitors, data.previous.visitors) : "Previous period unavailable"} />
        <Metric label="Sessions" value={data.current.sessions} description="A new session after 30 minutes of inactivity" note={data.previous ? change(data.current.sessions, data.previous.sessions) : "Previous period unavailable"} />
        <Metric label="Views per visitor" value={data.current.visitors ? (data.current.views / data.current.visitors).toFixed(2) : "—"} description="Average pages viewed by each unique browser" note={`${number(Math.max(0, data.current.views - data.current.visitors))} additional views beyond each browser’s first`} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-slate-900 px-5 py-4 text-white">
        <div><p className="text-xs font-semibold uppercase tracking-widest text-slate-400">All time</p><p className="mt-1 text-sm text-slate-300">Since tracking began</p></div>
        <p className="text-sm text-slate-300">Lifetime views <strong className="ml-3 text-xl tabular-nums text-white">{number(data.total_views)}</strong></p>
        <p className="text-sm text-slate-300">Lifetime visitors <strong className="ml-3 text-xl tabular-nums text-white">{number(data.total_visitors)}</strong></p>
      </div>
      {data.current.views > 0 && data.current.views === data.current.visitors && <p className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-900">Visits and visitors match because each browser has one recorded page view in this period. Reloads and repeat visits increase total visits while keeping the same visitor.</p>}
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold">Daily traffic</h2>
        <p className="mb-5 mt-1 text-sm text-slate-500">Page views and distinct browsers each day · UTC. Today is a partial day.</p>
        <div className="h-80" role="img" aria-label="Daily page views, unique visitors, and sessions. Exact values are available in the table below.">
          <ResponsiveContainer width="100%" height="100%"><LineChart data={data.daily}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="day" tickFormatter={(day: string) => day.slice(5)} /><YAxis allowDecimals={false} width={45} /><Tooltip /><Legend />
            <Line type="linear" dataKey="views" name="Total visits" stroke="#047857" strokeWidth={2} dot={data.daily.length === 1} />
            <Line type="linear" dataKey="visitors" name="Unique visitors" stroke="#4f46e5" strokeWidth={2} dot={data.daily.length === 1} />
            <Line type="linear" dataKey="sessions" name="Sessions" stroke="#d97706" dot={data.daily.length === 1} />
          </LineChart></ResponsiveContainer>
        </div>
        <details className="mt-4"><summary className="cursor-pointer text-sm text-emerald-800">View daily numbers</summary><TrafficTable label="Date" rows={data.daily.map((row) => ({ ...row, label: row.day }))} /></details>
      </section>
      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold">Countries</h2><p className="mt-1 text-xs text-slate-500">Approximate location. Visitors can appear in more than one country.</p><TrafficTable total={data.current.views} label="Country" rows={data.countries.map((row) => ({ ...row, label: countryName(row.country) }))} /></section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold">Top 20 pages</h2><TrafficTable total={data.current.views} label="Page" rows={data.pages.map((row) => ({ ...row, label: row.path }))} /></section>
      </div>
      <p className="max-w-4xl text-xs leading-5 text-slate-500">Visitors are browser identifiers, not verified people. Clearing browser storage or using another device creates a new visitor. Sessions restart after 30 minutes without a tracked page view; sessions shown were active in the selected period. Daily unique counts should not be added together. Blockers, opt-outs, and delivery failures can reduce recorded traffic. Detailed reports cover the last 90 days.</p>
    </>}
  </div>;
}

function Metric({ label, value, note, description, accent = false }: { label: string; value: number | string; note: string; description: string; accent?: boolean }) {
  return <section className={`rounded-2xl border p-5 shadow-sm ${accent ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white"}`} aria-label={label}><h2 className="text-sm font-medium text-slate-600">{label}</h2><p className="mt-3 text-4xl font-semibold tracking-tight tabular-nums">{typeof value === "number" ? number(value) : value}</p><p className="mt-2 text-xs leading-5 text-slate-500">{description}</p><p className="mt-4 border-t border-slate-200/70 pt-3 text-xs text-slate-600">{note}</p></section>;
}
function TrafficTable({ label, rows, total }: { total?: number; label: string; rows: (TrafficCounts & { label: string })[] }) {
  if (!rows.length) return <p className="py-8 text-sm text-slate-500">No recorded visits in this period.</p>;
  return <div className="mt-4 overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-3 pr-4">{label}</th><th className="px-2 text-right">Views</th><th className="px-2 text-right">Visitors</th><th className="px-2 text-right">Sessions</th>{total !== undefined && <th className="pl-3 text-right">Share</th>}</tr></thead><tbody>{rows.map((row) => <tr key={row.label} className="border-b border-slate-100 tabular-nums hover:bg-slate-50"><td className="max-w-64 break-words py-3 pr-4">{row.label}</td><td className="px-2 text-right">{number(row.views)}</td><td className="px-2 text-right">{number(row.visitors)}</td><td className="px-2 text-right">{number(row.sessions)}</td>{total !== undefined && <td className="min-w-20 pl-3 text-right"><span>{total ? ((row.views / total) * 100).toFixed(1) : "0.0"}%</span><div className="mt-1 h-1 rounded-full bg-slate-100"><div className="h-1 rounded-full bg-emerald-500" style={{ width: `${total ? row.views / total * 100 : 0}%` }} /></div></td>}</tr>)}</tbody></table></div>;
}

"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { getCardSets } from "@/lib/api";
import { CONTENT_REVIEWED, sources } from "@/lib/learning-content";
import { calendarEvents, eventsForCalendar, formatEventTime, pokemonCenterHistory, preorderLeadDays, pstDay, releaseDateSource, RELEASE_SOURCE_UPDATED, formatDay, mergeSets, monthDays, parseDay, printStatus, relativeRelease, retailers, shiftMonth, type CalendarEvent, type ReleaseSet } from "@/lib/release-calendar";

const control = "rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-slate-400";

export function ReleaseCalendar() {
  // A stable first render avoids a build-time/browser-time hydration mismatch.
  const [today, setToday] = useState(CONTENT_REVIEWED);
  const [month, setMonth] = useState(CONTENT_REVIEWED.slice(0, 7));
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<"month" | "list">("month");
  const [retailer, setRetailer] = useState("all");
  const [kind, setKind] = useState("all");
  const catalog = useReleaseSets();
  const [showExpected, setShowExpected] = useState(true);
  const [calendarLanguage, setCalendarLanguage] = useState("all");
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  useEffect(() => {
    const current = pstDay(); setToday(current); setMonth(current.slice(0, 7)); setReady(true);
    const timer = window.setInterval(() => setToday(pstDay()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const allEvents = useMemo(() => eventsForCalendar(catalog.sets, month, today, showExpected), [catalog.sets, month, today, showExpected]);
  const events = allEvents.filter((event) => (retailer === "all" || event.retailer === retailer) && (kind === "all" || event.kind === kind) && (calendarLanguage === "all" || !event.language || event.language === calendarLanguage));
  const dated = events.filter((event) => event.date?.startsWith(month)).sort((a, b) => a.date!.localeCompare(b.date!) || (a.startsAt ?? "").localeCompare(b.startsAt ?? ""));
  const undated = events.filter((event) => !event.date);
  const visible = selectedDay ? dated.filter((event) => event.date === selectedDay) : dated;
  const monthTitle = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" }).format(parseDay(`${month}-01`)!);
  function changeMonth(next: string) {
    if (!/^\d{4}-\d{2}$/.test(next) || !parseDay(`${next}-01`) || next < "1900-01" || next > "2100-12") return;
    setMonth(next); setSelectedDay(null);
  }
  return <>
    <div className="mb-6 grid gap-3 md:grid-cols-3">{retailers.map((item) => {
      const nextDrop = calendarEvents.filter((event) => event.kind === "drop" && event.retailer === item.id && event.date && event.date >= today).sort((a, b) => a.date!.localeCompare(b.date!))[0];
      return <div key={item.id} className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between gap-3"><h2 className="text-sm font-bold">{item.name}</h2><span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] text-slate-500">US online</span></div><p className="mt-3 text-xs font-medium text-slate-700">{nextDrop ? `Announced drop: ${formatDay(nextDrop.date)}` : item.id === "target" ? "Expected: Tue & Thu · 12:00 AM PST" : item.id === "walmart" ? "Expected: Wed · 6:00 PM PST" : "Preorders: see reported history below"}</p><p className="mt-2 text-xs leading-6 text-slate-500">{item.note}</p><a href={item.url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-xs font-bold underline underline-offset-4">Visit {item.name} ↗</a></div>; })}</div>
    <div className="mb-6 rounded-xl border border-slate-200 bg-slate-100/70 p-4 text-xs leading-6 text-slate-600"><p><strong className="text-slate-800">Researched calendar · reviewed {formatDay(CONTENT_REVIEWED)}.</strong> Set releases, reported preorders, and expected windows have separate labels. Expected Target/Walmart windows follow the site-owner schedule and are not confirmed stock. Times use fixed PST (UTC−8), without daylight-saving adjustment. Set releases remain date-only; elapsed days use the displayed PST date. This page does not track live inventory.</p><Link href="/faq/guides/releases-and-restocks" className="font-semibold underline underline-offset-4">How to read release and restock information →</Link></div>
    <section aria-labelledby="calendar-title" className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4"><div><p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Plan ahead</p><h2 id="calendar-title" className="mt-1 text-xl font-bold">Release & drop calendar</h2></div><div aria-label="Calendar view" role="group" className="flex rounded-lg bg-slate-100 p-1">{(["month", "list"] as const).map((item) => <button key={item} aria-pressed={view === item} onClick={() => setView(item)} className={`rounded-md px-3 py-2 text-xs font-bold capitalize ${view === item ? "bg-white shadow-xs" : "text-slate-500"}`}>{item}</button>)}</div></div>
      <div className="mt-5 flex flex-wrap items-end gap-3 border-b border-slate-100 pb-5"><label className="space-y-1 text-[10px] text-slate-500"><span className="block">Retailer</span><select className={control} value={retailer} onChange={(event) => { setRetailer(event.target.value); setSelectedDay(null); }}><option value="all">All retailers & set releases</option>{retailers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="space-y-1 text-[10px] text-slate-500"><span className="block">Event type</span><select className={control} value={kind} onChange={(event) => { setKind(event.target.value); setSelectedDay(null); }}><option value="all">All events</option><option value="release">Product / set releases</option><option value="drop">Online drops</option></select></label><label className="space-y-1 text-[10px] text-slate-500"><span className="block">Calendar language</span><select className={control} value={calendarLanguage} onChange={(event) => { setCalendarLanguage(event.target.value); setSelectedDay(null); }}><option value="all">English & Japanese</option><option value="pokemon">English</option><option value="pokemon-japan">Japanese</option></select></label><label className="flex items-center gap-2 py-2 text-xs text-slate-600"><input type="checkbox" checked={showExpected} onChange={(event) => setShowExpected(event.target.checked)} />Show expected windows & reminders</label><a href="#sets" className="ml-auto py-2 text-xs font-bold underline underline-offset-4">Set release directory ↓</a></div>
      <div className="my-5 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><button aria-label="Previous month" disabled={month === "1900-01"} onClick={() => changeMonth(shiftMonth(month, -1))} className={`${control} disabled:opacity-40`}>←</button><h3 className="min-w-0 text-sm font-bold sm:min-w-44 sm:text-center" aria-live="polite">{monthTitle}</h3><button aria-label="Next month" disabled={month === "2100-12"} onClick={() => changeMonth(shiftMonth(month, 1))} className={`${control} disabled:opacity-40`}>→</button></div><div className="flex flex-wrap items-center gap-2"><label className="sr-only" htmlFor="calendar-month">Jump to month</label><input id="calendar-month" type="month" min="1900-01" max="2100-12" value={month} onChange={(event) => changeMonth(event.target.value)} className={`${control} min-w-0 max-w-48`} /><button onClick={() => changeMonth(today.slice(0, 7))} className={control}>Today</button></div></div>
      {!ready ? <p className="py-10 text-center text-sm text-slate-500">Loading calendar…</p> : <>
        {view === "month" && <div className="overflow-hidden rounded-xl border border-slate-200"><div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <div key={day} className="py-2 text-center text-[10px] font-bold text-slate-500">{day}</div>)}</div><div className="grid grid-cols-7">{monthDays(month).map((day, index) => {
          const dayEvents = dated.filter((event) => event.date === day);
          return day ? <button key={day} aria-label={`${formatDay(day)}, ${dayEvents.length} event${dayEvents.length === 1 ? "" : "s"}`} aria-pressed={selectedDay === day} aria-current={day === today ? "date" : undefined} onClick={() => setSelectedDay((previous) => previous === day ? null : day)} className={`min-h-20 min-w-0 border-b border-r border-slate-100 p-1.5 text-left align-top transition hover:bg-slate-100 sm:min-h-28 sm:p-3 ${selectedDay === day ? "bg-slate-100 ring-2 ring-inset ring-slate-500" : "bg-white"}`}><span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs ${day === today ? "bg-slate-950 font-bold text-white" : "text-slate-600"}`}>{Number(day.slice(-2))}</span>{dayEvents.slice(0, 2).map((event) => <span key={event.id} className="mt-1 block truncate rounded bg-slate-100 px-1 py-1 text-[9px] font-medium text-slate-800"><span className="sm:hidden">{event.kind === "release" ? "Set" : event.confidence === "expected" ? "~Drop" : event.confidence === "reminder" ? "Watch" : "Drop"}</span><span className="hidden sm:inline">{event.confidence === "expected" ? "~ " : ""}{event.title}</span></span>)}{dayEvents.length > 2 && <span className="text-[10px]">+{dayEvents.length - 2} more</span>}</button> : <div key={`blank-${index}`} aria-hidden="true" className="min-h-20 border-b border-r border-slate-100 bg-slate-50/60 sm:min-h-28" />;
        })}</div></div>}
        <div className="mt-5" aria-live="polite"><div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-xs font-bold">{selectedDay ? formatDay(selectedDay) : "This month"} · {visible.length} dated event{visible.length === 1 ? "" : "s"}</h3>{selectedDay && <button onClick={() => setSelectedDay(null)} className="text-xs underline">Show entire month</button>}</div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{visible.map((event) => <EventCard key={event.id} event={event} today={today} />)}</div>{visible.length === 0 && <p className="rounded-xl border border-dashed border-slate-200 p-6 text-sm leading-6 text-slate-500">No dated events match this view. Unannounced drops appear below; this does not mean retailers have no stock.</p>}</div>
      </>}
    </section>
    <section aria-labelledby="unannounced-title" className="mt-7"><h2 id="unannounced-title" className="text-sm font-bold">Online drops awaiting an announcement</h2><p className="mt-2 text-xs leading-6 text-slate-500">Confirmed dates are still unknown for these next drops. Expected recurring windows, when enabled, are separate planning estimates. Reviewed {formatDay(CONTENT_REVIEWED)}; check each source for newer announcements.</p><div className="mt-3 grid gap-3 lg:grid-cols-3">{undated.map((event) => <EventCard key={event.id} event={event} today={today} />)}</div>{!undated.length && <p className="mt-3 text-xs text-slate-500">No undated online drops match your filters.</p>}</section>
    <PreorderHistory />
    <SetDirectory today={today} data={catalog} />
  </>;
}

function EventCard({ event, today }: { event: CalendarEvent; today: string }) {
  const label = event.confidence === "expected" ? "Expected window · unconfirmed" : event.confidence === "reminder" ? "Planning reminder · not a drop" : event.confidence === "reported" ? "Reported preorder opening" : event.kind === "release" ? (event.language ? "Set release" : "Announced release") : event.date ? "Announced online drop" : "Drop date unannounced";
  const color = event.confidence === "expected" || event.confidence === "reminder" ? "text-amber-700" : event.kind === "release" ? "text-emerald-700" : "text-slate-600";
  const dateDetail = event.startsAt ? formatEventTime(event.startsAt) : event.confidence === "reminder" ? "Date-only reminder" : event.language && event.kind === "release" ? "Date only · no checkout time" : event.confidence === "reported" ? "Exact time not verified" : "Time not announced";
  return <article className="rounded-xl border border-slate-200 bg-white p-4">
    <div className="flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-wide"><span className={color}>{label}</span>{event.date && <span className="text-slate-400">{event.date < today ? "Past date" : event.date === today ? "Today" : "Upcoming"}</span>}</div>
    <h3 className="mt-2 text-sm font-bold leading-6">{event.title}</h3>
    <p className="mt-1 text-xs text-slate-500">{event.date ? `${formatDay(event.date)} · ${dateDetail}` : "Date & time not verified"}</p>
    <p className="mt-3 text-xs leading-6 text-slate-600">{event.note}</p>
    <a href={event.source.url} target={event.source.url.startsWith("https:") ? "_blank" : undefined} rel="noreferrer" className="mt-3 inline-block text-[11px] underline underline-offset-4">{event.source.label} ↗</a>
    <p className="mt-2 text-[10px] text-slate-400">Reviewed {formatDay(event.reviewed)}</p>
  </article>;
}

function PreorderHistory() {
  return <details id="drop-patterns" className="mt-7 scroll-mt-36 rounded-2xl border border-slate-200 bg-white p-5">
    <summary className="cursor-pointer text-sm font-bold">Drop patterns & Pokémon Center preorder history</summary>
    <p className="mt-4 text-xs leading-6 text-slate-600">Target: Tuesday and Thursday at 12:00 AM PST (start of day). Walmart: Wednesday at 6:00 PM PST. These are site-owner supplied watch windows, not retailer promises. PST is fixed UTC−8; local Pacific daylight time is one hour ahead during summer.</p>
    <p className="mt-3 text-xs leading-6 text-slate-600">Recent reported Pokémon Center openings were 37 days before release; older examples below were 67–77 days early. One calendar month is a planning reminder, not a forecast. A known reported preorder replaces that reminder for its set. No checkout times are inferred from news publication timestamps.</p>
    <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><caption className="sr-only">Previous Pokémon Center preorder opening dates</caption><thead className="border-b border-slate-200 text-[10px] uppercase text-slate-500"><tr>{["English set", "Preorders opened", "Set release", "Lead time", "Source"].map((heading) => <th scope="col" className="py-3 pr-4" key={heading}>{heading}</th>)}</tr></thead><tbody>{pokemonCenterHistory.map((record) => <tr key={record.set} className="border-b border-slate-100"><th scope="row" className="py-4 pr-4 font-semibold">{record.set}</th><td className="py-4 pr-4">{formatDay(record.preorder)}</td><td className="py-4 pr-4">{formatDay(record.release)}</td><td className="py-4 pr-4">{preorderLeadDays(record.preorder, record.release)} days</td><td className="py-4"><a href={record.source.url} target="_blank" rel="noreferrer" className="underline underline-offset-4">{record.source.label} ↗</a></td></tr>)}</tbody></table></div>
    <p className="mt-3 text-[10px] text-slate-500">Selected reported dates, not an exhaustive history. Reviewed {formatDay(CONTENT_REVIEWED)}.</p>
  </details>;
}

function useReleaseSets() {
  const [sets, setSets] = useState<ReleaseSet[]>(() => mergeSets([]));
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setErrors([]);
    const languages = ["pokemon", "pokemon-japan"] as const;
    Promise.allSettled(languages.map((game) => getCardSets(game))).then((results) => {
      if (cancelled) return;
      const failures: string[] = [];
      const loaded: { language: ReleaseSet["language"]; sets: Awaited<ReturnType<typeof getCardSets>> }[] = [];
      results.forEach((result, index) => {
        if (result.status === "fulfilled") loaded.push({ language: languages[index], sets: result.value });
        else { console.error(`[ReleaseCalendar] Failed to load ${languages[index]} sets:`, result.reason); failures.push(languages[index] === "pokemon" ? "English" : "Japanese"); }
      });
      setSets(mergeSets(loaded)); setErrors(failures); setLoading(false);
    });
    return () => { cancelled = true; };
  }, [retry]);
  return { sets, loading, errors, retry: () => setRetry((value) => value + 1) };
}

function SetDirectory({ today, data }: { today: string; data: ReturnType<typeof useReleaseSets> }) {
  const { sets, loading, errors, retry } = data;
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("all");
  const [status, setStatus] = useState("all");
  const [series, setSeries] = useState("all");
  const [sort, setSort] = useState("newest");
  const [limit, setLimit] = useState(30);
  useEffect(() => setLimit(30), [query, language, status, sort, series]);
  const filtered = useMemo(() => sets.filter((set) => (language === "all" || set.language === language) && (series === "all" || set.series === series) && `${set.name} ${set.series ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()) && (status === "all" || (printStatus(set, today).evidence?.status ?? "unknown") === status)).sort((a, b) => {
    if (!a.date) return b.date ? 1 : a.name.localeCompare(b.name);
    if (!b.date) return -1;
    return (sort === "newest" ? b.date.localeCompare(a.date) : a.date.localeCompare(b.date)) || a.name.localeCompare(b.name);
  }), [sets, query, language, status, sort, series, today]);
  return <section id="sets" aria-labelledby="sets-title" className="mt-12 scroll-mt-36">
    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">The expansion timeline</p><h2 id="sets-title" className="mt-1 text-xl font-bold">Set releases & print status</h2><p className="mt-2 max-w-4xl text-xs leading-6 text-slate-500">English release dates and series from TCGplayer, including promotional and miscellaneous sets. Japanese dates and additional products come from the catalog. Release dates and elapsed days update independently of print status.</p>
    <p className="mt-2 text-xs leading-6 text-slate-500"><a href={releaseDateSource.url} target="_blank" rel="noreferrer" className="underline underline-offset-4">TCGplayer release-date reference ↗</a> · Article updated {formatDay(RELEASE_SOURCE_UPDATED)} · Reviewed {formatDay(CONTENT_REVIEWED)}. Promotional release dates mark their initial release, not every later card or product.</p>
    <details className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-xs leading-6 text-slate-600"><summary className="cursor-pointer font-semibold text-slate-800">Why do print statuses say Unknown?</summary><p className="mt-2">No complete official set-by-set printing list was found. In print / Out of print labels require dated, set-specific evidence and expire when a review is due. Age, tournament rotation, and a retailer selling out do not establish production status.</p><a href={sources.availability.url} target="_blank" rel="noreferrer" className="underline underline-offset-4">Read Pokémon's product availability statement ↗</a></details>
    <div className="my-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4"><label className="min-w-0 flex-1 space-y-1 text-[10px] text-slate-500"><span className="block">Search sets</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Set name…" className={`${control} w-full min-w-40`} /></label><label className="space-y-1 text-[10px] text-slate-500"><span className="block">Set language</span><select value={language} onChange={(event) => setLanguage(event.target.value)} className={control}><option value="all">English & Japanese</option><option value="pokemon">English</option><option value="pokemon-japan">Japanese</option></select></label><label className="space-y-1 text-[10px] text-slate-500"><span className="block">Series / collection</span><select value={series} onChange={(event) => setSeries(event.target.value)} className={`${control} max-w-60`}><option value="all">All series</option>{[...new Set(sets.map((set) => set.series).filter((value): value is string => Boolean(value)))].sort().map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label className="space-y-1 text-[10px] text-slate-500"><span className="block">Print status</span><select value={status} onChange={(event) => setStatus(event.target.value)} className={control}><option value="all">All statuses</option><option value="in-print">In print · sourced</option><option value="out-of-print">Out of print · sourced</option><option value="unknown">Unknown</option></select></label><label className="space-y-1 text-[10px] text-slate-500"><span className="block">Release order</span><select value={sort} onChange={(event) => setSort(event.target.value)} className={control}><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></label></div>
    {errors.length > 0 && <p role="alert" className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-900">Could not load {errors.join(" and ")} catalog sets. Showing reviewed announcements and any available catalog results. <button onClick={retry} className="font-bold underline">Retry sets</button></p>}
    <p aria-live="polite" className="mb-3 text-xs text-slate-500">{loading ? "Loading catalog sets…" : `${filtered.length} sets match · showing ${Math.min(limit, filtered.length)}`}</p>
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[680px] text-left text-xs"><caption className="sr-only">Set release dates, time since release, and sourced print status</caption><thead className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500"><tr>{["Set / language", "Release date", "Time since release", "Print status", "Date source"].map((heading) => <th scope="col" key={heading} className="px-4 py-3">{heading}</th>)}</tr></thead><tbody>{filtered.slice(0, limit).map((set) => {
      const printing = printStatus(set, today);
      const params = new URLSearchParams({ game: set.language, ...(set.catalogId ? { set: set.catalogId } : { q: set.name }) });
      return <tr key={set.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60"><th scope="row" className="max-w-80 px-4 py-4 font-semibold"><Link href={`/catalog?${params}`} className="hover:underline">{set.name} ↗</Link><span className="mt-1 block text-[10px] font-normal text-slate-500">{set.language === "pokemon" ? "English" : "Japanese"}{set.series ? ` · ${set.series}` : ""}</span></th><td className="whitespace-nowrap px-4 py-4">{formatDay(set.date)}</td><td className="whitespace-nowrap px-4 py-4 text-slate-500">{relativeRelease(set.date, today)}</td><td className="px-4 py-4"><span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] text-slate-600">{printing.label}</span>{printing.evidence && <><a href={printing.evidence.source.url} className="mt-2 block text-[10px] underline" target="_blank" rel="noreferrer">Evidence · {formatDay(printing.evidence.reviewed)} ↗</a><p className="mt-1 max-w-60 text-[10px] text-slate-500">{printing.evidence.note}</p></>}</td><td className="px-4 py-4 text-[10px] leading-5 text-slate-500">{set.source ? <><a href={set.source.url} target="_blank" rel="noreferrer" className="underline">{set.source.label} ↗</a><span className="block">Reviewed {formatDay(CONTENT_REVIEWED)}</span></> : "PPT catalog"}</td></tr>;
    })}</tbody></table></div>
    {!loading && !filtered.length && <p className="mt-4 rounded-xl border border-dashed border-slate-300 p-6 text-sm text-slate-500">No sets match these filters. Unknown does not mean out of print.</p>}
    {limit < filtered.length && <button onClick={() => setLimit((value) => value + 30)} className={`${control} mt-4`}>Show 30 more sets</button>}
  </section>;
}

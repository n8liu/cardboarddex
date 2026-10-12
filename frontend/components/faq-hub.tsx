"use client";

import { useState } from "react";
import Link from "next/link";
import { CONTENT_REVIEWED, faqs, guides } from "@/lib/learning-content";
import { formatDay } from "@/lib/release-calendar";

export function FaqHub() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All questions");
  const normalized = query.trim().toLowerCase();
  const questions = faqs.filter((faq) => (category === "All questions" || faq.category === category) && `${faq.question} ${faq.answer}`.toLowerCase().includes(normalized));
  const articles = guides.filter((guide) => `${guide.title} ${guide.description} ${guide.category} ${guide.sections.map((s) => s.paragraphs.join(" ")).join(" ")}`.toLowerCase().includes(normalized));
  return <>
    <div className="mb-8 grid gap-3 sm:grid-cols-3">
      {[{ href: "#questions", title: "Find an answer", detail: "Collecting, prices, and your binder", number: "01" }, { href: "#guides", title: "Learn something new", detail: "Practical guides and TCG history", number: "02" }, { href: "/faq#calendar", title: "Plan your next release", detail: "Dates, retailers, and print status", number: "03" }].map((item) => <Link key={item.href} href={item.href} className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-slate-400"><span className="text-[10px] font-bold text-slate-400">{item.number} / EXPLORE</span><h2 className="mt-3 text-sm font-bold">{item.title} <span aria-hidden="true" className="inline-block transition group-hover:translate-x-1">→</span></h2><p className="mt-1 text-xs leading-5 text-slate-500">{item.detail}</p></Link>)}
    </div>
    <section id="questions" aria-labelledby="questions-title" className="scroll-mt-36">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Quick answers</p><h2 id="questions-title" className="mt-1 text-xl font-bold">Frequently asked questions</h2></div><p className="text-[10px] text-slate-500">Reviewed {formatDay(CONTENT_REVIEWED)}</p></div>
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4">
        <label htmlFor="faq-search" className="sr-only">Search questions and guides</label><input id="faq-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search questions and guides…" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400" />
        <div role="group" aria-label="Question category" className="mt-3 flex flex-wrap gap-2">{["All questions", ...new Set(faqs.map((faq) => faq.category))].map((item) => <button key={item} onClick={() => setCategory(item)} aria-pressed={category === item} className={`rounded-lg px-3 py-2 text-xs font-medium ${category === item ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{item}</button>)}</div>
      </div>
      <p aria-live="polite" className="mb-3 text-xs text-slate-500">{questions.length} questions · {articles.length} guides match your search</p>
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        {questions.map((faq) => <details key={faq.id} id={faq.id} className="group scroll-mt-36 border-b border-slate-100 last:border-0">
          <summary className="cursor-pointer px-5 py-5 text-sm font-semibold marker:text-slate-400 hover:bg-slate-50">{faq.question}</summary>
          <div className="max-w-4xl space-y-3 px-5 pb-5 text-sm leading-7 text-slate-600"><p>{faq.answer}</p>{faq.link && <Link className="inline-block font-semibold text-slate-950 underline underline-offset-4" href={faq.link.href}>{faq.link.label} →</Link>}{faq.sources?.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="block text-xs underline underline-offset-4">{source.label} ↗</a>)}</div>
        </details>)}
        {questions.length === 0 && <div className="p-8 text-center"><p className="text-sm text-slate-600">No questions match these filters.</p><button onClick={() => { setQuery(""); setCategory("All questions"); }} className="mt-3 text-xs font-bold underline">Reset search and category</button></div>}
      </div>
    </section>
    <section id="guides" aria-labelledby="guides-title" className="mt-12 scroll-mt-36">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">The reading room</p><h2 id="guides-title" className="mt-1 text-xl font-bold">Guides & Pokémon TCG history</h2><p className="mt-2 text-sm text-slate-500">A little context for your next card, collection, or purchase.</p>
      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{articles.map((guide, index) => <Link href={`/faq/guides/${guide.slug}`} key={guide.slug} className="group flex flex-col rounded-2xl border border-slate-200 bg-white p-6 transition hover:-translate-y-0.5 hover:border-slate-400 hover:shadow-sm"><div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-slate-500"><span>{guide.category}</span><span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span></div><h3 className="mt-6 text-lg font-bold leading-7">{guide.title}</h3><p className="mt-3 flex-1 text-xs leading-6 text-slate-500">{guide.description}</p><span className="mt-6 border-t border-slate-100 pt-4 text-xs font-bold">Read guide <span aria-hidden="true">→</span></span></Link>)}</div>
      {!articles.length && <p className="mt-5 text-sm text-slate-500">No guides match your search. Try a broader phrase.</p>}
    </section>
  </>;
}

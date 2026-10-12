import Link from "next/link";
import type { ReactNode } from "react";

export function LearningShell({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: ReactNode }) {
  return <main className="min-h-[calc(100vh-65px)] bg-[#f7f8f6] text-slate-950">
    <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-8 sm:py-10">
      <div className="mb-7 flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div className="max-w-3xl"><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">{eyebrow}</p><h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1><p className="mt-3 text-sm leading-6 text-slate-600">{description}</p></div>
        <nav aria-label="Learning pages" className="flex rounded-xl border border-slate-200 bg-white p-1 text-xs font-bold">
          {[{ id: "calendar", href: "/faq#calendar", text: "Calendar" }, { id: "faq", href: "/faq#questions", text: "FAQ" }, { id: "guides", href: "/faq#guides", text: "Guides" }].map((item) => <Link key={item.id} href={item.href} className="rounded-lg px-3 py-2 text-slate-600 hover:bg-slate-100">{item.text}</Link>)}
        </nav>
      </div>
      {children}
    </div>
  </main>;
}

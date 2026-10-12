import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { LearningShell } from "@/components/learning-shell";
import { CONTENT_REVIEWED, guides } from "@/lib/learning-content";
import { formatDay } from "@/lib/release-calendar";

export function generateStaticParams() { return guides.map(({ slug }) => ({ slug })); }
export const dynamicParams = false;
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const guide = guides.find((item) => item.slug === slug);
  return guide ? { title: `${guide.title} | CardboardDex`, description: guide.description } : { title: "Guide not found | CardboardDex" };
}
export default async function GuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const guide = guides.find((item) => item.slug === slug);
  if (!guide) notFound();
  const wordCount = guide.sections.reduce((count, section) => count + section.paragraphs.join(" ").split(/\s+/).length, 0);
  return <LearningShell eyebrow={`Reading room / ${guide.category}`} title={guide.title} description={guide.description}>
    <Link href="/faq#guides" className="text-xs font-bold text-slate-600 hover:underline">← All guides</Link>
    <div className="mt-5 grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside><nav aria-label="On this page" className="rounded-2xl border border-slate-200 bg-white p-5 lg:sticky lg:top-28"><p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">On this page</p><ul className="mt-4 space-y-4">{guide.sections.map((section) => <li key={section.id}><a href={`#${section.id}`} className="text-xs leading-5 text-slate-600 hover:text-slate-950 hover:underline">{section.title}</a></li>)}</ul></nav></aside>
      <article className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-9">
        <p className="border-b border-slate-100 pb-5 text-[11px] leading-6 text-slate-500">CardboardDex editorial · {Math.max(1, Math.ceil(wordCount / 200))} min read · Reviewed {formatDay(CONTENT_REVIEWED)}</p>
        <div className="max-w-3xl">{guide.sections.map((section) => <section id={section.id} key={section.id} className="mt-8 scroll-mt-36"><h2 className="text-xl font-bold tracking-tight">{section.title}</h2>{section.paragraphs.map((paragraph, index) => <p key={index} className="mt-4 text-sm leading-8 text-slate-600">{paragraph}</p>)}</section>)}</div>
        <div className="mt-9 border-t border-slate-200 pt-6"><h2 className="text-xs font-bold uppercase tracking-wider">Sources & editorial notes</h2>{guide.sources.length ? <ul className="mt-3 space-y-3">{guide.sources.map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer" className="text-xs text-slate-600 underline underline-offset-4">{source.label} ↗</a></li>)}</ul> : <p className="mt-3 text-xs leading-6 text-slate-500">Original CardboardDex guidance. Website descriptions reflect the current implementation; card-care suggestions are general collecting practices.</p>}<Link href={guide.related.href} className="mt-6 inline-block rounded-xl bg-slate-950 px-4 py-3 text-xs font-bold text-white hover:bg-slate-800">{guide.related.label} →</Link></div>
      </article>
    </div>
  </LearningShell>;
}

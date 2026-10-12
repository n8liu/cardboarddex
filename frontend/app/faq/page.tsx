import type { Metadata } from "next";
import { FaqHub } from "@/components/faq-hub";
import { LearningShell } from "@/components/learning-shell";
import { ReleaseCalendar } from "@/components/release-calendar";

export const metadata: Metadata = { title: "FAQ, Release Calendar & Pokémon TCG Guides | CardboardDex", description: "Answers about collecting Pokémon cards, CardboardDex prices and binders, release dates, and practical collecting guides." };
export default function FaqPage() {
  return <LearningShell eyebrow="CardboardDex / Learn" title="Releases, answers & collecting guides." description="Plan upcoming releases, explore set dates, and find answers to your Pokémon TCG questions."><div id="calendar" className="scroll-mt-36"><ReleaseCalendar /></div><div className="mt-12 border-t border-slate-200 pt-10"><FaqHub /></div></LearningShell>;
}

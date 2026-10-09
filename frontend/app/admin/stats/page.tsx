import type { Metadata } from "next";
import { StatsDashboard } from "@/components/admin/stats-dashboard";

export const metadata: Metadata = {
  title: "Admin traffic statistics | CardboardDex",
  robots: { index: false, follow: false },
};

export default function AdminStatsPage() {
  return <main className="min-h-screen bg-[#f7f8f6] px-5 py-10 text-slate-950 sm:px-8">
    <div className="mx-auto max-w-[1400px]">
      <p className="text-xs font-bold uppercase tracking-widest text-emerald-800">Admin</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight">Traffic statistics</h1>
      <p className="mt-2 text-sm text-slate-500">Visits, popular pages, and countries across CardboardDex.</p>
      <StatsDashboard />
    </div>
  </main>;
}

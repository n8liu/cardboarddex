"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { analyticsOptedOut, setAnalyticsOptOut, trackPageView } from "@/lib/analytics";

export function AnalyticsTracker() {
  const pathname = usePathname();
  useEffect(() => { void trackPageView(pathname); }, [pathname]);
  useEffect(() => {
    // A cached document resumes without remounting React or changing pathname.
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) void trackPageView(window.location.pathname, true);
    };
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, []);
  return null;
}

export function AnalyticsPreference() {
  const [optedOut, setOptedOut] = useState(false);
  useEffect(() => { setOptedOut(analyticsOptedOut()); }, []);
  if (process.env.NEXT_PUBLIC_ANALYTICS_ENABLED !== "true") return null;
  return <div className="mt-3 max-w-2xl space-y-1">
    <p>Traffic statistics use a browser identifier, page paths, and approximate country. No binder contents or search text are collected. Detailed visits are retained for 90 days; visitor identifiers and daily totals are retained for lifetime counts.</p>
    <button type="button" className="underline underline-offset-2" onClick={() => {
      setAnalyticsOptOut(!optedOut);
      setOptedOut(analyticsOptedOut());
    }}>{optedOut ? "Traffic tracking is off · Enable" : "Turn off traffic tracking"}</button>
  </div>;
}

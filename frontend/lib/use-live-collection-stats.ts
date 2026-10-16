"use client";

import { useEffect, useState } from "react";
import { getHomeStats } from "@/lib/api";
import type { HomeStats } from "@/types/home";

export function useLiveCollectionStats() {
  const [data, setData] = useState<HomeStats | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    async function refresh() {
      if (document.hidden || controller) return;
      const request = new AbortController();
      controller = request;
      try {
        const result = await getHomeStats(request.signal);
        if (!disposed && !request.signal.aborted) { setData(result); setError(false); }
      } catch (err) {
        if (!disposed && !request.signal.aborted) { console.error("Collection totals failed:", err); setError(true); }
      } finally {
        if (controller === request) controller = null;
      }
    }
    function visibility() {
      if (document.hidden) { controller?.abort(); controller = null; }
      else void refresh();
    }
    void refresh();
    const timer = window.setInterval(refresh, 60_000);
    document.addEventListener("visibilitychange", visibility);
    return () => { disposed = true; controller?.abort(); clearInterval(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [attempt]);
  return { data, error, retry: () => setAttempt((n) => n + 1) };
}

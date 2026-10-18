"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getLiveStats } from "@/lib/api";
import type { LiveStatsResponse } from "@/types/card";

/** Independent polling: no feed or filter request waits for global totals. */
export function useLiveStats() {
  const [snapshot, setSnapshot] = useState<LiveStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(Date.now);
  const active = useRef<AbortController | null>(null);
  const lastAttempt = useRef<number | null>(null);
  const mounted = useRef(false);

  const refresh = useCallback(async () => {
    if (document.hidden || active.current) return;
    const controller = new AbortController();
    active.current = controller;
    lastAttempt.current = Date.now();
    setLoading(true);
    try {
      const result = await getLiveStats({ abortSignal: controller.signal });
      if (!mounted.current || controller.signal.aborted) return;
      setSnapshot(result);
      setError(false);
      setNow(Date.now());
    } catch (err) {
      if (!mounted.current || controller.signal.aborted) return;
      console.error("Failed fetching Live Comps totals:", err);
      setError(true);
    } finally {
      if (active.current === controller) {
        active.current = null;
        if (mounted.current) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const tick = () => {
      setNow(Date.now());
      if (lastAttempt.current === null || Date.now() - lastAttempt.current >= 60_000) void refresh();
    };
    const visibility = () => {
      if (document.hidden) {
        active.current?.abort();
        active.current = null;
        lastAttempt.current = null;
      } else tick();
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      mounted.current = false;
      active.current?.abort();
      active.current = null;
      lastAttempt.current = null;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [refresh]);

  const age = snapshot ? now - Date.parse(snapshot.generated_at) : Infinity;
  const stats = age >= 0 && age < 30 * 60_000 ? snapshot : null;
  return { stats, loading, error, stale: !!stats && (stats.is_stale || age >= 60_000), retry: () => void refresh() };
}

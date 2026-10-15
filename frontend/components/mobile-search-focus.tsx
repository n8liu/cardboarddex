"use client";

import { useEffect } from "react";

/** Align page searches without interfering with modal searches or typing. */
export function MobileSearchFocus() {
  useEffect(() => {
    let stop: (() => void) | undefined;
    function onFocus(event: FocusEvent) {
      stop?.();
      const input = event.target;
      if (!(input instanceof HTMLInputElement) || !input.hasAttribute("data-mobile-search") ||
          input.closest('[role="dialog"], dialog') || window.innerWidth >= 768) return;

      const viewport = window.visualViewport;
      const container = input.closest<HTMLElement>("[data-mobile-search-container]");
      let frame = 0;
      let settleTimer = 0;
      let active = true;
      const align = () => {
        if (!active || document.activeElement !== input || !input.isConnected || window.innerWidth >= 768) return;
        const header = document.querySelector<HTMLElement>("[data-site-header]");
        const viewportTop = viewport?.offsetTop ?? 0;
        const top = Math.max(header?.getBoundingClientRect().bottom ?? 0, viewportTop) + 8;
        const rect = input.getBoundingClientRect();
        // Instant positioning avoids competing with the keyboard's own animation.
        window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - top), behavior: "instant" });
        container?.style.setProperty("--search-results-max-height", `${Math.max(0, (viewport?.height ?? window.innerHeight) + viewportTop - top - rect.height - 16)}px`);
      };
      const schedule = () => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(align);
      };
      const onResize = () => {
        window.clearTimeout(settleTimer);
        settleTimer = window.setTimeout(schedule, 80);
      };
      schedule();
      viewport?.addEventListener("resize", onResize);
      // Stop repositioning after keyboard opening, so scrolling results stays free.
      const openingTimer = window.setTimeout(() => {
        viewport?.removeEventListener("resize", onResize);
        window.clearTimeout(settleTimer);
        schedule();
      }, 700);
      stop = () => {
        active = false;
        cancelAnimationFrame(frame);
        window.clearTimeout(settleTimer);
        window.clearTimeout(openingTimer);
        viewport?.removeEventListener("resize", onResize);
        container?.style.removeProperty("--search-results-max-height");
      };
    }
    function onBlur() { stop?.(); stop = undefined; }
    document.addEventListener("focusin", onFocus);
    document.addEventListener("focusout", onBlur);
    return () => {
      stop?.();
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("focusout", onBlur);
    };
  }, []);
  return null;
}

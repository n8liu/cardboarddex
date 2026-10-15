"use client";

import { useEffect, useRef, useState } from "react";

interface AnimatedNumberProps {
  value: number;
  duration?: number;
  format?: (val: number) => string;
  className?: string;
}

const formatCount = (value: number) => Math.round(value).toLocaleString("en-US");

export function AnimatedNumber({
  value,
  duration = 900,
  format = formatCount,
  className = "",
}: AnimatedNumberProps) {
  const target = Number.isFinite(value) ? value : 0;
  const elementRef = useRef<HTMLSpanElement>(null);
  // Keep server HTML and the first client render identical and useful without JS.
  const [currentValue, setCurrentValue] = useState(target);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let frame: number | null = null;
    let observer: IntersectionObserver | null = null;
    let started = false;
    let disposed = false;

    const finish = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      observer?.disconnect();
      setCurrentValue(target);
    };
    const onMotionChange = () => {
      if (motion?.matches) {
        started = true;
        finish();
      }
    };
    const start = () => {
      if (started || disposed) return;
      started = true;
      observer?.disconnect();
      let startTime: number | null = null;
      const animate = (timestamp: number) => {
        if (disposed) return;
        startTime ??= timestamp;
        const progress = Math.min((timestamp - startTime) / duration, 1);
        setCurrentValue(target * (1 - Math.pow(1 - progress, 3)));
        if (progress < 1) frame = requestAnimationFrame(animate);
      };
      frame = requestAnimationFrame(animate);
    };

    if (motion?.matches || duration <= 0 || !Number.isFinite(duration) || target === 0 || !window.IntersectionObserver) {
      finish();
    } else {
      setCurrentValue(0);
      observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) start();
      }, { threshold: 0.1 });
      observer.observe(element);
    }
    motion?.addEventListener("change", onMotionChange);
    return () => {
      disposed = true;
      if (frame !== null) cancelAnimationFrame(frame);
      observer?.disconnect();
      motion?.removeEventListener("change", onMotionChange);
    };
  }, [target, duration]);

  return (
    <span ref={elementRef} className={`inline-grid tabular-nums ${className}`}>
      {/* Reserve final width and expose only the real value to assistive tech. */}
      <span className="invisible col-start-1 row-start-1" aria-hidden="true">{format(target)}</span>
      <span className="col-start-1 row-start-1" aria-hidden="true">{format(currentValue)}</span>
      <span className="sr-only">{format(target)}</span>
    </span>
  );
}

"use client";

import React, { useEffect, useRef, useState } from "react";

interface AnimatedNumberProps {
  value: number;
  duration?: number;
  format?: (val: number) => string;
  className?: string;
}

export function AnimatedNumber({
  value,
  duration = 420,
  format,
  className = "",
}: AnimatedNumberProps) {
  const [currentValue, setCurrentValue] = useState<number>(() => (isNaN(value) ? 0 : value));
  const prevValueRef = useRef<number>(isNaN(value) ? 0 : value);
  const rafIdRef = useRef<number | null>(null);

  useEffect(() => {
    const target = isNaN(value) ? 0 : value;
    const startVal = prevValueRef.current;
    prevValueRef.current = target;

    if (startVal === target) {
      setCurrentValue(target);
      return;
    }

    // Check for prefers-reduced-motion
    if (
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setCurrentValue(target);
      return;
    }

    let startTime: number | null = null;

    const animate = (timestamp: number) => {
      if (startTime === null) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Ease out cubic: 1 - (1 - t)^3
      const ease = 1 - Math.pow(1 - progress, 3);
      const nextVal = startVal + (target - startVal) * ease;
      setCurrentValue(nextVal);

      if (progress < 1) {
        rafIdRef.current = requestAnimationFrame(animate);
      } else {
        setCurrentValue(target);
      }
    };

    rafIdRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
    };
  }, [value, duration]);

  const output = format ? format(currentValue) : Math.round(currentValue).toLocaleString();

  return <span className={`inline-block tabular-nums ${className}`}>{output}</span>;
}

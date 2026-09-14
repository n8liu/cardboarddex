"use client";

import React, { useRef, useState } from "react";

export type FoilType = "cosmic" | "gold" | "ultra" | "holo" | "satin";

interface HoloCardProps {
  children: React.ReactNode;
  className?: string;
  maxTilt?: number;
  enableGlare?: boolean;
  rarity?: string | null;
  foilType?: FoilType;
}

export function resolveFoilType(rarity?: string | null): FoilType {
  if (!rarity) return "holo";
  const r = rarity.toLowerCase().trim();

  // Gold / Secret / Hyper Rare
  if (
    r.includes("secret") ||
    r.includes("hyper") ||
    r.includes("gold") ||
    r.includes("crown rare") ||
    r === "hr" ||
    r === "ur"
  ) {
    return "gold";
  }

  // Cosmic / Starfield / Art Rare / Special Illustration Rare
  if (
    r.includes("special illustration") ||
    r.includes("illustration") ||
    r.includes("art rare") ||
    r.includes("radiant") ||
    r.includes("shiny") ||
    r.includes("sar") ||
    r.includes("ar") ||
    r.includes("trainer gallery") ||
    r.includes("character rare")
  ) {
    return "cosmic";
  }

  // Ultra Rare / Full Art / VMAX / VSTAR / ex
  if (
    r.includes("ultra") ||
    r.includes("double rare") ||
    r.includes("vmax") ||
    r.includes("vstar") ||
    r.includes("ace spec") ||
    r.includes("full art") ||
    r.includes("promo")
  ) {
    return "ultra";
  }

  // Classic Holo / Reverse Holo
  if (r.includes("holo") || r.includes("foil") || r.includes("reverse")) {
    return "holo";
  }

  // Common / Uncommon / Standard (Subtle satin light, no rainbow)
  if (r.includes("common") || r.includes("uncommon") || r.includes("standard") || r === "none") {
    return "satin";
  }

  return "holo";
}

function getFoilBackground(foil: FoilType, glareX: number, glareY: number): string {
  switch (foil) {
    case "gold":
      return `
        radial-gradient(circle at ${glareX}% ${glareY}%, rgba(255, 255, 220, 0.85) 0%, rgba(255, 215, 0, 0.35) 45%, rgba(180, 120, 10, 0) 70%),
        linear-gradient(
          ${glareX * 3.6}deg,
          rgba(255, 223, 0, 0.45) 0%,
          rgba(255, 170, 0, 0.4) 35%,
          rgba(255, 250, 180, 0.6) 65%,
          rgba(212, 175, 55, 0.45) 100%
        )
      `;
    case "cosmic":
      return `
        radial-gradient(circle at ${glareX}% ${glareY}%, rgba(255, 255, 255, 0.85) 0%, rgba(160, 210, 255, 0.4) 40%, rgba(255, 255, 255, 0) 70%),
        radial-gradient(circle at ${100 - glareX}% ${100 - glareY}%, rgba(255, 182, 193, 0.4) 0%, rgba(255, 255, 255, 0) 50%),
        linear-gradient(
          ${glareX * 2.8}deg,
          rgba(255, 105, 180, 0.3) 0%,
          rgba(0, 220, 255, 0.3) 25%,
          rgba(255, 240, 100, 0.3) 50%,
          rgba(147, 112, 219, 0.35) 75%,
          rgba(255, 105, 180, 0.3) 100%
        )
      `;
    case "ultra":
      return `
        radial-gradient(circle at ${glareX}% ${glareY}%, rgba(255, 255, 255, 0.8) 0%, rgba(255, 255, 255, 0) 55%),
        linear-gradient(
          ${glareX * 4}deg,
          rgba(0, 240, 255, 0.45) 0%,
          rgba(255, 0, 128, 0.45) 45%,
          rgba(112, 0, 255, 0.45) 80%,
          rgba(0, 240, 255, 0.45) 100%
        )
      `;
    case "satin":
      return `
        radial-gradient(circle at ${glareX}% ${glareY}%, rgba(255, 255, 255, 0.45) 0%, rgba(255, 255, 255, 0) 65%)
      `;
    case "holo":
    default:
      return `
        radial-gradient(circle at ${glareX}% ${glareY}%, rgba(255, 255, 255, 0.75) 0%, rgba(255, 255, 255, 0) 60%),
        linear-gradient(
          ${glareX * 3.6}deg,
          rgba(255, 0, 128, 0.35) 0%,
          rgba(0, 255, 255, 0.35) 30%,
          rgba(255, 255, 0, 0.35) 60%,
          rgba(128, 0, 255, 0.35) 100%
        )
      `;
  }
}

export function HoloCard({
  children,
  className = "",
  maxTilt = 12,
  enableGlare = true,
  rarity,
  foilType,
}: HoloCardProps) {
  const cardRef = useRef<HTMLDivElement | null>(null);
  const activeFoil = foilType || resolveFoilType(rarity);

  const [style, setStyle] = useState<{
    transform: string;
    glareX: number;
    glareY: number;
    glareOpacity: number;
    isHovered: boolean;
  }>({
    transform: "perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)",
    glareX: 50,
    glareY: 50,
    glareOpacity: 0,
    isHovered: false,
  });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const card = cardRef.current;
    if (!card) return;

    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const px = x / rect.width - 0.5; // -0.5 to 0.5
    const py = y / rect.height - 0.5; // -0.5 to 0.5

    const rotateX = -py * maxTilt * 2;
    const rotateY = px * maxTilt * 2;
    const glareX = (x / rect.width) * 100;
    const glareY = (y / rect.height) * 100;
    const distFromCenter = Math.hypot(px, py);
    const maxOpacity = activeFoil === "satin" ? 0.35 : activeFoil === "gold" ? 0.55 : 0.45;
    const glareOpacity = Math.min(distFromCenter * 1.4, maxOpacity);

    setStyle({
      transform: `perspective(800px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) scale3d(1.025, 1.025, 1.025)`,
      glareX,
      glareY,
      glareOpacity,
      isHovered: true,
    });
  };

  const handleMouseLeave = () => {
    setStyle((prev) => ({
      ...prev,
      transform: "perspective(800px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)",
      glareOpacity: 0,
      isHovered: false,
    }));
  };

  const blendMode = activeFoil === "satin" ? "screen" : "color-dodge";

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        transform: style.transform,
        transition: style.isHovered ? "transform 80ms ease-out" : "transform 400ms cubic-bezier(0.16, 1, 0.3, 1)",
        transformStyle: "preserve-3d",
      }}
      className={`relative will-change-transform ${className}`}
    >
      {children}

      {/* Holographic Prismatic Sheen Overlay */}
      {enableGlare && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-20 rounded-[inherit] overflow-hidden transition-opacity duration-300"
          style={{
            opacity: style.glareOpacity,
            mixBlendMode: blendMode,
            background: getFoilBackground(activeFoil, style.glareX, style.glareY),
          }}
        />
      )}
    </div>
  );
}

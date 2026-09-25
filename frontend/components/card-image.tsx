"use client";

import NextImage, { type ImageProps } from "next/image";
import { useState } from "react";

export function isDirectCardImage(src: ImageProps["src"]): boolean {
  if (typeof src !== "string") return false;
  try {
    const url = new URL(src, "https://cardboarddex.app");
    return url.hostname === "images.cardboarddex.app" ||
      (/^\/cards\/[A-Za-z0-9_-]+\/image$/.test(url.pathname) &&
        ["api.cardboarddex.app", "cardboarddex.app", "localhost", "127.0.0.1"].includes(url.hostname));
  } catch {
    return false;
  }
}

/** Card assets bypass runtime transformation and never retry through the API. */
export default function CardImage({ src, onError, unoptimized, ...props }: ImageProps) {
  const [failedSrc, setFailedSrc] = useState<ImageProps["src"] | null>(null);
  const direct = isDirectCardImage(src);
  const failed = direct && failedSrc === src;
  return <NextImage {...props}
    src={failed ? "/image-pending.svg" : src}
    unoptimized={direct || unoptimized}
    onError={(event) => {
      if (direct) setFailedSrc(src);
      onError?.(event);
    }}
  />;
}

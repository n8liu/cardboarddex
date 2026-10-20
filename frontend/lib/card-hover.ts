/**
 * Catalog-style hover shared by card/product tiles. The tile lifts; the image zooms only
 * slightly and carries its own padding (next/image `fill` ignores wrapper padding), so card
 * edges stay inside rounded `overflow-hidden` image boxes instead of being clipped.
 */
export const TILE_HOVER = "transition duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-[0_16px_40px_rgba(15,23,42,0.08)]";
export const IMAGE_HOVER = "transition duration-300 group-hover:scale-[1.02]";

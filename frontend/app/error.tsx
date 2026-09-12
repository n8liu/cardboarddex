"use client";

import { useEffect } from "react";

export default function ErrorPage({
  error,
  reset,
}: {
  error?: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (error) {
      console.error("[CardboardDex Error Boundary]:", error);
    }
  }, [error]);

  return (
    <main className="mx-auto min-h-[70vh] max-w-2xl px-5 py-20 text-center sm:px-8">
      <h1 className="text-2xl font-semibold text-zinc-950">Couldn&apos;t load the catalog</h1>
      <p className="mt-3 text-sm text-zinc-500">
        {error?.message || "An unexpected error occurred while communicating with the server."}
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <button
          className="rounded-md bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-800 transition shadow-xs"
          onClick={() => {
            if (typeof window !== "undefined") {
              window.location.reload();
            } else {
              reset();
            }
          }}
          type="button"
        >
          Reload page
        </button>
        <button
          className="rounded-md border border-zinc-200 bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition"
          onClick={reset}
          type="button"
        >
          Try again
        </button>
      </div>
    </main>
  );
}

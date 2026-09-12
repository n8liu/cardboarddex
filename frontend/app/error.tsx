"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="mx-auto min-h-[70vh] max-w-2xl px-5 py-20 text-center sm:px-8">
      <h1 className="text-2xl font-semibold text-zinc-950">Couldn&apos;t load the catalog</h1>
      <p className="mt-3 text-sm text-zinc-500">Sorry currently running errands.</p>
      <button
        className="mt-6 rounded-md bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-800"
        onClick={reset}
        type="button"
      >
        Try again
      </button>
    </main>
  );
}

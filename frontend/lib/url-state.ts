/**
 * Write filter state into the URL (null/empty removes a param). A discrete filter change
 * pushes a history entry so Back restores the previous view; a change limited to
 * `replaceKeys` (search text as it is typed) replaces the entry instead. Unchanged URLs are
 * left alone, so restoring state on popstate never adds an entry. Native pushState/replaceState
 * stay in sync with Next's useSearchParams.
 */
export function writeUrlFilters(values: Record<string, string | null | undefined>, replaceKeys: string[] = []): void {
  const url = new URL(window.location.href);
  const changed: string[] = [];
  for (const [key, value] of Object.entries(values)) {
    const next = value ? value : null;
    if (url.searchParams.get(key) === next) continue;
    changed.push(key);
    if (next === null) url.searchParams.delete(key);
    else url.searchParams.set(key, next);
  }
  if (!changed.length) return;
  const href = `${url.pathname}${url.search}`;
  if (changed.every((key) => replaceKeys.includes(key))) window.history.replaceState(null, "", href);
  else window.history.pushState(null, "", href);
}

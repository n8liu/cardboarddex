import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearClientCache, getCardSets, getLiveUpdates, getMarketMovers } from "@/lib/api";

const fetchMock = vi.fn();
const response = (data: unknown) => new Response(JSON.stringify(data));

beforeEach(() => {
  clearClientCache();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  clearClientCache();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("browser API caching", () => {
  it("fetches new observations on every Live Comps poll within 60 seconds", async () => {
    fetchMock
      .mockResolvedValueOnce(response({ items: [{ id: "older" }] }))
      .mockResolvedValueOnce(response({ items: [{ id: "newer" }] }));

    expect((await getLiveUpdates()).items[0].id).toBe("older");
    expect((await getLiveUpdates()).items[0].id).toBe("newer");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1].cache).toBe("no-store");
  });

  it("does not share in-flight no-store polls", async () => {
    let finish!: (value: Response) => void;
    fetchMock
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }))
      .mockResolvedValueOnce(response({ items: [{ id: "newer" }] }));
    const first = getLiveUpdates();
    expect((await getLiveUpdates()).items[0].id).toBe("newer");
    finish(response({ items: [{ id: "older" }] }));
    await first;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("reuses cacheable results and expires them after five minutes", async () => {
    const clock = vi.spyOn(Date, "now").mockReturnValue(1000);
    fetchMock.mockImplementation(async () => response([]));
    await getCardSets();
    await getCardSets();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    clock.mockReturnValue(301000);
    await getCardSets();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shares concurrent cacheable requests", async () => {
    fetchMock.mockImplementation(async () => response([]));
    await Promise.all([getCardSets(), getCardSets()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("evicts oldest responses when the browser cache reaches capacity", async () => {
    fetchMock.mockImplementation(async () => response({ gainers: [] }));
    for (let page = 1; page <= 65; page++) await getMarketMovers({ page });
    await getMarketMovers({ page: 65 });
    expect(fetchMock).toHaveBeenCalledTimes(65);
    await getMarketMovers({ page: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(66);
  });

  it("retries after a failed cacheable request", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(response([]));
    await expect(getCardSets()).rejects.toThrow("503");
    expect(await getCardSets()).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

it("caches browsing reads for one minute and preserves filter isolation", async () => {
  const { searchCards, getPokemonCards, getSetStats, getHomeOverview } = await import("@/lib/api");
  const clock = vi.spyOn(Date, "now").mockReturnValue(1000);
  fetchMock.mockImplementation(async () => response([]));
  for (const read of [() => searchCards("charizard"), () => getPokemonCards("pikachu"),
    () => getSetStats("base1"), () => getHomeOverview()]) {
    await read(); await read();
  }
  expect(fetchMock).toHaveBeenCalledTimes(4);
  await searchCards("charizard", { game: "pokemon-japan" });
  expect(fetchMock).toHaveBeenCalledTimes(5);
  clock.mockReturnValue(61000);
  await searchCards("charizard");
  expect(fetchMock).toHaveBeenCalledTimes(6);
});

it("retry bypasses memory and refuses to extend backend freshness", async () => {
  const { searchCards } = await import("@/lib/api");
  const clock = vi.spyOn(Date, "now").mockReturnValue(1000);
  const onCache = vi.fn();
  fetchMock.mockImplementation(async () => new Response("[]", { headers: {
    "X-Cache-Status": "hit", "X-Cache-Generated-At": new Date(0).toISOString(),
    "X-Cache-Expires-At": new Date(5000).toISOString(),
  } }));
  await searchCards("x", { onCache });
  await searchCards("x");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await searchCards("x", { bypassCache: true });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  clock.mockReturnValue(5000);
  await searchCards("x");
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(onCache).toHaveBeenCalledWith({ status: "hit", generatedAt: 0, expiresAt: 5000 });
});

it("does not retain stale or failed responses", async () => {
  const { searchCards } = await import("@/lib/api");
  fetchMock.mockImplementation(async () => new Response("[]", { headers: { "X-Cache-Status": "stale" } }));
  await searchCards("x"); await searchCards("x");
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("cancelling one subscriber does not cancel another", async () => {
  const { searchCards } = await import("@/lib/api");
  let finish!: (response: Response) => void;
  fetchMock.mockImplementation(() => new Promise<Response>((resolve) => { finish = resolve; }));
  const controller = new AbortController();
  const first = searchCards("x", { abortSignal: controller.signal });
  const second = searchCards("x");
  controller.abort();
  await expect(first).rejects.toThrow();
  expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(false);
  finish(response([]));
  expect(await second).toEqual([]);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("cancels the network when all subscribers leave, then allows retry", async () => {
  const { searchCards } = await import("@/lib/api");
  fetchMock.mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  })).mockResolvedValueOnce(response([]));
  const controller = new AbortController();
  const first = searchCards("x", { abortSignal: controller.signal });
  controller.abort();
  await expect(first).rejects.toThrow();
  expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  expect(await searchCards("x")).toEqual([]);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("a bypassed old request cannot overwrite its newer retry", async () => {
  const { searchCards } = await import("@/lib/api");
  let finish!: (response: Response) => void;
  fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }))
    .mockResolvedValueOnce(response([{ id: "new" }]));
  const old = searchCards("x");
  await searchCards("x", { bypassCache: true });
  finish(response([{ id: "old" }]));
  await old;
  expect(await searchCards("x")).toEqual([{ id: "new" }]);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("does not stack a Next server cache over backend freshness", async () => {
  vi.stubGlobal("window", undefined);
  fetchMock.mockResolvedValue(response([]));
  await getCardSets();
  expect(fetchMock.mock.calls[0][1].cache).toBe("no-store");
  expect(fetchMock.mock.calls[0][1].next).toBeUndefined();
});

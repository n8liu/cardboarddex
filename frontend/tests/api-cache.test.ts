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

  it("reuses cacheable results and expires them after 60 seconds", async () => {
    const clock = vi.spyOn(Date, "now").mockReturnValue(1000);
    fetchMock.mockImplementation(async () => response([]));
    await getCardSets();
    await getCardSets();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    clock.mockReturnValue(61000);
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

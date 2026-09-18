import test from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.mjs";

test("relay denies unauthenticated requests and disallowed paths", async () => {
  const env = { RELAY_KEY: "test-secret" };
  assert.equal((await worker.fetch(new Request("https://relay.example/"), env)).status, 401);
  const request = new Request("https://relay.example/arbitrary", {
    headers: { "X-CardboardDex-Proxy-Key": env.RELAY_KEY },
  });
  assert.equal((await worker.fetch(request, env)).status, 404);
});

test("relay only forwards allowed credentials to eBay and never forwards its own secret", async (t) => {
  let received;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    received = { url, options };
    return new Response('{"itemSummaries":[]}', { status: 200 });
  });
  const request = new Request("https://relay.example/buy/browse/v1/item_summary/search?q=Pikachu", {
    headers: { "X-CardboardDex-Proxy-Key": "test-secret", Authorization: "Bearer token", Cookie: "private" },
  });
  const response = await worker.fetch(request, { RELAY_KEY: "test-secret" });
  assert.equal(response.status, 200);
  assert.equal(received.url, "https://api.ebay.com/buy/browse/v1/item_summary/search?q=Pikachu");
  assert.equal(received.options.headers.get("Authorization"), "Bearer token");
  assert.equal(received.options.headers.get("X-CardboardDex-Proxy-Key"), null);
  assert.equal(received.options.headers.get("Cookie"), null);
  assert.equal(received.options.redirect, "manual");
});

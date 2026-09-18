const allowed = new Set([
  "POST /identity/v1/oauth2/token",
  "GET /buy/browse/v1/item_summary/search",
]);

export default {
  async fetch(request, env) {
    if (!env.RELAY_KEY || request.headers.get("X-CardboardDex-Proxy-Key") !== env.RELAY_KEY) {
      return new Response("Unauthorized", { status: 401 });
    }
    const incoming = new URL(request.url);
    if (!allowed.has(`${request.method} ${incoming.pathname}`)) {
      return new Response("Not found", { status: 404 });
    }
    const headers = new Headers();
    for (const name of ["Authorization", "Content-Type", "Accept", "X-EBAY-C-MARKETPLACE-ID"]) {
      if (request.headers.has(name)) headers.set(name, request.headers.get(name));
    }
    try {
      const upstream = await fetch(`https://api.ebay.com${incoming.pathname}${incoming.search}`, {
        method: request.method,
        headers,
        body: request.method === "POST" ? request.body : undefined,
        redirect: "manual",
      });
      return new Response(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type": upstream.headers.get("Content-Type") || "application/json",
          "Cache-Control": "no-store",
        },
      });
    } catch (error) {
      console.error("eBay relay request failed", error.name, error.message);
      return new Response("Upstream unavailable", { status: 502 });
    }
  },
};

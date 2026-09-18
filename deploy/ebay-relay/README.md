# eBay IPv6 relay

The IPv6-only Lightsail host cannot reach the IPv4-only eBay API directly.
This Worker forwards only OAuth token POSTs and Browse search GETs to
`https://api.ebay.com`. It requires `X-CardboardDex-Proxy-Key`, strips that
header before forwarding, disables caching, and does not follow redirects.

Deploy with `wrangler deploy --config deploy/ebay-relay/wrangler.toml`, then
set a random `RELAY_KEY` with `wrangler secret put RELAY_KEY --config
deploy/ebay-relay/wrangler.toml`. Configure the same value as `EBAY_RELAY_KEY`
and the Worker's HTTPS origin as `EBAY_RELAY_URL` in the server's protected
environment file. Never put these values in frontend configuration.

eBay credentials and responses pass through this Worker in the owner's
Cloudflare account. Deployment was explicitly approved during the IPv6
migration. Keep request/body logging disabled. The current 500-search/day
application quota fits within the Workers free request allowance.

Run `node --test deploy/ebay-relay/worker.test.mjs` to check access restrictions
and header forwarding. CI tests the Worker but does not automatically publish
changes to its live endpoint.

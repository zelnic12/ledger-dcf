// Ledger DCF relay: a Cloudflare Worker that forwards requests to Yahoo Finance
// and adds CORS headers so the GitHub Pages site can read the response.
// Only Yahoo Finance hosts are allowed, so this can't be used as an open proxy.

const ALLOWED_HOSTS = new Set(["query1.finance.yahoo.com", "query2.finance.yahoo.com"]);
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (request.method !== "GET") return new Response("Method not allowed", { status: 405, headers: CORS });

    const target = new URL(request.url).searchParams.get("url");
    let url;
    try { url = new URL(target); } catch { return json({ error: "Missing or invalid url parameter." }, 400); }
    if (url.protocol !== "https:" || !ALLOWED_HOSTS.has(url.hostname)) {
      return json({ error: "Only Yahoo Finance URLs are allowed." }, 403);
    }

    const upstream = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Accept": "application/json",
      },
      cf: { cacheTtl: 600, cacheEverything: true },
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "public, max-age=600" },
    });
  },
};

function json(body, status) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

/**
 * Fake fetch keyed by URL substring; unmatched URLs reject like a network
 * failure. Payload values may be objects (200 JSON) or {status} for errors.
 */
export function fakeFetch(routes) {
  const calls = [];
  const fetcher = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    let best = null;
    let bestLen = -1;
    for (const [needle, payload] of Object.entries(routes)) {
      if (String(url).includes(needle) && needle.length > bestLen) {
        best = payload;
        bestLen = needle.length;
      }
    }
    if (best !== null) {
      if (best && typeof best === "object" && typeof best.__http === "number") {
        const { __http, __text, ...body } = best;
        const textBody =
          __text !== undefined ? String(__text) : JSON.stringify(body);
        return {
          ok: __http < 400,
          status: __http,
          statusText: __http < 400 ? "OK" : "Error",
          json: async () => body,
          text: async () => textBody,
        };
      }
      if (best && typeof best === "object" && "status" in best && best.status >= 400) {
        return {
          ok: false,
          status: best.status,
          statusText: "Error",
          json: async () => ({}),
          text: async () => "",
        };
      }
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => best,
        text: async () => JSON.stringify(best),
      };
    }
    throw new TypeError("fetch failed");
  };
  fetcher.calls = calls;
  return fetcher;
}

export function loadDashboard({ fetch } = {}) {
  const html = readFileSync(join(root, "index.html"), "utf-8");
  const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://127.0.0.1:8787/" });
  if (fetch) dom.window.fetch = fetch;
  dom.window.__DAARI_WEB_UI_CONFIG__ = { apiBaseUrl: "http://127.0.0.1:11435" };
  const script = readFileSync(join(root, "app.js"), "utf-8");
  dom.window.eval(script);
  return dom;
}

/** Flush pending promise chains kicked off by DOM event handlers. */
export async function settle(rounds = 10) {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

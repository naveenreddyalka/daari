import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

export function fakeChrome(initialStorage = {}) {
  const data = { ...initialStorage };
  const calls = { openOptionsPage: 0 };
  return {
    data,
    calls,
    storage: {
      local: {
        async get(keys) {
          const wanted = Array.isArray(keys) ? keys : [keys];
          const result = {};
          for (const key of wanted) {
            if (key in data) result[key] = data[key];
          }
          return result;
        },
        async set(entries) {
          Object.assign(data, entries);
        },
      },
    },
    runtime: {
      openOptionsPage() {
        calls.openOptionsPage += 1;
      },
    },
  };
}

export function loadPage(page, { chrome, fetch } = {}) {
  const html = readFileSync(join(root, `${page}.html`), "utf-8");
  const dom = new JSDOM(html, { runScripts: "outside-only", url: "chrome-extension://daari/" });
  dom.window.chrome = chrome ?? fakeChrome();
  if (fetch) dom.window.fetch = fetch;
  const script = readFileSync(join(root, `${page}.js`), "utf-8");
  dom.window.eval(script);
  return dom;
}

/** Flush pending promise chains kicked off by DOM event handlers. */
export async function settle(rounds = 10) {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

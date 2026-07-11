import assert from "node:assert/strict";
import { test } from "node:test";

import { fakeChrome, loadPage, settle } from "./harness.js";

const OK_PAYLOAD = {
  choices: [{ message: { content: "hello from daari" } }],
  daari_meta: { tier: "L3", cache_hit: false },
};

function okFetch(recorded = {}) {
  return async (url, init) => {
    recorded.url = url;
    recorded.body = JSON.parse(init.body);
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      async json() {
        return OK_PAYLOAD;
      },
    };
  };
}

test("send flow renders response and tier metadata", async () => {
  const recorded = {};
  const dom = loadPage("popup", { fetch: okFetch(recorded) });
  const { document } = dom.window;

  document.getElementById("prompt").value = "what is daari?";
  document.getElementById("send").click();
  await settle();

  assert.equal(recorded.url, "http://127.0.0.1:11435/v1/chat/completions");
  assert.equal(recorded.body.model, "daari");
  assert.equal(recorded.body.messages[0].content, "what is daari?");
  assert.equal(document.getElementById("response").textContent, "hello from daari");
  assert.match(document.getElementById("meta").textContent, /"tier": "L3"/);
  assert.match(document.getElementById("status").textContent, /^Done at /);
  assert.equal(document.getElementById("send").disabled, false);
});

test("empty prompt is rejected before any request", async () => {
  let called = false;
  const dom = loadPage("popup", {
    fetch: async () => {
      called = true;
      throw new Error("should not fetch");
    },
  });
  dom.window.document.getElementById("send").click();
  await settle();

  assert.equal(called, false);
  assert.equal(dom.window.document.getElementById("status").textContent, "Enter a prompt first.");
});

test("unreachable daemon shows options hint", async () => {
  const dom = loadPage("popup");
  // Throw the window-realm TypeError, as a real browser fetch failure would.
  dom.window.fetch = async () => {
    throw new dom.window.TypeError("Failed to fetch");
  };
  const { document } = dom.window;
  document.getElementById("prompt").value = "ping";
  document.getElementById("send").click();
  await settle();

  assert.match(document.getElementById("response").textContent, /^Request failed: /);
  assert.match(
    document.getElementById("status").textContent,
    /Could not reach daari\. Check API URL in extension options/
  );
  assert.equal(document.getElementById("send").disabled, false);
});

test("http error status shows generic failure", async () => {
  const dom = loadPage("popup", {
    fetch: async () => ({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      async json() {
        return {};
      },
    }),
  });
  const { document } = dom.window;
  document.getElementById("prompt").value = "ping";
  document.getElementById("send").click();
  await settle();

  assert.match(document.getElementById("response").textContent, /500 Internal Server Error/);
  assert.match(document.getElementById("status").textContent, /^Request failed\./);
});

test("draft persists via chrome.storage and reloads", async () => {
  const chrome = fakeChrome();
  const dom = loadPage("popup", { chrome });
  const prompt = dom.window.document.getElementById("prompt");
  prompt.value = "draft in progress";
  prompt.dispatchEvent(new dom.window.Event("input"));
  await settle();

  assert.equal(chrome.data["daari_extension.prompt"], "draft in progress");

  const reloaded = loadPage("popup", { chrome });
  await settle();
  assert.equal(reloaded.window.document.getElementById("prompt").value, "draft in progress");
});

test("popup uses the API base URL saved in options", async () => {
  const chrome = fakeChrome({ "daari_extension.api_base_url": "https://tunnel.example.com/" });
  const recorded = {};
  const dom = loadPage("popup", { chrome, fetch: okFetch(recorded) });
  const { document } = dom.window;
  document.getElementById("prompt").value = "ping";
  document.getElementById("send").click();
  await settle();

  assert.equal(recorded.url, "https://tunnel.example.com/v1/chat/completions");
});

test("options button opens the options page", async () => {
  const chrome = fakeChrome();
  const dom = loadPage("popup", { chrome });
  dom.window.document.getElementById("open-options").click();
  await settle();

  assert.equal(chrome.calls.openOptionsPage, 1);
});

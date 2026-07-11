import assert from "node:assert/strict";
import { test } from "node:test";

import { fakeChrome, loadPage, settle } from "./harness.js";

const API_BASE_KEY = "daari_extension.api_base_url";

test("options load defaults to the local daemon URL", async () => {
  const dom = loadPage("options");
  await settle();
  assert.equal(dom.window.document.getElementById("api-base-url").value, "http://127.0.0.1:11435");
});

test("options load shows the previously saved URL", async () => {
  const chrome = fakeChrome({ [API_BASE_KEY]: "https://tunnel.example.com" });
  const dom = loadPage("options", { chrome });
  await settle();
  assert.equal(dom.window.document.getElementById("api-base-url").value, "https://tunnel.example.com");
});

test("save normalizes trailing slash and persists", async () => {
  const chrome = fakeChrome();
  const dom = loadPage("options", { chrome });
  const { document } = dom.window;
  document.getElementById("api-base-url").value = "https://tunnel.example.com/ ";
  document.getElementById("save").click();
  await settle();

  assert.equal(chrome.data[API_BASE_KEY], "https://tunnel.example.com");
  assert.match(document.getElementById("status").textContent, /^Saved at /);
});

test("invalid URL is rejected and not persisted", async () => {
  const chrome = fakeChrome();
  const dom = loadPage("options", { chrome });
  const { document } = dom.window;
  document.getElementById("api-base-url").value = "not-a-url";
  document.getElementById("save").click();
  await settle();

  assert.equal(chrome.data[API_BASE_KEY], undefined);
  assert.equal(document.getElementById("status").textContent, "URL must start with http:// or https://");
});

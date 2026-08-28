import assert from "node:assert/strict";
import { test } from "node:test";

import { JSDOM } from "jsdom";

import { matchProfile, PROFILES } from "../lib/profiles.js";
import {
  assistantText,
  isBoundaryRefusal,
  requestDaariChat,
} from "../lib/daemon.js";
import {
  emptySession,
  estimateSavedUsd,
  recordFallback,
  recordServe,
} from "../lib/session.js";
import {
  attachChatInterceptor,
  OUTCOME,
  tryServePrompt,
} from "../lib/intercept.js";
import { settle } from "./harness.js";

test("ships two site profiles with chat selectors and boundary ids", () => {
  assert.equal(PROFILES.length, 2);
  for (const profile of PROFILES) {
    assert.ok(profile.id);
    assert.ok(profile.hosts.length >= 1);
    assert.ok(profile.selectors.input);
    assert.ok(profile.selectors.send);
    assert.ok(profile.selectors.messages);
    assert.ok(profile.boundaryProfile);
  }
  assert.equal(matchProfile("127.0.0.1:8765", "/").id, "fintech-assist");
  assert.equal(matchProfile("localhost:8766", "/help").id, "docs-support");
  assert.equal(matchProfile("evil.example", "/"), null);
});

test("requestDaariChat sends boundary profile and meta headers", async () => {
  const recorded = {};
  const fetchFn = async (url, init) => {
    recorded.url = url;
    recorded.headers = init.headers;
    recorded.body = JSON.parse(init.body);
    return {
      ok: true,
      status: 200,
      async json() {
        return {
          choices: [{ message: { content: "ok" } }],
          daari_meta: { tier: "L3" },
        };
      },
    };
  };
  const payload = await requestDaariChat({
    prompt: "credit score?",
    apiBase: "http://127.0.0.1:11435/",
    boundaryProfile: "fintech-assist",
    clientId: "extension:fintech-assist",
    fetchFn,
  });
  assert.equal(recorded.url, "http://127.0.0.1:11435/v1/chat/completions");
  assert.equal(recorded.headers["X-Daari-Meta"], "true");
  assert.equal(recorded.headers["X-Daari-Boundary-Profile"], "fintech-assist");
  assert.equal(recorded.headers["X-Daari-Client-Id"], "extension:fintech-assist");
  assert.equal(assistantText(payload), "ok");
});

test("boundary refusal is detected from daari_meta.tier", () => {
  assert.equal(isBoundaryRefusal({ daari_meta: { tier: "boundary" } }), true);
  assert.equal(isBoundaryRefusal({ daari_meta: { tier: "L3" } }), false);
});

test("tryServePrompt falls back when daemon is down", async () => {
  const result = await tryServePrompt({
    prompt: "hello",
    fetchFn: async () => {
      throw new TypeError("Failed to fetch");
    },
  });
  assert.equal(result.outcome, OUTCOME.FALLBACK_DAEMON);
});

test("tryServePrompt falls back when boundary refuses", async () => {
  const result = await tryServePrompt({
    prompt: "write a novel",
    boundaryProfile: "fintech-assist",
    fetchFn: async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          choices: [{ message: { content: "out of scope" } }],
          daari_meta: { tier: "boundary", warning: "boundary_blocked" },
        };
      },
    }),
  });
  assert.equal(result.outcome, OUTCOME.FALLBACK_BOUNDARY);
});

test("tryServePrompt returns local assistant text on success", async () => {
  const result = await tryServePrompt({
    prompt: "what is my credit score band?",
    fetchFn: async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          choices: [{ message: { content: "locally served" } }],
          daari_meta: { tier: "L3", prompt_chars: 40 },
        };
      },
    }),
  });
  assert.equal(result.outcome, OUTCOME.SERVED);
  assert.equal(result.text, "locally served");
  assert.equal(result.meta.tier, "L3");
});

function chatDom(profileId = "fintech-assist") {
  const profile = PROFILES.find((p) => p.id === profileId);
  const { input, send, form, messages } = profile.selectors;
  const html = `<!doctype html><form id="${form.slice(1)}">
    <textarea id="${input.slice(1)}"></textarea>
    <button type="submit" id="${send.slice(1)}">Send</button>
  </form>
  <div id="${messages.slice(1)}"></div>`;
  const dom = new JSDOM(html, { url: "http://127.0.0.1:8765/" });
  return { dom, profile, document: dom.window.document };
}

test("interceptor serves via daari and does not fall through", async () => {
  const { dom, profile, document } = chatDom();
  let pageSubmitted = false;
  document.querySelector(profile.selectors.form).addEventListener("submit", () => {
    pageSubmitted = true;
  });
  const served = [];
  attachChatInterceptor(document, {
    profile,
    apiBase: "http://127.0.0.1:11435",
    fetchFn: async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          choices: [{ message: { content: "from daari" } }],
          daari_meta: { tier: "L4", prompt_chars: 20 },
        };
      },
    }),
    onServed: async (result) => served.push(result),
  });
  document.querySelector(profile.selectors.input).value = "credit card rewards?";
  document.querySelector(profile.selectors.send).click();
  await settle(20);
  assert.equal(pageSubmitted, false);
  assert.equal(served.length, 1);
  assert.equal(served[0].outcome, OUTCOME.SERVED);
  assert.match(document.querySelector(profile.selectors.messages).textContent, /from daari/);
});

test("interceptor falls through to page backend when daemon is down", async () => {
  const { profile, document } = chatDom();
  let pageSubmitted = 0;
  document.querySelector(profile.selectors.form).addEventListener("submit", (event) => {
    event.preventDefault();
    pageSubmitted += 1;
  });
  const fallbacks = [];
  attachChatInterceptor(document, {
    profile,
    fetchFn: async () => {
      throw new TypeError("Failed to fetch");
    },
    onFallback: async (result) => fallbacks.push(result),
  });
  document.querySelector(profile.selectors.input).value = "hello";
  document.querySelector(profile.selectors.send).click();
  await settle(20);
  assert.equal(fallbacks[0]?.outcome, OUTCOME.FALLBACK_DAEMON);
  assert.equal(pageSubmitted, 1);
});

test("interceptor falls through when boundary refuses", async () => {
  const { profile, document } = chatDom();
  let pageSubmitted = 0;
  document.querySelector(profile.selectors.form).addEventListener("submit", (event) => {
    event.preventDefault();
    pageSubmitted += 1;
  });
  attachChatInterceptor(document, {
    profile,
    fetchFn: async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          choices: [{ message: { content: "refused" } }],
          daari_meta: { tier: "boundary" },
        };
      },
    }),
  });
  document.querySelector(profile.selectors.input).value = "plan my wedding";
  document.querySelector(profile.selectors.send).click();
  await settle(20);
  assert.equal(pageSubmitted, 1);
});

test("session tracks last tier and estimated savings", () => {
  let session = emptySession();
  session = recordServe(session, { tier: "L3", prompt_chars: 4000 });
  assert.equal(session.lastTier, "L3");
  assert.equal(session.localRequests, 1);
  assert.ok(session.estimatedSavedUsd > 0);
  assert.ok(estimateSavedUsd({ tier: "L6" }) === 0);
  session = recordFallback(session);
  assert.equal(session.fallbacks, 1);
});

/**
 * MV3 service worker: daemon proxy + session stats (#171).
 * Content scripts message here so localhost host_permissions apply.
 */

import { matchProfile, PROFILES } from "./lib/profiles.js";
import { tryServePrompt, OUTCOME } from "./lib/intercept.js";
import {
  API_BASE_KEY,
  DEFAULT_API_BASE,
  normalizeApiBase,
} from "./lib/daemon.js";
import {
  SESSION_KEY,
  emptySession,
  recordFallback,
  recordServe,
} from "./lib/session.js";

async function getApiBase() {
  const state = await chrome.storage.local.get([API_BASE_KEY]);
  const raw = typeof state[API_BASE_KEY] === "string" ? state[API_BASE_KEY] : "";
  return normalizeApiBase(raw || DEFAULT_API_BASE);
}

async function loadSession() {
  const state = await chrome.storage.local.get([SESSION_KEY]);
  return state[SESSION_KEY] && typeof state[SESSION_KEY] === "object"
    ? { ...emptySession(), ...state[SESSION_KEY] }
    : emptySession();
}

async function saveSession(session) {
  await chrome.storage.local.set({ [SESSION_KEY]: session });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  void (async () => {
    try {
      if (message?.type === "daari.matchProfile") {
        sendResponse({
          ok: true,
          profile: matchProfile(message.host, message.pathname, PROFILES),
        });
        return;
      }
      if (message?.type === "daari.getSession") {
        sendResponse({ ok: true, session: await loadSession() });
        return;
      }
      if (message?.type === "daari.resetSession") {
        await saveSession(emptySession());
        sendResponse({ ok: true, session: emptySession() });
        return;
      }
      if (message?.type === "daari.tryServe") {
        const apiBase = await getApiBase();
        const result = await tryServePrompt({
          prompt: message.prompt,
          apiBase,
          boundaryProfile: message.boundaryProfile,
          clientId: message.clientId,
        });
        let session = await loadSession();
        if (result.outcome === OUTCOME.SERVED) {
          session = recordServe(session, result.meta);
        } else {
          session = recordFallback(session);
        }
        await saveSession(session);
        sendResponse({ ok: true, result, session });
        return;
      }
      sendResponse({ ok: false, error: "unknown_message" });
    } catch (error) {
      sendResponse({ ok: false, error: error?.message || "error" });
    }
  })();
  return true;
});

const promptNode = document.getElementById("prompt");
const sendButton = document.getElementById("send");
const optionsButton = document.getElementById("open-options");
const responseNode = document.getElementById("response");
const metaNode = document.getElementById("meta");
const statusNode = document.getElementById("status");
const sessionNode = document.getElementById("session-stats");

const STORAGE_KEY = "daari_extension.prompt";
const API_BASE_KEY = "daari_extension.api_base_url";
const SESSION_KEY = "daari_extension.session";
const DEFAULT_API_BASE = "http://127.0.0.1:11435";
const FRONTIER_USD_PER_1K = 0.002;

function setStatus(text) {
  statusNode.textContent = text;
}

function emptySession() {
  return {
    requests: 0,
    localRequests: 0,
    fallbacks: 0,
    lastTier: null,
    estimatedSavedUsd: 0,
  };
}

function estimateSavedUsd(meta) {
  if (!meta) return 0;
  if (meta.tier === "L6" || meta.tier === "boundary" || meta.tier === "guardrail") {
    return 0;
  }
  if (typeof meta.cost_usd === "number" && typeof meta.daari_cost_usd === "number") {
    return Math.max(0, Number((meta.cost_usd - meta.daari_cost_usd).toFixed(4)));
  }
  let tokens = 0;
  if (typeof meta.input_tokens === "number" && typeof meta.output_tokens === "number") {
    tokens = meta.input_tokens + meta.output_tokens;
  } else if (typeof meta.prompt_chars === "number") {
    tokens = Math.ceil(meta.prompt_chars / 4) + 32;
  } else {
    tokens = 64;
  }
  return Number(((tokens / 1000) * FRONTIER_USD_PER_1K).toFixed(4));
}

function recordServe(session, meta) {
  const next = { ...session };
  next.requests += 1;
  next.lastTier = meta?.tier || null;
  if (meta?.tier && meta.tier !== "L6" && meta.tier !== "boundary") {
    next.localRequests += 1;
    next.estimatedSavedUsd = Number(
      (next.estimatedSavedUsd + estimateSavedUsd(meta)).toFixed(4)
    );
  }
  return next;
}

function formatSession(session) {
  const tier = session.lastTier || "—";
  const saved = Number(session.estimatedSavedUsd || 0).toFixed(4);
  return `Last tier: ${tier} · Est. saved: $${saved} · Local: ${session.localRequests || 0} · Fallbacks: ${session.fallbacks || 0}`;
}

async function loadSession() {
  const state = await chrome.storage.local.get([SESSION_KEY]);
  const session =
    state[SESSION_KEY] && typeof state[SESSION_KEY] === "object"
      ? { ...emptySession(), ...state[SESSION_KEY] }
      : emptySession();
  if (sessionNode) {
    sessionNode.textContent =
      session.requests > 0 || session.fallbacks > 0
        ? formatSession(session)
        : "No intercepted requests yet.";
  }
  return session;
}

async function saveSession(session) {
  await chrome.storage.local.set({ [SESSION_KEY]: session });
  if (sessionNode) sessionNode.textContent = formatSession(session);
}

async function loadDraft() {
  const state = await chrome.storage.local.get([STORAGE_KEY]);
  if (typeof state[STORAGE_KEY] === "string") {
    promptNode.value = state[STORAGE_KEY];
  }
}

async function getApiBaseUrl() {
  const state = await chrome.storage.local.get([API_BASE_KEY]);
  const raw = typeof state[API_BASE_KEY] === "string" ? state[API_BASE_KEY].trim() : "";
  return (raw || DEFAULT_API_BASE).replace(/\/$/, "");
}

async function saveDraft() {
  await chrome.storage.local.set({ [STORAGE_KEY]: promptNode.value || "" });
}

async function sendPrompt() {
  const prompt = (promptNode.value || "").trim();
  if (!prompt) {
    setStatus("Enter a prompt first.");
    return;
  }
  sendButton.disabled = true;
  setStatus("Sending to local daari...");
  responseNode.textContent = "...";
  metaNode.textContent = "...";
  try {
    const apiBase = await getApiBaseUrl();
    const apiUrl = `${apiBase}/v1/chat/completions`;
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Daari-Meta": "true",
      },
      body: JSON.stringify({
        model: "daari",
        temperature: 0.2,
        messages: [{ role: "user", content: prompt }],
      }),
    });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    const payload = await response.json();
    const message = payload?.choices?.[0]?.message?.content || "(empty response)";
    responseNode.textContent = message;
    metaNode.textContent = JSON.stringify(payload?.daari_meta || {}, null, 2);
    setStatus(`Done at ${new Date().toLocaleTimeString()}`);
    await saveDraft();
    const meta = payload?.daari_meta || {};
    let session = await loadSession();
    session = recordServe(session, meta);
    await saveSession(session);
  } catch (error) {
    const message = error?.message || "unknown error";
    responseNode.textContent = `Request failed: ${message}`;
    metaNode.textContent = "-";
    if (error instanceof TypeError) {
      setStatus("Could not reach daari. Check API URL in extension options and verify daemon is running.");
    } else {
      setStatus("Request failed. Review response details and extension options.");
    }
  } finally {
    sendButton.disabled = false;
  }
}

promptNode.addEventListener("input", () => {
  void saveDraft();
});
sendButton.addEventListener("click", () => {
  void sendPrompt();
});
optionsButton.addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

void loadDraft();
void loadSession();

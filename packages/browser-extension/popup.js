const promptNode = document.getElementById("prompt");
const sendButton = document.getElementById("send");
const optionsButton = document.getElementById("open-options");
const responseNode = document.getElementById("response");
const metaNode = document.getElementById("meta");
const statusNode = document.getElementById("status");

const STORAGE_KEY = "daari_extension.prompt";
const API_BASE_KEY = "daari_extension.api_base_url";
const DEFAULT_API_BASE = "http://127.0.0.1:11435";

function setStatus(text) {
  statusNode.textContent = text;
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

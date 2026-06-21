const API_BASE_KEY = "daari_extension.api_base_url";
const DEFAULT_API_BASE = "http://127.0.0.1:11435";

const inputNode = document.getElementById("api-base-url");
const saveButton = document.getElementById("save");
const statusNode = document.getElementById("status");

function setStatus(text) {
  statusNode.textContent = text;
}

function normalizeUrl(raw) {
  return raw.trim().replace(/\/$/, "");
}

async function loadOptions() {
  const state = await chrome.storage.local.get([API_BASE_KEY]);
  const apiBase = typeof state[API_BASE_KEY] === "string" ? state[API_BASE_KEY] : DEFAULT_API_BASE;
  inputNode.value = apiBase;
}

async function saveOptions() {
  const value = normalizeUrl(inputNode.value || "");
  if (!value.startsWith("http://") && !value.startsWith("https://")) {
    setStatus("URL must start with http:// or https://");
    return;
  }
  await chrome.storage.local.set({ [API_BASE_KEY]: value });
  setStatus(`Saved at ${new Date().toLocaleTimeString()}`);
}

saveButton.addEventListener("click", () => {
  void saveOptions();
});

void loadOptions();

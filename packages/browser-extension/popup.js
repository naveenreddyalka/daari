const promptNode = document.getElementById("prompt");
const sendButton = document.getElementById("send");
const responseNode = document.getElementById("response");
const metaNode = document.getElementById("meta");
const statusNode = document.getElementById("status");

const API_URL = "http://127.0.0.1:11435/v1/chat/completions";
const STORAGE_KEY = "daari_extension.prompt";

function setStatus(text) {
  statusNode.textContent = text;
}

async function loadDraft() {
  const state = await chrome.storage.local.get([STORAGE_KEY]);
  if (typeof state[STORAGE_KEY] === "string") {
    promptNode.value = state[STORAGE_KEY];
  }
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
    const response = await fetch(API_URL, {
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
    responseNode.textContent = `Request failed: ${error.message}`;
    metaNode.textContent = "-";
    setStatus("Failed. Is daari serve running on :11435?");
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

void loadDraft();

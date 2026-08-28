/** Intercept → try local daemon → fallback decision (#171). */

import { assistantText, isBoundaryRefusal, requestDaariChat } from "./daemon.js";

export const OUTCOME = {
  SERVED: "served",
  FALLBACK_DAEMON: "fallback_daemon",
  FALLBACK_BOUNDARY: "fallback_boundary",
};

/**
 * Attempt to serve a prompt via local daari.
 * @returns {Promise<{ outcome: string, text?: string, meta?: object, error?: string }>}
 */
export async function tryServePrompt({
  prompt,
  apiBase,
  boundaryProfile,
  clientId,
  fetchFn,
}) {
  const trimmed = (prompt || "").trim();
  if (!trimmed) {
    return { outcome: OUTCOME.FALLBACK_DAEMON, error: "empty" };
  }
  try {
    const payload = await requestDaariChat({
      prompt: trimmed,
      apiBase,
      boundaryProfile,
      clientId,
      fetchFn,
    });
    if (isBoundaryRefusal(payload)) {
      return {
        outcome: OUTCOME.FALLBACK_BOUNDARY,
        meta: payload.daari_meta || null,
        text: assistantText(payload),
      };
    }
    return {
      outcome: OUTCOME.SERVED,
      text: assistantText(payload) || "(empty response)",
      meta: payload.daari_meta || null,
    };
  } catch (error) {
    return {
      outcome: OUTCOME.FALLBACK_DAEMON,
      error: error?.message || "unknown error",
    };
  }
}

/**
 * Append an assistant bubble into a messages container.
 * @param {ParentNode} container
 * @param {string} text
 * @param {Document} doc
 */
export function appendAssistantMessage(container, text, doc = document) {
  if (!container) return;
  const bubble = doc.createElement("div");
  bubble.className = "daari-ext-assistant";
  bubble.setAttribute("data-daari-served", "true");
  bubble.textContent = text;
  container.appendChild(bubble);
}

/**
 * Wire capture-phase interceptors on a document for one site profile.
 * Returns a dispose function.
 */
export function attachChatInterceptor(doc, {
  profile,
  apiBase,
  fetchFn,
  tryServe = tryServePrompt,
  onServed,
  onFallback,
}) {
  const { input: inputSel, send: sendSel, form: formSel, messages: messagesSel } =
    profile.selectors;
  let bypass = false;

  async function handleIntercept(event) {
    if (bypass) return;
    const input = doc.querySelector(inputSel);
    if (!input) return;
    const prompt = "value" in input ? input.value : input.textContent;
    if (!(prompt || "").trim()) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const result = await tryServe({
      prompt,
      apiBase,
      boundaryProfile: profile.boundaryProfile,
      clientId: `extension:${profile.id}`,
      fetchFn,
    });

    if (result.outcome === OUTCOME.SERVED) {
      const messages = doc.querySelector(messagesSel);
      appendAssistantMessage(messages, result.text, doc);
      if (onServed) await onServed(result);
      if ("value" in input) input.value = "";
      return;
    }

    if (onFallback) await onFallback(result);
    bypass = true;
    try {
      const send = doc.querySelector(sendSel);
      const form = formSel ? doc.querySelector(formSel) : null;
      if (form && typeof form.requestSubmit === "function") {
        form.requestSubmit(send || undefined);
      } else if (send) {
        send.click();
      } else if (form) {
        form.dispatchEvent(new doc.defaultView.Event("submit", { bubbles: true, cancelable: true }));
      }
    } finally {
      bypass = false;
    }
  }

  const form = formSel ? doc.querySelector(formSel) : null;
  const send = doc.querySelector(sendSel);
  const listeners = [];

  if (form) {
    const fn = (event) => {
      void handleIntercept(event);
    };
    form.addEventListener("submit", fn, true);
    listeners.push(() => form.removeEventListener("submit", fn, true));
  }
  if (send) {
    const fn = (event) => {
      void handleIntercept(event);
    };
    send.addEventListener("click", fn, true);
    listeners.push(() => send.removeEventListener("click", fn, true));
  }

  return () => {
    for (const off of listeners) off();
  };
}

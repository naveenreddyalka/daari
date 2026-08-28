/**
 * Content script: intercept in-page chat widgets for matched site profiles (#171).
 */

(function () {
  const OUTCOME = {
    SERVED: "served",
    FALLBACK_DAEMON: "fallback_daemon",
    FALLBACK_BOUNDARY: "fallback_boundary",
  };

  function appendAssistantMessage(container, text) {
    if (!container) return;
    const bubble = document.createElement("div");
    bubble.className = "daari-ext-assistant";
    bubble.setAttribute("data-daari-served", "true");
    bubble.textContent = text;
    container.appendChild(bubble);
  }

  function attach(profile) {
    const { input: inputSel, send: sendSel, form: formSel, messages: messagesSel } =
      profile.selectors;
    let bypass = false;

    async function handleIntercept(event) {
      if (bypass) return;
      const input = document.querySelector(inputSel);
      if (!input) return;
      const prompt = "value" in input ? input.value : input.textContent;
      if (!(prompt || "").trim()) return;

      event.preventDefault();
      event.stopImmediatePropagation();

      const response = await chrome.runtime.sendMessage({
        type: "daari.tryServe",
        prompt,
        boundaryProfile: profile.boundaryProfile,
        clientId: `extension:${profile.id}`,
      });
      const result = response?.result;

      if (result?.outcome === OUTCOME.SERVED) {
        appendAssistantMessage(document.querySelector(messagesSel), result.text);
        if ("value" in input) input.value = "";
        return;
      }

      bypass = true;
      try {
        const send = document.querySelector(sendSel);
        const form = formSel ? document.querySelector(formSel) : null;
        if (form && typeof form.requestSubmit === "function") {
          form.requestSubmit(send || undefined);
        } else if (send) {
          send.click();
        } else if (form) {
          form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
        }
      } finally {
        bypass = false;
      }
    }

    const form = formSel ? document.querySelector(formSel) : null;
    const send = document.querySelector(sendSel);
    if (form) {
      form.addEventListener("submit", (event) => {
        void handleIntercept(event);
      }, true);
    }
    if (send) {
      send.addEventListener("click", (event) => {
        void handleIntercept(event);
      }, true);
    }
  }

  chrome.runtime
    .sendMessage({
      type: "daari.matchProfile",
      host: location.host,
      pathname: location.pathname,
    })
    .then((response) => {
      if (response?.ok && response.profile) {
        attach(response.profile);
      }
    })
    .catch(() => {
      /* extension context invalidated */
    });
})();

/** Daemon client + boundary refusal helpers (#171). */

export const DEFAULT_API_BASE = "http://127.0.0.1:11435";
export const API_BASE_KEY = "daari_extension.api_base_url";

export function normalizeApiBase(raw) {
  const value = (raw || "").trim().replace(/\/$/, "");
  return value || DEFAULT_API_BASE;
}

/**
 * @param {{
 *   prompt: string,
 *   apiBase?: string,
 *   boundaryProfile?: string,
 *   clientId?: string,
 *   fetchFn?: typeof fetch,
 * }} opts
 */
export async function requestDaariChat(opts) {
  const fetchFn = opts.fetchFn || fetch;
  const apiBase = normalizeApiBase(opts.apiBase);
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
    "X-Daari-Meta": "true",
  };
  if (opts.boundaryProfile) {
    headers["X-Daari-Boundary-Profile"] = opts.boundaryProfile;
  }
  if (opts.clientId) {
    headers["X-Daari-Client-Id"] = opts.clientId;
  }
  const response = await fetchFn(`${apiBase}/v1/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      model: "daari",
      temperature: 0.2,
      messages: [{ role: "user", content: opts.prompt }],
    }),
  });
  if (!response.ok) {
    const err = new Error(`${response.status} ${response.statusText}`);
    err.status = response.status;
    throw err;
  }
  return response.json();
}

/** Boundary block → fall through to the page backend. */
export function isBoundaryRefusal(payload) {
  const meta = payload?.daari_meta;
  if (!meta) return false;
  if (meta.tier === "boundary") return true;
  if (meta.warning === "boundary_blocked") return true;
  return false;
}

export function assistantText(payload) {
  return payload?.choices?.[0]?.message?.content || "";
}

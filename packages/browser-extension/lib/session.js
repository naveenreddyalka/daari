/** Session tier + estimated-savings accumulator (#171). */

export const SESSION_KEY = "daari_extension.session";

/** Rough frontier $/1k tokens used when the daemon does not report costs. */
export const FRONTIER_USD_PER_1K = 0.002;

export function emptySession() {
  return {
    requests: 0,
    localRequests: 0,
    fallbacks: 0,
    lastTier: null,
    estimatedSavedUsd: 0,
  };
}

export function estimateSavedUsd(meta) {
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

export function recordServe(session, meta) {
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

export function recordFallback(session) {
  return {
    ...session,
    fallbacks: (session.fallbacks || 0) + 1,
  };
}

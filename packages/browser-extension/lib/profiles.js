/** Site profiles for in-page chat interception (#171). */

export const PROFILES = [
  {
    id: "fintech-assist",
    name: "Fintech Assist demo",
    hosts: ["127.0.0.1:8765", "localhost:8765"],
    pathPrefix: "/",
    selectors: {
      input: "#daari-chat-input",
      send: "#daari-chat-send",
      form: "#daari-chat-form",
      messages: "#daari-chat-messages",
    },
    boundaryProfile: "fintech-assist",
    storeListingHosts: "http://127.0.0.1:8765 and http://localhost:8765 (local demo only)",
  },
  {
    id: "docs-support",
    name: "Docs Support demo",
    hosts: ["127.0.0.1:8766", "localhost:8766"],
    pathPrefix: "/",
    selectors: {
      input: "#support-prompt",
      send: "#support-submit",
      form: "#support-form",
      messages: "#support-thread",
    },
    boundaryProfile: "docs-support",
    storeListingHosts: "http://127.0.0.1:8766 and http://localhost:8766 (local demo only)",
  },
];

/**
 * @param {string} host host[:port]
 * @param {string} pathname
 * @param {typeof PROFILES} [profiles]
 */
export function matchProfile(host, pathname, profiles = PROFILES) {
  const path = pathname || "/";
  for (const profile of profiles) {
    if (!profile.hosts.includes(host)) continue;
    const prefix = profile.pathPrefix || "/";
    if (path === prefix || path.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`) || prefix === "/") {
      return profile;
    }
  }
  return null;
}

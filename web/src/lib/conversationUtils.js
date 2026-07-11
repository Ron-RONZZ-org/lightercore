/**
 * Shared conversation utility functions for semantika and lighterbird.
 *
 * Provides pure-JS helpers for formatting and copying conversation history.
 * No DOM or styling — these are data-transformation utilities shared via
 * the `@lightercore/ui` package.
 */

/**
 * Strip HTML tags from a string, returning plain text content.
 * @param {string} html
 * @returns {string}
 */
function stripHtml(html) {
  if (!html) return "";
  const div = document.createElement("div");
  div.innerHTML = html;
  return div.textContent || div.innerText || "";
}

/**
 * Format an array of conversation messages into a plain-text transcript.
 *
 * Each message is rendered as:
 *   [Role] Content
 *
 * Messages are separated by a blank line.
 *
 * @param {Array<{role:string, text?:string, html?:string}>} messages
 * @param {object} [opts]
 * @param {string} [opts.userLabel="You"]
 * @param {string} [opts.assistantLabel="Assistant"]
 * @returns {string}
 */
export function formatConversationText(messages, opts = {}) {
  const { userLabel = "You", assistantLabel = "Assistant" } = opts;
  return messages
    .filter((m) => m.role && (m.text || m.html))
    .map((m) => {
      const label = m.role === "user" ? userLabel : assistantLabel;
      const text = m.text || stripHtml(m.html || "");
      return `[${label}] ${text}`;
    })
    .join("\n\n");
}

/**
 * Copy text to clipboard. Uses `navigator.clipboard.writeText()` when
 * available, falling back to a temporary `<textarea>` + `execCommand("copy")`.
 *
 * @param {string} text
 * @returns {Promise<void>}
 */
export async function copyToClipboard(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}

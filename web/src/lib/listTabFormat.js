/**
 * Formatting utilities for list tabs.
 * Pure functions — no Svelte runes needed.
 */

/**
 * Format an ISO date string for display in a list.
 * - Today: shows time only
 * - This year: shows month + day
 * - Older: shows full date
 */
export function formatListItemDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 10);
    const now = new Date();
    const opts = d.toDateString() === now.toDateString()
      ? { hour: "2-digit", minute: "2-digit" }
      : d.getFullYear() === now.getFullYear()
        ? { month: "short", day: "numeric" }
        : { year: "numeric", month: "short", day: "numeric" };
    return d.toLocaleDateString([], opts);
  } catch {
    return iso.slice(0, 10);
  }
}

/**
 * Truncate a string with ellipsis if it exceeds max length.
 */
export function truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "\u2026" : s;
}

/**
 * Preview text: first line, stripped of markdown, truncated.
 */
export function preview(s, max = 60) {
  if (!s) return "";
  const firstLine = s.split("\n")[0].trim();
  return truncate(firstLine.replace(/[#*_~`>]/g, ""), max);
}

/**
 * Focus trap for modal dialogs.
 * Wraps Tab/Shift+Tab within the container's focusable elements.
 *
 * @param {() => HTMLElement} getContainer — callback returning the dialog root
 * @param {(e: KeyboardEvent) => void} [onKeydown] — optional extra handler
 * @returns {(e: KeyboardEvent) => void} keydown handler to mount on the overlay
 */
export function createDialogTrap(getContainer, onKeydown) {
  const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

  return function trapKeydown(e) {
    if (e.key === "Tab") {
      const container = getContainer();
      if (!container) return;
      const focusable = container.querySelectorAll(FOCUSABLE);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    if (onKeydown) onKeydown(e);
  };
}

/**
 * Sanitize a filename to only alphanumeric characters plus - and _.
 * Falls back to "export" if the result would be empty.
 *
 * @param {string} name — base name (without extension)
 * @param {string} [extension] — file extension including dot, e.g. ".md"
 * @param {number} [maxLen=64] — max length of the base part
 * @returns {string} sanitized filename with extension
 */
export function sanitizeFilename(name, extension = "", maxLen = 64) {
  if (!name) return `export${extension}`;
  const base = name.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, maxLen);
  return `${base || "export"}${extension}`;
}

/**
 * Extract a label from a labels dict preferring the given locale.
 * Falls back to English, then any available language, then the raw value.
 *
 * @param {string|object} labels - JSON string or object with locale keys
 * @param {string} [locale="en"] - Preferred locale code (e.g. "fr", "en-US")
 * @returns {string}
 */
export function getLabel(labels, locale) {
  if (!labels) return "";
  if (typeof labels === "string") {
    try { labels = JSON.parse(labels); } catch { return labels; }
  }
  if (!labels || typeof labels !== "object") return "";
  // Try exact locale match
  if (locale && labels[locale]) return labels[locale];
  // Try language-only prefix (e.g. "en" matches "en-US")
  if (locale && locale.length > 2) {
    const lang = locale.slice(0, 2);
    if (labels[lang]) return labels[lang];
  }
  // Fallback to English
  if (labels.en || labels["en"]) return labels.en || labels["en"];
  // Any language
  const keys = Object.keys(labels);
  return keys.length > 0 ? labels[keys[0]] : "";
}

/**
 * Strip prefix from an ID for compact display.
 * e.g. "http://example.org/Foo" -> "Foo", "ex:knows" -> "ex:knows"
 */
export function shortId(id) {
  if (!id) return "";
  const hashIdx = id.indexOf("#");
  if (hashIdx > 0 && hashIdx < id.length - 1) return id.slice(hashIdx + 1);
  const slashIdx = id.lastIndexOf("/");
  if (slashIdx > 0 && slashIdx < id.length - 1) return id.slice(slashIdx + 1);
  return id;
}

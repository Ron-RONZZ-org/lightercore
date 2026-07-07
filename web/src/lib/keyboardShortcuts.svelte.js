/**
 * Shared keyboard shortcut registry.
 *
 * Components declare their shortcuts here so they appear in the shortcut
 * overlay and can be queried programmatically. Actual keydown handling
 * remains in the individual component's handleKeydown (TabView, list tabs, etc.)
 *
 * Shortcut priority (handled by each component):
 *   1. INPUT/TEXTAREA focus — blocks all plain-key shortcuts
 *   2. Active tab local (selection mode, search, etc.)
 *   3. Global tab-level (Escape, h, i, q in TabView)
 *   4. Browser defaults
 *
 * Button text first-letter fallback:
 *   a = add, s = save, c = cancel, d = delete, etc.
 *   (Only active when no higher-priority shortcut exists)
 */

// ── Shortcut registry ──────────────────────────────────────────────────
// Keyed by scope (component name), each entry is a Map of key → descriptor.
/** @type {Map<string, Map<string, {key: string, desc: string, modifiers?: string}>>} */
const _registry = new Map();

/**
 * Register one or more shortcuts for a component scope.
 *
 * @param {string} scope   — component identifier (e.g. "NodeListTab", "TodoListTab")
 * @param {Array<{key: string, desc: string, modifiers?: string, category?: string}>} items
 */
export function registerShortcuts(scope, items) {
  let map = _registry.get(scope);
  if (!map) {
    map = new Map();
    _registry.set(scope, map);
  }
  for (const item of items) {
    map.set(item.key.toLowerCase(), item);
  }
}

/**
 * Get all registered shortcuts, grouped by scope category.
 * Returns a flat array suitable for rendering in KeyboardShortcutOverlay.
 *
 * @returns {Array<{category: string, keys: Array<{key: string, desc: string}>}>}
 */
export function getAllShortcuts() {
  /** @type {Map<string, Array<{key: string, desc: string}>>} */
  const groups = new Map();

  // Navigation (always present)
  groups.set("Navigation", [
    { key: "Alt + 1-9", desc: "Switch to tab by position" },
    { key: "Alt + N/P", desc: "Next / previous tab" },
    { key: "q / Esc", desc: "Close current tab" },
    { key: "i", desc: "Focus command input" },
  ]);

  // General (always present)
  groups.set("General", [
    { key: "h", desc: "Toggle help overlay" },
    { key: "!command", desc: "Run a command" },
  ]);

  // Scoped shortcuts
  for (const [, map] of _registry) {
    for (const [, shortcut] of map) {
      const category = shortcut.category || "Other";
      if (!groups.has(category)) {
        groups.set(category, []);
      }
      const keyLabel = shortcut.modifiers
        ? `${shortcut.modifiers} + ${shortcut.key}`
        : shortcut.key;
      groups.get(category).push({ key: keyLabel, desc: shortcut.desc });
    }
  }

  return [...groups].map(([category, keys]) => ({ category, keys }));
}

/**
 * Get shortcuts for a specific category/scope.
 *
 * @param {string} scope
 * @returns {Array<{key: string, desc: string, modifiers?: string}>}
 */
export function getScopeShortcuts(scope) {
  const map = _registry.get(scope);
  return map ? [...map.values()] : [];
}

/**
 * Normalize a key for shortcut matching (lowercase, strip shift).
 *
 * @param {string} key — event.key value
 * @returns {string}
 */
export function normalizeKey(key) {
  return key.toLowerCase();
}

/**
 * Check whether a key event should be processed (not from input/textarea).
 *
 * @param {KeyboardEvent} e
 * @returns {boolean} true if the event is from an inert element
 */
export function isInputFocused(e) {
  const tag = e.target?.tagName;
  return !!(tag === "INPUT" || tag === "TEXTAREA" || e.target?.isContentEditable);
}

/**
 * overlayStack — lightweight singleton stack of active overlays/popups.
 *
 * Many components (CowritePanel, ConfirmDialog, modals) render as overlays
 * inside a tab.  When the user presses Escape or Q, TabView's global handler
 * would close the tab — but it should close the **top-most overlay** first.
 *
 * Usage (in an overlay component, typically on mount/unmount):
 *
 *   import { overlayStack } from "@lightercore/ui/overlayStack.svelte.js";
 *
 *   $effect(() => {
 *     const entry = overlayStack.push("cowrite-panel", () => cowrite.close());
 *     return () => overlayStack.remove(entry.id);
 *   });
 *
 * TabView's ESC handler then checks:
 *
 *   if (overlayStack.top) {
 *     overlayStack.top.close();  // calls the registered close callback
 *     return;                    // don't close the tab
 *   }
 *
 * See also:
 *   - ConfirmDialog, CowritePanel for consumer examples
 */

// ── State ──────────────────────────────────────────────────────────────

let _nextId = 1;

/**
 * @typedef {Object} OverlayEntry
 * @property {number} id
 * @property {string} name — descriptive name for debugging
 * @property {() => void} close — callback invoked when overlay should close
 */

/** @type {OverlayEntry[]} */
let _stack = $state([]);

// ── Derived signals (export them through getters — see tabStore for rationale) ──

const _top = $derived(_stack.length > 0 ? _stack[_stack.length - 1] : null);
const _count = $derived(_stack.length);

// ── Helpers ────────────────────────────────────────────────────────────

/**
 * Push a new overlay onto the stack.
 *
 * @param {string} name — descriptive label (e.g. "cowrite-panel", "confirm-dialog")
 * @param {() => void} close — callback that closes/dismisses this overlay
 * @returns {OverlayEntry} — the newly created entry (store the ``id`` to pass to ``remove()``)
 */
function push(name, close) {
  const entry = { id: _nextId++, name, close };
  _stack = [..._stack, entry];
  return entry;
}

/**
 * Remove an overlay entry by id (typically called on unmount).
 *
 * @param {number} id
 */
function remove(id) {
  _stack = _stack.filter((e) => e.id !== id);
}

/**
 * Pop (remove and return) the top-most overlay entry.
 * If the entry's ``id`` does not match *expectedId*, the stack is inconsistent
 * and nothing is removed (a defensive guard).
 *
 * @param {number} [expectedId] — if given, only pops if the top entry has this id
 * @returns {OverlayEntry|null}
 */
function pop(expectedId) {
  if (_stack.length === 0) return null;
  const top = _stack[_stack.length - 1];
  if (expectedId !== undefined && top.id !== expectedId) return null;
  _stack = _stack.slice(0, -1);
  return top;
}

/**
 * Check whether an overlay with *name* is currently on the stack.
 *
 * @param {string} name
 * @returns {boolean}
 */
function has(name) {
  return _stack.some((e) => e.name === name);
}

/**
 * Find the first overlay entry matching *name*.
 *
 * @param {string} name
 * @returns {OverlayEntry|undefined}
 */
function find(name) {
  return _stack.find((e) => e.name === name);
}

/** Remove all overlays from the stack. */
function clear() {
  _stack = [];
}

// ── Exported singleton ─────────────────────────────────────────────────

export const overlayStack = {
  /** @returns {OverlayEntry|null} — the top-most overlay, or null if stack is empty */
  get top() { return _top; },
  /** @returns {number} — number of active overlays */
  get count() { return _count; },
  /** @returns {OverlayEntry[]} — full stack (for debugging) */
  get entries() { return _stack; },
  push,
  remove,
  pop,
  has,
  find,
  clear,
};

/**
 * Highlight utility — scroll-and-flash animation for list rows.
 *
 * Provides a reactive manager (``createHighlightManager``) for Svelte
 * components and a pure DOM function (``applyHighlight``) for testing.
 *
 * Usage:
 *   import { createHighlightManager } from "@lightercore/ui/highlight.svelte.js";
 *
 *   // In a Svelte component:
 *   let { data = [], something = $state([]) } = $props();
 *   createHighlightManager({
 *     getData: () => data,
 *     getItems: () => something,
 *     idField: 'node_id',
 *     rowPrefix: 'row-',
 *   });
 *
 * CSS (add to component's <style>):
 *   .hc-highlight-flash { animation: hc-pulse 2s ease-out; }
 *   @keyframes hc-pulse { 0%, 100% { background-color: transparent; } 30% { background-color: rgba(60, 180, 75, 0.25); } }
 */

/** CSS class added to the highlighted row during animation. */
export const HIGHLIGHT_CLASS = "hc-highlight-flash";

/**
 * Pure DOM function: scroll a row into view and flash it.
 *
 * @param {string} highlightId  The entity ID to highlight (e.g. ``"HAMLET_QUOTE_1"``).
 * @param {Array<object>} items  The current list of items to verify the ID exists.
 * @param {object} [opts]
 * @param {string} [opts.idField="id"]  Item field containing the ID.
 * @param {string} [opts.rowPrefix="row-"]  DOM id prefix for rows.
 * @param {number} [opts.duration=2000]  Animation duration in ms.
 * @returns {boolean}  ``true`` if the element was found and animated, ``false`` otherwise.
 */
export function applyHighlight(highlightId, items, { idField = "id", rowPrefix = "row-", duration = 2000 } = {}) {
  if (!highlightId || !items?.length) return false;
  const exists = items.some((item) => item[idField] === highlightId);
  if (!exists) return false;
  const el = document.getElementById(`${rowPrefix}${CSS.escape(highlightId)}`);
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add(HIGHLIGHT_CLASS);
  setTimeout(() => el.classList.remove(HIGHLIGHT_CLASS), duration);
  return true;
}

/**
 * Reactive manager — wraps ``applyHighlight`` in a ``$effect``.
 *
 * Call once per component.  The ``$effect`` watches both ``getData()``
 * (to detect ``_highlight`` from the data prop) and ``getItems()``
 * (to wait until items have loaded).
 *
 * @param {object} opts
 * @param {() => any} opts.getData  Returns the component's data prop.
 * @param {() => Array<object>} opts.getItems  Returns the component's loaded items.
 * @param {string} [opts.idField="id"]  Item field containing the ID.
 * @param {string} [opts.rowPrefix="row-"]  DOM id prefix for rows.
 */
export function createHighlightManager({ getData, getItems, idField = "id", rowPrefix = "row-" } = {}) {
  let consumed = $state(false);

  $effect(() => {
    const d = getData();
    const h = d?._highlight;
    if (!h || consumed) return;
    const items = getItems();
    const ok = applyHighlight(h, items, { idField, rowPrefix });
    if (ok) consumed = true;
  });
}

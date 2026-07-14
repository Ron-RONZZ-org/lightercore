/**
 * List sort/filter state management — reusable across list tabs.
 *
 * Provides reactive sort state (sort column + direction toggle) and
 * filter state (visibility toggles for item categories).
 *
 * Usage:
 * ```js
 *   import { createSortState, createFilterState } from "./listSort.svelte.js";
 *
 *   let sort = createSortState(["created_at", "node_id"]);
 *   let filter = createFilterState(["concept", "photo", "video"]);
 *
 *   // Derive sorted/filtered list:
 *   let displayItems = $derived(
 *     filter.apply(items).toSorted(sort.comparator)
 *   );
 * ```
 */

/**
 * Available sort modes for list tabs.
 * Each entry: { column, label, direction, icon }
 */
export const SORT_MODES = [
  { column: "created_at", label: "Date created", direction: "desc", icon: "↓" },
  { column: "created_at", label: "Date created", direction: "asc", icon: "↑" },
  { column: "node_id",    label: "Alphabetical", direction: "asc", icon: "A" },
  { column: "node_id",    label: "Alphabetical", direction: "desc", icon: "Z" },
];

/**
 * Create reactive sort state that cycles through sort modes.
 *
 * @param {string} initialColumn - Starting sort column (default "created_at")
 * @param {string} initialDirection - Starting direction (default "desc")
 * @returns {{ readonly mode: object, cycle: () => void, comparator: (a, b) => number }}
 */
export function createSortState(initialColumn = "created_at", initialDirection = "desc") {
  let currentIndex = $state(
    SORT_MODES.findIndex(
      (m) => m.column === initialColumn && m.direction === initialDirection,
    ) || 0,
  );

  /** Current sort mode object. */
  let mode = $derived(SORT_MODES[currentIndex]);

  /** Cycle to the next sort mode. */
  function cycle() {
    currentIndex = (currentIndex + 1) % SORT_MODES.length;
  }

  /**
   * Comparator function for `Array.toSorted()`.
   * Sorts by the current mode's column and direction.
   */
  function comparator(a, b) {
    const col = mode.column;
    let valA, valB;
    if (col === "node_id") {
      valA = (a.node_id || "").toLowerCase();
      valB = (b.node_id || "").toLowerCase();
    } else if (col === "created_at") {
      valA = a.created_at || "";
      valB = b.created_at || "";
    } else {
      valA = String(a[col] ?? "");
      valB = String(b[col] ?? "");
    }
    const cmp = valA < valB ? -1 : valA > valB ? 1 : 0;
    return mode.direction === "desc" ? -cmp : cmp;
  }

  return {
    get mode() { return mode; },
    cycle,
    comparator,
  };
}

/**
 * Filter state for node types — controls which categories are visible.
 *
 * @param {string[]} defaultCategories - All category names (default all visible).
 * @returns {{ visible: Set<string>, toggle: (cat: string) => void, setAll: (visible: boolean) => void, isVisible: (cat: string) => boolean }}
 */
export function createFilterState(defaultCategories = []) {
  let visibleSet = $state(new Set(defaultCategories));

  function toggle(category) {
    const next = new Set(visibleSet);
    if (next.has(category)) {
      next.delete(category);
    } else {
      next.add(category);
    }
    visibleSet = next;
  }

  function setAll(visible) {
    visibleSet = new Set(visible ? defaultCategories : []);
  }

  function isVisible(category) {
    return visibleSet.has(category);
  }

  return {
    get visible() { return visibleSet; },
    toggle,
    setAll,
    isVisible,
  };
}

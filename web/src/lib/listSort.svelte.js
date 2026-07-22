/**
 * List sort/filter state management — reusable across list tabs.
 *
 * Supports two interaction patterns:
 *
 * **Mode cycling** (semantika-style): cycle through predefined sort modes
 * (column + direction pairs) via ``cycle()``.
 *
 * **Column toggle** (ronzzdoi-style): click any column header to sort by
 * that column; click again to toggle direction via ``toggleColumn(col)``.
 *
 * The two patterns share the same ``comparator`` — derived lists in either
 * pattern use ``items.toSorted(sort.comparator)``.
 *
 * Usage:
 * ```js
 *   import { createSortState, createFilterState } from "./listSort.svelte.js";
 *
 *   // Mode-cycling (default):
 *   let sort = createSortState();
 *   sort.cycle();
 *   let displayItems = $derived(items.toSorted(sort.comparator));
 *
 *   // Column-toggle:
 *   let sort2 = createSortState();
 *   sort2.toggleColumn("target_url");
 *   let displayItems2 = $derived(items.toSorted(sort2.comparator));
 * ```
 */

/**
 * Default sort modes for the mode-cycling pattern.
 * Each entry: { column, label, direction, icon }
 */
export const SORT_MODES = [
  { column: "created_at", label: "Date created", direction: "desc", icon: "↓" },
  { column: "created_at", label: "Date created", direction: "asc", icon: "↑" },
  { column: "node_id",    label: "Alphabetical", direction: "asc", icon: "A" },
  { column: "node_id",    label: "Alphabetical", direction: "desc", icon: "Z" },
];

/**
 * Create reactive sort state.
 *
 * @param {string} initialColumn - Starting sort column (default "created_at")
 * @param {string} initialDirection - Starting direction (default "desc")
 * @returns {{
 *   readonly mode: { column: string, label: string, direction: string, icon: string },
 *   cycle: () => void,
 *   toggleColumn: (col: string) => void,
 *   comparator: (a: any, b: any) => number,
 * }}
 */
export function createSortState(initialColumn = "created_at", initialDirection = "desc") {
  // Internal column + direction — used directly by toggleColumn, derived into
  // mode for cycle() callers.
  let _column = $state(initialColumn);
  let _direction = $state(initialDirection);
  let _currentIndex = $state(
    SORT_MODES.findIndex(
      (m) => m.column === _column && m.direction === _direction,
    ) || 0,
  );

  /**
   * Current mode — derived from the active column/direction.
   * When the state matches one of the predefined SORT_MODES, that entry is
   * returned (so cycle()-based callers get the correct label/icon). For
   * dynamic columns set via toggleColumn, a synthetic mode is returned.
   */
  let mode = $derived.by(() => {
    const match = SORT_MODES.find(
      (m) => m.column === _column && m.direction === _direction,
    );
    if (match) return match;
    return {
      column: _column,
      label: _column.replace(/_/g, " "),
      direction: _direction,
      icon: _direction === "asc" ? "↑" : "↓",
    };
  });

  /** Cycle to the next predefined sort mode. */
  function cycle() {
    const next = (_currentIndex + 1) % SORT_MODES.length;
    _currentIndex = next;
    _column = SORT_MODES[next].column;
    _direction = SORT_MODES[next].direction;
  }

  /**
   * Sort by *column*: first click sorts ascending, second click toggles direction.
   * This is the column-header-click pattern — unlike cycle(), it lets the caller
   * pick any column name at runtime (dynamic columns).
   */
  function toggleColumn(col) {
    if (_column === col) {
      _direction = _direction === "asc" ? "desc" : "asc";
    } else {
      _column = col;
      _direction = "asc";
    }
    // Keep cycle index in sync for callers that mix both patterns
    const matchIdx = SORT_MODES.findIndex(
      (m) => m.column === _column && m.direction === _direction,
    );
    if (matchIdx >= 0) _currentIndex = matchIdx;
  }

  /**
   * Comparator function for `Array.toSorted()`.
   * Generic — handles any column, not just predefined modes.
   * Compares locale-aware for strings, numeric for numbers.
   */
  function comparator(a, b) {
    const col = _column;
    const valA = a[col];
    const valB = b[col];
    let cmp;
    if (typeof valA === "number" && typeof valB === "number") {
      cmp = valA - valB;
    } else {
      cmp = String(valA ?? "").localeCompare(String(valB ?? ""));
    }
    return _direction === "desc" ? -cmp : cmp;
  }

  return {
    get mode() { return mode; },
    cycle,
    toggleColumn,
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

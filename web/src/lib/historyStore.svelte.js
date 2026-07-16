/**
 * `createHistory` — generic undo/redo state management.
 *
 * Follows the factory pattern established by `createSelectionManager`,
 * `createCopyState`, and `createFormGuard`.
 *
 * Usage:
 * ```js
 *   let hist = createHistory(initialRecords);
 *
 *   // Push a new state snapshot (saves current for undo)
 *   hist.push([...hist.records, newItem]);
 *
 *   // Undo/redo
 *   hist.undo();  // returns true if undone
 *   hist.redo();  // returns true if redone
 *
 *   // Reactively watch
 *   $effect(() => { console.log(hist.records); });
 * ```
 *
 * @param {Array} initialRecords — Initial array of records
 * @returns {{ records: Array, push: (r: Array) => void, undo: () => boolean,
 *             redo: () => boolean, canUndo: boolean, canRedo: boolean,
 *             reset: (r: Array) => void }}
 */
export function createHistory(initialRecords = []) {
  let records = $state([...initialRecords]);
  let undoStack = $state([]);
  let redoStack = $state([]);

  function snapshot() {
    return JSON.parse(JSON.stringify(records));
  }

  function push(newRecords) {
    undoStack = [...undoStack, snapshot()];
    records = [...newRecords];
    redoStack = []; // new action invalidates redo
  }

  function undo() {
    if (undoStack.length === 0) return false;
    redoStack = [...redoStack, snapshot()];
    records = undoStack[undoStack.length - 1];
    undoStack = undoStack.slice(0, -1);
    return true;
  }

  function redo() {
    if (redoStack.length === 0) return false;
    undoStack = [...undoStack, snapshot()];
    records = redoStack[redoStack.length - 1];
    redoStack = redoStack.slice(0, -1);
    return true;
  }

  function reset(newRecords) {
    records = [...newRecords];
    undoStack = [];
    redoStack = [];
  }

  return {
    get records() { return records; },
    push,
    undo,
    redo,
    reset,
    get canUndo() { return undoStack.length > 0; },
    get canRedo() { return redoStack.length > 0; },
  };
}

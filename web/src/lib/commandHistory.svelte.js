/**
 * Reactive command history factory — module-level $state with localStorage persistence.
 *
 * Creates a singleton history store that persists up to 100 entries to
 * localStorage.  Up/Down arrow recall works across page refreshes.
 *
 * Usage:
 *   ```js
 *   import { createCommandHistory } from "@lightercore/ui/commandHistory.svelte.js";
 *   export const history = createCommandHistory("myapp:commandHistory");
 *
 *   history.push("!email list");
 *   const prev = history.back();    // up arrow
 *   const next = history.forward(); // down arrow
 *   ```
 *
 * @param {string} [lsKey="lightercore:commandHistory"] — localStorage key
 * @returns {{ entries: string[], index: number, push: Function, back: Function, forward: Function, reset: Function }}
 */
export function createCommandHistory(lsKey = "lightercore:commandHistory") {
  /** Load persisted entries from localStorage. */
  function _load() {
    try {
      const raw = localStorage.getItem(lsKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed.slice(0, 100);
      }
    } catch {
      // localStorage unavailable or corrupt — start fresh
    }
    return [];
  }

  /** Save entries to localStorage. */
  function _save(entries) {
    try {
      localStorage.setItem(lsKey, JSON.stringify(entries));
    } catch {
      // localStorage full or unavailable — silently fail
    }
  }

  let _entries = $state(_load());
  let _index = $state(-1);

  return {
    /** @returns {string[]} */
    get entries() {
      return _entries;
    },

    /** @returns {number} */
    get index() {
      return _index;
    },

    /** Add a command to history (persisted). */
    push(cmd) {
      if (!cmd.trim()) return;
      // Avoid duplicating the identical command at the top
      if (_entries.length > 0 && _entries[0] === cmd) {
        _index = -1;
        return;
      }
      _entries = [cmd, ..._entries].slice(0, 100);
      _index = -1;
      _save(_entries);
    },

    /** Navigate back in history. Returns the command string. */
    back() {
      if (_entries.length === 0) return "";
      _index = Math.min(_entries.length - 1, _index + 1);
      return _entries[_index];
    },

    /** Navigate forward in history. Returns the command string. */
    forward() {
      if (_index <= 0) {
        _index = -1;
        return "";
      }
      _index -= 1;
      return _entries[_index];
    },

    /** Reset navigation index. */
    reset() {
      _index = -1;
    },
  };
}

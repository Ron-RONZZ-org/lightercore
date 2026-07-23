/** Reactive tab store — manages multiple open tabs, with pinned home tab. */

const HOME_TAB = {
  id: "home",
  type: "home",
  title: "Home",
  data: null,
  idKey: "home",
  closable: false,
  pinned: true,
};

let _tabs = $state([HOME_TAB]);
let _activeId = $state(HOME_TAB.id);
let _nextId = 1;

// ── Derived signals for computed properties ────────────────────────────
// These MUST be $derived (not plain getters) so that Svelte 5's runtime
// signal tracking properly propagates changes through the exported
// ``tabStore`` object's getter chain to subscribing components.
// See lighterbird PR #197 for the full analysis.
const _active = $derived.by(
  () => _tabs.find((t) => t.id === _activeId) || HOME_TAB,
);
const _activeIndex = $derived.by(
  () => _tabs.findIndex((t) => t.id === _activeId),
);
const _count = $derived(_tabs.length);
const _isHome = $derived(_activeId === HOME_TAB.id);

function genId() {
  return `tab-${_nextId++}-${Date.now()}`;
}

/** Blur the input field when switching away from home, so the first
 *  Escape press closes the active tab instead of being trapped by a
 *  hidden-but-focused textarea. */
function _blurInputOnTabSwitch(newActiveId) {
  if (newActiveId === HOME_TAB.id) return;
  requestAnimationFrame(() => {
    const el = document.querySelector(".input-field");
    if (el && el === document.activeElement) el.blur();
  });
}

/** Focus the input after switching back to the Home tab. */
function _refocusInput() {
  requestAnimationFrame(() => {
    const el = document.querySelector(".input-field");
    if (el) el.focus();
  });
}

export const tabStore = {
  get tabs() {
    return _tabs;
  },

  get active() {
    return _active;
  },

  get activeIndex() {
    return _activeIndex;
  },

  get count() {
    return _count;
  },

  /**
   * Open a new result tab.
   *
   * @param {string} type
   * @param {string} title
   * @param {any} data
   * @param {object} [opts]
   * @param {string} [opts.idKey] — dedup key
   * @param {boolean} [opts.closable=true]
   */
  open(type, title, data, opts = {}) {
    const { idKey, closable = true } = opts;

    // Dedup by idKey
    if (idKey) {
      const existing = _tabs.find((t) => t.idKey === idKey && t.id !== HOME_TAB.id);
      if (existing) {
        _activeId = existing.id;
        _tabs = _tabs.map((t) => (t.id === existing.id ? { ...t, title, data } : t));
        _blurInputOnTabSwitch(_activeId);
        return existing.id;
      }
    }

    const tab = {
      id: genId(),
      type,
      title,
      data,
      idKey: idKey || null,
      closable,
      pinned: false,
    };

    // Insert the new tab immediately after the currently active tab
    const activeIdx = _tabs.findIndex((t) => t.id === _activeId);
    if (activeIdx >= 0) {
      _tabs = [..._tabs.slice(0, activeIdx + 1), tab, ..._tabs.slice(activeIdx + 1)];
    } else {
      _tabs = [..._tabs, tab];
    }
    _activeId = tab.id;
    _blurInputOnTabSwitch(_activeId);
    return tab.id;
  },

  close(id) {
    if (id === HOME_TAB.id) return; // home tab never closes
    const idx = _tabs.findIndex((t) => t.id === id);
    if (idx === -1) return;

    const newTabs = _tabs.filter((t) => t.id !== id);
    _tabs = newTabs;

    if (id === _activeId) {
      // Activate the nearest tab, preferring home (index 0)
      _activeId = newTabs.length > 0 ? newTabs[Math.min(idx, newTabs.length - 1)].id : HOME_TAB.id;
      if (_activeId === HOME_TAB.id) _refocusInput();
    }
  },

  setActive(id) {
    if (_tabs.find((t) => t.id === id)) _activeId = id;
  },

  setActiveIndex(index) {
    if (index >= 0 && index < _tabs.length) {
      _activeId = _tabs[index].id;
    }
  },

  update(id, data, title, idKey) {
    _tabs = _tabs.map((t) =>
      t.id === id
        ? { ...t, data, ...(title !== undefined ? { title } : {}), ...(idKey !== undefined ? { idKey } : {}) }
        : t,
    );
  },

  /**
   * Find a tab's ID by its idKey.
   * Returns the tab's id (string) if found, or null if no tab has that key.
   * Useful for async callbacks (search, refresh, paginate) that need to
   * update a specific list tab regardless of which tab is currently active.
   */
  findByKey(idKey) {
    const tab = _tabs.find((t) => t.idKey === idKey && t.id !== HOME_TAB.id);
    return tab ? tab.id : null;
  },

  /**
   * Safe update — guards against stale tab references.
   * Only updates if the tab still exists (user may have closed the tab
   * during an async operation).
   */
  safeUpdate(id, data, title) {
    if (_tabs.find((t) => t.id === id)) {
      _tabs = _tabs.map((t) =>
        t.id === id ? { ...t, data, ...(title !== undefined ? { title } : {}) } : t,
      );
    }
  },

  closeAll() {
    _tabs = [HOME_TAB];
    _activeId = HOME_TAB.id;
    _refocusInput();
  },

  goHome() {
    _activeId = HOME_TAB.id;
    _refocusInput();
  },

  /** @returns {boolean} true if the home tab is currently active */
  get isHome() {
    return _isHome;
  },
};

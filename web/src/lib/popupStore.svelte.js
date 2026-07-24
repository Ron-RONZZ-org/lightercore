/**
 * Generic popup store — manages result tabs and a key-value data cache.
 *
 * Centralises shared popup logic that was previously duplicated across
 * lighterbird and semantika. Each project re-exports the ``popup`` object
 * and uses ``updateCache(data)`` with its domain-specific cache keys.
 *
 * Cache:
 *   A flat ``$state`` object whose keys are set dynamically by
 *   ``updateCache()``.  Each project calls:
 *
 *     popup.updateCache({ accounts: [...], contacts: [...], ... })   // lighterbird
 *     popup.updateCache({ nodes: [...], predicates: [...], ... })    // semantika
 *
 *   Consumers read keys directly: ``popup.cache.accounts`` etc.
 *   The ``$derived`` wrapper ensures Svelte 5's runtime tracks reads
 *   through the plain-object getter chain.
 *
 * See also:
 *   - tabStore for the underlying tab lifecycle
 *   - UuidPicker / CommandBar for cache-consuming components
 */

import { tabStore } from "./tabStore.svelte.js";

// ── State ──────────────────────────────────────────────────────────────

let _dataCache = $state({});
let _persistentDataType = $state(null);

// ── Derived signals for reactive export through getters ────────────────

const _cache = $derived(_dataCache);
const _persistentType = $derived(_persistentDataType);

// ── Helpers ────────────────────────────────────────────────────────────

function _cacheData(data) {
  if (!data) return;
  for (const key of Object.keys(data)) {
    const value = data[key];
    if (value !== undefined) {
      _dataCache[key] = value;
    }
  }
}

function _closeLoadingTabs() {
  const ids = tabStore.tabs
    .filter((t) => t.type === "loading")
    .map((t) => t.id);
  for (const id of ids) {
    tabStore.close(id);
  }
}

// ── Exported API ──────────────────────────────────────────────────────

export const popup = {
  /** @returns {object} — the data cache (read properties directly, e.g. ``popup.cache.accounts``) */
  get cache() {
    return _cache;
  },

  /** @returns {string|null} — the persistent data type set by the last ``showPersistent`` call */
  get persistentDataType() {
    return _persistentType;
  },

  /**
   * Backward-compat: return the active non-home tab if any, else ``null``.
   * Delegates to ``tabStore.active``.
   */
  get current() {
    const a = tabStore.active;
    if (a && a.type !== "home") return a;
    return null;
  },

  /**
   * Show a one-off result tab.
   *
   * @param {string} type — tab type (e.g. "status", "email", "error")
   * @param {string} title — tab title
   * @param {any} data — tab data
   */
  show(type, title, data) {
    _closeLoadingTabs();
    const idKey =
      type.endsWith("-list")
        ? type
        : type === "email"
          ? `email-${data?.uuid}`
          : null;
    tabStore.open(type, title, data, { idKey });
    _persistentDataType = null;
    _cacheData(data);
  },

  /**
   * Open (or update) a persistent list tab keyed by *dataType*.
   *
   * @param {string} type — tab type
   * @param {string} title — tab title
   * @param {any} data — tab data
   * @param {string} dataType — persistent idKey suffix (e.g. "email-list")
   */
  showPersistent(type, title, data, dataType) {
    _closeLoadingTabs();
    tabStore.open(type, title, data, { idKey: `persistent-${dataType}` });
    _persistentDataType = dataType;
    _cacheData(data);
  },

  /**
   * Update the data of the currently active persistent tab.
   * Falls back to a no-op if there is no active tab.
   */
  updatePersistent(data) {
    const active = tabStore.active;
    if (active) {
      tabStore.update(active.id, data);
    }
    _cacheData(data);
  },

  /**
   * Show a non-closable loading tab.
   * @param {string} title — loading message
   */
  showLoading(title) {
    tabStore.open("loading", title, null, { closable: true });
  },

  /** Close the active result tab (if closable). */
  close() {
    const active = tabStore.active;
    if (active && active.closable) {
      tabStore.close(active.id);
    }
    _persistentDataType = null;
  },

  /**
   * Merge *data* into the in-memory cache without opening a tab.
   * Each key in *data* replaces the cached value for that key.
   */
  updateCache(data) {
    _cacheData(data);
  },
};

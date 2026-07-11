/**
 * Banner store — lightweight notification banners.
 *
 * Supports both transient (auto-dismiss) and persistent (manual dismiss) banners.
 *
 * Usage:
 *   import { banner } from "@lightercore/ui/bannerStore.svelte.js";
 *   banner.show("Email sent", "success");           // shows for 3s then auto-dismisses
 *   banner.show("Something failed", "error", 5000); // 5s timeout
 *   banner.show("Server offline", "warning", 0);    // persistent until dismiss()
 *
 * The BannerContainer component (mounted in App.svelte) renders the active banner.
 */

const DEFAULT_DURATION = 3000;

let _message = $state("");
let _type = $state("success"); // "success" | "error" | "info" | "warning"
let _visible = $state(false);
let _persistent = $state(false);
let _timer = null;

// ── Derived signals for reactive export through getters ────────────────
// $derived ensures Svelte 5's runtime properly tracks signal reads through
// the exported plain-object getter chain. Without this, components reading
// ``banner.message`` etc. in reactive contexts ($derived, $effect, template)
// may not re-render when the underlying $state changes.
const _messageDerived = $derived(_message);
const _typeDerived = $derived(_type);
const _visibleDerived = $derived(_visible);
const _persistentDerived = $derived(_persistent);

function _clearTimer() {
  if (_timer) {
    clearTimeout(_timer);
    _timer = null;
  }
}

export const banner = {
  get message() { return _messageDerived; },
  get type() { return _typeDerived; },
  get visible() { return _visibleDerived; },
  get persistent() { return _persistentDerived; },

  /**
   * Show a banner notification.
   *
   * @param {string} message — text to display
   * @param {"success"|"error"|"info"|"warning"} type — visual style
   * @param {number} [duration=3000] — milliseconds before auto-dismiss (0 = persistent)
   */
  show(message, type = "success", duration = DEFAULT_DURATION) {
    _clearTimer();
    _message = message;
    _type = type;
    _visible = true;
    _persistent = duration === 0;
    if (duration > 0) {
      _timer = setTimeout(() => {
        _visible = false;
        _message = "";
        _persistent = false;
      }, duration);
    }
  },

  /** Dismiss the current banner immediately. */
  dismiss() {
    _clearTimer();
    _visible = false;
    _message = "";
    _persistent = false;
  },
};

/**
 * Banner store — lightweight temporary notification banners.
 *
 * Usage:
 *   import { banner } from "@lightercore/ui/bannerStore.svelte.js";
 *   banner.show("Email sent", "success");  // shows for 3s then auto-dismisses
 *   banner.show("Something failed", "error", 5000);  // 5s timeout
 *
 * The BannerContainer component (mounted in App.svelte) renders the active banner.
 */

const DEFAULT_DURATION = 3000;

let _message = $state("");
let _type = $state("success"); // "success" | "error" | "info"
let _visible = $state(false);
let _timer = null;

function _clearTimer() {
  if (_timer) {
    clearTimeout(_timer);
    _timer = null;
  }
}

export const banner = {
  get message() { return _message; },
  get type() { return _type; },
  get visible() { return _visible; },

  /**
   * Show a temporary banner notification.
   *
   * @param {string} message — text to display
   * @param {"success"|"error"|"info"} type — visual style
   * @param {number} [duration=3000] — milliseconds before auto-dismiss
   */
  show(message, type = "success", duration = DEFAULT_DURATION) {
    _clearTimer();
    _message = message;
    _type = type;
    _visible = true;
    _timer = setTimeout(() => {
      _visible = false;
      _message = "";
    }, duration);
  },

  /** Dismiss the current banner immediately. */
  dismiss() {
    _clearTimer();
    _visible = false;
    _message = "";
  },
};

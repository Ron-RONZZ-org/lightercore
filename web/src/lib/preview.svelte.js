/**
 * Preview utility — shared logic for rendering content previews.
 *
 * Provides a reactive store-free helper for content preview across
 * ComposeEmail, JournalWrite, LetterBodyEditor, and DynamicForm.
 *
 * Usage:
 *   import { showPreviewInTab, createPreviewState, PREVIEW_CSS } from "@lightercore/ui/preview.svelte.js";
 *
 *   // Open rendered content in a new browser tab:
 *   await showPreviewInTab(content, format);
 *
 *   // Reactive state for PreviewDialog:
 *   let preview = createPreviewState();
 *   preview.show(content, format);  // sets preview.showing = true + data
 */

/** Default preview CSS — matches LetterBodyEditor's new-tab style */
export const PREVIEW_CSS = `body{font-family:Georgia,"Times New Roman",serif;padding:2em;line-height:1.6;color:#000;background:#fff;max-width:21cm;margin:0 auto;}img{max-width:100%;}pre{background:#f5f5f5;padding:1em;overflow-x:auto;}code{background:#f0f0f0;padding:0.15em 0.3em;border-radius:3px;}pre code{background:none;padding:0;}table{border-collapse:collapse;width:100%;}td,th{border:1px solid #ccc;padding:0.4em;}th{background:#f0f0f0;}blockquote{border-left:3px solid #ccc;margin-left:0;padding-left:1em;color:#555;}`;

/**
 * Fetch rendered HTML from the backend and open in a new tab.
 * Falls back to the shared preview URL.
 */
export async function showPreviewInTab(content, format = "markdown") {
  if (!content || !content.trim()) return;
  try {
    const resp = await fetch("/api/v1/render-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, format }),
    });
    if (resp.ok) {
      const data = await resp.json();
      const html = data.html || "<p>(empty)</p>";
      const win = window.open("", "_blank");
      if (win) {
        win.document.write(
          '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
          + '<title>Preview</title>'
          + `<style>${PREVIEW_CSS}</style>`
          + '</head><body>'
          + html
          + '</body></html>'
        );
        win.document.close();
      }
    } else {
      alert("Preview unavailable");
    }
  } catch {
    alert("Preview unavailable");
  }
}

/**
 * Create reactive preview state for use with PreviewDialog.
 *
 * Returns:
 *   { showing, htmlContent, title, show(content, format, title?), close() }
 *
 * In a .svelte.js module, these are not runes (they're regular JS),
 * so the caller binds the state to their component.
 */
export function createPreviewState() {
  let _showing = $state(false);
  let _htmlContent = $state("");
  let _title = $state("Preview");

  return {
    get showing() { return _showing; },
    get htmlContent() { return _htmlContent; },
    get title() { return _title; },
    async show(content, format = "markdown", title = "Preview") {
      if (!content || !content.trim()) return;
      _title = title;
      try {
        const resp = await fetch("/api/v1/render-preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content, format }),
        });
        if (resp.ok) {
          const data = await resp.json();
          _htmlContent = data.html || "<p>(empty)</p>";
          _showing = true;
        } else {
          _htmlContent = `<p class="error">Preview unavailable (${resp.status})</p>`;
          _showing = true;
        }
      } catch (e) {
        _htmlContent = `<p class="error">Preview unavailable: ${e.message}</p>`;
        _showing = true;
      }
    },
    close() {
      _showing = false;
      _htmlContent = "";
    },
  };
}

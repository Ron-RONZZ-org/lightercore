<script>
  /**
   * CowriteButton — toolbar button that opens the co-writing panel.
   * Place this in each form's toolbar area.
   */

  /** @type {import("./CowriteEngine.svelte.js").ReturnType<typeof import("./CowriteEngine.svelte.js").createCowrite>} */
  let { cowrite } = $props();
</script>

<button
  type="button"
  class="cowrite-btn"
  class:active={cowrite.isActive}
  onclick={() => { if (!cowrite.isActive) cowrite.openPanel(); else cowrite.close(); }}
  title="Ask LLM to help write or edit this content"
>
  <span class="cowrite-icon">✨</span>
  <span class="cowrite-label">Ask LLM</span>
</button>

<style>
  .cowrite-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    background: transparent;
    border: 1px solid #444;
    border-radius: 4px;
    color: #b0b0c0;
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.1s, color 0.1s, border-color 0.1s;
    white-space: nowrap;
  }
  .cowrite-btn:hover {
    background: #2a2a44;
    color: #e0e0e0;
  }
  .cowrite-btn.active {
    background: #2a3a2a;
    color: #7fdb7f;
    border-color: #3a6a3a;
  }
  .cowrite-icon {
    font-size: 0.85rem;
  }
</style>

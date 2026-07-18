<script>
  /**
   * CowritePanel — slide-in overlay displaying LLM-proposed edits
   * with Accept/Reject controls and inline diff visualization.
   */

  import { overlayStack } from "../overlayStack.svelte.js";

  /** @type {import("./CowriteEngine.svelte.js").ReturnType<typeof import("./CowriteEngine.svelte.js").createCowrite>} */
  let { cowrite } = $props();

  let refinementText = $state("");

  // Register with overlay stack so TabView defers to this overlay on ESC/Q
  let _overlayEntry = $state(null);
  $effect(() => {
    _overlayEntry = overlayStack.push("cowrite-panel", () => cowrite.close());
    return () => {
      if (_overlayEntry) overlayStack.remove(_overlayEntry.id);
      _overlayEntry = null;
    };
  });

  /** Render a single field's diff ops as HTML. */
  function renderDiff(original, ops) {
    if (!ops || ops.length === 0) return escapeHtml(original);

    let html = "";
    for (const op of ops) {
      if (op.tag === "equal") {
        html += escapeHtml(op.deleted || "");
      } else if (op.tag === "replace") {
        html += `<span class="diff-del">${escapeHtml(op.deleted)}</span>`;
        html += `<span class="diff-ins">${escapeHtml(op.inserted)}</span>`;
      } else if (op.tag === "delete") {
        html += `<span class="diff-del">${escapeHtml(op.deleted)}</span>`;
      } else if (op.tag === "insert") {
        html += `<span class="diff-ins">${escapeHtml(op.inserted)}</span>`;
      }
    }
    return html;
  }

  function escapeHtml(s) {
    if (!s) return "";
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");
  }

  /** Status badge for a field edit. */
  function statusLabel(fe) {
    if (fe.accepted) return "Accepted ✓";
    if (fe.rejected) return "Rejected ✕";
    return "";
  }

  /** Submit a refinement request. */
  async function handleRefine() {
    const trimmed = refinementText.trim();
    if (!trimmed) return;
    refinementText = "";
    await cowrite.startCowrite(trimmed);
  }

  function handleKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleRefine();
    }
  }

  let allAcceptedOrRejected = $derived(
    cowrite.fieldEdits.length > 0 &&
    cowrite.fieldEdits.every((fe) => fe.accepted || fe.rejected)
  );
</script>

<!-- svelte-ignore a11y_click_events_have_key_events,a11y_no_static_element_interactions -->
<div class="cowrite-overlay" role="presentation" onclick={() => cowrite.close()}
     onkeydown={(e) => { if (e.key === "Escape") { e.stopPropagation(); cowrite.close(); } }}>
  <!-- svelte-ignore a11y_click_events_have_key_events,a11y_no_static_element_interactions -->
  <div class="cowrite-panel" role="presentation" onclick={(e) => e.stopPropagation()}>
    <!-- Header -->
    <div class="panel-header">
      <span class="panel-title">LLM Co-Writing</span>
      <button class="close-btn" onclick={() => cowrite.close()} aria-label="Close">✕</button>
    </div>

    <!-- Instruction input (top, always visible) -->
    <div class="panel-footer">
      <div class="input-row">
        <input
          type="text"
          class="instruction-input"
          placeholder="e.g. make it more formal, add detail..."
          bind:value={refinementText}
          onkeydown={handleKeydown}
          disabled={cowrite.isLoading}
        />
        <button
          type="button"
          class="btn-ask"
          onclick={() => cowrite.startCowrite(refinementText)}
          disabled={cowrite.isLoading || !refinementText.trim()}
        >
          {#if cowrite.isLoading}
            Thinking...
          {:else}
            Ask LLM
          {/if}
        </button>
      </div>
    </div>

    <!-- Content area -->
    <div class="panel-body">
      {#if cowrite.error}
        <div class="error-banner">{cowrite.error}</div>
      {/if}

      {#if cowrite.isLoading}
        <div class="loading-state">
          <span class="spinner"></span>
          <span>LLM is thinking...</span>
        </div>
      {:else if cowrite.fieldEdits.length === 0}
        <div class="empty-state">
          <p class="empty-hint">Enter an instruction above and click "Ask LLM" to get writing suggestions.</p>
        </div>
      {:else}
        <!-- Batch actions -->
        {#if cowrite.hasUnprocessed}
          <div class="batch-actions">
            <button class="btn-accept-all" onclick={() => cowrite.acceptAll()}>
              Accept All
            </button>
            <button class="btn-reject-all" onclick={() => cowrite.rejectAll()}>
              Reject All
            </button>
          </div>
        {:else if allAcceptedOrRejected}
          <div class="batch-done">
            All edits processed.
          </div>
        {/if}

        <!-- Field edits -->
        <div class="edits-list">
          {#each cowrite.fieldEdits as fe, i}
            <div class="edit-card" class:accepted={fe.accepted} class:rejected={fe.rejected}>
              <div class="edit-header">
                <span class="edit-field-name">{fe.field}</span>
                {#if fe.accepted || fe.rejected}
                  <span class="edit-status">{statusLabel(fe)}</span>
                {/if}
              </div>

              {#if fe.accepted}
                <div class="edit-result">Applied: {fe.revised}</div>
              {:else if fe.rejected}
                <div class="edit-result">Kept original.</div>
              {:else}
                <div class="diff-area">
                  {@html renderDiff(fe.original, fe.ops)}
                </div>
                <div class="edit-actions">
                  <button class="btn-accept" onclick={() => cowrite.acceptEdit(i)} title="Accept this change">
                    ✓ Accept
                  </button>
                  <button class="btn-reject" onclick={() => cowrite.rejectEdit(i)} title="Reject this change">
                    ✕ Reject
                  </button>
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </div>

  </div>
</div>

<style>
  /* ── Overlay ─────────────────────────────────── */
  .cowrite-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 100;
    display: flex;
    justify-content: flex-end;
  }
  .cowrite-panel {
    width: 420px;
    max-width: 90vw;
    background: #1e1e32;
    border-left: 1px solid #444;
    display: flex;
    flex-direction: column;
    animation: slideIn 0.15s ease;
  }
  @keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }

  /* ── Header ──────────────────────────────────── */
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }
  .panel-title {
    font-family: monospace;
    font-size: 0.85rem;
    color: #b0b0c0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .close-btn {
    background: none;
    border: none;
    color: #7c7c9a;
    font-size: 1rem;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 4px;
  }
  .close-btn:hover { color: #fff; background: #2a2a44; }

  /* ── Body ────────────────────────────────────── */
  .panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  /* ── Error ───────────────────────────────────── */
  .error-banner {
    background: #3a1a1a;
    border: 1px solid #6a3a3a;
    color: #e08080;
    padding: 8px 12px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.8rem;
  }

  /* ── Loading ─────────────────────────────────── */
  .loading-state {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 2rem 0;
    color: #7c7c9a;
    font-family: monospace;
    font-size: 0.85rem;
    justify-content: center;
  }
  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid #444;
    border-top-color: #7c7c9a;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Empty ───────────────────────────────────── */
  .empty-state {
    padding: 2rem 0;
    text-align: center;
  }
  .empty-hint {
    color: #5a5a7a;
    font-family: monospace;
    font-size: 0.82rem;
  }

  /* ── Batch actions ───────────────────────────── */
  .batch-actions {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
  }
  .btn-accept-all, .btn-reject-all {
    flex: 1;
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.78rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-accept-all { background: #1a3a1a; color: #6aaa6a; border-color: #3a6a3a; }
  .btn-accept-all:hover { background: #2a4a2a; }
  .btn-reject-all { background: #3a1a1a; color: #aa6a6a; border-color: #6a3a3a; }
  .btn-reject-all:hover { background: #4a2a2a; }

  .batch-done {
    text-align: center;
    color: #5a7a5a;
    font-family: monospace;
    font-size: 0.8rem;
    padding: 4px 0;
  }

  /* ── Edit cards ──────────────────────────────── */
  .edits-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .edit-card {
    background: #16162a;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 10px 12px;
  }
  .edit-card.accepted { border-color: #3a6a3a; }
  .edit-card.rejected { border-color: #6a3a3a; opacity: 0.6; }

  .edit-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .edit-field-name {
    font-family: monospace;
    font-size: 0.72rem;
    color: #7c7c9a;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }
  .edit-status {
    font-size: 0.7rem;
    color: #5a7a5a;
    font-family: monospace;
  }
  .edit-result {
    font-family: monospace;
    font-size: 0.82rem;
    color: #b0b0c0;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* ── Diff visualization ──────────────────────── */
  .diff-area {
    font-family: monospace;
    font-size: 0.82rem;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    color: #d0d0e0;
    padding: 6px 0;
  }
  .diff-area :global(.diff-del) {
    background: #4a1a1a;
    color: #e08080;
    text-decoration: line-through;
    padding: 1px 2px;
    border-radius: 2px;
  }
  .diff-area :global(.diff-ins) {
    background: #3a4a1a;
    color: #b0d080;
    padding: 1px 2px;
    border-radius: 2px;
  }

  /* ── Edit actions (per-field) ────────────────── */
  .edit-actions {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .btn-accept, .btn-reject {
    padding: 3px 10px;
    border-radius: 4px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-accept { background: #1a3a1a; color: #6aaa6a; border-color: #3a6a3a; }
  .btn-accept:hover { background: #2a4a2a; }
  .btn-reject { background: #3a1a1a; color: #aa6a6a; border-color: #6a3a3a; }
  .btn-reject:hover { background: #4a2a2a; }

  /* ── Footer / instruction input ──────────────── */
  .panel-footer {
    border-top: 1px solid #333;
    padding: 10px 14px;
    flex-shrink: 0;
  }
  .input-row {
    display: flex;
    gap: 6px;
  }
  .instruction-input {
    flex: 1;
    background: #12122a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 8px 10px;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.82rem;
    outline: none;
  }
  .instruction-input:focus { border-color: #5a5a8a; }
  .instruction-input::placeholder { color: #555; }
  .btn-ask {
    padding: 8px 14px;
    border-radius: 6px;
    border: 1px solid #3a6a3a;
    background: #1e3a1e;
    color: #7fdb7f;
    font-family: monospace;
    font-size: 0.82rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .btn-ask:hover:not(:disabled) { background: #2a4a2a; }
  .btn-ask:disabled { opacity: 0.4; cursor: not-allowed; }
</style>

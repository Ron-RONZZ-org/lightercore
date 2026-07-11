<script>
  import { tick } from "svelte";

  /**
   * Shared ConfirmDialog — Human-in-the-loop approval for LLM tool calls.
   *
   * Shows a list of pending write/destructive operations the LLM wants to
   * perform.  The user can approve/reject each one individually, toggle
   * "Approve All", provide per-item or global feedback, then submit.
   *
   * Props:
   *   message          – Optional heading/message shown above the batch list.
   *   batch            – Array of `{index, tokens, flags, description}` items.
   *   formatCommand    – Function `(item) => string` to render a command.
   *   allowFeedback    – Show per-item feedback textarea for rejected items.
   *   allowGlobalFeedback – Show the global "Tell LLM what to do instead" toggle.
   *   onSubmit         – Callback `(decisions, feedback) => void`.
   *   onDismiss        – Callback for cancel/escape.
   */

  let {
    message = "",
    batch = [],
    formatCommand = (item) => {
      const tokens = item.tokens || [];
      const flags = item.flags || {};
      let cmd = "!" + tokens.join(" ");
      for (const [k, v] of Object.entries(flags)) {
        cmd += v ? ` --${k} ${v}` : ` --${k}`;
      }
      return cmd;
    },
    allowFeedback = true,
    allowGlobalFeedback = true,
    onSubmit = () => {},
    onDismiss = () => {},
  } = $props();

  // Per-item state: index → "approved" | "rejected" | null (undecided)
  let itemStatus = $state({});
  // Per-item feedback: index → feedback text (only for rejected)
  let itemFeedback = $state({});
  let showGlobalFeedback = $state(false);
  let globalFeedbackText = $state("");
  let overlay = $state(null);
  /** Tracks whether the Approve All toggle is in "approved" mode. */
  let allApprovedToggle = $state(false);

  $effect(() => {
    tick().then(() => {
      const firstBtn = document.querySelector(".batch-item-btn");
      if (firstBtn) firstBtn.focus();
    });
  });

  /** True when every item is in "approved" state. */
  function allApproved() {
    return batch.length > 0 && batch.every((item) => itemStatus[item.index] === "approved");
  }

  function trapKeydown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onDismiss();
    }
  }

  function handleItemApprove(index) {
    itemStatus = { ...itemStatus, [index]: "approved" };
    itemFeedback = { ...itemFeedback, [index]: "" };
  }

  function handleItemReject(index) {
    itemStatus = { ...itemStatus, [index]: "rejected" };
  }

  function handleItemFeedbackChange(index, text) {
    itemFeedback = { ...itemFeedback, [index]: text };
  }

  /** Toggle "Approve All": approve all on first click, undo on second. */
  function handleToggleApproveAll() {
    if (allApprovedToggle) {
      // Undo — reset all to undecided
      itemStatus = {};
      itemFeedback = {};
      allApprovedToggle = false;
    } else {
      // Approve all
      const all = {};
      for (const item of batch) {
        all[item.index] = "approved";
      }
      itemStatus = all;
      itemFeedback = {};
      allApprovedToggle = true;
    }
    globalFeedbackText = "";
    showGlobalFeedback = false;
  }

  function handleGlobalFeedbackToggle() {
    showGlobalFeedback = !showGlobalFeedback;
    if (showGlobalFeedback) {
      // Set all undecided items to rejected
      const updated = { ...itemStatus };
      for (const item of batch) {
        if (updated[item.index] == null) {
          updated[item.index] = "rejected";
        }
      }
      itemStatus = updated;
      tick().then(() => {
        const el = document.querySelector(".global-feedback-input");
        if (el) el.focus();
      });
    }
  }

  function handleSubmit() {
    const decisions = {};
    const feedback = {};
    for (const item of batch) {
      const idx = item.index;
      const status = itemStatus[idx];
      decisions[idx] = status === "approved";
      if (status === "rejected") {
        const fb = itemFeedback[idx] || "";
        if (fb.trim()) {
          feedback[idx] = fb.trim();
        }
      }
    }

    if (showGlobalFeedback && globalFeedbackText.trim()) {
      onSubmit(decisions, globalFeedbackText.trim());
    } else if (Object.keys(feedback).length > 0) {
      onSubmit(decisions, feedback);
    } else {
      onSubmit(decisions, null);
    }
  }
</script>

<div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Confirm"
     onclick={(e) => { if (e.target === e.currentTarget) onDismiss(); }}
     onkeydown={trapKeydown} bind:this={overlay} tabindex="0">
  <div class="confirm-box" role="presentation" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
    {#if message}
      <p class="confirm-message">{message}</p>
    {/if}

    {#if batch.length > 0}
      <div class="batch-list">
        {#each batch as item (item.index)}
          {@const cmd = formatCommand(item)}
          {@const idx = item.index}
          {@const status = itemStatus[idx]}
          <div class="batch-item" class:item-approved={status === "approved"} class:item-rejected={status === "rejected"}>
            <div class="batch-item-header">
              <div class="batch-item-cmd">
                <span class="batch-idx">{idx + 1}.</span>
                <code class="cmd-text">{cmd}</code>
              </div>
              {#if item.description}
                <div class="batch-desc">{item.description}</div>
              {/if}
            </div>
            <div class="batch-item-actions">
              {#if status === "approved"}
                <span class="status-badge approved-badge" role="button" tabindex="0"
                      onclick={() => { itemStatus = { ...itemStatus, [idx]: null }; allApprovedToggle = false; }}
                      onkeydown={(e) => { if (e.key === "Enter") { itemStatus = { ...itemStatus, [idx]: null }; allApprovedToggle = false; } }}>
                  &#10003; Approved
                </span>
              {:else if status === "rejected"}
                <span class="status-badge rejected-badge" role="button" tabindex="0"
                      onclick={() => { itemStatus = { ...itemStatus, [idx]: null }; itemFeedback = { ...itemFeedback, [idx]: "" }; }}
                      onkeydown={(e) => { if (e.key === "Enter") { itemStatus = { ...itemStatus, [idx]: null }; itemFeedback = { ...itemFeedback, [idx]: "" }; } }}>
                  &#10007; Rejected
                </span>
              {:else}
                <button class="btn btn-approve batch-item-btn" onclick={() => handleItemApprove(idx)}>
                  &#10003; Approve
                </button>
                <button class="btn btn-reject" onclick={() => handleItemReject(idx)}>
                  Tell LLM what to do instead&#8230;
                </button>
              {/if}
            </div>

            {#if status === "rejected" && allowFeedback}
              <div class="item-feedback-area">
                <textarea
                  class="feedback-input item-feedback-input"
                  placeholder="What should the LLM do instead?"
                  value={itemFeedback[idx] || ""}
                  oninput={(e) => handleItemFeedbackChange(idx, e.target.value)}
                  rows="1"
                ></textarea>
              </div>
            {/if}
          </div>
        {/each}
      </div>

      <div class="global-actions">
        <button class="btn btn-approve-all" onclick={handleToggleApproveAll}>
          {allApprovedToggle ? "&#10003; Approved All" : "&#10003; Approve All"}
        </button>
        {#if allowGlobalFeedback}
          <button class="btn btn-global-feedback" onclick={handleGlobalFeedbackToggle}>
            {showGlobalFeedback ? "Hide global feedback" : "Tell LLM what to do instead (global)\u2026"}
          </button>
        {/if}
      </div>

      {#if showGlobalFeedback && allowGlobalFeedback}
        <div class="global-feedback-area">
          <textarea
            class="feedback-input global-feedback-input"
            placeholder="What should the LLM do instead for all rejected operations?"
            bind:value={globalFeedbackText}
            rows="2"
          ></textarea>
        </div>
      {/if}

      <div class="actions submit-actions">
        <button class="btn btn-submit" onclick={handleSubmit}>
          Submit Decisions
        </button>
        <button class="btn btn-cancel" onclick={onDismiss}>Cancel</button>
      </div>
    {:else}
      <div class="actions">
        <button class="btn btn-submit" onclick={() => onSubmit({}, null)}>Confirm</button>
        <button class="btn" onclick={onDismiss}>Cancel</button>
      </div>
    {/if}
  </div>
</div>

<style>
  .confirm-overlay {
    position: fixed; inset: 0;
    background: var(--confirm-overlay-bg, rgba(0,0,0,0.6));
    display: flex; align-items: center; justify-content: center;
    z-index: var(--confirm-z-index, 100);
  }
  .confirm-box {
    background: var(--confirm-box-bg, #1e1e32);
    border: 1px solid var(--confirm-box-border, #444);
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    max-width: 640px;
    width: 90%;
    max-height: 85vh;
    overflow-y: auto;
  }
  .confirm-message {
    margin: 0 0 0.75rem 0;
    color: var(--confirm-text, #e0e0e0);
    font-size: 0.95rem;
    line-height: 1.4;
    text-align: center;
  }
  .actions { display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }

  /* ── Buttons ──────────────────────────────── */
  .btn {
    padding: 0.35rem 0.85rem;
    border: 1px solid var(--btn-border, #555);
    border-radius: 4px;
    background: var(--btn-bg, #2a2a3e);
    color: var(--btn-text, #e0e0e0);
    cursor: pointer;
    font-size: 0.82rem;
    white-space: nowrap;
  }
  .btn:hover { background: var(--btn-hover-bg, #3a3a5a); }
  .btn-approve { background: var(--btn-approve-bg, #2a4a3a); border-color: var(--btn-approve-border, #3a7a4a); }
  .btn-approve:hover { background: var(--btn-approve-hover-bg, #3a6a4a); }
  .btn-reject { background: var(--btn-reject-bg, #4a2a2a); border-color: var(--btn-reject-border, #7a3a3a); }
  .btn-reject:hover { background: var(--btn-reject-hover-bg, #6a3a3a); }
  .btn-approve-all { background: var(--btn-approve-all-bg, #2a4a5a); border-color: var(--btn-approve-all-border, #3a6a7a); }
  .btn-approve-all:hover { background: var(--btn-approve-all-hover-bg, #3a5a6a); }
  .btn-global-feedback { background: var(--btn-global-feedback-bg, #3a2a4a); border-color: var(--btn-global-feedback-border, #5a3a7a); }
  .btn-global-feedback:hover { background: var(--btn-global-feedback-hover-bg, #4a3a5a); }
  .btn-submit { background: var(--btn-submit-bg, #3a6a3a); border-color: var(--btn-submit-border, #4a8a4a); color: var(--btn-submit-text, #fff); font-weight: 600; }
  .btn-submit:hover { background: var(--btn-submit-hover-bg, #4a8a4a); }
  .btn-cancel { background: var(--btn-cancel-bg, #3a3a3a); border-color: var(--btn-cancel-border, #555); }

  /* ── Batch list ───────────────────────────── */
  .batch-list {
    max-height: 45vh;
    overflow-y: auto;
    margin-bottom: 0.75rem;
    text-align: left;
    border: 1px solid var(--batch-border, #333);
    border-radius: 6px;
  }
  .batch-item {
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    color: var(--batch-item-text, #ccc);
    border-bottom: 1px solid var(--batch-item-border, #2a2a2a);
  }
  .batch-item:last-child { border-bottom: none; }
  .batch-item.item-approved {
    background: var(--item-approved-bg, rgba(42, 90, 58, 0.12));
    border-left: 3px solid var(--item-approved-border, #4a8a4a);
  }
  .batch-item.item-rejected {
    background: var(--item-rejected-bg, rgba(90, 42, 42, 0.12));
    border-left: 3px solid var(--item-rejected-border, #8a4a4a);
  }
  .batch-item-header {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    margin-bottom: 0.35rem;
  }
  .batch-item-cmd {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }
  .batch-idx {
    color: var(--idx-color, #888);
    font-size: 0.8rem;
    flex-shrink: 0;
    min-width: 1.2rem;
    text-align: right;
  }
  .cmd-text {
    background: var(--cmd-bg, #2a2a3e);
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    font-size: 0.82rem;
    color: var(--cmd-text-color, #c8c8e8);
    word-break: break-all;
    white-space: pre-wrap;
    line-height: 1.5;
  }
  .batch-desc {
    color: var(--desc-color, #999);
    font-size: 0.78rem;
    line-height: 1.4;
  }
  .batch-item-actions {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
    align-items: center;
  }
  .status-badge {
    font-size: 0.8rem;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    cursor: pointer;
    user-select: none;
  }
  .status-badge:hover { opacity: 0.8; }
  .approved-badge {
    background: var(--badge-approved-bg, rgba(42, 90, 58, 0.3));
    color: var(--badge-approved-text, #6aba6a);
  }
  .rejected-badge {
    background: var(--badge-rejected-bg, rgba(90, 42, 42, 0.3));
    color: var(--badge-rejected-text, #ba6a6a);
  }

  /* ── Feedback ─────────────────────────────── */
  .item-feedback-area {
    margin-top: 0.4rem;
  }
  .feedback-input {
    width: 100%;
    box-sizing: border-box;
    background: var(--feedback-bg, #2a2a3e);
    border: 1px solid var(--feedback-border, #555);
    border-radius: 6px;
    padding: 0.4rem 0.6rem;
    color: var(--feedback-text, #e0e0e0);
    font-family: inherit;
    font-size: 0.82rem;
    resize: vertical;
    outline: none;
  }
  .feedback-input:focus { border-color: var(--feedback-focus-border, #7c7c9a); }
  .global-feedback-area {
    margin-bottom: 0.75rem;
  }

  /* ── Global actions ───────────────────────── */
  .global-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--global-actions-border, #333);
  }
  .submit-actions {
    margin-top: 0.25rem;
  }
</style>

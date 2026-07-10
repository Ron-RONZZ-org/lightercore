<script>
  /**
   * Reusable account/profile list with action buttons.
   *
   * Props:
   *   type  — "llm" | "email" | "calendar"
   *   items — array of account/profile objects
   *   activeName — (llm only) name of the currently active profile
   *   onAdd, onModify(item), onRemove(item) — callbacks
   *   onActivate(item) — (llm only) set a profile as active
   */

  let { type = "email", items = [], activeName = "", onAdd = () => {}, onModify = () => {}, onRemove = () => {}, onActivate = () => {} } = $props();

  const LABELS = {
    llm: { title: "LLM Profiles", add: "Add Profile", empty: "No LLM profiles configured." },
    email: { title: "Email Accounts", add: "Add Account", empty: "No email accounts configured." },
    calendar: { title: "Calendars", add: "Add Calendar", empty: "No calendars configured." },
  };

  const EMPTY_HINTS = {
    llm: [
      "!llm profile new deepseek --alias my-deepseek",
      "!llm profile new ollama --alias local",
    ],
    email: [
      "!email account add user@example.com",
    ],
    calendar: [
      "!calendar account add https://your-caldav-server.com",
    ],
  };

  let labels = $derived(LABELS[type] || LABELS.email);
  let hints = $derived(EMPTY_HINTS[type] || []);
</script>

<div class="account-list">
  <div class="header">
    <h3 class="title">{labels.title}</h3>
    <button class="btn-add" onclick={onAdd}>+ {labels.add}</button>
  </div>

  {#if items.length === 0}
    <div class="empty-state">
      <p class="empty-msg">{labels.empty}</p>
      <div class="hints">
        {#each hints as hint}
          <code class="hint-cmd">{hint}</code>
        {/each}
      </div>
    </div>
  {:else}
    <div class="list">
      {#each items as item}
        <div class="row">
          <div class="row-info">
            {#if type === "llm"}
              <span class="row-main">{item.name}</span>
              <span class="row-sub">{item.provider_type} · {item.model || "default model"}</span>
              <span class="row-meta">{item.base_url || ""}</span>
            {:else if type === "email"}
              <span class="row-main">{item.email || item.retposto || ""}</span>
              <span class="row-sub">{item.name || item.nomo || ""}</span>
              <span class="row-meta">{item.uuid?.slice(0, 8) || ""}</span>
            {:else if type === "calendar"}
              <span class="row-main">{item.url || ""}</span>
              <span class="row-sub">{item.username ? `User: ${item.username}` : ""}</span>
              <span class="row-meta">{item.uuid?.slice(0, 8) || ""} · {item.remote ? "remote" : "local"}</span>
            {/if}
          </div>
          <div class="row-actions">
            {#if type === "llm"}
              {#if item.name === activeName}
                <span class="badge-active">Activated</span>
              {:else}
                <button class="btn-activate" onclick={() => onActivate(item)} title="Set as active profile">Activate</button>
              {/if}
            {/if}
            <button class="btn-modify" onclick={() => onModify(item)} title="Modify">Modify</button>
            <button class="btn-remove" onclick={() => onRemove(item)} title="Remove">Remove</button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .account-list {
    font-family: monospace;
    font-size: 0.85rem;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .title {
    font-size: 0.95rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  .btn-add {
    background: #2a4a2a;
    color: #b0d0b0;
    border: 1px solid #3a6a3a;
    border-radius: 6px;
    padding: 0.35rem 0.75rem;
    font-family: monospace;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-add:hover {
    background: #3a6a3a;
  }
  .empty-state {
    text-align: center;
    padding: 2rem 0;
  }
  .empty-msg {
    color: var(--clr-sub);
    margin-bottom: 1rem;
  }
  .hints {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    align-items: center;
  }
  .hint-cmd {
    display: inline-block;
    background: #2a2a3e;
    padding: 0.3rem 0.6rem;
    border-radius: 4px;
    color: var(--clr-sub);
    font-size: 0.78rem;
    border: 1px solid #333;
  }
  .list {
    display: flex;
    flex-direction: column;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.4rem;
    border-bottom: 1px solid #2a2a3e;
    transition: background 0.1s;
  }
  .row:last-child {
    border-bottom: none;
  }
  .row:hover {
    background: #22223a;
  }
  .row-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
    flex: 1;
  }
  .row-main {
    color: #e0e0e0;
    font-size: 0.85rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row-sub {
    color: var(--clr-sub);
    font-size: 0.75rem;
  }
  .row-meta {
    color: var(--clr-muted);
    font-size: 0.7rem;
  }
  .row-actions {
    display: flex;
    gap: 0.4rem;
    flex-shrink: 0;
    margin-left: 1rem;
  }
  .btn-activate, .btn-modify, .btn-remove {
    padding: 0.25rem 0.55rem;
    border-radius: 4px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-activate {
    background: #2a4a3a;
    color: #80c080;
    border-color: #3a6a4a;
  }
  .btn-activate:hover {
    background: #3a6a4a;
  }
  .badge-active {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.72rem;
    background: #1a3a2a;
    color: #60b080;
    border: 1px solid #2a5a3a;
  }
  .btn-modify {
    background: #2a3a5a;
    color: #b0c0d0;
    border-color: #3a5a7a;
  }
  .btn-modify:hover {
    background: #3a5a7a;
  }
  .btn-remove {
    background: #4a2a2a;
    color: #d0a0a0;
    border-color: #6a3a3a;
  }
  .btn-remove:hover {
    background: #6a3a3a;
  }
</style>

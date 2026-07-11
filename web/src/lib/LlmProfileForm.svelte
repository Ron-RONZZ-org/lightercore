<script>
  /**
   * Blocking popup form for creating/editing an LLM profile.
   *
   * Props:
   *   profile   — null for new, or {name, provider_type, base_url, model, has_api_key} for edit
   *   apiBase   — base URL for API calls (default: "/api/v1")
   *   onSaved   — called after successful save
   *   onDismiss — called when user closes the dialog
   */

  let { profile = null, apiBase = "/api/v1", onSaved = () => {}, onDismiss = () => {} } = $props();

  let isEdit = $derived(profile !== null);

  // svelte-ignore state_referenced_locally
  const _init = profile || {};
  let name = $state(_init.name || "");
  let providerType = $state(_init.provider_type || "deepseek");
  let apiKey = $state("");
  let baseUrl = $state(_init.base_url || "");
  let model = $state(_init.model || "");
  let saving = $state(false);
  let error = $state("");

  const PROVIDERS = [
    { id: "deepseek", name: "DeepSeek", baseUrl: "https://api.deepseek.com", model: "deepseek-v4-flash" },
    { id: "ollama", name: "Ollama (local)", baseUrl: "http://localhost:11434/v1", model: "llama3.2", noKey: true },
    { id: "openai", name: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-4o" },
    { id: "custom", name: "Custom (OpenAI-compatible)", baseUrl: "", model: "" },
  ];

  function updatePreset() {
    const p = PROVIDERS.find((p) => p.id === providerType);
    if (p && providerType !== "custom") {
      baseUrl = p.baseUrl;
      model = p.model;
    }
  }

  function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      handleSave();
    }
  }

  async function handleSave() {
    if (!name.trim()) {
      error = "Profile name is required.";
      return;
    }
    saving = true;
    error = "";
    try {
      const payload = {
        name: name.trim(),
        provider_type: providerType,
        api_key: apiKey,
        base_url: baseUrl,
        model: model,
      };
      if (isEdit) {
        if (!apiKey) delete payload.api_key; // keep existing key
        const resp = await fetch(`${apiBase}/llm/profiles/${encodeURIComponent(profile.name)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${resp.status}`);
        }
      } else {
        const resp = await fetch(`${apiBase}/llm/profiles`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${resp.status}`);
        }
      }
      onSaved();
    } catch (err) {
      error = err.message || "Failed to save profile.";
    } finally {
      saving = false;
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="modal-overlay" onclick={onDismiss} onkeydown={(e) => e.key === "Escape" && onDismiss()} role="button" tabindex="-1" aria-label="Dismiss">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="0" onkeydown={() => {}}>
    <div class="modal-header">
      <h2>{isEdit ? "Edit LLM Profile" : "Add LLM Profile"}</h2>
      <p class="subtitle">{isEdit ? `Editing "${profile.name}"` : "Create a new provider configuration"}</p>
    </div>
    <div class="form">
      <label class="field">
        <span class="field-label">Profile Name</span>
        <!-- svelte-ignore a11y_autofocus -->
        <input type="text" class="text-input" bind:value={name} placeholder="my-profile" disabled={isEdit} autofocus />
      </label>
      <label class="field">
        <span class="field-label">Provider Type</span>
        <select class="text-input" bind:value={providerType} onchange={updatePreset}>
          {#each PROVIDERS as p}
            <option value={p.id}>{p.name}</option>
          {/each}
        </select>
      </label>
      <label class="field">
        <span class="field-label">Base URL</span>
        <input type="text" class="text-input" bind:value={baseUrl} placeholder="https://api.openai.com" />
      </label>
      <label class="field">
        <span class="field-label">Model</span>
        <input type="text" class="text-input" bind:value={model} placeholder="gpt-4o" />
      </label>
      {#if providerType !== "ollama"}
        <label class="field">
          <span class="field-label">API Key</span>
          <input type="password" class="text-input" bind:value={apiKey} placeholder={isEdit ? "Leave blank to keep current" : "sk-..."} />
        </label>
      {/if}
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <div class="form-actions">
        <button class="btn-primary" onclick={handleSave} disabled={saving || !name.trim()}>
          {saving ? "Saving…" : isEdit ? "Update" : "Create"}
        </button>
        <button class="btn-secondary" onclick={onDismiss}>Cancel</button>
      </div>
    </div>
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6);
    z-index: 500; display: flex; align-items: center; justify-content: center;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .modal {
    background: #1e1e32; border: 1px solid #444; border-radius: 16px;
    padding: 1.5rem; width: 420px; max-width: 90vw;
    max-height: 80vh; overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  }
  .modal-header { margin-bottom: 1rem; }
  .modal-header h2 { font-size: 1.1rem; color: #e0e0e0; font-weight: 600; }
  .subtitle { font-size: 0.8rem; color: #7c7c9a; margin-top: 0.25rem; }
  .form { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  .field-label { font-size: 0.78rem; color: #7c7c9a; font-family: monospace; }
  .text-input {
    background: #2a2a3e; border: 1px solid #444; border-radius: 8px;
    padding: 0.5rem 0.7rem; color: #e0e0e0; font-size: 0.85rem;
    outline: none; font-family: monospace;
  }
  .text-input:focus { border-color: #7c7c9a; }
  select.text-input { cursor: pointer; }
  .error { color: #aa6a6a; font-size: 0.8rem; }
  .form-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .btn-primary, .btn-secondary {
    padding: 0.45rem 1rem; border-radius: 8px; border: 1px solid #444;
    font-family: monospace; font-size: 0.85rem; cursor: pointer;
    transition: background 0.1s;
  }
  .btn-primary {
    background: #3a6a3a; color: #e0e0e0; border-color: #4a8a4a; flex: 1;
  }
  .btn-primary:hover { background: #4a8a4a; }
  .btn-primary:disabled { opacity: 0.4; cursor: default; }
  .btn-secondary { background: #2a2a3e; color: #b0b0c0; }
  .btn-secondary:hover { background: #3a3a5a; }
</style>

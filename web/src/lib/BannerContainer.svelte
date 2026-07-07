<script>
  /** Banner notification container — must be mounted once in App.svelte. */

  import { banner } from "./bannerStore.svelte.js";

  let msg = $derived(banner.message);
  let type = $derived(banner.type);
  let visible = $derived(banner.visible);
</script>

{#if visible && msg}
  <div class="banner-container" class:banner-success={type === "success"} class:banner-error={type === "error"} class:banner-info={type === "info"} role="status">
    <span class="banner-icon">
      {#if type === "success"}✓
      {:else if type === "error"}✗
      {:else}ℹ
      {/if}
    </span>
    <span class="banner-text">{msg}</span>
    <button class="banner-close" onclick={() => banner.dismiss()} aria-label="Dismiss">✕</button>
  </div>
{/if}

<style>
  .banner-container {
    position: fixed;
    top: 8px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 2000;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.85rem;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.4);
    animation: banner-in 0.2s ease;
    max-width: 90vw;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .banner-success {
    background: #1e3a2e;
    color: #8fdb9f;
    border: 1px solid #3a7a4a;
  }
  .banner-error {
    background: #3a1e1e;
    color: #db8f8f;
    border: 1px solid #7a3a3a;
  }
  .banner-info {
    background: #1e2a3a;
    color: #8fbfdb;
    border: 1px solid #3a5a7a;
  }
  .banner-icon {
    font-size: 1rem;
    flex-shrink: 0;
  }
  .banner-text {
    flex: 1;
    min-width: 0;
  }
  .banner-close {
    flex-shrink: 0;
    background: none;
    border: none;
    color: inherit;
    opacity: 0.6;
    cursor: pointer;
    padding: 0 2px;
    font-size: 0.85rem;
    line-height: 1;
  }
  .banner-close:hover {
    opacity: 1;
  }
  @keyframes banner-in {
    from { opacity: 0; transform: translateX(-50%) translateY(-12px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>

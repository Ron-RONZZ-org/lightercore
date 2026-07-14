<script>
  /**
   * ScrollList — Infinite-scroll list container with IntersectionObserver.
   *
   * Wraps an `{#each}` block and automatically loads more items when the
   * user scrolls near the bottom.
   *
   * Props:
   *   items       – Array of items to display.
   *   hasMore     – Whether more items are available.
   *   loading     – Whether a load is in progress.
   *   getKey      – Function `(item) => string` for keyed each block.
   *   onLoadMore  – Async callback triggered when sentinel enters viewport.
   *   emptyMessage – Text shown when items is empty.
   *   children    – Snippet `(item, index) => Snippet`.
   *
   * Usage:
   * ```svelte
   * <ScrollList {items} hasMore={true} loading={loading}
   *   onLoadMore={loadMore} getKey={(i) => i.id}>
   *   {#snippet children(item, index)}
   *     <div>{item.name}</div>
   *   {/snippet}
   * </ScrollList>
   * ```
   */
  import { tick } from "svelte";

  let {
    items = [],
    hasMore = false,
    loading = false,
    getKey = (item) => item,
    onLoadMore = async () => {},
    emptyMessage = "No items.",
    children,
  } = $props();

  let sentinelEl = $state(null);

  $effect(() => {
    const el = sentinelEl;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          onLoadMore();
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  });
</script>

<div class="scroll-list">
  {#each items as item, i (getKey(item))}
    {@render children(item, i)}
  {:else}
    <p class="scroll-empty">{emptyMessage}</p>
  {/each}

  {#if hasMore}
    <div bind:this={sentinelEl} class="scroll-sentinel">
      {#if loading}
        <span class="scroll-loading">Loading…</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .scroll-list {
    flex: 1;
    overflow-y: auto;
    padding: 0;
  }
  .scroll-sentinel {
    display: flex;
    justify-content: center;
    padding: 1rem;
  }
  .scroll-loading {
    color: var(--clr-sub, #7c7c9a);
    font-family: monospace;
    font-size: 0.82rem;
  }
  .scroll-empty {
    color: var(--clr-muted, #555);
    text-align: center;
    padding: 2rem;
    font-family: monospace;
  }
</style>

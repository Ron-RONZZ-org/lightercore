import { describe, it, expect, vi, beforeEach } from "vitest";

let createSelectionManager, createCopyState;

// jsdom doesn't provide CSS.escape — polyfill it
if (typeof CSS === "undefined") {
  globalThis.CSS = { escape: (s) => s.replace(/[!"#$%&'()*+,./:;<=>?@[\]^`{|}~]/g, "\\$&") };
}

beforeEach(async () => {
  vi.resetModules();
  const mod = await import("./listTabSelection.svelte.js");
  createSelectionManager = mod.createSelectionManager;
  createCopyState = mod.createCopyState;
});

describe("createCopyState", () => {
  it("starts with empty copiedKey", () => {
    const state = createCopyState();
    expect(state.copiedKey).toBe("");
  });

  it("copyToClipboard writes to clipboard and sets copiedKey", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });

    const state = createCopyState();
    await state.copyToClipboard("test-id");
    expect(writeText).toHaveBeenCalledWith("test-id");
  });
});

describe("createSelectionManager", () => {
  let items, sel;

  beforeEach(() => {
    items = [
      { uuid: "a", name: "Item A" },
      { uuid: "b", name: "Item B" },
      { uuid: "c", name: "Item C" },
    ];
    sel = createSelectionManager(
      () => items,
      vi.fn(),
      vi.fn(),
      vi.fn(),
    );
  });

  it("starts with selection mode off", () => {
    expect(sel.selectionMode).toBe(false);
    expect(sel.numSelected).toBe(0);
    expect(sel.focusedIndex).toBe(-1);
    expect(sel.confirmDelete).toBe(false);
  });

  it("toggleSelectionMode toggles on and off", () => {
    sel.toggleSelectionMode();
    expect(sel.selectionMode).toBe(true);
    expect(sel.focusedIndex).toBe(0);

    sel.toggleSelectionMode();
    expect(sel.selectionMode).toBe(false);
    expect(sel.numSelected).toBe(0);
  });

  it("toggleItem adds and removes from selectedKeys", () => {
    sel.toggleItem("a");
    expect(sel.isSelected("a")).toBe(true);
    expect(sel.numSelected).toBe(1);

    sel.toggleItem("a");
    expect(sel.isSelected("a")).toBe(false);
    expect(sel.numSelected).toBe(0);
  });

  it("isSelected returns false for unselected keys", () => {
    expect(sel.isSelected("nonexistent")).toBe(false);
  });

  it("handleRowClick in view mode calls onOpen", () => {
    const onOpen = vi.fn();
    sel = createSelectionManager(() => items, onOpen, vi.fn(), vi.fn());
    sel.handleRowClick({ shiftKey: false }, "a");
    expect(onOpen).toHaveBeenCalledWith("a");
  });

  it("handleRowClick in selection mode toggles item", () => {
    sel.toggleSelectionMode();
    sel.handleRowClick({ shiftKey: false }, "a");
    expect(sel.isSelected("a")).toBe(true);
  });

  it("handleKeydown v toggles selection mode", () => {
    const e = { key: "v", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" } };
    expect(sel.selectionMode).toBe(false);
    sel.handleKeydown(e);
    expect(sel.selectionMode).toBe(true);
  });

  it("handleKeydown Escape exits selection mode", () => {
    sel.toggleSelectionMode();
    const e = { key: "Escape", preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.selectionMode).toBe(false);
  });

  it("handleKeydown ignores input when in INPUT", () => {
    const onNew = vi.fn();
    sel = createSelectionManager(() => items, vi.fn(), vi.fn(), vi.fn(), { onNew });
    const e = { key: "n", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "INPUT" } };
    sel.handleKeydown(e);
    expect(onNew).not.toHaveBeenCalled();
  });

  it("handleKeydown n triggers onNew in view mode", () => {
    const onNew = vi.fn();
    sel = createSelectionManager(() => items, vi.fn(), vi.fn(), vi.fn(), { onNew });
    const e = { key: "n", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(onNew).toHaveBeenCalled();
  });

  it("handleKeydown Delete sets confirmDelete when items selected", () => {
    sel.toggleSelectionMode();
    sel.toggleItem("a");
    const e = { key: "Delete", preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.confirmDelete).toBe(true);
  });

  it("confirmDelete cleared by Escape key when active", () => {
    sel.toggleSelectionMode();
    sel.toggleItem("a");
    let e = { key: "Delete", preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.confirmDelete).toBe(true);

    e = { key: "Escape", preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.confirmDelete).toBe(false);
  });

  it("deleteSelected calls onDeleteSelected and refreshes", async () => {
    const onDelete = vi.fn(() => Promise.resolve());
    const onRefresh = vi.fn(() => Promise.resolve());
    sel = createSelectionManager(() => items, vi.fn(), onDelete, onRefresh);
    sel.toggleSelectionMode();
    sel.toggleItem("a");
    sel.toggleItem("b");

    await sel.deleteSelected();
    expect(onDelete).toHaveBeenCalledWith(["a", "b"]);
    expect(onRefresh).toHaveBeenCalled();
    expect(sel.selectionMode).toBe(false);
  });

  it("accepts custom getKey via opts", () => {
    const customItems = [
      { node_id: "n1", label: "Node 1" },
      { node_id: "n2", label: "Node 2" },
    ];
    sel = createSelectionManager(
      () => customItems,
      vi.fn(),
      vi.fn(),
      vi.fn(),
      { getKey: (item) => item.node_id },
    );
    sel.toggleSelectionMode();
    sel.handleRowClick({ shiftKey: false }, "n1");
    expect(sel.isSelected("n1")).toBe(true);
  });

  it("arrow keys navigate rows", () => {
    sel.toggleSelectionMode();
    // toggleSelectionMode sets focusedIndex to 0 (first item)

    // ArrowDown: 0 -> 1
    let e = { key: "ArrowDown", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.focusedIndex).toBe(1);

    // ArrowDown: 1 -> 2
    e = { key: "ArrowDown", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.focusedIndex).toBe(2);

    // ArrowUp: 2 -> 1
    e = { key: "ArrowUp", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.focusedIndex).toBe(1);
  });

  it("Space toggles focused item", () => {
    sel.toggleSelectionMode();
    // toggleSelectionMode sets focusedIndex to 0 (item "a")

    // Move to item at index 1 ("b")
    let e = { key: "ArrowDown", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);

    // Space toggles the focused item (index 1 = "b")
    e = { key: " ", preventDefault: vi.fn(), target: { tagName: "DIV" } };
    sel.handleKeydown(e);
    expect(sel.isSelected("b")).toBe(true);
  });

  // ── Anchor management ──────────────────────────────────────────

  it("toggleSelectionMode sets anchorIndex on entry", () => {
    sel.toggleSelectionMode();
    expect(sel.selectionMode).toBe(true);
    expect(sel.focusedIndex).toBe(0);
    // With empty list, focusedIndex and anchorIndex remain -1
    sel = createSelectionManager(() => [], vi.fn(), vi.fn(), vi.fn());
    sel.toggleSelectionMode();
    expect(sel.focusedIndex).toBe(-1);
    expect(sel.anchorIndex).toBe(-1);
  });

  it("plain navigation preserves anchorIndex", () => {
    sel.toggleSelectionMode();
    // anchorIndex = 0 on entry

    // Click item "a" to set anchor and select it
    sel.handleRowClick({ shiftKey: false }, "a");
    expect(sel.isSelected("a")).toBe(true);

    // Press END (no shift) — should move focus but NOT move anchor
    let e = { key: "End", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" }, shiftKey: false };
    sel.handleKeydown(e);
    expect(sel.focusedIndex).toBe(2);
    expect(sel.anchorIndex).toBe(0); // anchor preserved

    // Press Home (no shift) — focus moves, anchor stays
    e = { key: "Home", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" }, shiftKey: false };
    sel.handleKeydown(e);
    expect(sel.focusedIndex).toBe(0);
    expect(sel.anchorIndex).toBe(0); // anchor still at 0

    // ArrowDown (no shift) — focus moves, anchor stays
    e = { key: "ArrowDown", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" }, shiftKey: false };
    sel.handleKeydown(e);
    expect(sel.focusedIndex).toBe(1);
    expect(sel.anchorIndex).toBe(0); // anchor still at 0
  });

  it("shift+click after plain END selects from anchor to end", () => {
    sel.toggleSelectionMode();
    // anchorIndex = 0 on entry

    // Click item "a" sets anchor
    sel.handleRowClick({ shiftKey: false }, "a");
    expect(sel.isSelected("a")).toBe(true);

    // Press END (no shift) — focus moves to last, anchor stays at 0
    let e = { key: "End", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" }, shiftKey: false };
    sel.handleKeydown(e);

    // Shift+click last item — should select items 0 through 2 (a, b, c)
    sel.handleRowClick({ shiftKey: true }, "c");
    expect(sel.isSelected("a")).toBe(true);
    expect(sel.isSelected("b")).toBe(true);
    expect(sel.isSelected("c")).toBe(true);
  });

  it("shift+End extends selection from anchor to end", () => {
    sel.toggleSelectionMode();
    // anchorIndex = 0 on entry

    // Click item "b" (index 1) to change focus and anchor
    sel.handleRowClick({ shiftKey: false }, "b");
    expect(sel.isSelected("b")).toBe(true);

    // Shift+End — should extend from anchor (index 1) to end (index 2)
    const e = { key: "End", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" }, shiftKey: true };
    sel.handleKeydown(e);
    expect(sel.isSelected("b")).toBe(true);
    expect(sel.isSelected("c")).toBe(true);
    expect(sel.isSelected("a")).toBe(false); // not in range 1-2
  });

  it("shift+ArrowDown extends selection from anchor", () => {
    sel.toggleSelectionMode();
    // anchorIndex = 0 on entry

    // Click item "a" at index 0
    sel.handleRowClick({ shiftKey: false }, "a");
    expect(sel.isSelected("a")).toBe(true);

    // Shift+ArrowDown — select from 0 to 1
    const e = { key: "ArrowDown", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" }, shiftKey: true };
    sel.handleKeydown(e);
    expect(sel.isSelected("a")).toBe(true);
    expect(sel.isSelected("b")).toBe(true);
    expect(sel.isSelected("c")).toBe(false);
  });

  it("shift+ArrowUp selects from anchor upward", () => {
    // Navigate to item at index 2 first by arrow keys
    sel.toggleSelectionMode();
    // Click item "c" at index 2
    sel.handleRowClick({ shiftKey: false }, "c");

    // Shift+ArrowUp — select from anchor (2) to 1
    const e = { key: "ArrowUp", ctrlKey: false, metaKey: false, altKey: false, preventDefault: vi.fn(), target: { tagName: "DIV" }, shiftKey: true };
    sel.handleKeydown(e);
    expect(sel.isSelected("c")).toBe(true);
    expect(sel.isSelected("b")).toBe(true);
    expect(sel.isSelected("a")).toBe(false); // not in range 1-2
  });

  it("empty list does not crash on selection mode entry", () => {
    sel = createSelectionManager(() => [], vi.fn(), vi.fn(), vi.fn());
    sel.toggleSelectionMode();
    expect(sel.selectionMode).toBe(true);
    expect(sel.focusedIndex).toBe(-1);
    expect(sel.anchorIndex).toBe(-1);
  });
});

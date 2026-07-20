import { describe, it, expect, vi, beforeEach } from "vitest";

// Polyfill CSS.escape for jsdom (not available in jsdom by default).
if (typeof CSS === "undefined") {
  globalThis.CSS = {};
}
if (!CSS.escape) {
  CSS.escape = (value) => String(value).replace(/[!"#$%&'()*+,./:;<=>?@[\]^`{|}~\\]/g, "\\$&");
}

describe("applyHighlight", () => {
  let applyHighlight;

  beforeEach(async () => {
    vi.restoreAllMocks();
    // jsdom in vitest provides document.getElementById etc.
    const mod = await import("./highlight.svelte.js");
    applyHighlight = mod.applyHighlight;
  });

  it("returns false for empty highlightId", () => {
    const result = applyHighlight("", [{ id: "A" }], { idField: "id" });
    expect(result).toBe(false);
  });

  it("returns false for empty items", () => {
    const result = applyHighlight("A", [], { idField: "id" });
    expect(result).toBe(false);
  });

  it("returns false if highlightId not in items", () => {
    const result = applyHighlight("B", [{ id: "A" }], { idField: "id" });
    expect(result).toBe(false);
  });

  it("returns false if DOM element not found", () => {
    const result = applyHighlight("A", [{ id: "A" }], { idField: "id" });
    expect(result).toBe(false);
  });

  it("adds highlight class and scrolls when element exists", () => {
    // Set up DOM
    document.body.innerHTML = '<div id="row-A">Item A</div>';
    const el = document.getElementById("row-A");

    // Mock scrollIntoView
    const scrollMock = vi.fn();
    el.scrollIntoView = scrollMock;

    const result = applyHighlight("A", [{ id: "A" }], { idField: "id", rowPrefix: "row-" });

    expect(result).toBe(true);
    expect(scrollMock).toHaveBeenCalledWith({ behavior: "smooth", block: "center" });
    expect(el.classList.contains("hc-highlight-flash")).toBe(true);
  });

  it("removes highlight class after duration", async () => {
    vi.useFakeTimers();
    document.body.innerHTML = '<div id="row-A">Item A</div>';
    const el = document.getElementById("row-A");
    el.scrollIntoView = vi.fn();

    applyHighlight("A", [{ id: "A" }], { idField: "id", rowPrefix: "row-", duration: 100 });

    expect(el.classList.contains("hc-highlight-flash")).toBe(true);

    vi.advanceTimersByTime(100);

    expect(el.classList.contains("hc-highlight-flash")).toBe(false);
    vi.useRealTimers();
  });

  it("uses custom idField and rowPrefix", () => {
    document.body.innerHTML = '<div id="node-42">Item</div>';
    const el = document.getElementById("node-42");
    el.scrollIntoView = vi.fn();

    const result = applyHighlight("42", [{ node_id: "42" }], { idField: "node_id", rowPrefix: "node-" });

    expect(result).toBe(true);
  });

  it("escapes special characters in ID", () => {
    document.body.innerHTML = '<div id="row-A_B_C">Item</div>';
    const el = document.getElementById("row-A_B_C");
    el.scrollIntoView = vi.fn();

    const result = applyHighlight("A_B_C", [{ id: "A_B_C" }], { idField: "id" });

    expect(result).toBe(true);
  });
});

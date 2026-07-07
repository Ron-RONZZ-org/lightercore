import { describe, it, expect, vi, beforeEach } from "vitest";

let mod;

beforeEach(async () => {
  vi.resetModules();
  mod = await import("./keyboardShortcuts.svelte.js");
});

describe("registerShortcuts / getAllShortcuts", () => {
  it("registers shortcuts for a scope", () => {
    mod.registerShortcuts("TestScope", [
      { key: "n", desc: "New item" },
      { key: "d", desc: "Delete item" },
    ]);
    const all = mod.getAllShortcuts();
    const other = all.find((g) => g.category === "Other");
    expect(other).toBeDefined();
    expect(other.keys).toEqual(
      expect.arrayContaining([
        { key: "n", desc: "New item" },
        { key: "d", desc: "Delete item" },
      ]),
    );
  });

  it("always includes Navigation and General groups", () => {
    const all = mod.getAllShortcuts();
    const categories = all.map((g) => g.category);
    expect(categories).toContain("Navigation");
    expect(categories).toContain("General");
  });

  it("includes shortcuts with custom category", () => {
    mod.registerShortcuts("CustomScope", [
      { key: "f", desc: "Filter", category: "Search" },
    ]);
    const all = mod.getAllShortcuts();
    const search = all.find((g) => g.category === "Search");
    expect(search).toBeDefined();
    expect(search.keys).toEqual([{ key: "f", desc: "Filter" }]);
  });

  it("renders modifiers in key label", () => {
    mod.registerShortcuts("WithMods", [
      { key: "a", desc: "Add", modifiers: "Shift" },
    ]);
    const all = mod.getAllShortcuts();
    const other = all.find((g) => g.category === "Other");
    expect(other.keys).toContainEqual({ key: "Shift + a", desc: "Add" });
  });

  it("returns empty for unknown scope", () => {
    expect(mod.getScopeShortcuts("NonExistent")).toEqual([]);
  });

  it("getScopeShortcuts returns registered items", () => {
    mod.registerShortcuts("ScopeA", [{ key: "x", desc: "Action X" }]);
    const items = mod.getScopeShortcuts("ScopeA");
    expect(items).toHaveLength(1);
    expect(items[0].key).toBe("x");
  });
});

describe("normalizeKey", () => {
  it("lowercases a key", () => {
    expect(mod.normalizeKey("Escape")).toBe("escape");
    expect(mod.normalizeKey("Enter")).toBe("enter");
    expect(mod.normalizeKey("A")).toBe("a");
  });
});

describe("isInputFocused", () => {
  it("returns true for INPUT element", () => {
    const e = { target: { tagName: "INPUT" } };
    expect(mod.isInputFocused(e)).toBe(true);
  });

  it("returns true for TEXTAREA element", () => {
    const e = { target: { tagName: "TEXTAREA" } };
    expect(mod.isInputFocused(e)).toBe(true);
  });

  it("returns true for contentEditable element", () => {
    const e = { target: { tagName: "DIV", isContentEditable: true } };
    expect(mod.isInputFocused(e)).toBe(true);
  });

  it("returns false for non-input elements", () => {
    const e = { target: { tagName: "BUTTON" } };
    expect(mod.isInputFocused(e)).toBe(false);

    const e2 = { target: { tagName: "DIV" } };
    expect(mod.isInputFocused(e2)).toBe(false);
  });

  it("handles null/undefined target gracefully", () => {
    expect(mod.isInputFocused({ target: null })).toBe(false);
    expect(mod.isInputFocused({})).toBe(false);
  });
});

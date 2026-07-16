/**
 * Tests for `createHistory` — generic undo/redo state management.
 *
 * Follows the existing test patterns in lightercore (e.g. listTabSelection.test.js).
 */

import { describe, it } from "vitest";
import { createHistory } from "./historyStore.svelte.js";

describe("createHistory", () => {
  it("initialises with provided records", () => {
    const h = createHistory([1, 2, 3]);
    expect(h.records).toEqual([1, 2, 3]);
    expect(h.canUndo).toBe(false);
    expect(h.canRedo).toBe(false);
  });

  it("initialises with empty array by default", () => {
    const h = createHistory();
    expect(h.records).toEqual([]);
  });

  it("push saves snapshot for undo", () => {
    const h = createHistory([1, 2, 3]);
    h.push([1, 2, 3, 4]);
    expect(h.records).toEqual([1, 2, 3, 4]);
    expect(h.canUndo).toBe(true);
    expect(h.canRedo).toBe(false);
  });

  it("undo restores previous state", () => {
    const h = createHistory([1, 2, 3]);
    h.push([1, 2, 3, 4]);
    const ok = h.undo();
    expect(ok).toBe(true);
    expect(h.records).toEqual([1, 2, 3]);
    expect(h.canUndo).toBe(false);
    expect(h.canRedo).toBe(true);
  });

  it("redo restores undone state", () => {
    const h = createHistory([1, 2, 3]);
    h.push([1, 2, 3, 4]);
    h.undo();
    const ok = h.redo();
    expect(ok).toBe(true);
    expect(h.records).toEqual([1, 2, 3, 4]);
    expect(h.canUndo).toBe(true);
    expect(h.canRedo).toBe(false);
  });

  it("push after undo clears redo stack", () => {
    const h = createHistory([1, 2, 3]);
    h.push([1, 2, 3, 4]);
    h.undo();
    h.push([1, 2, 3, 5]);
    expect(h.records).toEqual([1, 2, 3, 5]);
    expect(h.canRedo).toBe(false);
    // Can still undo to initial
    h.undo();
    expect(h.records).toEqual([1, 2, 3]);
  });

  it("undo returns false when nothing to undo", () => {
    const h = createHistory([1, 2, 3]);
    expect(h.undo()).toBe(false);
    expect(h.records).toEqual([1, 2, 3]);
  });

  it("redo returns false when nothing to redo", () => {
    const h = createHistory([1, 2, 3]);
    expect(h.redo()).toBe(false);
    expect(h.records).toEqual([1, 2, 3]);
  });

  it("reset clears undo/redo stacks", () => {
    const h = createHistory([1, 2, 3]);
    h.push([1, 2, 3, 4]);
    h.reset([5, 6]);
    expect(h.records).toEqual([5, 6]);
    expect(h.canUndo).toBe(false);
    expect(h.canRedo).toBe(false);
  });

  it("stores deep copies not references", () => {
    const initial = [{ a: 1 }];
    const h = createHistory(initial);
    initial[0].a = 999; // mutate original
    expect(h.records[0].a).toBe(1); // should not reflect mutation

    h.push([{ a: 2 }]);
    h.records[0].a = 888; // mutate current
    h.undo();
    expect(h.records[0].a).toBe(1); // undo should restore deep copy
  });
});

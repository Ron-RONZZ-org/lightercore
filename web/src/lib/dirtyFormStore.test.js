import { describe, it, expect, vi, beforeEach } from "vitest";

let dirtyFormStore, createFormGuard;

beforeEach(async () => {
  vi.resetModules();
  const mod = await import("./dirtyFormStore.svelte.js");
  dirtyFormStore = mod.dirtyFormStore;
  createFormGuard = mod.createFormGuard;
});

describe("dirtyFormStore", () => {
  it("starts with no dirty forms", () => {
    expect(dirtyFormStore.hasAnyDirty).toBe(false);
    expect(dirtyFormStore.dirtyForms.size).toBe(0);
  });

  it("isDirty returns false for unknown tab", () => {
    expect(dirtyFormStore.isDirty("nonexistent")).toBe(false);
  });

  it("setDirty marks a tab as dirty", () => {
    dirtyFormStore.setDirty("tab-1", true);
    expect(dirtyFormStore.isDirty("tab-1")).toBe(true);
    expect(dirtyFormStore.hasAnyDirty).toBe(true);
  });

  it("setDirty(false) clears a tab's dirty state", () => {
    dirtyFormStore.setDirty("tab-1", true);
    dirtyFormStore.setDirty("tab-1", false);
    expect(dirtyFormStore.isDirty("tab-1")).toBe(false);
    expect(dirtyFormStore.hasAnyDirty).toBe(false);
  });

  it("clear removes a tab from dirty tracking", () => {
    dirtyFormStore.setDirty("tab-1", true);
    dirtyFormStore.clear("tab-1");
    expect(dirtyFormStore.isDirty("tab-1")).toBe(false);
    expect(dirtyFormStore.dirtyForms.has("tab-1")).toBe(false);
  });

  it("multiple dirty tabs: hasAnyDirty is true while any tab is dirty", () => {
    dirtyFormStore.setDirty("tab-1", true);
    dirtyFormStore.setDirty("tab-2", true);
    expect(dirtyFormStore.hasAnyDirty).toBe(true);

    dirtyFormStore.clear("tab-1");
    expect(dirtyFormStore.hasAnyDirty).toBe(true);

    dirtyFormStore.clear("tab-2");
    expect(dirtyFormStore.hasAnyDirty).toBe(false);
  });
});

describe("createFormGuard", () => {
  it("returns a guard with dirty=false initially", () => {
    const guard = createFormGuard("tab-1");
    expect(guard.dirty).toBe(false);
  });

  it("setDirty updates local state and global store", () => {
    const guard = createFormGuard("tab-1");
    guard.setDirty(true);
    expect(guard.dirty).toBe(true);
    expect(dirtyFormStore.isDirty("tab-1")).toBe(true);
  });

  it("setDirty(false) clears both local and global", () => {
    const guard = createFormGuard("tab-1");
    guard.setDirty(true);
    guard.setDirty(false);
    expect(guard.dirty).toBe(false);
    expect(dirtyFormStore.isDirty("tab-1")).toBe(false);
  });

  it("clear resets local and global", () => {
    const guard = createFormGuard("tab-1");
    guard.setDirty(true);
    guard.clear();
    expect(guard.dirty).toBe(false);
    expect(dirtyFormStore.isDirty("tab-1")).toBe(false);
  });

  it("guard without tabId updates local state only", () => {
    const guard = createFormGuard(null);
    guard.setDirty(true);
    expect(guard.dirty).toBe(true);
    expect(dirtyFormStore.hasAnyDirty).toBe(false);
  });
});

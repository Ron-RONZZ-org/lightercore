import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock localStorage for node test environment
function mockLocalStorage() {
  const store = {};
  return {
    getItem: vi.fn((key) => store[key] ?? null),
    setItem: vi.fn((key, value) => { store[key] = String(value); }),
    clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]); }),
    removeItem: vi.fn((key) => { delete store[key]; }),
    get length() { return Object.keys(store).length; },
    key: vi.fn((i) => Object.keys(store)[i] ?? null),
  };
}

describe("createCommandHistory", () => {
  let history;
  const LS_KEY = "test:commandHistory";
  let lsMock;

  beforeEach(() => {
    lsMock = mockLocalStorage();
    Object.defineProperty(globalThis, "localStorage", {
      value: lsMock,
      configurable: true,
      writable: true,
    });
    vi.restoreAllMocks();
  });

  async function createHistory() {
    const mod = await import("./commandHistory.svelte.js");
    return mod.createCommandHistory(LS_KEY);
  }

  it("starts empty", async () => {
    history = await createHistory();
    expect(history.entries).toEqual([]);
    expect(history.index).toBe(-1);
  });

  it("push adds an entry", async () => {
    history = await createHistory();
    history.push("!email list");
    expect(history.entries).toEqual(["!email list"]);
  });

  it("push persists to localStorage", async () => {
    history = await createHistory();
    history.push("!email list");
    const stored = JSON.parse(lsMock.setItem.mock.calls[0][1]);
    expect(stored).toEqual(["!email list"]);
  });

  it("push loads persisted entries on init", async () => {
    // Pre-populate localStorage
    lsMock.getItem.mockReturnValue(JSON.stringify(["!prev cmd"]));
    history = await createHistory();
    expect(history.entries).toEqual(["!prev cmd"]);
  });

  it("back navigates through history", async () => {
    history = await createHistory();
    history.push("first");
    history.push("second");
    history.push("third");
    expect(history.back()).toBe("third");
    expect(history.back()).toBe("second");
    expect(history.back()).toBe("first");
    expect(history.index).toBe(2);
  });

  it("forward navigates back up", async () => {
    history = await createHistory();
    history.push("first");
    history.push("second");
    history.back(); // → second
    history.back(); // → first
    expect(history.forward()).toBe("second");
    expect(history.forward()).toBe("");
    expect(history.index).toBe(-1);
  });

  it("forward at top returns empty string", async () => {
    history = await createHistory();
    history.push("cmd");
    expect(history.forward()).toBe("");
    expect(history.index).toBe(-1);
  });

  it("back on empty history returns empty string", async () => {
    history = await createHistory();
    expect(history.back()).toBe("");
  });

  it("reset sets index to -1", async () => {
    history = await createHistory();
    history.push("cmd");
    history.back();
    history.reset();
    expect(history.index).toBe(-1);
  });

  it("deduplicates consecutive identical commands", async () => {
    history = await createHistory();
    history.push("!email list");
    history.push("!email list");
    expect(history.entries).toEqual(["!email list"]);
  });

  it("pushes same command after different command", async () => {
    history = await createHistory();
    history.push("!email list");
    history.push("!journal write");
    history.push("!email list");
    expect(history.entries).toEqual([
      "!email list",
      "!journal write",
      "!email list",
    ]);
  });

  it("caps at 100 entries", async () => {
    history = await createHistory();
    for (let i = 0; i < 110; i++) {
      history.push(`cmd-${i}`);
    }
    expect(history.entries.length).toBe(100);
    expect(history.entries[0]).toBe("cmd-109");
    expect(history.entries[99]).toBe("cmd-10");
  });

  it("ignores empty push", async () => {
    history = await createHistory();
    history.push("");
    history.push("   ");
    expect(history.entries).toEqual([]);
  });

  it("uses different localStorage keys for different instances", async () => {
    const mod = await import("./commandHistory.svelte.js");
    const histA = mod.createCommandHistory("appA:hist");
    const histB = mod.createCommandHistory("appB:hist");

    histA.push("!a cmd");
    histB.push("!b cmd");

    // Ensure setItem was called with different keys
    const calls = lsMock.setItem.mock.calls;
    const keyFor = (key) => calls.filter(([k]) => k === key);
    expect(keyFor("appA:hist").length).toBeGreaterThan(0);
    expect(keyFor("appB:hist").length).toBeGreaterThan(0);
  });
});

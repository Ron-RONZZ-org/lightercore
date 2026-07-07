import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Must reset modules so $state re-run for each test
let banner;

beforeEach(async () => {
  vi.resetModules();
  const mod = await import("./bannerStore.svelte.js");
  banner = mod.banner;
});

describe("bannerStore", () => {
  it("starts with no visible banner", () => {
    expect(banner.visible).toBe(false);
    expect(banner.message).toBe("");
    expect(banner.type).toBe("success");
  });

  it("show sets message, type, and makes visible", () => {
    banner.show("Hello world", "info");
    expect(banner.visible).toBe(true);
    expect(banner.message).toBe("Hello world");
    expect(banner.type).toBe("info");
  });

  it("show defaults to success type and 3000ms duration", () => {
    vi.useFakeTimers();
    banner.show("Test message");
    expect(banner.visible).toBe(true);
    expect(banner.type).toBe("success");

    // Should auto-dismiss after 3000ms
    vi.advanceTimersByTime(3000);
    expect(banner.visible).toBe(false);
    expect(banner.message).toBe("");
    vi.useRealTimers();
  });

  it("show accepts custom duration", () => {
    vi.useFakeTimers();
    banner.show("Long banner", "error", 5000);
    expect(banner.visible).toBe(true);

    vi.advanceTimersByTime(3000);
    expect(banner.visible).toBe(true); // still visible at 3s

    vi.advanceTimersByTime(2000);
    expect(banner.visible).toBe(false); // dismissed at 5s
    vi.useRealTimers();
  });

  it("dismiss hides banner immediately", () => {
    banner.show("Will be dismissed", "error");
    expect(banner.visible).toBe(true);

    banner.dismiss();
    expect(banner.visible).toBe(false);
    expect(banner.message).toBe("");
  });

  it("dismiss clears the timer so auto-dismiss doesn't fire after manual dismiss", () => {
    vi.useFakeTimers();
    banner.show("Message", "success", 5000);
    banner.dismiss();

    // Advance past the original timer
    vi.advanceTimersByTime(5000);
    expect(banner.visible).toBe(false); // still hidden, no crash
    vi.useRealTimers();
  });

  it("show replaces a visible banner and resets its timer", () => {
    vi.useFakeTimers();
    banner.show("First", "info", 10000);
    banner.show("Second", "error", 2000);

    expect(banner.message).toBe("Second");
    expect(banner.type).toBe("error");

    // Advance past the second's duration — first's timer was cancelled
    vi.advanceTimersByTime(2000);
    expect(banner.visible).toBe(false);
    vi.useRealTimers();
  });
});

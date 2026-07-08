import { describe, it, expect, vi, beforeEach } from "vitest";

// Ensure alert exists in node test environment (used by showPreviewInTab error path)
if (typeof globalThis.alert !== "function") {
  globalThis.alert = vi.fn();
}

describe("createPreviewState", () => {
  let createPreviewState;
  let fetchSpy;

  beforeEach(async () => {
    vi.restoreAllMocks();
    const mod = await import("./preview.svelte.js");
    createPreviewState = mod.createPreviewState;
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  it("returns initial state with showing=false", () => {
    const state = createPreviewState();
    expect(state.showing).toBe(false);
    expect(state.htmlContent).toBe("");
    expect(state.title).toBe("Preview");
  });

  it("show fetches render-preview and sets htmlContent", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ html: "<p>Hello</p>" }),
    });

    const state = createPreviewState();
    await state.show("Hello", "markdown", "Test Preview");
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/render-preview", expect.any(Object));
    expect(state.showing).toBe(true);
    expect(state.htmlContent).toBe("<p>Hello</p>");
    expect(state.title).toBe("Test Preview");
  });

  it("show handles network error gracefully", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("Network failure"));

    const state = createPreviewState();
    await state.show("Hello", "markdown");
    expect(state.showing).toBe(true);
    expect(state.htmlContent).toContain("Network failure");
  });

  it("close resets state", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ html: "<p>Hello</p>" }),
    });

    const state = createPreviewState();
    await state.show("Hello", "markdown");
    expect(state.showing).toBe(true);

    state.close();
    expect(state.showing).toBe(false);
    expect(state.htmlContent).toBe("");
  });

  it("show with empty content does nothing", async () => {
    const state = createPreviewState();
    await state.show("", "markdown");
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(state.showing).toBe(false);
  });
});

describe("showPreviewInTab", () => {
  let showPreviewInTab;
  let fetchSpy;

  beforeEach(async () => {
    vi.restoreAllMocks();
    const mod = await import("./preview.svelte.js");
    showPreviewInTab = mod.showPreviewInTab;
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  it("calls fetch with correct args", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ html: "<p>Hello</p>" }),
    });

    await showPreviewInTab("Hello", "markdown");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/render-preview",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("Hello"),
      })
    );
  });

  it("empty content does nothing", async () => {
    await showPreviewInTab("", "markdown");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

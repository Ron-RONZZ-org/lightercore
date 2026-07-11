/**
 * Tests for conversationUtils.js — pure JS helper, no DOM required.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { formatConversationText, copyToClipboard } from "./conversationUtils.js";

describe("formatConversationText", () => {
  it("returns empty string for empty messages", () => {
    expect(formatConversationText([])).toBe("");
  });

  it("filters out messages without role", () => {
    const msgs = [
      { role: "user", text: "Hello" },
      { role: "assistant", text: "Hi" },
      { nonsense: true },
    ];
    const result = formatConversationText(msgs);
    expect(result).toContain("[You] Hello");
    expect(result).toContain("[Assistant] Hi");
  });

  it("formats user and assistant messages", () => {
    const msgs = [
      { role: "user", text: "!node list" },
      { role: "assistant", text: "Here are the nodes" },
    ];
    const result = formatConversationText(msgs);
    expect(result).toBe("[You] !node list\n\n[Assistant] Here are the nodes");
  });

  it("strips HTML from html field when text is absent", () => {
    const msgs = [
      { role: "assistant", html: "<p>Hello <b>world</b></p>" },
    ];
    const result = formatConversationText(msgs);
    expect(result).toBe("[Assistant] Hello world");
  });

  it("prefers text over html when both present", () => {
    const msgs = [
      { role: "user", text: "plain text", html: "<p>HTML</p>" },
    ];
    const result = formatConversationText(msgs);
    expect(result).toBe("[You] plain text");
  });

  it("accepts custom labels", () => {
    const msgs = [
      { role: "user", text: "test" },
      { role: "assistant", text: "response" },
    ];
    const result = formatConversationText(msgs, {
      userLabel: "Human",
      assistantLabel: "Bot",
    });
    expect(result).toBe("[Human] test\n\n[Bot] response");
  });
});

describe("copyToClipboard", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls navigator.clipboard.writeText with given text", async () => {
    await copyToClipboard("hello");
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("hello");
  });

  it("does nothing for empty text", async () => {
    await copyToClipboard("");
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
    await copyToClipboard(null);
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
  });

  it("falls back to execCommand when clipboard API fails", async () => {
    navigator.clipboard.writeText.mockRejectedValue(new Error("denied"));
    const execCommand = vi.fn();
    document.execCommand = execCommand;
    const mockTa = {
      value: "",
      style: {},
      select: vi.fn(),
    };
    const createElement = vi.spyOn(document, "createElement").mockReturnValue(mockTa);
    const appendChild = vi.spyOn(document.body, "appendChild").mockReturnValue(null);
    const removeChild = vi.spyOn(document.body, "removeChild").mockReturnValue(null);

    await copyToClipboard("fallback text");

    expect(createElement).toHaveBeenCalledWith("textarea");
    expect(mockTa.value).toBe("fallback text");
    expect(mockTa.select).toHaveBeenCalled();
    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(removeChild).toHaveBeenCalledWith(mockTa);
  });
});

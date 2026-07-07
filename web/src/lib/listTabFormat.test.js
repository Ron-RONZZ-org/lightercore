import { describe, it, expect } from "vitest";

import {
  formatListItemDate,
  truncate,
  preview,
  createDialogTrap,
  sanitizeFilename,
  getLabel,
  shortId,
} from "./listTabFormat.js";

describe("formatListItemDate", () => {
  it("returns empty string for null/undefined", () => {
    expect(formatListItemDate(null)).toBe("");
    expect(formatListItemDate(undefined)).toBe("");
    expect(formatListItemDate("")).toBe("");
  });

  it("returns fallback for invalid date", () => {
    expect(formatListItemDate("not-a-date")).toBe("not-a-date");
  });

  it("returns time for today's date", () => {
    const today = new Date();
    const iso = today.toISOString();
    const result = formatListItemDate(iso);
    // Should contain time digits (not a full date)
    expect(result).toMatch(/\d{1,2}/);
  });
});

describe("truncate", () => {
  it("returns empty for null/undefined", () => {
    expect(truncate(null, 5)).toBe("");
    expect(truncate(undefined, 5)).toBe("");
  });

  it("returns string as-is if under max length", () => {
    expect(truncate("hello", 10)).toBe("hello");
  });

  it("truncates with ellipsis when exceeding max", () => {
    const result = truncate("hello world", 8);
    expect(result).toBe("hello w\u2026");
    expect(result.length).toBe(8);
  });

  it("handles exact length match", () => {
    expect(truncate("hello", 5)).toBe("hello");
  });
});

describe("preview", () => {
  it("returns empty for null/undefined", () => {
    expect(preview(null)).toBe("");
    expect(preview(undefined)).toBe("");
  });

  it("takes first line and strips markdown", () => {
    expect(preview("# Hello\nWorld", 20)).toBe(" Hello");
  });

  it("truncates to max length", () => {
    const long = "a".repeat(100);
    expect(preview(long, 10)).toBe("a".repeat(9) + "\u2026");
  });
});

describe("sanitizeFilename", () => {
  it("keeps alphanumeric and hyphens", () => {
    expect(sanitizeFilename("My File (1).txt", ".md")).toBe("MyFile1txt.md");
  });

  it("falls back to 'export' for empty input", () => {
    expect(sanitizeFilename("", ".md")).toBe("export.md");
    expect(sanitizeFilename(null, ".md")).toBe("export.md");
  });

  it("respects max length", () => {
    const long = "a".repeat(100);
    const result = sanitizeFilename(long, ".txt", 10);
    expect(result).toBe("a".repeat(10) + ".txt");
  });
});

describe("getLabel", () => {
  it("returns empty for null/undefined", () => {
    expect(getLabel(null)).toBe("");
    expect(getLabel(undefined)).toBe("");
  });

  it("parses JSON string labels", () => {
    expect(getLabel('{"en": "Hello", "fr": "Bonjour"}', "en")).toBe("Hello");
  });

  it("returns raw string if JSON parse fails", () => {
    expect(getLabel("plain-text", "en")).toBe("plain-text");
  });

  it("matches exact locale first", () => {
    const labels = { en: "Hello", fr: "Bonjour", "en-US": "Howdy" };
    expect(getLabel(labels, "en-US")).toBe("Howdy");
  });

  it("falls back to language prefix", () => {
    const labels = { en: "Hello", fr: "Bonjour" };
    expect(getLabel(labels, "en-GB")).toBe("Hello");
  });

  it("falls back to any language when English missing", () => {
    const labels = { fr: "Bonjour", de: "Hallo" };
    expect(getLabel(labels, "es")).toBe("Bonjour");
  });

  it("falls back to any language when English missing", () => {
    const labels = { fr: "Bonjour" };
    expect(getLabel(labels, "es")).toBe("Bonjour");
  });
});

describe("shortId", () => {
  it("returns empty for null/undefined", () => {
    expect(shortId(null)).toBe("");
    expect(shortId(undefined)).toBe("");
  });

  it("extracts fragment after #", () => {
    expect(shortId("http://example.org#Foo")).toBe("Foo");
  });

  it("extracts last path segment after /", () => {
    expect(shortId("http://example.org/ontology/Person")).toBe("Person");
  });

  it("handles prefixed IDs (no slash/hash)", () => {
    expect(shortId("ex:knows")).toBe("ex:knows");
  });

  it("handles plain IDs", () => {
    expect(shortId("Person")).toBe("Person");
  });
});

describe("createDialogTrap", () => {
  it("returns a function", () => {
    const trap = createDialogTrap(() => null);
    expect(typeof trap).toBe("function");
  });

  it("handles null container gracefully", () => {
    const trap = createDialogTrap(() => null);
    // Should not throw
    trap({ key: "Tab", preventDefault: () => {} });
  });
});

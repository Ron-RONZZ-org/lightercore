import { describe, it, expect } from "vitest";
import { splitCommands, isMultiCommand } from "./multiCommand.js";

describe("splitCommands", () => {
  it("returns empty array for empty input", () => {
    expect(splitCommands("")).toEqual([]);
  });

  it("returns empty array for input that doesn't start with !", () => {
    expect(splitCommands("hello world")).toEqual([]);
    expect(splitCommands("/*weekly")).toEqual([]);
    expect(splitCommands("")).toEqual([]);
  });

  it("returns single command as-is for single !-command", () => {
    const result = splitCommands("!email list");
    expect(result).toEqual(["!email list"]);
  });

  it("splits multiple commands separated by !", () => {
    const result = splitCommands("!email list !todo list");
    expect(result).toEqual(["!email list", "!todo list"]);
  });

  it("splits multiple commands with arguments and flags", () => {
    const result = splitCommands(
      "!email account modify ron@ronzz.org --redetect !email account modify hi@rongzhou.me --redetect",
    );
    expect(result).toEqual([
      "!email account modify ron@ronzz.org --redetect",
      "!email account modify hi@rongzhou.me --redetect",
    ]);
  });

  it("does NOT split on ! inside double-quoted strings", () => {
    const result = splitCommands('!todo add "urgent! fix bug"');
    expect(result).toEqual(['!todo add "urgent! fix bug"']);
  });

  it("does NOT split on ! inside single-quoted strings", () => {
    const result = splitCommands("!todo add 'urgent! fix bug'");
    expect(result).toEqual(["!todo add 'urgent! fix bug'"]);
  });

  it("correctly splits when quoted strings are followed by more commands", () => {
    const result = splitCommands(
      '!todo add "task one" --priority high !email list',
    );
    expect(result).toEqual([
      '!todo add "task one" --priority high',
      "!email list",
    ]);
  });

  it("handles mixed quote types correctly", () => {
    const result = splitCommands(
      '!todo add "double!quote" \'single!quote\' !email list',
    );
    expect(result).toEqual([
      '!todo add "double!quote" \'single!quote\'',
      "!email list",
    ]);
  });

  it("handles consecutive ! markers (second ! absorbed into next command)", () => {
    // `!!` means the first `!` is the boundary, the second `!` is just
    // part of the next command's prefix. This is not a realistic input
    // but validates the parser doesn't crash or create empty parts.
    const result = splitCommands("!email list !!todo list");
    expect(result).toEqual(["!email list", "!!todo list"]);
  });

  it("handles leading whitespace before first !", () => {
    const result = splitCommands("  !email list !todo list");
    expect(result).toEqual(["!email list", "!todo list"]);
  });

  it("handles trailing whitespace", () => {
    const result = splitCommands("!email list !todo list   ");
    expect(result).toEqual(["!email list", "!todo list"]);
  });

  it("returns single command when there is no second !", () => {
    const result = splitCommands("!email list");
    expect(result).toEqual(["!email list"]);
  });

  it("does not split on ! that is part of a URL or token", () => {
    // ! inside a URL path (not between commands) — no space before it
    const result = splitCommands("!search term!with!bangs");
    expect(result).toEqual(["!search term!with!bangs"]);
  });

  it("parses multiple commands with complex flags", () => {
    const result = splitCommands(
      "!calendar event add --title Meeting --date 2026-07-10 !email send to@x.com",
    );
    expect(result).toEqual([
      "!calendar event add --title Meeting --date 2026-07-10",
      "!email send to@x.com",
    ]);
  });

  it("handles many commands in one batch", () => {
    const result = splitCommands(
      "!cmd1 !cmd2 !cmd3 !cmd4 !cmd5",
    );
    expect(result).toEqual([
      "!cmd1", "!cmd2", "!cmd3", "!cmd4", "!cmd5",
    ]);
  });
});

describe("isMultiCommand", () => {
  it("returns false for single !-command", () => {
    expect(isMultiCommand("!email list")).toBe(false);
  });

  it("returns true for multiple commands", () => {
    expect(isMultiCommand("!email list !todo list")).toBe(true);
  });

  it("returns false for non-command input", () => {
    expect(isMultiCommand("hello world")).toBe(false);
  });

  it("returns false for empty input", () => {
    expect(isMultiCommand("")).toBe(false);
  });

  it("returns false for single !-command with quoted content", () => {
    expect(isMultiCommand('!todo add "urgent! fix bug"')).toBe(false);
  });
});

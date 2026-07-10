/**
 * Multi-command input support — split a !-prefixed input containing multiple
 * commands separated by `!` (at command boundaries) into individual command strings.
 *
 * The split rule tracks quote state so that `!` characters inside quoted
 * argument strings (single or double quotes) are NOT treated as command
 * boundaries. For example:
 *
 *   "!todo add \"urgent! fix bug\""       → ["!todo add \"urgent! fix bug\""]  (1 command)
 *   "!email list !todo list"              → ["!email list", "!todo list"]       (2 commands)
 *   "!todo add 'high!' !other"            → ["!todo add 'high!'", "!other"]     (2 commands)
 */

/**
 * Split a multi-command input into individual command strings.
 *
 * @param {string} input — raw user input (e.g. `"!email list !todo list"`)
 * @returns {string[]} — individual command strings, each prefixed with `!`.
 *   Returns an empty array if input is empty or does not start with `!`.
 *
 * @example
 * splitCommands("!email list !todo list")
 * // → ["!email list", "!todo list"]
 *
 * @example
 * splitCommands("!todo add \"urgent! fix bug\"")
 * // → ["!todo add \"urgent! fix bug\""]   // inner `!` inside quotes is not a boundary
 */
export function splitCommands(input) {
  const trimmed = input.trimStart();
  if (!trimmed || !trimmed.startsWith("!")) return [];

  const parts = [];
  let start = 0;
  let inSingleQuote = false;
  let inDoubleQuote = false;

  for (let i = 1; i < trimmed.length; i++) {
    const ch = trimmed[i];

    // Track quote state — only split on `!` when NOT inside quotes
    if (ch === '"' && !inSingleQuote) {
      inDoubleQuote = !inDoubleQuote;
    } else if (ch === "'" && !inDoubleQuote) {
      inSingleQuote = !inSingleQuote;
    }

    // `!` preceded by whitespace is a command boundary (but only outside quotes)
    if (ch === "!" && !inSingleQuote && !inDoubleQuote && trimmed[i - 1] === " ") {
      const prev = trimmed.slice(start, i).trimEnd();
      if (prev) parts.push(prev);
      start = i;
    }
  }

  // Capture the last (or only) command
  const last = trimmed.slice(start).trimEnd();
  if (last) parts.push(last);

  return parts;
}

/**
 * Check whether the input contains multiple !-prefixed commands.
 *
 * @param {string} input — raw user input
 * @returns {boolean}
 *
 * @example
 * isMultiCommand("!email list !todo list")   // → true
 * isMultiCommand("!email list")              // → false
 * isMultiCommand("hello world")              // → false
 */
export function isMultiCommand(input) {
  return splitCommands(input).length > 1;
}

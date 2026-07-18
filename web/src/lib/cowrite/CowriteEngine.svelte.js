/**
 * CowriteEngine — shared state management for LLM co-writing sessions.
 *
 * Usage (in a form component):
 *   import { createCowrite } from "@lightercore/ui/cowrite/index.js";
 *   let cowrite = $state(createCowrite({
 *     formType: "node-add-concept",
 *     getCurrentContent: () => ({ label: labelText, definition: defText }),
 *     applyEdit: (field, text) => { if (field === "label") labelText = text; ... }
 *   }));
 *
 * Then in the template:
 *   <CowriteButton cowrite={cowrite} />
 *   {#if cowrite.isActive}
 *     <CowritePanel cowrite={cowrite} />
 *   {/if}
 */

/**
 * @typedef {Object} EditOp
 * @property {"equal"|"replace"|"delete"|"insert"} tag
 * @property {number} start_orig
 * @property {number} end_orig
 * @property {string} deleted
 * @property {string} inserted
 */

/**
 * @typedef {Object} CowriteResult
 * @property {Object.<string, EditOp[]>} edits
 * @property {Object.<string, string>} revised
 * @property {Object.<string, string>} original
 * @property {string} session_id
 */

/**
 * @typedef {Object} FieldEdit
 * @property {string} field — field name
 * @property {string} original — original text
 * @property {string} revised — revised full text
 * @property {EditOp[]} ops — computed diff operations
 * @property {boolean} accepted — user accepted this field
 * @property {boolean} rejected — user rejected this field
 */

/**
 * Create a cowrite session for a form.
 *
 * @param {Object} opts
 * @param {string} opts.formType — e.g. "node-add-concept", "triple-add"
 * @param {() => Object.<string, string>} opts.getCurrentContent — callback returning current form fields
 * @param {(field: string, text: string) => void} opts.applyEdit — callback to apply revised text to a field
 * @returns {Object} cowrite session object
 */
export function createCowrite(opts) {
  const { formType, getCurrentContent, applyEdit } = opts;

  /** @type {boolean} */
  let isActive = $state(false);
  /** @type {boolean} */
  let isLoading = $state(false);
  /** @type {string} */
  let instruction = $state("");
  /** @type {string} */
  let error = $state("");
  /** @type {FieldEdit[]} */
  let fieldEdits = $state([]);
  /** @type {string} */
  let sessionId = $state("");
  /** @type {Object|null} */
  let embedRequired = $state(null);  // {models: [...]} when embed needed

  /**
   * Open the co-writing panel (even without an instruction yet).
   * The user can then type an instruction and hit "Ask LLM".
   */
  function openPanel() {
    isActive = true;
    error = "";
  }

  /**
   * Start a co-writing request with the given instruction.
   * @param {string} instr
   */
  async function startCowrite(instr) {
    const trimmed = (instr || instruction).trim();
    isActive = true;
    if (!trimmed) return;
    instruction = trimmed;

    isLoading = true;
    error = "";
    fieldEdits = [];

    const fields = getCurrentContent();

    try {
      const resp = await fetch("/api/v1/cowrite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          form_type: formType,
          fields,
          instruction: trimmed,
        }),
      });

      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        error = detail.detail || "Co-writing request failed";
        isLoading = false;
        return;
      }

      /** @type {CowriteResult} */
      const result = await resp.json();

      // Embedding not available — signal parent to show install dialog
      if (result._embed_required) {
        embedRequired = { models: result.models || [] };
        isLoading = false;
        return;
      }

      sessionId = result.session_id;

      /** @type {FieldEdit[]} */
      const edits = Object.entries(result.edits).map(([field, ops]) => ({
        field,
        original: result.original[field],
        revised: result.revised[field],
        ops,
        accepted: false,
        rejected: false,
      }));

      fieldEdits = edits;
    } catch (err) {
      error = err.message || "Network error";
    } finally {
      isLoading = false;
    }
  }

  /** Accept all edits for all fields. */
  function acceptAll() {
    for (const fe of fieldEdits) {
      if (!fe.accepted && !fe.rejected) {
        applyEdit(fe.field, fe.revised);
        fe.accepted = true;
      }
    }
    fieldEdits = [...fieldEdits]; // trigger reactivity
  }

  /** Reject all edits (revert to original). */
  function rejectAll() {
    for (const fe of fieldEdits) {
      if (!fe.accepted && !fe.rejected) {
        applyEdit(fe.field, fe.original);
        fe.rejected = true;
      }
    }
    fieldEdits = [...fieldEdits]; // trigger reactivity
  }

  /** Accept a single field edit. */
  function acceptEdit(index) {
    const fe = fieldEdits[index];
    if (!fe || fe.accepted || fe.rejected) return;
    applyEdit(fe.field, fe.revised);
    fe.accepted = true;
    fieldEdits = [...fieldEdits];
  }

  /** Reject a single field edit. */
  function rejectEdit(index) {
    const fe = fieldEdits[index];
    if (!fe || fe.accepted || fe.rejected) return;
    applyEdit(fe.field, fe.original);
    fe.rejected = true;
    fieldEdits = [...fieldEdits];
  }

  /** Close the panel and reset state. */
  function close() {
    isActive = false;
    fieldEdits = [];
    error = "";
    instruction = "";
    sessionId = "";
  }

  /** Check if there are any unprocessed edits. */
  let hasUnprocessed = $derived(
    fieldEdits.some((fe) => !fe.accepted && !fe.rejected)
  );

  return {
    get isActive() { return isActive; },
    get isLoading() { return isLoading; },
    get instruction() { return instruction; },
    get error() { return error; },
    get fieldEdits() { return fieldEdits; },
    get sessionId() { return sessionId; },
    get hasUnprocessed() { return hasUnprocessed; },
    get embedRequired() { return embedRequired; },
    startCowrite,
    openPanel,
    acceptAll,
    rejectAll,
    acceptEdit,
    rejectEdit,
    close,
  };
}

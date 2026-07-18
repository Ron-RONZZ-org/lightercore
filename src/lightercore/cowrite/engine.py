"""Core co-writing engine — protocol prompt, session, diff computation.

This module contains the PROTOCOL LAYER of the co-writing prompt.
It is NEVER user-editable. See ``style.py`` for the user-editable style
layer, and call ``cowrite()`` from the app's route handler.

The app is responsible for:
1. Providing a chat function (``chat_fn``) — typically ``provider.chat``
   from a configured :class:`~lightercore.llm.base.BaseLLMProvider`.
2. Pre-loading style content via ``load_cowrite_style()`` from ``style.py``.
3. Gathering app-specific context (writing samples, etc.) if desired.
"""

from __future__ import annotations

import difflib
import json
import logging
import uuid as _uuid
from typing import Any

logger = logging.getLogger(__name__)

# ── Protocol prompt (hardcoded, NEVER user-editable) ────────────────────────

COWRITE_PROTOCOL_PROMPT = """You are a writing assistant. Your job is to help the user improve, rewrite, or expand text they are composing.

CRITICAL RULES — Read carefully. Violating these breaks the feature:

1. You MUST return the COMPLETE revised text for EVERY field, not just the changes or a summary.
2. Return ONLY a valid JSON object. No markdown, no explanation, no extra text.
3. The JSON keys MUST be the exact field names from the request. Do not add or remove fields.
4. Each field value must be the FULL revised text — not truncated, not a description of changes.
5. Preserve all original content unless the user asks you to change it.
6. If you cannot improve anything meaningful, return the original text unchanged.

Examples of what NOT to do:
  BAD:  {"body": "fixed typo: ths \u2192 this"}            \u2190 description, not full text
  BAD:  {"body": "This is the first paragraph"}         \u2190 truncated
  BAD:  {"subject": "..."}                               \u2190 missing "body" field
  BAD:  Here is the revised text: {"body": "..."}        \u2190 extra text outside JSON

GOOD: {"subject": "Complete revised subject", "body": "Complete revised body text including all original content with improvements applied."}

RESPONSE FORMAT (JSON only):
{
  "field_name_1": "Complete revised text for field 1",
  "field_name_2": "Complete revised text for field 2"
}

WRITING SAMPLES \u2014 You may receive ``writing_samples`` in the ``context``
section of the request.  These are real examples of the user's past
writing.  Use them to match the user's personal style: tone, sentence
structure, vocabulary, formality level, paragraph length, and typical
sign-offs.  Do NOT copy content from the samples \u2014 draw style
inspiration only.
"""


# ── Diff data structures ────────────────────────────────────────────────────


class EditOp:
    """A single edit operation from the diff.

    Attributes:
        tag: ``"equal"``, ``"replace"``, ``"delete"``, or ``"insert"``.
        start_orig: Start index in original text.
        end_orig: End index in original text.
        deleted: The text being removed (for replace/delete).
        inserted: The text being added (for replace/insert).
    """

    __slots__ = ("deleted", "end_orig", "inserted", "start_orig", "tag")

    def __init__(
        self,
        tag: str,
        start_orig: int = 0,
        end_orig: int = 0,
        deleted: str = "",
        inserted: str = "",
    ) -> None:
        self.tag = tag
        self.start_orig = start_orig
        self.end_orig = end_orig
        self.deleted = deleted
        self.inserted = inserted

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "start_orig": self.start_orig,
            "end_orig": self.end_orig,
            "deleted": self.deleted,
            "inserted": self.inserted,
        }


def compute_diffs(original: str, revised: str) -> list[dict[str, Any]]:
    """Compute structured diffs between original and revised text.

    Uses ``difflib.SequenceMatcher`` to produce character-level edit
    operations. The LLM returns *full revised text* and this function
    computes the exact changes.

    Args:
        original: The original text.
        revised: The revised (LLM-returned) text.

    Returns:
        List of ``EditOp`` dicts with keys ``tag``, ``start_orig``,
        ``end_orig``, ``deleted``, ``inserted``.
    """
    matcher = difflib.SequenceMatcher(None, original, revised)
    ops: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            if i2 - i1 > 0:
                ops.append(EditOp("equal", i1, i2).to_dict())
        elif tag == "replace":
            ops.append(
                EditOp("replace", i1, i2, original[i1:i2], revised[j1:j2]).to_dict()
            )
        elif tag == "delete":
            ops.append(EditOp("delete", i1, i2, original[i1:i2]).to_dict())
        elif tag == "insert":
            ops.append(EditOp("insert", i1, i1, inserted=revised[j1:j2]).to_dict())
    return ops


# ── Response parsing ────────────────────────────────────────────────────────


def _validate_response(
    result: dict[str, Any],
    expected_fields: set[str],
) -> dict[str, str]:
    """Validate and normalize the LLM response.

    Ensures every expected field is present (empty strings OK for optional fields).

    Args:
        result: Parsed JSON from the LLM.
        expected_fields: Set of field names that must be present.

    Returns:
        Dict mapping field name \u2192 full revised text.

    Raises:
        ValueError: If fields are missing or empty.
    """
    validated: dict[str, str] = {}
    for field in expected_fields:
        val = result.get(field)
        if val is None or not isinstance(val, str) or not val.strip():
            raise ValueError(
                f"LLM response missing or empty field '{field}'. "
                f"Expected fields: {expected_fields}"
            )
        validated[field] = val
    return validated


def _clean_llm_response(raw: str, expected_fields: set[str]) -> dict[str, str]:
    """Parse and validate LLM JSON response, stripping markdown fences.

    Handles common LLM wrapping patterns: markdown code fences,
    surrounding explanatory text, etc.

    Args:
        raw: Raw response string from the LLM.
        expected_fields: Set of field names that must be present.

    Returns:
        Dict mapping field name to full revised text.

    Raises:
        ValueError: If the response cannot be parsed or validated.
    """
    cleaned = raw.strip()
    # Strip markdown code fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0] if "```" in cleaned else cleaned
        cleaned = cleaned.strip()
    # Strip leading/trailing non-JSON text
    brace_start = cleaned.find("{")
    brace_end = cleaned.rfind("}")
    if brace_start != -1 and brace_end != -1:
        cleaned = cleaned[brace_start : brace_end + 1]

    parsed: dict[str, Any] = json.loads(cleaned)
    return _validate_response(parsed, expected_fields)


# ── Main co-writing function ────────────────────────────────────────────────


async def cowrite(
    form_type: str,
    fields: dict[str, str],
    instruction: str,
    *,
    chat_fn: Any,
    style_content: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the co-writing flow: build prompt, call LLM, compute diffs.

    Args:
        form_type: Type of form (``"node-add"``, ``"triple-add"``, etc.).
        fields: Current content ``{field_name: text}``.
        instruction: User's instruction for the LLM (e.g. "make it formal").
        chat_fn: Async callable ``(messages, stream=False) -> str``.
            Typically ``provider.chat`` from a BaseLLMProvider subclass.
            The app is responsible for providing a *raw* chat function
            (no injected system prompt).
        style_content: Pre-loaded user style guide (from
            ``load_cowrite_style()``), or ``None``.
        context: Optional app-specific context dict (writing samples, etc.).

    Returns:
        Dict with keys:
            - ``edits``: ``{field: [EditOp_dict, ...]}``
            - ``revised``: ``{field: revised_text}``
            - ``original``: ``{field: original_text}``
            - ``session_id``: str

    Raises:
        RuntimeError: If the LLM call fails or returns empty.
        ValueError: If the LLM response is malformed.
    """
    # Build system content: protocol + optional style
    system_content = COWRITE_PROTOCOL_PROMPT
    if style_content:
        system_content += "\n\n## User Style Guide\n\n" + style_content

    # Build user message
    ctx = context or {}
    user_content = json.dumps(
        {
            "form_type": form_type,
            "instruction": instruction,
            "fields": {k: {"current": v} for k, v in fields.items()},
            "context": ctx,
        },
        indent=2,
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    expected_fields = set(fields.keys())

    # Call LLM
    try:
        raw_response = await chat_fn(messages, stream=False)
    except Exception as exc:
        logger.warning("Cowrite LLM call failed: %s", exc)
        raise RuntimeError(f"LLM call failed: {exc}") from exc

    if not raw_response or not raw_response.strip():
        raise RuntimeError("LLM returned empty response.")

    validated = _clean_llm_response(raw_response, expected_fields)

    # Length-sanity check: keep a threshold of 25% to catch truncation
    for field in expected_fields:
        orig_len = len(fields[field])
        rev_len = len(validated[field])
        if orig_len > 10 and rev_len < orig_len * 0.25:
            logger.warning(
                "Possible truncated LLM response for '%s': "
                "%d vs %d original chars (<25%% threshold)",
                field,
                rev_len,
                orig_len,
            )

    # Compute diffs
    edits: dict[str, list[dict[str, Any]]] = {}
    for field in expected_fields:
        edits[field] = compute_diffs(fields[field], validated[field])

    session_id = str(_uuid.uuid4())

    return {
        "edits": edits,
        "revised": validated,
        "original": fields,
        "session_id": session_id,
    }

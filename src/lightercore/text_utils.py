"""Basic text-processing utilities — sanitization, normalization, diacritic stripping, diffs.

These are pure functions with no project-specific dependencies. They are shared
across lightercore consumers (lighterbird, semantika) to avoid duplicating
common Unicode-safe identifier cleaning logic.

``EditOp`` and ``compute_diffs`` originally lived in ``lightercore.cowrite.engine``
and were moved here during the lighterllm split. They are pure stdlib with zero
LLM coupling.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any


# ── Diff data structures (moved from lightercore.cowrite.engine) ──────────────


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


# ── Original utilities ────────────────────────────────────────────────────────


def sanitize_node_id(raw_id: str) -> str:
    """Strip invisible Unicode characters from a node/predicate ID.

    Removes format characters (category ``Cf``, e.g. zero-width joiner, BOM)
    and control characters (category ``Cc``, e.g. null, tab — though tab is
    explicitly kept because it occasionally appears in pasted text). Visible
    whitespace (space, tab) is preserved.

    Args:
        raw_id: Arbitrary user-supplied ID string.

    Returns:
        Clean ID with invisible characters removed.
    """
    return "".join(
        ch for ch in raw_id.strip()
        if unicodedata.category(ch) not in ("Cf", "Cc")
        or ch in (" ", "\t")
    )


def normalize_label_to_id(label: str) -> str:
    """Convert a human-readable label into an ASCII-safe identifier.

    Pipeline:
    1. NFKD Unicode decomposition (é → e + combining acute).
    2. Strip non-ASCII characters (keeps only ``[A-Za-z0-9]`` — diacritics
       are decomposed and the combining marks discarded).
    3. Collapse runs of non-alphanumeric characters into a single ``_``.
    4. Strip leading/trailing ``_``.
    5. Convert to UPPERCASE.

    Args:
        label: A human label string (e.g. ``"Matière"``).

    Returns:
        A clean ASCII identifier (e.g. ``"MATIERE"``), or ``"_UNLABELED"``
        if the label produces an empty result after the pipeline.
    """
    nfkd = unicodedata.normalize("NFKD", label)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_str)
    safe = safe.strip("_")
    if not safe:
        return "_UNLABELED"
    return safe.upper()


def strip_diacritics(text: str) -> str:
    """Strip diacritical marks from text, keeping base ASCII characters.

    Uses NFKD decomposition to split base characters from combining marks,
    then discards all combining diacritical marks (category ``Mn``,
    ``Mc``, ``Me``). Non-ASCII letters that decompose to ASCII+marks are
    reduced to their ASCII base (e.g. ``â → a``, ``ĵ → j``, ``ü → u``).

    Non-letter characters (digits, punctuation, spaces) are preserved as-is.

    Args:
        text: Input string with potential diacritics.

    Returns:
        String with diacritics removed (e.g. ``"Matière"`` → ``"Matiere"``).
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(
        ch for ch in nfkd
        if unicodedata.category(ch) not in ("Mn", "Mc", "Me")
    )


__all__ = [
    "EditOp",
    "compute_diffs",
    "sanitize_node_id",
    "normalize_label_to_id",
    "strip_diacritics",
]

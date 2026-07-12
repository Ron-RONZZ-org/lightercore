"""Basic text-processing utilities — sanitization, normalization, diacritic stripping.

These are pure functions with no project-specific dependencies. They are shared
across lightercore consumers (lighterbird, semantika) to avoid duplicating
common Unicode-safe identifier cleaning logic.
"""

from __future__ import annotations

import re
import unicodedata


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

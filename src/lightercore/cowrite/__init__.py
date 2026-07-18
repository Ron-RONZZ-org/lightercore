"""Co-writing engine and style cascade for LLM-assisted editing.

This package provides the shared infrastructure for AI co-writing
("cowrite") — an LLM-powered editing assistant integrated into GUI forms.
Consumed by both lighterbird and semantika.

Usage (app-side — see each module for details)::

    from lightercore.cowrite.engine import cowrite
    from lightercore.cowrite.style import load_cowrite_style

    style = load_cowrite_style(config_dir(), form_type, ...)
    result = await cowrite(form_type, fields, instruction,
                           chat_fn=provider.chat,
                           style_content=style)
"""

from lightercore.cowrite.engine import (
    COWRITE_PROTOCOL_PROMPT,
    EditOp,
    _clean_llm_response,
    compute_diffs,
    cowrite,
)
from lightercore.cowrite.style import (
    cowrite_style_domain_path,
    cowrite_style_path,
    load_cowrite_style,
)

__all__ = [
    "COWRITE_PROTOCOL_PROMPT",
    "EditOp",
    "_clean_llm_response",
    "compute_diffs",
    "cowrite",
    "cowrite_style_domain_path",
    "cowrite_style_path",
    "load_cowrite_style",
]

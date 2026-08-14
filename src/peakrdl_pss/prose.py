"""Rendering SystemRDL ``desc`` text as PSS comment lines.

``desc`` is a first-class SystemRDL property, not a lexical comment: it is part
of the elaborated model and is *defined* as the documentation slot. That makes
it the only description in an RDL file worth carrying downstream -- ``//`` and
``/* */`` comments are discarded by the compiler long before an exporter sees
the design, and nothing in the elaborated model records that they existed.

What comes out of ``get_property("desc")`` is the source text verbatim,
including the newlines and indentation that wrapped it in the ``.rdl`` file.
Those are formatting, not content: a ``desc`` is a paragraph. So it is reflowed
here rather than transcribed, and the generated PSS is wrapped to its own width.
"""
import textwrap
from typing import List, Optional

#: Width of the *text*, excluding the indent and the `// ` marker. Keeps a
#: field's comment inside a conventional line width once both are added.
DEFAULT_WIDTH = 72


def desc_lines(desc: Optional[str], width: int = DEFAULT_WIDTH) -> List[str]:
    """*desc* as comment-ready lines, reflowed to *width*.

    Returns ``[]`` for a missing or blank description, so a template can
    iterate unconditionally.

    Paragraph breaks -- a blank line in the source -- are preserved, because
    they are the one piece of structure a `desc` reliably carries. Everything
    else collapses to a single space.
    """
    if not desc or not desc.strip():
        return []

    out: List[str] = []
    for para in desc.replace("\r\n", "\n").split("\n\n"):
        text = " ".join(para.split())
        if not text:
            continue
        if out:
            out.append("")
        out.extend(textwrap.wrap(text, width=width) or [])
    return out


def desc_inline(desc: Optional[str]) -> str:
    """*desc* collapsed to a single line, for a trailing comment."""
    if not desc:
        return ""
    return " ".join(desc.split())

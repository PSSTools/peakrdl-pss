"""The SystemRDL ``desc`` property reaching the generated PSS.

``desc`` is the only description in an RDL file worth exporting. ``//`` and
``/* */`` comments are lexical: the compiler discards them and the elaborated
model carries no record that they existed. ``desc`` is a property -- part of the
model, and *defined* by the standard as the documentation slot -- so it is
unambiguous about what it documents, with none of the positional guesswork a
comment needs.

It was extracted into the IR (``FieldRow.desc``, ``EnumMember.desc``) and
included in the change-detection signature long before anything emitted it, so
these tests pin the last step: that it reaches the output, and in a shape a
downstream consumer can use.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_text, export_str  # noqa: E402

from peakrdl_pss.prose import desc_inline, desc_lines  # noqa: E402


def _export(tmp_path, body: str) -> str:
    return export_str(compile_text(body, tmp_path), tmp_path)


def test_a_field_desc_becomes_a_comment_above_its_member(tmp_path):
    text = _export(tmp_path, """
        addrmap inline {
            reg {
                field { sw=rw; hw=r; desc = "Channel enable."; } ch_en[0:0];
            } csr @ 0x0;
        };
    """)
    lines = [l.strip() for l in text.split("\n")]
    i = lines.index("// Channel enable.")
    assert lines[i + 1].startswith("bit ch_en;")


def test_the_layout_facts_stay_beside_the_member(tmp_path):
    """Two comments, two positions, two different kinds of fact.

    The prose above is what nothing downstream can re-derive; the bit range and
    access mode beside it are re-derivable, and are what a reader scanning the
    struct wants on the same line.
    """
    text = _export(tmp_path, """
        addrmap inline {
            reg {
                field { sw=rw; hw=r; desc = "Channel enable."; } ch_en[0:0];
            } csr @ 0x0;
        };
    """)
    decl = next(l for l in text.split("\n") if "bit ch_en;" in l)
    assert "// [0] sw=rw hw=r" in decl
    assert "Channel enable." not in decl


def test_a_field_without_a_desc_is_unchanged(tmp_path):
    text = _export(tmp_path, """
        addrmap inline {
            reg {
                field { sw=rw; hw=r; } ch_en[0:0];
            } csr @ 0x0;
        };
    """)
    decl = [l for l in text.split("\n") if "bit ch_en;" in l]
    assert len(decl) == 1
    idx = text.split("\n").index(decl[0])
    assert "//" not in text.split("\n")[idx - 1] or "struct" in text.split("\n")[idx - 1]


def test_an_enum_member_desc_becomes_a_comment(tmp_path):
    text = _export(tmp_path, """
        addrmap inline {
            enum mode_e { off = 2'd0 { desc = "disabled"; }; on = 2'd1; };
            reg {
                field { sw=rw; hw=r; encode = mode_e; } mode[1:0];
            } csr @ 0x0;
        };
    """)
    lines = [l.strip() for l in text.split("\n")]
    i = lines.index("// disabled")
    assert lines[i + 1].startswith("static const")
    assert "mode_e__off" in lines[i + 1]


# --- reflowing --------------------------------------------------------------

def test_source_line_breaks_are_reflowed_not_transcribed():
    """A `desc` is a paragraph; the newlines in the .rdl are line-wrapping.

    Transcribing them would carry the RDL file's indentation into the PSS and
    wrap at whatever width that file happened to use.
    """
    desc = """One sentence that was
                wrapped across source lines
                with deep indentation."""
    assert desc_lines(desc, width=72) == [
        "One sentence that was wrapped across source lines with deep indentation."
    ]


def test_a_paragraph_break_survives():
    """The one piece of structure a `desc` reliably carries."""
    assert desc_lines("First para.\n\nSecond para.", width=72) == [
        "First para.", "", "Second para."]


def test_long_text_wraps_to_the_requested_width():
    out = desc_lines("word " * 40, width=30)
    assert len(out) > 1
    assert all(len(l) <= 30 for l in out)


def test_a_missing_or_blank_desc_yields_nothing():
    """So a template can iterate unconditionally."""
    assert desc_lines(None) == []
    assert desc_lines("") == []
    assert desc_lines("   \n  ") == []
    assert desc_inline(None) == ""


def test_desc_inline_collapses_to_one_line():
    assert desc_inline("a\n   b\n\n c ") == "a b c"

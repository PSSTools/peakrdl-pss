"""Byte-for-byte golden files.

Goldens are the only test that notices *formatting* regressions, and formatting
is most of what makes generated source reviewable.  They are also the test most
likely to be defeated by how it is maintained: an expectation edited by hand to
match new behavior is no longer a regression test, just a transcript.  So the
only supported way to update one is ``PEAKRDL_PSS_UPDATE_GOLDEN=1``, and the
resulting diff is reviewed like any other change.

Every golden case also runs the parser gate on its own output, so a golden can
never be "matches the expectation but does not parse".
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import assert_golden, assert_parses, compile_rdl, export_file  # noqa: E402

from conftest import corpus_names  # noqa: E402  isort:skip

#: Corpus designs rendered with default options.
DEFAULT_CASES = corpus_names()

#: (rdl, golden suffix, kwargs) for option-specific output shapes.
OPTION_CASES = [
    ("gaps", "pad_tail", {"pad_tail": True}),
    ("gaps", "rsvd_prefix", {"rsvd_prefix": "RESERVED"}),
    ("reset", "reset_consts", {"emit_reset_consts": True}),
    ("arrays_nd", "index_helpers", {"emit_index_helpers": True}),
    ("basic", "hier", {"type_style": "hier"}),
    ("basic", "no_pure", {"pure_components": False}),
    ("encode", "enums_off", {"emit_enums": "off"}),
    ("scalar_regs", "base_address", {"emit_top": True, "base_address": 0x8000_0000}),
]


@pytest.mark.parametrize("name", DEFAULT_CASES)
def test_default_golden(name, tmp_path):
    root = compile_rdl(name)
    path = export_file(root, tmp_path, name + ".pss", package_name=name)
    assert_golden(open(path).read(), name + ".pss")


@pytest.mark.parametrize(
    "name,label,kwargs", OPTION_CASES, ids=["%s-%s" % (c[0], c[1]) for c in OPTION_CASES]
)
def test_option_golden(name, label, kwargs, tmp_path):
    root = compile_rdl(name)
    stem = "%s__%s" % (name, label)
    path = export_file(root, tmp_path, stem + ".pss", package_name=name, **kwargs)
    assert_golden(open(path).read(), stem + ".pss")

    if kwargs.get("emit_top"):
        top = path[: -len(".pss")] + "_top.pss"
        assert_golden(open(top).read(), stem + "_top.pss")


# The parse check is a *separate* test rather than a tail call in the two above.
# require_pssparser() skips the whole test when the parser is absent, so folding
# the two together would report a golden comparison as "skipped" in any
# environment without the parser -- hiding, in the summary line, the one thing
# that suite exists to prove.
@pytest.mark.pssparser
@pytest.mark.parametrize(
    "name,label,kwargs",
    [(n, "default", {}) for n in DEFAULT_CASES] + OPTION_CASES,
    ids=list(DEFAULT_CASES) + ["%s-%s" % (c[0], c[1]) for c in OPTION_CASES],
)
def test_golden_output_parses(name, label, kwargs, tmp_path):
    root = compile_rdl(name)
    path = export_file(root, tmp_path, name + ".pss", package_name=name, **kwargs)
    paths = [path]
    if kwargs.get("emit_top"):
        paths.append(path[: -len(".pss")] + "_top.pss")
    assert_parses(*paths)


def test_enums_off_emits_no_encoding_constants(tmp_path):
    """A golden alone would not say *why* this file differs; assert the intent."""
    root = compile_rdl("encode")
    path = export_file(
        root, tmp_path, "off.pss", package_name="encode", emit_enums="off"
    )
    text = open(path).read()
    assert "static const" not in text
    assert "mode_e" not in text
    # ...and the fields that used the encoding are still there.
    assert "bit[2] mode;" in text


def test_sidecar_golden(tmp_path):
    """The sidecar is a published schema; pin its shape, not just its validity."""
    root = compile_rdl("access_matrix")
    side = str(tmp_path / "sidecar.json")
    export_file(
        root, tmp_path, "access_matrix.pss",
        package_name="access_matrix", sidecar_path=side,
    )
    assert_golden(open(side).read(), "access_matrix.sidecar.json")

"""Naming properties asserted over the emitted text, not over intentions.

Every check here scans the *output* for a class of illegal or ambiguous name.
Asserting over the text rather than the IR is deliberate: it is the text a PSS
tool compiles, and a bug in the templates could reintroduce a raw SystemRDL name
that the IR never carried.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_rdl, export_str  # noqa: E402

from peakrdl_pss.design import DesignScanner  # noqa: E402
from peakrdl_pss.identifiers import PSS_KEYWORDS  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

from conftest import corpus_names  # noqa: E402  isort:skip

_DECL = re.compile(
    r"^\s*(?:pure\s+)?(?:component|struct)\s+(\w+)|"          # type declarations
    r"^\s*(?:bit(?:\[\d+\])?|\w+_c)\s+(\w+)\s*[;\[]|"          # members
    r"^\s*static\s+const\s+bit\[\d+\]\s+(\w+)\s*=",            # constants
    re.M,
)


def _declared_names(text):
    for match in _DECL.finditer(text):
        for group in match.groups():
            if group:
                yield group


@pytest.mark.parametrize("name", corpus_names())
def test_no_declared_name_is_a_pss_keyword(name, tmp_path):
    text = export_str(
        compile_rdl(name), tmp_path, package_name="p",
        emit_reset_consts=True, emit_index_helpers=True,
    )
    offenders = sorted({n for n in _declared_names(text) if n in PSS_KEYWORDS})
    assert not offenders, (
        "%s emits PSS keyword(s) as declared name(s): %s" % (name, offenders)
    )


@pytest.mark.parametrize("name", corpus_names())
def test_emitted_type_names_are_unique(name):
    design = DesignScanner(ExportOptions(package_name="p")).scan(compile_rdl(name).top)
    names = (
        [rt.struct_name for rt in design.reg_types]
        + [rt.component_name for rt in design.reg_types]
        + [gt.component_name for gt in design.group_types]
        + [et.name for et in design.enums]
    )
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, "duplicate emitted type name(s): %s" % duplicates


@pytest.mark.parametrize("name", corpus_names())
def test_member_names_are_unique_within_each_component(name):
    design = DesignScanner(
        ExportOptions(package_name="p", emit_reset_consts=True)
    ).scan(compile_rdl(name).top)

    for gt in design.group_types:
        members = [c.inst_name for c in gt.children] + [c[0] for c in gt.reset_consts]
        dupes = sorted({m for m in members if members.count(m) > 1})
        assert not dupes, "%s declares %s twice" % (gt.component_name, dupes)

    for rt in design.reg_types:
        members = [f.name for f in rt.fields]
        dupes = sorted({m for m in members if members.count(m) > 1})
        assert not dupes, "%s declares %s twice" % (rt.struct_name, dupes)


def test_reset_const_never_takes_an_instance_name():
    """Instance names win collisions; the constant is what gets renamed.

    Renaming the instance instead would silently change the key of
    get_offset_of_instance -- so a design with a register called ``ctrl_reset``
    next to ``ctrl`` would break every consumer that looks ``ctrl_reset`` up.
    """
    design = DesignScanner(
        ExportOptions(package_name="p", emit_reset_consts=True)
    ).scan(compile_rdl("reset").top)

    gt = next(g for g in design.group_types if g.reset_consts)
    inst_names = {c.inst_name for c in gt.children}
    assert "ctrl_reset" in inst_names, (
        "the register named 'ctrl_reset' lost its name to a generated constant"
    )
    for const_name, _, _ in gt.reset_consts:
        assert const_name not in inst_names, (
            "generated constant %r collides with an instance name" % const_name
        )


def test_keywords_corpus_renames_everything_it_must(tmp_path):
    text = export_str(compile_rdl("keywords"), tmp_path, package_name="p")
    # The RDL names are keywords; none may survive as a declared identifier.
    for keyword in ("component", "action", "pool", "state", "buffer", "struct"):
        assert not re.search(r"\b%s\s+\w+\s*;" % keyword, text), (
            "keyword %r survived into a declaration" % keyword
        )
    # ...but the mangled forms must be present, i.e. nothing was dropped.
    for expected in ("component_", "action_", "pool_", "state_", "buffer_",
                     "struct_", "reg_c_"):
        assert expected in text, "expected mangled name %r is missing" % expected


def test_escaped_rdl_identifier_drops_its_backslash(tmp_path):
    text = export_str(compile_rdl("keywords"), tmp_path, package_name="p")
    assert "\\" not in text, "an escaped SystemRDL identifier reached the output"
    # \reg is not a PSS keyword, so it should pass through unmangled.
    assert re.search(r"^\s+bit\[4\] reg;", text, re.M), (
        "escaped \\reg should emit as plain 'reg' -- it is legal in PSS"
    )

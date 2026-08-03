import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peakrdl_pss.identifiers import (  # noqa: E402
    PSS_IMPORTED_NAMES,
    PSS_KEYWORDS,
    Namespace,
    is_legal_identifier,
    mangle,
)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEXER = os.path.join(REPO, "packages", "pssparser", "src", "PSSLexer.g4")
SPEC = os.path.join(REPO, "PSS 3.1 Draft 19 2026.07.14 clean.md")


def _lexer_keywords():
    if not os.path.exists(LEXER):
        pytest.skip("pssparser grammar not available")
    out = set()
    with open(LEXER, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^[A-Z_0-9]+\s*:\s*'([a-z_][a-z_0-9]*)'\s*;?\s*$", line)
            if m:
                out.add(m.group(1))
    return out


def test_keyword_table_covers_the_parser_grammar():
    """The table must be a *superset* of what pssparser tokenizes as a keyword.

    Superset rather than equality on purpose: the spec's Table 3 and the parser
    grammar do not agree exactly (the parser accepts 'mutable' and 'pyimport',
    which Table 3 omits; the spec reserves 'this' and 'pre_body', which the
    parser does not tokenize). Mangling against the union is strictly safer than
    either source, and this assertion is what makes a parser upgrade that adds a
    keyword show up as a test failure rather than as a mystery syntax error in
    generated output.
    """
    missing = sorted(_lexer_keywords() - PSS_KEYWORDS)
    assert not missing, (
        "pssparser tokenizes these as keywords but PSS_KEYWORDS does not list "
        "them: %s" % missing
    )


def test_keyword_table_covers_the_spec_table():
    if not os.path.exists(SPEC):
        pytest.skip("PSS specification text not available")
    with open(SPEC, encoding="utf-8") as f:
        lines = f.read().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith("14.4 Keywords"))
    except StopIteration:  # pragma: no cover
        pytest.skip("keyword table not locatable in the specification text")

    spec = set()
    for line in lines[start : start + 30]:
        if not line.startswith("|"):
            continue
        for cell in line.split("|"):
            cell = cell.strip()
            if re.fullmatch(r"[a-z_][a-z_0-9]*", cell):
                spec.add(cell)
    spec.discard("yieldman")  # table artifact from the PDF-to-markdown conversion

    missing = sorted(spec - PSS_KEYWORDS)
    assert not missing, "spec Table 3 keywords absent from PSS_KEYWORDS: %s" % missing


@pytest.mark.parametrize("word", ["component", "action", "pool", "struct", "bit"])
def test_keywords_are_not_legal_identifiers(word):
    assert not is_legal_identifier(word)


@pytest.mark.parametrize("word", ["foo", "_bar", "r1", "reg_x"])
def test_ordinary_names_are_legal(word):
    assert is_legal_identifier(word)


def test_keyword_gets_a_trailing_underscore():
    assert mangle("component", set()) == ("component_", True)


def test_imported_name_is_mangled_too():
    """reg_c is not a keyword, but a member named reg_c shadows addr_reg_pkg's
    component and produces a package that fails to link."""
    assert "reg_c" in PSS_IMPORTED_NAMES
    out, changed = mangle("reg_c", set())
    assert (out, changed) == ("reg_c_", True)


def test_escaped_rdl_identifier_loses_its_backslash():
    assert mangle("\\reg", set()) == ("reg", True)


def test_illegal_characters_are_replaced():
    assert mangle("a-b", set())[0] == "a_b"


def test_leading_digit_is_prefixed():
    out, _ = mangle("1st", set())
    assert is_legal_identifier(out)
    assert out == "_1st"


def test_collision_appends_then_numbers():
    taken = {"f"}
    assert mangle("f", taken) == ("f_", True)
    taken.add("f_")
    assert mangle("f", taken) == ("f_1", True)


def test_unchanged_name_reports_no_change():
    assert mangle("foo", set()) == ("foo", False)


def test_namespace_allocates_uniquely_and_records_renames():
    ns = Namespace()
    assert ns.allocate("f") == ("f", False)
    assert ns.allocate("f") == ("f_", True)
    assert ns.allocate("component") == ("component_", True)
    assert ns.mangled == {"f": "f_", "component": "component_"}


def test_namespace_reserve_blocks_a_later_allocation():
    ns = Namespace()
    ns.reserve("f")
    assert ns.allocate("f")[0] != "f"


def test_mangle_does_not_mutate_the_taken_set():
    """Callers decide what to reserve; two independent namespaces must not leak
    into each other through a shared set."""
    taken = {"f"}
    snapshot = set(taken)
    mangle("f", taken)
    assert taken == snapshot

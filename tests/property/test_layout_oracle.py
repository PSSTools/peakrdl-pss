"""Independently reconstruct each packed struct's bit assignment.

``packed_s<LITTLE_ENDIAN>`` assigns bits to members in declaration order,
starting at bit 0.  This test re-derives that assignment from the emitted member
*widths alone* -- deliberately ignoring the lsb/msb the IR records -- and asserts
each non-reserved member lands where the SystemRDL model says it should.

Ignoring the recorded lsb is the point.  A test that read ``row.lsb`` would be
checking that the field carries the number it was given, which is trivially true;
this one checks that the *emitted declaration order and widths* put the field at
the right bit, which is what a PSS tool will actually do.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_rdl  # noqa: E402

from peakrdl_pss.design import DesignScanner  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

from conftest import corpus_names  # noqa: E402  isort:skip


def _pack(rows):
    """Assign bits the way packed_s<LITTLE_ENDIAN> does: in declaration order."""
    placement = {}
    bit = 0
    for row in rows:
        placement[row.name] = (bit, bit + row.width - 1)
        bit += row.width
    return placement, bit


@pytest.mark.parametrize("name", corpus_names())
def test_packed_layout_matches_model(name):
    root = compile_rdl(name)
    top = root.top
    design = DesignScanner(ExportOptions(package_name=name)).scan(top)

    by_type = {rt.type_name: rt for rt in design.reg_types}
    checked = 0

    for rt in design.reg_types:
        placement, total = _pack(rt.fields)

        # Contiguity and origin: the properties that make packed_s usable at all.
        assert total <= rt.regwidth, (
            "%s packs %d bits into a %d-bit register" % (rt.type_name, total, rt.regwidth)
        )
        for row in rt.fields:
            lo, hi = placement[row.name]
            assert (lo, hi) == (row.lsb, row.msb), (
                "%s.%s: declaration order puts it at [%d:%d], model says [%d:%d]"
                % (rt.type_name, row.name, hi, lo, row.msb, row.lsb)
            )
            checked += 1

    # Now cross-check against the model itself, by path.
    for reg in top.descendants(unroll=False):
        if not hasattr(reg, "fields"):
            continue
        rt = _reg_type_for(reg, by_type, design)
        if rt is None:
            continue
        placement, _ = _pack(rt.fields)
        rdl_to_emitted = {r.rdl_name: r.name for r in rt.fields if not r.reserved}
        for fld in reg.fields():
            emitted = rdl_to_emitted.get(fld.inst_name)
            assert emitted is not None, (
                "field %s is missing from emitted type %s" % (fld.get_path(), rt.type_name)
            )
            lo, hi = placement[emitted]
            assert (lo, hi) == (fld.low, fld.high), (
                "%s lands at [%d:%d] in the emitted struct but occupies [%d:%d] "
                "in the model" % (fld.get_path(), hi, lo, fld.high, fld.low)
            )

    assert checked, "layout oracle checked no fields in %s" % name


def _reg_type_for(reg, by_type, design):
    path = reg.get_path()
    for rt in design.reg_types:
        if path in rt.instances:
            return rt
    return None


@pytest.mark.parametrize("name", corpus_names())
def test_rows_are_contiguous_from_bit_zero(name):
    """No gap may be implicit: packed_s cannot skip, so an unmaterialized gap
    would shift every field above it without changing a single visible number."""
    root = compile_rdl(name)
    design = DesignScanner(ExportOptions(package_name=name)).scan(root.top)
    for rt in design.reg_types:
        expect = 0
        for row in rt.fields:
            assert row.lsb == expect, (
                "%s.%s starts at bit %d, expected %d -- a gap was not materialized"
                % (rt.type_name, row.name, row.lsb, expect)
            )
            expect = row.msb + 1


def test_pad_tail_fills_to_regwidth():
    root = compile_rdl("gaps")
    design = DesignScanner(
        ExportOptions(package_name="gaps", pad_tail=True)
    ).scan(root.top)
    for rt in design.reg_types:
        assert rt.fields[-1].msb == rt.regwidth - 1, (
            "--pad-tail must extend %s to regwidth" % rt.type_name
        )


def test_no_pad_tail_leaves_tail_to_pss():
    """Without --pad-tail the struct stops at the last real field.

    SZ is emitted explicitly as regwidth, so PSS's own "SZ > sizeof_s<R>"
    reserved-tail rule covers the remainder; padding would only add members that
    claim to describe bits nobody can access.
    """
    root = compile_rdl("gaps")
    design = DesignScanner(ExportOptions(package_name="gaps")).scan(root.top)
    rt = design.reg_types[0]
    assert rt.fields[-1].msb < rt.regwidth - 1
    assert not rt.fields[-1].reserved

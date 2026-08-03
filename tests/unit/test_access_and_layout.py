import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systemrdl.rdltypes import AccessType  # noqa: E402

from peakrdl_pss import access, layout  # noqa: E402
from peakrdl_pss.ir import FieldRow  # noqa: E402

RW = AccessType.rw
R = AccessType.r
W = AccessType.w
NA = AccessType.na
RW1 = AccessType.rw1
W1 = AccessType.w1


@pytest.mark.parametrize("sw_list,expected", [
    ([R], "READONLY"),
    ([R, R], "READONLY"),
    ([W], "WRITEONLY"),
    ([W, W1], "WRITEONLY"),
    ([RW], "READWRITE"),
    ([R, W], "READWRITE"),
    ([RW1], "READWRITE"),
    ([R, NA], "READONLY"),
    ([NA, W], "WRITEONLY"),
])
def test_access_derivation(sw_list, expected):
    assert access.derive(sw_list) == expected


def test_na_fields_are_excluded_not_counted_as_readonly():
    """An 'na' field beside a writable one must not drag the register to
    READWRITE; it contributes nothing at all."""
    assert access.derive([NA, W]) == "WRITEONLY"


def test_register_with_no_accessible_fields_is_readonly():
    """The conservative direction: generating writes to a register software
    cannot write is the worse failure.

    This case is not reachable through SystemRDL -- the compiler rejects sw=na on
    a field in a register -- so it is pinned here rather than in the corpus.
    """
    assert access.derive([NA, NA]) == "READONLY"
    assert access.derive([]) == "READONLY"


# --- layout ---------------------------------------------------------------


def _rows(*specs):
    return [
        FieldRow(name=n, rdl_name=n, width=msb - lsb + 1, lsb=lsb, msb=msb, reset=rst)
        for n, lsb, msb, rst in specs
    ]


def test_reset_value_assembles_from_fields():
    rows = _rows(("a", 0, 15, 0x1234), ("b", 16, 31, 0x5678))
    assert layout.reset_value(rows) == 0x5678_1234


def test_reset_value_masks_oversized_field_resets():
    rows = _rows(("a", 0, 3, 0xFF),)
    assert layout.reset_value(rows) == 0xF


def test_absent_reset_is_none_not_zero():
    """Absence and zero are different. Emitting 0 for an unspecified reset would
    put a value nobody wrote into a 'static const' the consumer will trust."""
    rows = _rows(("a", 0, 31, None))
    assert layout.reset_value(rows) is None


def test_partial_reset_contributes_only_known_bits():
    rows = _rows(("a", 0, 15, 0x1234), ("b", 16, 31, None))
    assert layout.reset_value(rows) == 0x1234


def test_rows_cover_detects_a_hole():
    good = _rows(("a", 0, 7, None), ("b", 8, 15, None))
    bad = _rows(("a", 0, 7, None), ("b", 12, 15, None))
    assert layout.rows_cover(good)
    assert not layout.rows_cover(bad)


def test_rows_cover_requires_starting_at_bit_zero():
    assert not layout.rows_cover(_rows(("a", 4, 7, None)))


def test_rows_cover_accepts_empty():
    assert layout.rows_cover([])

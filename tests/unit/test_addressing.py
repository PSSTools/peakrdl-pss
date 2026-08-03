import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peakrdl_pss import addressing  # noqa: E402
from peakrdl_pss.ir import KIND_REG, ChildRef  # noqa: E402


def _array(dims, offset=0x1000, stride=0x100):
    return ChildRef(
        inst_name="bar", rdl_name="bar", type_name="t", kind=KIND_REG,
        offset=offset, is_array=True, dims=tuple(dims),
        flat_count=addressing.flat_count(dims), stride=stride,
    )


def test_flat_count():
    assert addressing.flat_count((4, 3, 2)) == 24
    assert addressing.flat_count(()) == 1


@pytest.mark.parametrize("dims,idx,flat", [
    ((4, 3), (0, 0), 0),
    ((4, 3), (0, 2), 2),
    ((4, 3), (1, 0), 3),
    ((4, 3), (2, 1), 7),
    ((4, 3), (3, 2), 11),
    ((4, 3, 2), (1, 1, 1), 9),
])
def test_row_major_flattening(dims, idx, flat):
    assert addressing.flatten_index(dims, idx) == flat
    assert addressing.unflatten_index(dims, flat) == idx


def test_flatten_rejects_out_of_range():
    with pytest.raises(IndexError):
        addressing.flatten_index((4, 3), (4, 0))


def test_flatten_rejects_arity_mismatch():
    with pytest.raises(ValueError):
        addressing.flatten_index((4, 3), (1,))


def test_array_offset_expression():
    child = _array((4,))
    assert addressing.array_offset_expr(child) == "0x1000 + index*0x100"


def test_element_offset_matches_the_emitted_expression():
    """The Python side and the emitted text must agree, or the offset oracle is
    validating a formula nobody ships."""
    child = _array((4, 3))
    for index in range(12):
        assert addressing.element_offset(child, index) == 0x1000 + index * 0x100


def test_no_index_helper_for_one_dimension():
    """A 1-D helper would be the identity function."""
    assert addressing.index_helper_signature(_array((4,))) is None
    assert addressing.index_helper_body(_array((4,))) is None


def test_two_dimension_helper():
    child = _array((4, 3))
    assert addressing.index_helper_signature(child) == "int i0, int i1"
    assert addressing.index_helper_body(child) == "i0*3 + i1"


def test_three_dimension_helper_nests_left():
    child = _array((4, 3, 2))
    assert addressing.index_helper_signature(child) == "int i0, int i1, int i2"
    assert addressing.index_helper_body(child) == "(i0*3 + i1)*2 + i2"


def test_helper_body_agrees_with_flatten_index():
    """Evaluate the emitted expression and compare against the reference
    implementation -- the helper is what users will actually call."""
    dims = (4, 3, 2)
    child = _array(dims)
    body = addressing.index_helper_body(child)
    for i0 in range(4):
        for i1 in range(3):
            for i2 in range(2):
                got = eval(body, {}, {"i0": i0, "i1": i1, "i2": i2})  # noqa: S307
                assert got == addressing.flatten_index(dims, (i0, i1, i2))


def test_hex_literal_is_lowercase_and_unpadded():
    assert addressing.hex_literal(0) == "0x0"
    assert addressing.hex_literal(0xABCD) == "0xabcd"

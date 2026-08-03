"""The offset oracle -- the single most valuable test in the suite.

Array and stride arithmetic is the most likely source of *silent* wrongness:
a wrong offset produces output that parses, links, and reads plausibly, and the
failure only appears when someone runs a test against real hardware.

The oracle closes that loop.  For every leaf register in every corpus design it
interprets the offsets the generated package actually declares -- walking the IR
the way a PSS tool would walk ``get_offset_of_instance`` /
``get_offset_of_instance_array`` down the instance path -- and asserts the
accumulated sum equals the address systemrdl-compiler independently computed.

The two sides are genuinely independent: the left comes from what we emit, the
right from ``node.absolute_address``, which we never consult during export.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systemrdl.node import AddressableNode, RegNode  # noqa: E402
from util import compile_rdl  # noqa: E402

from peakrdl_pss import addressing  # noqa: E402
from peakrdl_pss.design import DesignScanner  # noqa: E402
from peakrdl_pss.ir import KIND_REG  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

from conftest import corpus_names  # noqa: E402  isort:skip


def _group_by_name(design):
    return {gt.type_name: gt for gt in design.group_types}


def _emitted_offset_of(design, groups, group_type_name, child_name, index):
    """Interpret what the generated package says the offset of one child is.

    This mirrors the emitted match statements: a scalar child resolves through
    get_offset_of_instance, an array child through get_offset_of_instance_array
    with the flattened index.
    """
    gt = groups[group_type_name]
    for child in gt.children:
        # Look up by the SystemRDL name: the emitted instance name may have been
        # mangled, and the oracle walks the model, not the output.
        if child.rdl_name != child_name:
            continue
        if child.is_array:
            assert index is not None, "array child %s needs an index" % child_name
            return addressing.element_offset(child, index), child
        assert index is None, "scalar child %s given an index" % child_name
        return child.offset, child
    raise AssertionError(
        "generated group %s declares no child for RDL instance %r (declares %s)"
        % (group_type_name, child_name, [c.rdl_name for c in gt.children])
    )


def _walk(node: AddressableNode, design, groups, group_type_name, base, seen):
    """Descend the model and the emitted IR in lockstep."""
    for child in node.children(unroll=False):
        if not isinstance(child, AddressableNode):
            continue

        dims = child.array_dimensions
        indices = [None] if not dims else [
            addressing.flatten_index(dims, idx)
            for idx in _all_indices(dims)
        ]
        raw_indices = [None] if not dims else list(_all_indices(dims))

        for flat, raw in zip(indices, raw_indices):
            emitted, ref = _emitted_offset_of(
                design, groups, group_type_name, child.inst_name, flat
            )
            here = base + emitted

            # The model's own view of the same element.
            concrete = child
            if raw is not None:
                concrete = child.__class__(child.inst, child.env, child.parent)
                concrete.current_idx = list(raw)

            if isinstance(child, RegNode):
                expected = concrete.absolute_address
                assert here == expected, (
                    "offset mismatch for %s%s:\n"
                    "  emitted package says 0x%x\n"
                    "  systemrdl says        0x%x"
                    % (concrete.get_path(), "", here, expected)
                )
                seen.append(concrete.get_path())
            elif ref.kind != KIND_REG:
                _walk(concrete, design, groups, ref.type_name, here, seen)


def _all_indices(dims):
    if not dims:
        yield ()
        return
    total = 1
    for d in dims:
        total *= d
    for flat in range(total):
        yield addressing.unflatten_index(dims, flat)


@pytest.mark.parametrize("name", corpus_names())
def test_emitted_offsets_match_model(name):
    root = compile_rdl(name)
    top = root.top
    design = DesignScanner(ExportOptions(package_name=name)).scan(top)
    groups = _group_by_name(design)

    seen = []
    _walk(top, design, groups, design.top_type_name, top.absolute_address, seen)

    # A pass with zero registers checked would be vacuous.
    assert seen, "oracle checked no registers in %s" % name


def test_flatten_roundtrip():
    dims = (4, 3, 2)
    total = 4 * 3 * 2
    flats = set()
    for flat in range(total):
        idx = addressing.unflatten_index(dims, flat)
        assert addressing.flatten_index(dims, idx) == flat
        flats.add(flat)
    assert len(flats) == total


def test_row_major_matches_documented_example():
    """The docs promise bar[2][1] -> flat 7 for dims [4][3]; hold them to it."""
    assert addressing.flatten_index((4, 3), (2, 1)) == 7

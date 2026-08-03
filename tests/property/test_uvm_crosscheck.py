"""Cross-check our addresses against peakrdl-uvm's, an independent implementation.

The offset oracle already compares us to ``node.absolute_address``.  This adds a
second, differently-derived opinion: peakrdl-uvm walks the model its own way and
builds its own offset expressions, so agreement across all three is meaningfully
stronger than agreement between two.

The array comparison is the valuable half.  UVM keeps the N-dimensional form::

    add_reg(this.r1[i0][i1], 'h1000 + i0*'h300 + i1*'h100)

while we flatten to one dimension::

    ["bar"]: return 0x1000 + index*0x100;      // index = i0*3 + i1

Those are the same function only if the row-major flattening is right.  Checking
them against each other over every index is a direct test of the claim that
flattening is lossless -- which is the least obvious thing this exporter does.

Skipped when peakrdl-uvm is unavailable: this is a cross-check, not a dependency.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_rdl  # noqa: E402

from peakrdl_pss import addressing  # noqa: E402
from peakrdl_pss.design import DesignScanner  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

from conftest import corpus_names  # noqa: E402  isort:skip

uvm = pytest.importorskip("peakrdl_uvm.exporter", reason="peakrdl-uvm not installed")

_ADD = re.compile(
    r"this\.default_map\.add_(?:reg|submap)\(this\.(\w+)((?:\[\w+\])*)"
    r"(?:\.default_map)?\s*,\s*([^;]+?)\);",
    re.M,
)
_HEX = re.compile(r"'h([0-9a-fA-F_]+)")


def _uvm_offsets(text):
    """{inst_name: offset_expression} from the generated UVM model."""
    out = {}
    for inst, subscripts, expr in _ADD.findall(text):
        out.setdefault(inst, (expr.strip(), subscripts.count("[")))
    return out


def _eval_uvm_expr(expr, indices):
    """Evaluate UVM's ``'h1000 + i0*'h300 + i1*'h100`` for a given index tuple."""
    python = _HEX.sub(lambda m: "0x" + m.group(1).replace("_", ""), expr)
    env = {"i%d" % i: v for i, v in enumerate(indices)}
    return eval(python, {"__builtins__": {}}, env)  # noqa: S307


def _pss_children(design):
    """{rdl_name: ChildRef} across every emitted group."""
    out = {}
    for gt in design.group_types:
        for child in gt.children:
            out.setdefault(child.rdl_name, child)
    return out


@pytest.mark.uvm
@pytest.mark.parametrize("name", corpus_names())
def test_uvm_and_pss_agree_on_every_offset(name, tmp_path):
    root = compile_rdl(name)

    uvm_path = str(tmp_path / (name + ".sv"))
    uvm.UVMExporter().export(root, uvm_path)
    uvm_offsets = _uvm_offsets(open(uvm_path).read())
    assert uvm_offsets, "no offsets found in the UVM output for %s" % name

    design = DesignScanner(ExportOptions(package_name=name)).scan(root.top)
    pss_children = _pss_children(design)

    common = sorted(set(uvm_offsets) & set(pss_children))
    assert common, "no comparable instances between the two exporters for %s" % name

    compared = 0
    for inst in common:
        expr, ndims = uvm_offsets[inst]
        child = pss_children[inst]

        if not child.is_array:
            assert ndims == 0, "%s: array/scalar disagreement between exporters" % inst
            assert _eval_uvm_expr(expr, ()) == child.offset, (
                "%s.%s: peakrdl-uvm says %s, peakrdl-pss says 0x%x"
                % (name, inst, expr, child.offset)
            )
            compared += 1
            continue

        dims = child.dims
        assert len(dims) == ndims, (
            "%s: peakrdl-uvm sees %d dimension(s), peakrdl-pss recorded %s"
            % (inst, ndims, dims)
        )

        # The heart of it: every N-D index must land at the same address under
        # both the N-D expression and our flattened one.
        for flat in range(addressing.flat_count(dims)):
            indices = addressing.unflatten_index(dims, flat)
            expected = _eval_uvm_expr(expr, indices)
            got = addressing.element_offset(child, flat)
            assert got == expected, (
                "%s.%s%s (flat index %d): peakrdl-uvm computes 0x%x from %r, "
                "peakrdl-pss computes 0x%x -- the row-major flattening is wrong"
                % (name, inst, list(indices), flat, expected, expr, got)
            )
            compared += 1

    assert compared, "cross-check compared nothing for %s" % name

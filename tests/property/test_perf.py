"""Benchmark on a 4096-register design.

The assertion is deliberately loose: this is a tripwire for a pathological
regression (accidental quadratic behavior in dedup or naming), not a performance
target.  The measured numbers are printed so they can be recorded rather than
guessed at.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_rdl, export_str  # noqa: E402

from peakrdl_pss.design import DesignScanner  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

CEILING_SECONDS = 30.0


@pytest.mark.slow
def test_wide_design_exports_quickly(tmp_path, capsys):
    root = compile_rdl("wide")

    start = time.monotonic()
    text = export_str(root, tmp_path, package_name="wide")
    elapsed = time.monotonic() - start

    with capsys.disabled():
        print(
            "\nwide.rdl: %d registers exported in %.2fs, %d bytes of output"
            % (4096, elapsed, len(text))
        )
    assert elapsed < CEILING_SECONDS


@pytest.mark.slow
def test_output_size_scales_with_types_not_instances(tmp_path):
    """4096 instances of one register type must not emit 4096 register types.

    If dedup ever regresses to per-instance emission this is the test that
    notices: the output would grow by three orders of magnitude while every
    correctness test still passed.
    """
    design = DesignScanner(ExportOptions(package_name="wide")).scan(
        compile_rdl("wide").top
    )
    assert len(design.reg_types) == 1, (
        "expected one register type for 4096 identical registers, got %d"
        % len(design.reg_types)
    )
    assert len(design.group_types) == 2, (
        "expected the block type plus the top, got %d" % len(design.group_types)
    )

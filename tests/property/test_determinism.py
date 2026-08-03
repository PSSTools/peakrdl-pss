"""Byte-identical output, run to run and interpreter to interpreter.

Generated source lands in version control.  If the output moves because a set
iterated differently, every consumer sees a spurious diff and real changes stop
being visible in review.  Two exports of the same model must be byte-identical,
including under a different ``PYTHONHASHSEED``.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_rdl, export_str  # noqa: E402

from peakrdl_pss.design import DesignScanner  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

from conftest import corpus_names  # noqa: E402  isort:skip

_DRIVER = r"""
import sys
sys.path.insert(0, %(tests)r)
from util import compile_rdl, export_str
root = compile_rdl(%(name)r)
sys.stdout.write(export_str(root, %(tmp)r, package_name="p",
                            emit_reset_consts=True, emit_index_helpers=True))
"""


@pytest.mark.parametrize("name", corpus_names())
def test_repeated_export_is_identical(name, tmp_path):
    root = compile_rdl(name)
    first = export_str(root, tmp_path, package_name="p")
    second = export_str(root, tmp_path, package_name="p")
    assert first == second


@pytest.mark.parametrize("name", corpus_names())
def test_recompiled_model_gives_identical_output(name, tmp_path):
    """A fresh compile must not reorder anything.

    Catches state that leaks between the compiler's object identities and our
    traversal -- e.g. keying anything on ``id()`` or on dict insertion order that
    depends on allocation.
    """
    a = export_str(compile_rdl(name), tmp_path, package_name="p")
    b = export_str(compile_rdl(name), tmp_path, package_name="p")
    assert a == b


@pytest.mark.parametrize("seed", ["0", "1", "42"])
def test_hash_seed_does_not_change_output(seed, tmp_path):
    """The real test of the "no set iteration reaches output" rule.

    String hashing is randomized per process, so if any set or dict iteration
    order influenced the output this varies between seeds.
    """
    tests_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = _DRIVER % {"tests": tests_dir, "name": "basic", "tmp": str(tmp_path)}

    outputs = []
    for run_seed in ("0", seed):
        env = dict(os.environ, PYTHONHASHSEED=run_seed)
        proc = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, env=env
        )
        assert proc.returncode == 0, proc.stderr
        outputs.append(proc.stdout)
    assert outputs[0] == outputs[1], (
        "output changed with PYTHONHASHSEED=%s; some set or dict iteration is "
        "reaching the emitted text" % seed
    )


@pytest.mark.parametrize("name", corpus_names())
def test_ir_collections_are_lists(name):
    """The determinism rule, asserted structurally rather than only observed."""
    design = DesignScanner(ExportOptions(package_name="p")).scan(compile_rdl(name).top)
    assert isinstance(design.reg_types, list)
    assert isinstance(design.group_types, list)
    assert isinstance(design.enums, list)
    for gt in design.group_types:
        assert isinstance(gt.children, list)
    for rt in design.reg_types:
        assert isinstance(rt.fields, list)

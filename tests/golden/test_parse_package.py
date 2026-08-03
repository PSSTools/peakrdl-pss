"""The hard CI gate: every generated package must be accepted by pssparser.

Kept separate from the consumer-side suite on purpose.  This suite covers *our
artifact* and must always pass; the consumer suite exercises stdlib surface we do
not emit and is allowed to carry xfails.  Merging them would let a gap in
someone else's stdlib mask a defect in our output.

Since symbolic register names were dropped from scope, everything the exporter
emits by default -- including the ``--emit-reset-consts`` constants -- is inside
the subset pssparser validates today.  So this suite covers 100% of shipped
output: there is no feature CI cannot check.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import assert_parses, compile_rdl, export_file  # noqa: E402

from conftest import corpus_names  # noqa: E402  isort:skip

#: Option sets that change the *shape* of the output, not just a name.
OPTION_SETS = [
    ("default", {}),
    ("reset-consts", {"emit_reset_consts": True}),
    ("index-helpers", {"emit_index_helpers": True}),
    ("pad-tail", {"pad_tail": True}),
    ("no-pure", {"pure_components": False}),
    ("hier", {"type_style": "hier"}),
    ("enums-off", {"emit_enums": "off"}),
    ("everything", {
        "emit_reset_consts": True, "emit_index_helpers": True,
        "pad_tail": True, "type_style": "hier",
    }),
]


@pytest.mark.pssparser
@pytest.mark.parametrize("label,kwargs", OPTION_SETS, ids=[o[0] for o in OPTION_SETS])
@pytest.mark.parametrize("name", corpus_names())
def test_generated_package_parses(name, label, kwargs, tmp_path):
    root = compile_rdl(name)
    path = export_file(root, tmp_path, name + ".pss", package_name=name, **kwargs)
    assert_parses(path)


@pytest.mark.pssparser
@pytest.mark.parametrize("name", corpus_names())
def test_generated_top_wrapper_parses(name, tmp_path):
    """--emit-top writes a second file; it has to parse *with* the package."""
    root = compile_rdl(name)
    path = export_file(
        root, tmp_path, name + ".pss",
        package_name=name, emit_top=True, base_address=0x8000_0000,
    )
    top = path[: -len(".pss")] + "_top.pss"
    assert os.path.exists(top), "--emit-top wrote no wrapper file"
    assert_parses(path, top)

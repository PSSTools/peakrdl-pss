"""Mechanize the signature invariant, using rendered text as the oracle.

    A type's signature must change if and only if the text emitted for that type
    changes.

Both halves matter, and for different reasons:

* If a signature can stay the same while the text changes, two structurally
  different components share one emitted type and one of them is silently wrong.
  That is precisely the ``peakrdl-uvm`` defect this exporter exists not to
  inherit.
* If a signature changes while the text does not, the output fills with ``__vN``
  variants that are byte-identical -- correct, but noisy enough that users stop
  trusting the suffix to mean anything.

Rather than assert the property abstractly, this test *mutates* real designs one
property at a time and compares (signature, rendered text) pairs.  A claim about
a hash function is cheap; a mutation that survives is not.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_text  # noqa: E402

from peakrdl_pss import signature  # noqa: E402
from peakrdl_pss.exporter import PSSExporter  # noqa: E402
from peakrdl_pss.ir import ChildRef, FieldRow  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

BASE = """
addrmap top {
    reg r_t {
        field {sw=rw; hw=r;} f1[15:0] = 1234;
        field {sw=rw; hw=r;} f2[31:16] = 0;
    };
    r_t a @ 0x0;
    r_t b[4] @ 0x10 += 0x4;
};
"""

#: (label, mutated source).  Each changes exactly one thing that the emitted text
#: depends on, so every one of them must move the signature.
MUTATIONS = [
    ("field sw", BASE.replace("field {sw=rw; hw=r;} f1", "field {sw=r; hw=w;} f1")),
    ("field reset", BASE.replace("f1[15:0] = 1234", "f1[15:0] = 4321")),
    ("field width", BASE.replace("f1[15:0]", "f1[11:0]")),
    ("field name", BASE.replace("f1[15:0]", "renamed[15:0]")),
    ("scalar offset", BASE.replace("r_t a @ 0x0", "r_t a @ 0x40")),
    ("array offset", BASE.replace("r_t b[4] @ 0x10", "r_t b[4] @ 0x20")),
    ("array stride", BASE.replace("b[4] @ 0x10 += 0x4", "b[4] @ 0x10 += 0x8")),
    ("array size", BASE.replace("r_t b[4]", "r_t b[8]")),
    ("instance name", BASE.replace("r_t a @ 0x0", "r_t renamed_inst @ 0x0")),
    ("regwidth", BASE.replace(
        "reg r_t {", "reg r_t { regwidth = 64;").replace(
        "f2[31:16] = 0;", "f2[63:16] = 0;").replace(
        "r_t b[4] @ 0x10 += 0x4", "r_t b[4] @ 0x10 += 0x8")),
]


def _sigs_and_text(source, tmp_path, name, **kwargs):
    root = compile_text(source, tmp_path, name)
    exporter = PSSExporter()
    options = ExportOptions(package_name="p", **kwargs)
    design = exporter.build(root.top, options)
    text = exporter.render_package(design, options)
    sigs = {rt.type_name: rt.signature for rt in design.reg_types}
    sigs.update({gt.type_name: gt.signature for gt in design.group_types})
    return sigs, text


@pytest.mark.parametrize("label,mutated", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_text_change_implies_signature_change(label, mutated, tmp_path):
    assert mutated != BASE, "mutation %r did not change the source" % label

    base_sigs, base_text = _sigs_and_text(BASE, tmp_path, "base")
    mut_sigs, mut_text = _sigs_and_text(mutated, tmp_path, "mut")

    assert base_text != mut_text, (
        "mutation %r produced identical output; it is not a useful mutation" % label
    )
    assert set(base_sigs.values()) != set(mut_sigs.values()), (
        "mutation %r changed the emitted text but every signature stayed the "
        "same -- two different components could share one emitted type" % label
    )


def test_identical_designs_have_identical_signatures(tmp_path):
    """The 'only if' half: same input, same signatures, no spurious __vN."""
    a_sigs, a_text = _sigs_and_text(BASE, tmp_path, "a")
    b_sigs, b_text = _sigs_and_text(BASE, tmp_path, "b")
    assert a_sigs == b_sigs
    assert a_text == b_text


def test_dynamic_assignment_forces_a_distinct_type(tmp_path):
    """The case the whole scheme exists for.

    r1 and r3 share the SystemRDL type name ``reg_t``; r3's field was retargeted
    after instantiation.  A name-keyed cache emits one type and gives r3 the
    wrong access policy -- in output that parses cleanly.
    """
    source = """
    addrmap top {
        reg reg_t {
            field {sw=rw; hw=r;} f1[15:0] = 1234;
        };
        reg_t r1 @ 0x0;
        reg_t r2 @ 0x4;
        reg_t r3 @ 0x8;
        r3.f1->sw = w;
        r3.f1->reset = 200;
    };
    """
    _, text = _sigs_and_text(source, tmp_path, "dyn")

    # r1/r2 share a type; r3 must not.
    decls = {inst: typ for typ, inst in
             re.findall(r"^\s+(\w+_c)\s+(r\d);$", text, re.M)}
    assert decls["r1"] == decls["r2"], "r1 and r2 are identical and should share a type"
    assert decls["r3"] != decls["r1"], (
        "r3 was given r1's type despite `r3.f1->sw = w`; this is the silent-"
        "wrongness case the structural signature exists to prevent"
    )
    # And the distinct type must actually carry the different policy.
    assert "sw=w" in text


def test_reset_consts_participate_in_the_group_signature():
    """Two groups identical except for an instance's reset value differ.

    --emit-reset-consts puts the value inside the component body, so if the
    signature ignored it the second group would silently reuse the first group's
    constant.
    """
    children = [ChildRef(
        inst_name="r1", rdl_name="r1", type_name="t", kind="reg", offset=0
    )]
    a = signature.of_group("g", children, ["sig"], [("r1_reset", 32, 0x1234)])
    b = signature.of_group("g", children, ["sig"], [("r1_reset", 32, 0x5678)])
    assert a != b


def test_comment_only_differences_move_the_signature():
    """Comments are emitted text too.

    Two fields differing only in a dropped-property note render differently, so
    treating them as the same type would emit one comment for both and misdescribe
    one of them.
    """
    common = {"width": 8, "lsb": 0, "msb": 7, "sw": "rw", "hw": "r"}
    plain = FieldRow(name="f", rdl_name="f", **common)
    noted = FieldRow(name="f", rdl_name="f", lossy_notes=("onread=rclr",), **common)
    assert signature.of_field(plain) != signature.of_field(noted)

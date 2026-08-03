"""Turn a SystemRDL register's fields into an ordered, gap-free list of
``packed_s`` members.

The invariant this module maintains, and that ``tests/property`` re-derives
independently, is:

    rows are ascending by ``lsb``, contiguous (``row[i].lsb == row[i-1].msb+1``),
    start at bit 0, and each non-reserved row lands at exactly the ``[msb:lsb]``
    the SystemRDL model reports.

``packed_s<LITTLE_ENDIAN>`` packs members from the least significant bit in
declaration order, so a missing gap row silently shifts every subsequent field.
That failure is invisible in the generated text, which is why the rows are built
here rather than in a template.
"""

from typing import TYPE_CHECKING, List, Optional, Tuple

from systemrdl.rdltypes.builtin_enums import AccessType

from . import access as access_mod
from . import diagnostics as diag
from .identifiers import Namespace
from .ir import FieldRow

if TYPE_CHECKING:  # pragma: no cover
    from systemrdl.node import FieldNode, RegNode

    from .options import ExportOptions


def _reset_of(fld: "FieldNode") -> Tuple[Optional[int], bool]:
    """Return ``(literal_reset, is_reference)``.

    A reference-valued reset has no constant value.  Returning ``None`` rather
    than ``0`` matters: absent and zero are different, and inventing a zero would
    put a wrong value into an emitted reset constant.
    """
    try:
        value = fld.get_property("reset", default=None)
    except LookupError:  # pragma: no cover - defensive
        return None, False
    if value is None:
        return None, False
    if isinstance(value, int):
        return value, False
    return None, True


def _enum_name_of(fld: "FieldNode") -> Optional[str]:
    encode = fld.get_property("encode", default=None)
    if encode is None:
        return None
    return encode.__name__


def build_rows(
    reg: "RegNode",
    options: "ExportOptions",
    findings: diag.FindingLog,
) -> List[FieldRow]:
    """Build the ordered field rows for *reg*."""
    regwidth = reg.get_property("regwidth")
    is_msb0 = reg.is_msb0_order

    if is_msb0:
        findings.add(
            diag.W_MSB0_ORDER,
            "register uses msb0 field ordering: each field's bit span is emitted "
            "correctly, but the implied within-field bit swap is not representable "
            "in packed_s",
            reg,
        )

    ns = Namespace()
    entries: List[FieldRow] = []
    for fld in reg.fields():
        # ``lsb``/``msb`` already account for is_msb0_order in systemrdl-compiler:
        # ``low``/``high`` are always the physical lsb/msb.  Use low/high so the
        # rows are correct under either ordering, and let the msb0 finding above
        # record that the declaration order differs from the emitted order.
        low = fld.low
        high = fld.high
        name, changed = ns.allocate(fld.inst_name)
        if changed:
            findings.add(
                diag.I_MANGLED,
                "field '%s' renamed to '%s'" % (fld.inst_name, name),
                fld,
                original=fld.inst_name,
                emitted=name,
            )
        reset, reset_is_ref = _reset_of(fld)
        if reset_is_ref:
            findings.add(
                diag.W_RESET_IS_REFERENCE,
                "field '%s' has a reference-valued reset; no constant emitted"
                % fld.inst_name,
                fld,
            )
        notes = access_mod.lossiness(fld)
        for spec, msg in access_mod.side_effect_findings(reg.get_path(), fld, notes):
            findings.add(spec, msg, fld)

        entries.append(FieldRow(
            name=name,
            rdl_name=fld.inst_name,
            width=high - low + 1,
            lsb=low,
            msb=high,
            reserved=False,
            sw=fld.get_property("sw").name,
            hw=fld.get_property("hw").name,
            reset=reset,
            reset_is_ref=reset_is_ref,
            enum_type=_enum_name_of(fld),
            lossy_notes=tuple(notes),
            desc=fld.get_property("desc", default=None),
        ))

    entries.sort(key=lambda r: r.lsb)
    rows = _insert_reserved(entries, regwidth, options, ns)
    return rows


def _insert_reserved(
    entries: List[FieldRow],
    regwidth: int,
    options: "ExportOptions",
    ns: Namespace,
) -> List[FieldRow]:
    """Materialize every gap between (and before) fields as a reserved row."""
    rows: List[FieldRow] = []
    next_bit = 0

    def reserved(lsb: int, width: int) -> FieldRow:
        name, _ = ns.allocate("%s%d" % (options.rsvd_prefix, lsb))
        return FieldRow(
            name=name,
            rdl_name="",
            width=width,
            lsb=lsb,
            msb=lsb + width - 1,
            reserved=True,
            sw=AccessType.na.name,
            hw=AccessType.na.name,
        )

    for row in entries:
        if row.lsb > next_bit:
            rows.append(reserved(next_bit, row.lsb - next_bit))
        rows.append(row)
        next_bit = row.msb + 1

    if options.pad_tail and next_bit < regwidth:
        rows.append(reserved(next_bit, regwidth - next_bit))

    return rows


def reset_value(rows: List[FieldRow]) -> Optional[int]:
    """Assemble a register-level reset from its field resets.

    Returns ``None`` when *no* field carries a literal reset -- a register with
    no specified reset is different from one that resets to zero, and emitting
    ``0`` for the former would be a silent fabrication.  A register where only
    some fields specify a reset yields those fields' contribution, with the rest
    reading as zero; that matches SystemRDL, where an unspecified field reset is
    undefined but the register-level constant is only useful as "the bits we do
    know".
    """
    known = [r for r in rows if r.reset is not None]
    if not known:
        return None
    value = 0
    for row in known:
        mask = (1 << row.width) - 1
        value |= (row.reset & mask) << row.lsb  # type: ignore[operator]
    return value


def rows_cover(rows: List[FieldRow]) -> bool:
    """True if *rows* are contiguous from bit 0 -- the module's invariant."""
    expect = 0
    for row in rows:
        if row.lsb != expect or row.msb < row.lsb:
            return False
        expect = row.msb + 1
    return True

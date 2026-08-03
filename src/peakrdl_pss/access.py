"""Derive a PSS ``reg_access`` value from SystemRDL field properties, and name
everything that derivation throws away.

PSS offers exactly three access policies; SystemRDL offers a lattice of ``sw``
values plus orthogonal side-effect properties.  The mapping is therefore lossy
by construction, and the point of this module is that every lossy step produces
a *named* finding rather than silently disappearing.
"""

from typing import TYPE_CHECKING, List, Tuple

from systemrdl.rdltypes.builtin_enums import AccessType

from . import diagnostics as diag

if TYPE_CHECKING:  # pragma: no cover
    from systemrdl.node import FieldNode

READWRITE = "READWRITE"
READONLY = "READONLY"
WRITEONLY = "WRITEONLY"

#: sw access -> (readable, writable).  ``na`` is neither and is excluded from
#: the derivation entirely.
_SW_RW = {
    AccessType.rw: (True, True),
    AccessType.r: (True, False),
    AccessType.w: (False, True),
    AccessType.rw1: (True, True),
    AccessType.w1: (False, True),
    AccessType.na: (False, False),
}

#: Policies that PSS cannot express exactly: the "write once" qualifier is lost.
_APPROXIMATED = (AccessType.rw1, AccessType.w1)


def field_rw(sw: AccessType) -> Tuple[bool, bool]:
    return _SW_RW.get(sw, (True, True))


def derive(field_sw: List[AccessType]) -> str:
    """Reduce a register's field ``sw`` values to one PSS ``reg_access``.

    ``na`` fields are excluded.  A register with no accessible field at all
    derives ``READONLY`` -- the conservative choice, since generating writes to
    a register software cannot write is the worse failure.
    """
    readable = False
    writable = False
    for sw in field_sw:
        if sw == AccessType.na:
            continue
        r, w = field_rw(sw)
        readable = readable or r
        writable = writable or w
    if readable and writable:
        return READWRITE
    if writable:
        return WRITEONLY
    return READONLY


def lossiness(field: "FieldNode") -> List[str]:
    """Name every SystemRDL property of *field* that the PSS output drops.

    Returned strings are human-readable and land both in the emitted comment and
    in the ``--sidecar`` JSON, so a consumer can recover what was lost.
    """
    notes: List[str] = []

    onread = field.get_property("onread")
    if onread is not None:
        notes.append("onread=%s" % onread.name)
    onwrite = field.get_property("onwrite")
    if onwrite is not None:
        notes.append("onwrite=%s" % onwrite.name)

    for prop in ("singlepulse", "swmod", "swacc", "counter", "intr"):
        if field.get_property(prop, default=False):
            notes.append(prop)

    for prop in ("incr", "decr", "enable", "mask", "haltmask", "next", "precedence"):
        try:
            value = field.get_property(prop, default=None)
        except LookupError:  # pragma: no cover - property not applicable
            continue
        if value is not None and value is not False:
            notes.append(prop)

    return notes


def side_effect_findings(reg_path: str, field: "FieldNode", notes: List[str]) -> List[
    Tuple[diag.DiagSpec, str]
]:
    """Map the notes of :func:`lossiness` onto diagnostics."""
    out: List[Tuple[diag.DiagSpec, str]] = []
    if notes:
        out.append((
            diag.W_SIDE_EFFECTS,
            "field '%s' has behavior with no PSS equivalent: %s" % (field.inst_name, ", ".join(notes)),
        ))
    sw = field.get_property("sw")
    if sw in _APPROXIMATED:
        out.append((
            diag.W_ACCESS_APPROXIMATED,
            "field '%s' has sw=%s; PSS reg_access cannot express write-once"
            % (field.inst_name, sw.name),
        ))
    return out

"""Structural signatures: the key that decides when two SystemRDL components
may share one emitted PSS type.

Keying type reuse on the lexical type name alone is wrong, and demonstrably so.
SystemRDL dynamic property assignment lets two instances of the same type differ
in content::

    reg_t r1;
    reg_t r3;
    r3.f1->sw = w;          // r3 is now a different register than r1

An exporter that caches on ``reg_t`` emits one definition and gives ``r3`` the
wrong access policy -- silently, in output that parses cleanly.  This module
computes a digest of *exactly the values the templates consume*, so the cache
key is ``(type_name, signature)`` and a structural difference produces a
``__v2`` variant instead of a wrong reuse.

The invariant, mechanized in ``tests/property/test_signature_fidelity.py``:

    the signature changes if and only if the rendered text for that type changes.

Both directions matter.  Too coarse means silent wrongness; too fine means the
output is littered with ``__vN`` variants that are textually identical.
"""

import hashlib
from typing import Any, Sequence, Tuple

from .ir import ChildRef, EnumType, FieldRow, RegType

_DIGEST_LEN = 16


def _digest(parts: Any) -> str:
    return hashlib.sha1(repr(parts).encode("utf-8")).hexdigest()[:_DIGEST_LEN]


def of_field(f: FieldRow) -> Tuple[Any, ...]:
    """The tuple of a field's render-visible values.

    ``rdl_name``, ``desc``, and ``lossy_notes`` are included because they reach
    the output as comments -- omitting them would make the signature coarser
    than the rendered text and break the "only if" half of the invariant.
    """
    return (
        f.name, f.rdl_name, f.width, f.lsb, f.msb, f.reserved,
        f.sw, f.hw, f.reset, f.reset_is_ref, f.enum_type, f.lossy_notes, f.desc,
    )


def of_reg(
    type_name: str,
    regwidth: int,
    accesswidth: int,
    reg_access: str,
    fields: Sequence[FieldRow],
    is_msb0: bool,
) -> str:
    return _digest((
        "reg", type_name, regwidth, accesswidth, reg_access, is_msb0,
        tuple(of_field(f) for f in fields),
    ))


def of_child(c: ChildRef) -> Tuple[Any, ...]:
    return (
        c.inst_name, c.rdl_name, c.type_name, c.kind, c.offset,
        c.is_array, c.flat_count, c.dims, c.stride,
    )


def of_group(
    type_name: str,
    children: Sequence[ChildRef],
    child_signatures: Sequence[str],
    reset_consts: Sequence[Tuple[str, int, int]] = (),
) -> str:
    """Digest a group.

    *child_signatures* carries the signature of each child's own type, so a
    difference nested arbitrarily deep propagates upward: two addrmaps that
    instantiate same-named but structurally different registers are themselves
    different types.  Post-order traversal guarantees the child signatures are
    already computed.

    *reset_consts* participate because ``--emit-reset-consts`` puts them inside
    the component body -- two groups whose instances differ only in reset value
    render differently and must not share a type.
    """
    return _digest((
        "group", type_name,
        tuple(of_child(c) for c in children),
        tuple(child_signatures),
        tuple(reset_consts),
    ))


def of_enum(e: EnumType) -> str:
    return _digest((
        "enum", e.name, e.rdl_name, e.width,
        tuple((m.name, m.value, m.rdl_name, m.desc) for m in e.members),
    ))


def of_reg_type(rt: RegType) -> str:
    """Convenience wrapper for an already-built :class:`RegType`."""
    return of_reg(
        rt.type_name, rt.regwidth, rt.accesswidth, rt.access, rt.fields, rt.is_msb0
    )

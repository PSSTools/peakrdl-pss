"""Offsets, strides, and the flattening of N-dimensional SystemRDL arrays.

PSS component arrays are one-dimensional.  SystemRDL allows ``foo bar[4][3][2]``.
The mapping is a row-major flattening -- ``bar[i][j][k]`` becomes ``bar[((i*3)+j)*2+k]``
-- which keeps ``get_offset_of_instance_array(name, index)`` a single affine
expression.

Every offset here is *relative to the containing group*, matching
``raw_address_offset``, because that is exactly what ``get_offset_of_instance``
is defined to return.  Absolute addresses are never emitted; they are only used
by the offset oracle in the test suite as an independent check.
"""

from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from systemrdl.node import AddressableNode

    from .ir import ChildRef


def flat_count(dims: Sequence[int]) -> int:
    n = 1
    for d in dims:
        n *= d
    return n


def flatten_index(dims: Sequence[int], indices: Sequence[int]) -> int:
    """Row-major flatten: the inverse of :func:`unflatten_index`."""
    if len(dims) != len(indices):
        raise ValueError("dimension/index arity mismatch")
    flat = 0
    for dim, idx in zip(dims, indices):
        if not 0 <= idx < dim:
            raise IndexError("index %d out of range for dimension %d" % (idx, dim))
        flat = flat * dim + idx
    return flat


def unflatten_index(dims: Sequence[int], flat: int) -> Tuple[int, ...]:
    out: List[int] = []
    for dim in reversed(dims):
        out.append(flat % dim)
        flat //= dim
    return tuple(reversed(out))


def child_geometry(node: "AddressableNode") -> Tuple[bool, Optional[Tuple[int, ...]], Optional[int], Optional[int]]:
    """Return ``(is_array, dims, flat_count, stride)`` for a child instance."""
    dims = node.array_dimensions
    if not dims:
        return False, None, None, None
    dims_t = tuple(int(d) for d in dims)
    stride = node.array_stride
    return True, dims_t, flat_count(dims_t), int(stride) if stride is not None else None


def hex_literal(value: int) -> str:
    """Format an address/offset consistently everywhere it is emitted."""
    return "0x%x" % value


def scalar_offset_expr(child: "ChildRef") -> str:
    return hex_literal(child.offset)


def array_offset_expr(child: "ChildRef") -> str:
    """``get_offset_of_instance_array`` body for one array child."""
    return "%s + index*%s" % (hex_literal(child.offset), hex_literal(child.stride or 0))


def element_offset(child: "ChildRef", index: int) -> int:
    """The offset the emitted expression evaluates to, computed in Python.

    Used by the offset oracle so the test does not re-implement the formula from
    the same reasoning that produced it -- it evaluates *this* function against
    the model's ``absolute_address``.
    """
    if not child.is_array:
        return child.offset
    return child.offset + index * (child.stride or 0)


def index_helper_name(child: "ChildRef") -> str:
    return "%s_index" % child.inst_name


def index_helper_signature(child: "ChildRef") -> Optional[str]:
    """Parameter list for the N-D index helper, or ``None`` for 1-D arrays.

    A helper for a 1-D array would be the identity function, so none is emitted.
    """
    if not child.is_array or not child.dims or len(child.dims) < 2:
        return None
    return ", ".join("int i%d" % i for i in range(len(child.dims)))


def index_helper_body(child: "ChildRef") -> Optional[str]:
    """The row-major flattening expression, e.g. ``(i0*3 + i1)*2 + i2``."""
    if not child.is_array or not child.dims or len(child.dims) < 2:
        return None
    dims = child.dims
    expr = "i0"
    for i in range(1, len(dims)):
        # Parenthesize only what needs it: (i0*3 + i1)*2 + i2, not ((i0)*3 + i1)*2
        inner = expr if i == 1 else "(%s)" % expr
        expr = "%s*%d + i%d" % (inner, dims[i], i)
    return expr

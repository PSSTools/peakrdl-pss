"""The intermediate representation the templates render.

The plan places these dataclasses in ``design.py`` alongside the scanner; they
live here instead because ``layout.py`` and ``addressing.py`` *build* IR objects
and ``design.py`` *calls* those modules, which would be an import cycle.  The
split is otherwise invisible: ``design.py`` re-exports every name here.

Everything in the IR is plain data.  No template ever calls ``get_property()``;
by the time rendering starts, the compiled SystemRDL model is no longer
consulted.  That is what makes the offset and layout logic testable without
Jinja, and what makes the determinism guarantee checkable.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .diagnostics import FindingLog

# Kind discriminator for ChildRef.  A plain str rather than an enum so the IR
# stays trivially reprable for signature computation.
KIND_REG = "reg"
KIND_GROUP = "group"


@dataclass(frozen=True)
class FieldRow:
    """One member of a register's ``packed_s`` struct.

    Rows are contiguous and ascending by ``lsb``; gaps in the SystemRDL field
    layout are materialized as ``reserved`` rows, because ``packed_s`` assigns
    bits by declaration order and cannot skip.
    """

    name: str
    rdl_name: str
    width: int
    lsb: int
    msb: int
    reserved: bool = False
    sw: str = "rw"
    hw: str = "na"
    reset: Optional[int] = None
    reset_is_ref: bool = False
    enum_type: Optional[str] = None
    lossy_notes: Tuple[str, ...] = ()
    desc: Optional[str] = None


@dataclass(frozen=True)
class EnumMember:
    name: str
    value: int
    rdl_name: str
    desc: Optional[str] = None


@dataclass(frozen=True)
class EnumType:
    """A SystemRDL ``encode`` enumeration.

    Emitted either as a set of ``static const`` values (default) or as a typed
    ``enum`` with an explicit base type (``--emit-enums=typed``, which needs
    pssparser Tier 1.1).
    """

    name: str
    rdl_name: str
    width: int
    members: Tuple[EnumMember, ...]


@dataclass
class RegType:
    """A distinct register *type*: one ``packed_s`` plus one ``reg_c`` component.

    Two SystemRDL registers share a ``RegType`` only when their structural
    signatures match, not merely when their type names match.  Name-keyed reuse
    is the defect this exporter exists to avoid: a dynamic property assignment
    (``r3.f1->sw = w;``) produces a register with the same lexical type name and
    different content.
    """

    type_name: str
    friendly: str
    regwidth: int
    accesswidth: int
    access: str
    fields: List[FieldRow]
    reset_value: Optional[int] = None
    is_msb0: bool = False
    signature: str = ""
    #: RDL paths of every instance of this type, in traversal order (docs/sidecar).
    instances: List[str] = field(default_factory=list)

    @property
    def struct_name(self) -> str:
        return self.type_name + "_s"

    @property
    def component_name(self) -> str:
        return self.type_name + "_c"


@dataclass(frozen=True)
class ChildRef:
    """One child instance inside a ``reg_group_c``.

    ``offset`` is ``raw_address_offset`` -- the offset relative to the parent,
    which is what ``get_offset_of_instance`` must return.  For arrays,
    ``flat_count`` and ``stride`` describe the row-major flattening of what may
    have been an N-dimensional SystemRDL array; PSS component arrays are 1-D.
    """

    inst_name: str
    rdl_name: str
    type_name: str
    kind: str
    offset: int
    is_array: bool = False
    flat_count: Optional[int] = None
    dims: Optional[Tuple[int, ...]] = None
    stride: Optional[int] = None

    @property
    def component_name(self) -> str:
        return self.type_name + "_c"


@dataclass
class GroupType:
    """A distinct ``reg_group_c`` type (an addrmap or regfile)."""

    type_name: str
    friendly: str
    children: List[ChildRef]
    size: int = 0
    signature: str = ""
    instances: List[str] = field(default_factory=list)
    #: ``(const_name, width, value)`` for --emit-reset-consts.  Instance-scoped:
    #: reset is an instance property in SystemRDL, so the constant belongs beside
    #: the instance rather than at package scope.
    reset_consts: List[Tuple[str, int, int]] = field(default_factory=list)

    @property
    def component_name(self) -> str:
        return self.type_name + "_c"

    @property
    def array_children(self) -> List[ChildRef]:
        return [c for c in self.children if c.is_array]

    @property
    def scalar_children(self) -> List[ChildRef]:
        return [c for c in self.children if not c.is_array]


@dataclass
class Design:
    """Everything the templates need, and nothing else."""

    package_name: str
    reg_types: List[RegType] = field(default_factory=list)
    group_types: List[GroupType] = field(default_factory=list)
    enums: List[EnumType] = field(default_factory=list)
    top_type_name: str = ""
    top_size: int = 0
    base_address: int = 0
    findings: FindingLog = field(default_factory=FindingLog)
    #: original RDL name -> emitted name, for every rename performed.
    mangle_map: Dict[str, str] = field(default_factory=dict)

    @property
    def top_component_name(self) -> str:
        return self.top_type_name + "_c"

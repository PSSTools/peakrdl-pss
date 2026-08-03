"""Walk the compiled SystemRDL model and build the :mod:`.ir` design.

This module is the **only** place ``get_property()`` is called.  Everything
downstream -- validation, rendering, the sidecar -- reads the IR.  That boundary
is what makes offsets and layouts testable without Jinja, and it is why a
template can never accidentally reach back into the model and produce output
that depends on compiler state the signature does not cover.

Determinism rule: every collection reaching the IR is a ``list`` built in
traversal order.  Sets and dicts are used only for membership tests, never
iterated into output.  ``tests/property/test_determinism.py`` re-exports under
several ``PYTHONHASHSEED`` values to keep that honest.
"""

from typing import Dict, List, Optional, Tuple

from systemrdl.node import (
    AddressableNode,
    AddrmapNode,
    MemNode,
    Node,
    RegfileNode,
    RegNode,
    RootNode,
)

from . import addressing, layout, signature
from . import diagnostics as diag
from .identifiers import Namespace, mangle
from .ir import (
    KIND_GROUP,
    KIND_REG,
    ChildRef,
    Design,
    EnumMember,
    EnumType,
    GroupType,
    RegType,
)
from .options import ExportOptions

# Re-export the IR under the name the plan uses, so callers can treat design.py
# as the single import for "the IR and the scanner".
__all__ = [
    "ChildRef", "Design", "DesignScanner", "EnumMember", "EnumType",
    "GroupType", "RegType", "KIND_GROUP", "KIND_REG",
]


class DesignScanner:
    def __init__(self, options: ExportOptions) -> None:
        self.options = options
        self.findings = diag.FindingLog()
        self._reg_types: List[RegType] = []
        self._group_types: List[GroupType] = []
        self._enums: List[EnumType] = []
        # (type_name, signature) -> emitted type name
        self._reg_index: Dict[Tuple[str, str], str] = {}
        self._group_index: Dict[Tuple[str, str], str] = {}
        self._enum_index: Dict[str, str] = {}
        # emitted type name -> RegType/GroupType, for signature lookup by name
        self._by_name: Dict[str, object] = {}
        # base type name -> number of variants allocated so far
        self._variant_count: Dict[str, int] = {}
        # package-level namespace, so no two emitted types can collide
        self._types_ns = Namespace()
        self.mangle_map: Dict[str, str] = {}

    # -- public -----------------------------------------------------------

    def scan(self, top: AddrmapNode) -> Design:
        package_name = self.options.package_name or "regs"
        design = Design(
            package_name=package_name,
            base_address=self.options.base_address,
            findings=self.findings,
        )

        top_type = self._scan_group(top)

        design.reg_types = self._reg_types
        design.group_types = self._group_types
        design.enums = self._enums
        design.top_type_name = top_type.type_name if top_type else ""
        design.top_size = int(top.size)
        design.mangle_map = self.mangle_map
        return design

    # -- naming -----------------------------------------------------------

    def _base_type_name(self, node: Node) -> str:
        """The unsuffixed emitted type name for *node*'s SystemRDL type."""
        if self.options.type_style == "hier":
            raw = node.get_path(
                array_suffix="", empty_array_suffix=""
            ).replace(".", "__")
        else:
            global_name = node.get_global_type_name("__")
            raw = global_name if global_name is not None else ""
            if global_name is None:
                # Anonymous/parameterized type with no derivable global name.
                # Fall back to the instance path, matching peakrdl-uvm's
                # ``xtern__`` convention but keeping it legible.
                raw = "anon__" + node.get_path(
                    array_suffix="", empty_array_suffix=""
                ).replace(".", "__")
        name, changed = mangle(raw, set())
        if changed:
            self.mangle_map.setdefault(raw, name)
        return name

    def _allocate_type_name(self, base: str) -> str:
        """Reserve *base*, or ``base__vN`` if *base* is already emitted.

        The suffix marks a *structural variant*: same SystemRDL type name,
        different content.  It is informational, not an error -- see
        ``PSS-I202``.
        """
        if base not in self._types_ns:
            self._types_ns.reserve(base)
            return base
        n = self._variant_count.get(base, 1) + 1
        while "%s__v%d" % (base, n) in self._types_ns:
            n += 1
        self._variant_count[base] = n
        name = "%s__v%d" % (base, n)
        self._types_ns.reserve(name)
        return name

    # -- registers --------------------------------------------------------

    def _scan_reg(self, reg: RegNode) -> Optional[RegType]:
        regwidth = int(reg.get_property("regwidth"))
        accesswidth = int(reg.get_property("accesswidth", default=regwidth))

        if regwidth > 64:
            self.findings.add(
                diag.E_REGWIDTH_TOO_WIDE,
                "regwidth=%d exceeds the 64-bit maximum PSS can access" % regwidth,
                reg,
            )
            return None
        if accesswidth < regwidth:
            self.findings.add(
                diag.E_ACCESSWIDTH_LT_REGWIDTH,
                "accesswidth=%d is narrower than regwidth=%d; the register would "
                "need multiple accesses" % (accesswidth, regwidth),
                reg,
            )
            return None

        rows = layout.build_rows(reg, self.options, self.findings)
        field_sw = [f.get_property("sw") for f in reg.fields()]
        reg_access = self._derive_access(reg, field_sw)
        is_msb0 = bool(reg.is_msb0_order)

        for row in rows:
            if row.enum_type is not None:
                self._intern_enum(reg, row)

        base = self._base_type_name(reg)
        sig = signature.of_reg(base, regwidth, accesswidth, reg_access, rows, is_msb0)

        key = (base, sig)
        existing = self._reg_index.get(key)
        if existing is not None:
            rt = self._by_name[existing]
            assert isinstance(rt, RegType)
            rt.instances.append(reg.get_path())
            return rt

        type_name = self._allocate_type_name(base)
        if type_name != base:
            self.findings.add(
                diag.I_TYPE_VARIANT,
                "structural variant of '%s' emitted as '%s'" % (base, type_name),
                reg,
                base=base,
                emitted=type_name,
            )

        rt = RegType(
            type_name=type_name,
            friendly=reg.get_path(),
            regwidth=regwidth,
            accesswidth=accesswidth,
            access=reg_access,
            fields=rows,
            reset_value=layout.reset_value(rows),
            is_msb0=is_msb0,
            signature=sig,
            instances=[reg.get_path()],
        )
        self._reg_types.append(rt)
        self._reg_index[key] = type_name
        self._by_name[type_name] = rt
        return rt

    def _derive_access(self, reg: RegNode, field_sw: List[object]) -> str:
        from systemrdl.rdltypes.builtin_enums import AccessType

        from . import access as access_mod

        sw_list = [sw for sw in field_sw if isinstance(sw, AccessType)]
        if sw_list and all(sw == AccessType.na for sw in sw_list):
            self.findings.add(
                diag.W_ALL_FIELDS_NA,
                "no field is software accessible; emitting READONLY",
                reg,
            )
        return access_mod.derive(sw_list)

    # -- enums ------------------------------------------------------------

    def _intern_enum(self, reg: RegNode, row: object) -> None:
        from .ir import FieldRow

        assert isinstance(row, FieldRow)
        rdl_name = row.enum_type
        if rdl_name is None or rdl_name in self._enum_index:
            return
        for fld in reg.fields():
            if fld.inst_name != row.rdl_name:
                continue
            encode = fld.get_property("encode", default=None)
            if encode is None:
                return
            members = []
            member_ns = Namespace()
            for member in encode:
                mname, _ = member_ns.allocate(member.name)
                members.append(EnumMember(
                    name=mname,
                    value=int(member.value),
                    rdl_name=member.name,
                    desc=getattr(member, "rdl_desc", None),
                ))
            name, changed = mangle(rdl_name, set())
            et = EnumType(
                name=name, rdl_name=rdl_name, width=row.width, members=tuple(members)
            )
            self._enums.append(et)
            self._enum_index[rdl_name] = name
            if changed:
                self.mangle_map.setdefault(rdl_name, name)
            return

    # -- groups -----------------------------------------------------------

    def _scan_group(self, node: AddressableNode) -> Optional[GroupType]:
        """Depth-first, post-order: children are interned before their parent,
        so a parent's signature can incorporate its children's signatures."""
        if isinstance(node, AddrmapNode) and node.get_property("bridge", default=False):
            self.findings.add(
                diag.E_BRIDGE,
                "bridge addrmaps introduce a second address space",
                node,
            )
            return None

        children: List[ChildRef] = []
        child_sigs: List[str] = []
        member_ns = Namespace()
        # Reset constants are named after their instance, so they can collide
        # with a *later* sibling instance ("ctrl" and "ctrl_reset" side by side).
        # Instance names must win -- renaming a register out from under the user
        # would change the key of get_offset_of_instance -- so the constants are
        # deferred to a second pass, after every instance name is reserved.
        pending_resets: List[Tuple[str, RegType]] = []

        for child in node.children(unroll=False):
            if not isinstance(child, AddressableNode):
                continue  # signals and similar are not addressable members

            if isinstance(child, MemNode):
                self.findings.add(
                    diag.E_MEM,
                    "memories are not representable in the generated package",
                    child,
                )
                continue

            if isinstance(child, RegNode):
                if child.is_alias:
                    self.findings.add(
                        diag.I_ALIAS_DROPPED,
                        "alias register '%s' is emitted as an independent register"
                        % child.inst_name,
                        child,
                    )
                sub = self._scan_reg(child)
                kind = KIND_REG
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                sub = self._scan_group(child)  # type: ignore[assignment]
                kind = KIND_GROUP
            else:
                continue

            if sub is None:
                continue  # an error was recorded; keep scanning to report all of them

            inst_name, changed = member_ns.allocate(child.inst_name)
            if changed:
                self.findings.add(
                    diag.I_MANGLED,
                    "instance '%s' renamed to '%s'" % (child.inst_name, inst_name),
                    child,
                    original=child.inst_name,
                    emitted=inst_name,
                )
                self.mangle_map.setdefault(child.get_path(), inst_name)

            is_array, dims, count, stride = addressing.child_geometry(child)
            offset = int(child.raw_address_offset)

            ref = ChildRef(
                inst_name=inst_name,
                rdl_name=child.inst_name,
                type_name=sub.type_name,
                kind=kind,
                offset=offset,
                is_array=is_array,
                flat_count=count,
                dims=dims,
                stride=stride,
            )
            children.append(ref)
            child_sigs.append(sub.signature)

            self._check_alignment(child, offset)

            if (
                self.options.emit_reset_consts
                and kind == KIND_REG
                and isinstance(sub, RegType)
                and sub.reset_value is not None
            ):
                pending_resets.append((inst_name, sub))

        reset_consts = [
            self._reset_const(member_ns, inst_name, rt)
            for inst_name, rt in pending_resets
        ]

        base = self._base_type_name(node)
        sig = signature.of_group(base, children, child_sigs, reset_consts)

        key = (base, sig)
        existing = self._group_index.get(key)
        if existing is not None:
            gt = self._by_name[existing]
            assert isinstance(gt, GroupType)
            gt.instances.append(node.get_path())
            return gt

        type_name = self._allocate_type_name(base)
        if type_name != base:
            self.findings.add(
                diag.I_TYPE_VARIANT,
                "structural variant of '%s' emitted as '%s'" % (base, type_name),
                node,
                base=base,
                emitted=type_name,
            )

        gt = GroupType(
            type_name=type_name,
            friendly=node.get_path(),
            children=children,
            size=int(node.size),
            signature=sig,
            instances=[node.get_path()],
            reset_consts=reset_consts,
        )
        self._group_types.append(gt)
        self._group_index[key] = type_name
        self._by_name[type_name] = gt
        return gt

    def _reset_const(
        self, member_ns: Namespace, inst_name: str, rt: RegType
    ) -> Tuple[str, int, int]:
        """Allocate the ``<inst>_reset`` companion constant (see plan §4.9).

        Allocated from the *same* namespace as the child instances, so a register
        literally named ``r1_reset`` sitting beside ``r1`` cannot collide with
        ``r1``'s generated constant.  One constant per array instance: array
        elements share a type and therefore a reset.
        """
        name, _ = member_ns.allocate("%s_reset" % inst_name)
        assert rt.reset_value is not None
        return (name, rt.regwidth, rt.reset_value)

    def _check_alignment(self, node: AddressableNode, offset: int) -> None:
        if isinstance(node, RegNode):
            width = int(node.get_property("regwidth"))
            size = max(width // 8, 1)
            if offset % size:
                self.findings.add(
                    diag.W_UNALIGNED,
                    "offset 0x%x is not a multiple of the %d-byte access size"
                    % (offset, size),
                    node,
                )


def scan(top: Node, options: ExportOptions) -> Design:
    """Convenience entry point: accepts a ``RootNode`` or an addressable node."""
    if isinstance(top, RootNode):
        top = top.top
    assert isinstance(top, AddrmapNode)
    return DesignScanner(options).scan(top)

"""Checks that run against the IR, after the scan and before rendering.

Most findings are raised by the scanner, where the SystemRDL node is in hand.
This module owns the checks that need a *whole-design* view -- ones no single
node can answer -- plus the invariants that assert the IR itself is well-formed
before it reaches a template.

The IR invariants are not user-facing diagnostics: if one fails it is a bug in
this exporter, not in the input, so it raises ``AssertionError`` rather than
producing a ``Finding``.  Conflating the two would let a generator bug be
reported as a problem with the user's SystemRDL.
"""

from typing import Dict, List

from . import layout
from .ir import Design
from .options import ExportOptions


class Validator:
    def __init__(self, options: ExportOptions) -> None:
        self.options = options

    def run(self, design: Design) -> None:
        self._check_ir_invariants(design)
        self._check_unique_type_names(design)

    def _check_ir_invariants(self, design: Design) -> None:
        for rt in design.reg_types:
            assert layout.rows_cover(rt.fields), (
                "internal error: field rows of %s are not contiguous from bit 0; "
                "packed_s would misplace every field after the discontinuity"
                % rt.type_name
            )
            if rt.fields:
                assert rt.fields[-1].msb < rt.regwidth, (
                    "internal error: field rows of %s extend past regwidth=%d"
                    % (rt.type_name, rt.regwidth)
                )
            for row in rt.fields:
                assert row.width == row.msb - row.lsb + 1, (
                    "internal error: width/bit-range mismatch in %s.%s"
                    % (rt.type_name, row.name)
                )

        for gt in design.group_types:
            for child in gt.children:
                if child.is_array:
                    assert child.flat_count and child.flat_count > 0, (
                        "internal error: array child %s.%s has no element count"
                        % (gt.type_name, child.inst_name)
                    )

    def _check_unique_type_names(self, design: Design) -> None:
        """Two emitted types sharing a name is unrepresentable, not merely lossy.

        The scanner allocates names from one namespace so this cannot happen; the
        check exists because the consequence -- a package that fails to link, or
        worse, links against the wrong type -- is severe enough to be worth
        asserting rather than assuming.
        """
        seen: Dict[str, str] = {}
        collisions: List[str] = []
        for rt in design.reg_types:
            for name in (rt.struct_name, rt.component_name):
                if name in seen:
                    collisions.append(name)
                seen[name] = rt.type_name
        for gt in design.group_types:
            name = gt.component_name
            if name in seen:
                collisions.append(name)
            seen[name] = gt.type_name
        for et in design.enums:
            if et.name in seen:
                collisions.append(et.name)
            seen[et.name] = et.name
        assert not collisions, (
            "internal error: duplicate emitted type name(s): %s" % ", ".join(collisions)
        )

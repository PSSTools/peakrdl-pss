"""PeakRDL exporter plugin.

``do_export`` is intentionally logic-free: every option maps one-to-one onto an
``export()`` keyword of the same name, and ``tests/integration/test_cli_parity.py``
asserts that mapping is total in both directions.  Any logic here would be logic
the Python API does not get.
"""

from typing import TYPE_CHECKING

from peakrdl.config import schema
from peakrdl.plugins.exporter import ExporterSubcommandPlugin

from .exporter import PSSExporter
from .options import ENUM_MODES, OFFSET_MODES, TYPE_STYLES

if TYPE_CHECKING:  # pragma: no cover
    import argparse

    from systemrdl.node import AddrmapNode


def _auto_int(text: str) -> int:
    """Accept 0x-prefixed addresses as well as decimal."""
    return int(text, 0)


class Exporter(ExporterSubcommandPlugin):
    short_desc = "Generate a PSS register package"
    long_desc = (
        "Export the SystemRDL register model as a PSS (Portable Test and Stimulus) "
        "register package: a packed_s struct and reg_c component per register type, "
        "and a reg_group_c component per addrmap/regfile."
    )

    cfg_schema = {
        "user_template_dir": schema.DirectoryPath(),
        "user_template_context": schema.UserMapping(schema.String()),
    }

    def add_exporter_arguments(self, arg_group: "argparse._ActionsContainer") -> None:
        arg_group.add_argument(
            "--package-name",
            default=None,
            help="PSS package name (default: derived from the output file name)",
        )
        arg_group.add_argument(
            "--type-style",
            choices=TYPE_STYLES,
            default="lexical",
            help="How emitted type names are derived (default: lexical)",
        )
        arg_group.add_argument(
            "--emit-top",
            action="store_true",
            default=False,
            help="Also write a <output>_top.pss wrapper that binds the top group to "
                 "an address region",
        )
        arg_group.add_argument(
            "--base-address",
            type=_auto_int,
            default=0,
            help="Base address used by the --emit-top wrapper (default: 0)",
        )
        arg_group.add_argument(
            "--emit-enums",
            choices=ENUM_MODES,
            default="const",
            help="How SystemRDL 'encode' enumerations are emitted (default: const)",
        )
        arg_group.add_argument(
            "--emit-reset-consts",
            action="store_true",
            default=False,
            help="Emit a 'static const' reset value beside each register instance",
        )
        arg_group.add_argument(
            "--emit-index-helpers",
            action="store_true",
            default=False,
            help="Emit an index-flattening helper function for each N-D array",
        )
        arg_group.add_argument(
            "--pad-tail",
            action="store_true",
            default=False,
            help="Pad each register struct with a reserved field up to regwidth",
        )
        arg_group.add_argument(
            "--rsvd-prefix",
            default="rsvd_",
            help="Name prefix for generated reserved fields (default: rsvd_)",
        )
        arg_group.add_argument(
            "--no-pure",
            action="store_true",
            default=False,
            help="Emit components without the 'pure' qualifier",
        )
        arg_group.add_argument(
            "--offset-mode",
            choices=OFFSET_MODES,
            default="instance",
            help="Which get_offset_of_* functions to implement (default: instance)",
        )
        arg_group.add_argument(
            "--sidecar",
            dest="sidecar_path",
            default=None,
            metavar="PATH",
            help="Write a JSON record of everything the PSS output cannot represent",
        )
        arg_group.add_argument(
            "--strict",
            action="store_true",
            default=False,
            help="Treat warnings as errors",
        )

    def do_export(self, top_node: "AddrmapNode", options: "argparse.Namespace") -> None:
        exporter = PSSExporter(
            user_template_dir=self.cfg["user_template_dir"],
            user_template_context=self.cfg["user_template_context"],
        )
        exporter.export(
            top_node,
            options.output,
            package_name=options.package_name,
            type_style=options.type_style,
            emit_top=options.emit_top,
            base_address=options.base_address,
            emit_enums=options.emit_enums,
            emit_reset_consts=options.emit_reset_consts,
            emit_index_helpers=options.emit_index_helpers,
            pad_tail=options.pad_tail,
            rsvd_prefix=options.rsvd_prefix,
            pure_components=not options.no_pure,
            offset_mode=options.offset_mode,
            sidecar_path=options.sidecar_path,
            strict=options.strict,
        )

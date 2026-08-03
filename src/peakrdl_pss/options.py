"""One object threaded through scanner, validator, and renderer.

Every CLI flag maps to exactly one field here and to one ``export()`` keyword of
the same name; ``tests/integration/test_cli_parity.py`` asserts that mapping is
total in both directions, which is how the CLI and the Python API stay in sync
as flags are added.
"""

from dataclasses import dataclass
from typing import Optional

TYPE_STYLES = ("lexical", "hier")
ENUM_MODES = ("const", "typed", "off")
OFFSET_MODES = ("instance", "path")


@dataclass(frozen=True)
class ExportOptions:
    package_name: Optional[str] = None
    type_style: str = "lexical"
    emit_top: bool = False
    base_address: int = 0
    emit_enums: str = "const"
    emit_reset_consts: bool = False
    emit_index_helpers: bool = False
    pad_tail: bool = False
    rsvd_prefix: str = "rsvd_"
    pure_components: bool = True
    offset_mode: str = "instance"
    sidecar_path: Optional[str] = None
    strict: bool = False

    def validate(self) -> None:
        if self.type_style not in TYPE_STYLES:
            raise ValueError("type_style must be one of %s" % (TYPE_STYLES,))
        if self.emit_enums not in ENUM_MODES:
            raise ValueError("emit_enums must be one of %s" % (ENUM_MODES,))
        if self.offset_mode not in OFFSET_MODES:
            raise ValueError("offset_mode must be one of %s" % (OFFSET_MODES,))
        if self.emit_enums == "typed":
            raise NotImplementedError(
                "--emit-enums=typed requires a pssparser release with typed enum base "
                "types (parser requirements Tier 1.1); use 'const' (the default)"
            )
        if self.offset_mode == "path":
            raise NotImplementedError(
                "--offset-mode=path requires a pssparser release with node_s/"
                "get_offset_of_path (parser requirements Tier 1.3); use 'instance' "
                "(the default)"
            )

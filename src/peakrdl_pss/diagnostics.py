"""Diagnostic identity: severities, the stable ID table, and ``Finding``.

Split out of ``validate.py`` (which the plan named as the owner) because the
*scanner* also raises findings, and validate.py imports the IR that design.py
defines.  Keeping ``Finding`` here breaks that cycle and gives the docs
generator a single module to introspect.

IDs are stable strings.  Docs (``diagnostics.rst``) and tests reference the ID,
never the message text, so message wording can be improved without breaking
either.
"""

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class Severity(enum.IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2


@dataclass(frozen=True)
class DiagSpec:
    id: str
    severity: Severity
    title: str
    #: Short explanation used by the generated ``diagnostics.rst`` page.
    detail: str


def _spec(id: str, sev: Severity, title: str, detail: str) -> DiagSpec:
    return DiagSpec(id=id, severity=sev, title=title, detail=detail)


# --- Errors: unconditional, never downgraded ------------------------------
# These four implement the review's "Unsupported" answers.  Each produces output
# that *parses* but is wrong, so a warning would ship silent wrongness.

E_REGWIDTH_TOO_WIDE = _spec(
    "PSS-E001", Severity.ERROR, "regwidth greater than 64",
    "PSS register access is defined over integer types of at most 64 bits. A wider "
    "register cannot be represented; split it in the SystemRDL description.",
)
E_ACCESSWIDTH_LT_REGWIDTH = _spec(
    "PSS-E002", Severity.ERROR, "accesswidth less than regwidth",
    "A register accessed in multiple bus transactions has no PSS representation: "
    "reg_c models a single access of the full register width.",
)
E_BRIDGE = _spec(
    "PSS-E003", Severity.ERROR, "bridge addrmap",
    "A bridge introduces a second address space. The generated package models one "
    "transparent address space; export each side separately with --top.",
)
E_MEM = _spec(
    "PSS-E004", Severity.ERROR, "mem component",
    "Memories are not representable as reg_group_c members and are not exported.",
)
# There is deliberately no PSS-E005 for "regwidth not in {8,16,32,64}".
# systemrdl-compiler's own elaboration already fatals on regwidth < 8 and on
# regwidth that is not a power of 2, so the only width that can reach us outside
# that set is > 64 -- which PSS-E001 already owns.  Shipping an ID that can never
# appear in a diagnostic would leave a phantom entry in the docs.

# --- Warnings: promoted to errors under --strict --------------------------

W_SIDE_EFFECTS = _spec(
    "PSS-W101", Severity.WARNING, "field side-effect semantics dropped",
    "onread/onwrite/singlepulse/counter/interrupt behavior has no PSS equivalent and "
    "is recorded only in a comment (and the --sidecar file).",
)
W_ACCESS_APPROXIMATED = _spec(
    "PSS-W102", Severity.WARNING, "software access policy approximated",
    "sw=rw1/w1 and similar policies collapse to the nearest reg_access value.",
)
W_RESET_IS_REFERENCE = _spec(
    "PSS-W103", Severity.WARNING, "reset value is a reference",
    "A reset driven by a signal or field reference has no constant value; no reset "
    "constant is emitted for it.",
)
W_MIXED_ENDIAN = _spec(
    "PSS-W104", Severity.WARNING, "mixed endianness",
    "The generated packed structs assume LITTLE_ENDIAN throughout.",
)
W_MSB0_ORDER = _spec(
    "PSS-W105", Severity.WARNING, "msb0 field ordering",
    "In msb0 mode a field's most significant bit sits at its *low* register bit "
    "position, which implies a bit swap within the field. The generated packed_s "
    "member occupies the correct bit span but not the reversed bit order, which "
    "packed_s cannot express: consumers must swap the field value themselves.",
)
W_UNALIGNED = _spec(
    "PSS-W106", Severity.WARNING, "unaligned register offset",
    "The register offset is not a multiple of its access size.",
)
W_ALL_FIELDS_NA = _spec(
    "PSS-W107", Severity.WARNING, "no software-accessible fields",
    "No field is software accessible; the register is emitted as READONLY.",
)

# --- Info: never promoted -------------------------------------------------

I_MANGLED = _spec(
    "PSS-I201", Severity.INFO, "identifier renamed",
    "The SystemRDL name is not a legal PSS identifier, or collided; it was renamed.",
)
I_TYPE_VARIANT = _spec(
    "PSS-I202", Severity.INFO, "structural type variant emitted",
    "Two instances share a SystemRDL type name but differ structurally (typically a "
    "dynamic property assignment), so a __vN variant type was emitted.",
)
I_ALIAS_DROPPED = _spec(
    "PSS-I203", Severity.INFO, "alias relationship dropped",
    "The register is emitted normally; its alias relationship is not represented.",
)

#: Every diagnostic the exporter can raise, in ID order.  ``diagnostics.rst`` is
#: generated from this tuple and a test asserts every entry is documented, so a
#: new check cannot ship undocumented.
ALL_SPECS: Tuple[DiagSpec, ...] = (
    E_REGWIDTH_TOO_WIDE,
    E_ACCESSWIDTH_LT_REGWIDTH,
    E_BRIDGE,
    E_MEM,
    W_SIDE_EFFECTS,
    W_ACCESS_APPROXIMATED,
    W_RESET_IS_REFERENCE,
    W_MIXED_ENDIAN,
    W_MSB0_ORDER,
    W_UNALIGNED,
    W_ALL_FIELDS_NA,
    I_MANGLED,
    I_TYPE_VARIANT,
    I_ALIAS_DROPPED,
)

SPEC_BY_ID: Dict[str, DiagSpec] = {s.id: s for s in ALL_SPECS}


@dataclass
class Finding:
    spec: DiagSpec
    message: str
    #: RDL path of the offending node, for tests and the sidecar.
    path: str = ""
    #: The systemrdl ``SourceRefBase`` for the node, when available.
    src_ref: Any = None
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def severity(self) -> Severity:
        return self.spec.severity

    def effective_severity(self, strict: bool) -> Severity:
        if strict and self.severity == Severity.WARNING:
            return Severity.ERROR
        return self.severity

    def render(self) -> str:
        loc = " (%s)" % self.path if self.path else ""
        return "%s: %s%s" % (self.id, self.message, loc)


class FindingLog:
    """Ordered, append-only collection of findings."""

    def __init__(self) -> None:
        self.findings: List[Finding] = []

    def add(
        self,
        spec: DiagSpec,
        message: str,
        node: Any = None,
        **context: Any,
    ) -> Finding:
        path = ""
        src_ref = None
        if node is not None:
            try:
                path = node.get_path()
            except Exception:  # pragma: no cover - defensive
                path = ""
            src_ref = getattr(node, "inst", None)
            src_ref = getattr(src_ref, "inst_src_ref", None)
        f = Finding(spec=spec, message=message, path=path, src_ref=src_ref, context=context)
        self.findings.append(f)
        return f

    def by_id(self, id: str) -> List[Finding]:
        return [f for f in self.findings if f.id == id]

    def ids(self) -> List[str]:
        return [f.id for f in self.findings]

    def has_errors(self, strict: bool = False) -> bool:
        return any(f.effective_severity(strict) == Severity.ERROR for f in self.findings)

    def errors(self, strict: bool = False) -> List[Finding]:
        return [f for f in self.findings if f.effective_severity(strict) == Severity.ERROR]

    def extend(self, other: "FindingLog") -> None:
        self.findings.extend(other.findings)

    def __len__(self) -> int:
        return len(self.findings)

    def __iter__(self) -> Any:
        return iter(self.findings)


class PSSExportError(Exception):
    """Raised when the export cannot produce correct output."""

    def __init__(self, findings: Optional[List[Finding]] = None) -> None:
        self.findings = findings or []
        if self.findings:
            detail = "\n".join("  " + f.render() for f in self.findings)
            super().__init__(
                "PSS export failed with %d error(s):\n%s" % (len(self.findings), detail)
            )
        else:
            super().__init__("PSS export failed")

"""Shared test helpers.

Written before any feature test, because every later test depends on them and
because the shape of these helpers determines what the suite can assert.  Two
choices here matter more than they look:

* ``compile_rdl`` captures compiler messages instead of printing them, so tests
  can assert on diagnostics rather than on stdout.
* ``assert_golden`` regenerates via an environment variable.  Without that,
  goldens get "fixed" by hand-editing the expectation, which quietly turns a
  regression test into a transcript of whatever the code does today.
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pytest
from systemrdl import RDLCompiler
from systemrdl.messages import MessagePrinter
from systemrdl.node import AddrmapNode, RootNode

from peakrdl_pss.exporter import PSSExporter

TESTS_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))
RDL_DIR = os.path.join(TESTS_DIR, "golden", "rdl")
EXPECT_DIR = os.path.join(TESTS_DIR, "golden", "expect")

UPDATE_GOLDEN_ENV = "PEAKRDL_PSS_UPDATE_GOLDEN"


# --- compiling -----------------------------------------------------------


@dataclass
class CapturedMessage:
    severity: str
    text: str


class _CapturingPrinter(MessagePrinter):
    def __init__(self) -> None:
        super().__init__()
        self.messages: List[CapturedMessage] = []

    def emit_message(self, lines: Sequence[str]) -> None:
        self.messages.append(CapturedMessage("", "\n".join(lines)))


def rdl_path(name: str) -> str:
    if not name.endswith(".rdl"):
        name += ".rdl"
    return os.path.join(RDL_DIR, name)


def compile_rdl(*sources: str, top: Optional[str] = None) -> RootNode:
    """Compile corpus files (by bare name) or absolute paths."""
    printer = _CapturingPrinter()
    rdlc = RDLCompiler(message_printer=printer)
    for src in sources:
        rdlc.compile_file(src if os.path.isabs(src) else rdl_path(src))
    root = rdlc.elaborate(top_def_name=top)
    return root


def compile_text(text: str, tmp_path: Any, name: str = "inline") -> RootNode:
    """Compile an inline RDL snippet -- used by the docs-example tests."""
    path = os.path.join(str(tmp_path), name + ".rdl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return compile_rdl(path)


def top_of(root: RootNode) -> AddrmapNode:
    return root.top


# --- exporting -----------------------------------------------------------


def export_str(root: Any, tmp_path: Any, **kwargs: Any) -> str:
    """Export to a temp file and return the text.

    Everything goes through a temp path; no test writes into the repo tree.
    """
    out = os.path.join(str(tmp_path), "out.pss")
    PSSExporter().export(root, out, **kwargs)
    with open(out, "r", encoding="utf-8") as f:
        return f.read()


def export_file(root: Any, tmp_path: Any, name: str = "out.pss", **kwargs: Any) -> str:
    out = os.path.join(str(tmp_path), name)
    PSSExporter().export(root, out, **kwargs)
    return out


# --- pssparser gate ------------------------------------------------------


@dataclass
class ParseResult:
    returncode: int
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    raw: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def pssparser_exe() -> Optional[str]:
    return shutil.which("pssparser") or shutil.which(
        "pssparser", path=os.path.dirname(sys.executable)
    )


def require_pssparser() -> str:
    """Skip -- not fail -- when the parser is unavailable.

    The suite has to be usable outside this workspace; a missing external tool is
    a missing capability, not a defect in the exporter.  CI pins it as a hard gate
    separately (see the parser-gate job).
    """
    exe = pssparser_exe()
    if exe is None:
        pytest.skip("pssparser CLI not found on PATH")
    return exe


def run_pssparser(*paths: str) -> ParseResult:
    exe = require_pssparser()
    proc = subprocess.run(
        [exe, "--json", *paths], capture_output=True, text=True, timeout=300
    )
    diags: List[Dict[str, Any]] = []
    out = proc.stdout.strip()
    if out:
        try:
            parsed = json.loads(out)
            diags = parsed if isinstance(parsed, list) else parsed.get("diagnostics", [])
        except json.JSONDecodeError:
            pass
    return ParseResult(proc.returncode, diags, proc.stdout + proc.stderr)


def assert_parses(*paths: str) -> None:
    result = run_pssparser(*paths)
    assert result.ok, "pssparser rejected generated output:\n%s" % result.raw


# --- goldens -------------------------------------------------------------


def assert_golden(text: str, name: str) -> None:
    """Compare *text* against ``tests/golden/expect/<name>``.

    Set ``PEAKRDL_PSS_UPDATE_GOLDEN=1`` to rewrite expectations after an
    intentional change; review the resulting diff like any other code change.
    """
    path = os.path.join(EXPECT_DIR, name)
    if os.environ.get(UPDATE_GOLDEN_ENV):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return
    if not os.path.exists(path):
        raise AssertionError(
            "missing golden %s; run with %s=1 to create it" % (path, UPDATE_GOLDEN_ENV)
        )
    with open(path, "r", encoding="utf-8") as f:
        expected = f.read()
    assert text == expected, (
        "output differs from golden %s\n"
        "If the change is intended, re-run with %s=1 and review the diff."
        % (name, UPDATE_GOLDEN_ENV)
    )


# --- findings ------------------------------------------------------------


def finding_ids(design: Any) -> List[str]:
    return [f.id for f in design.findings]


def assert_finding(design: Any, id: str, count: Optional[int] = None) -> None:
    """Assert by diagnostic ID, never by message text, so wording can improve."""
    hits = [f for f in design.findings if f.id == id]
    assert hits, "expected finding %s; got %s" % (id, sorted(set(finding_ids(design))))
    if count is not None:
        assert len(hits) == count, "expected %d x %s, got %d" % (count, id, len(hits))


def assert_no_finding(design: Any, id: str) -> None:
    hits = [f.id for f in design.findings if f.id == id]
    assert not hits, "unexpected finding %s" % id

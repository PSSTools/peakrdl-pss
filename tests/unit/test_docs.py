"""Keep the documentation from drifting away from the code.

Documentation drift is invisible until a user hits it, so the checks that can be
mechanized should be.  These are cheap and they cover the two places drift
actually happens: diagnostics added without documentation, and options added
without documentation.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peakrdl_pss.diagnostics import ALL_SPECS, Severity  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(REPO, "docs")


def _docs_text():
    if not os.path.isdir(DOCS):
        pytest.skip("docs/ not present")
    out = []
    for root, _, files in os.walk(DOCS):
        if "_build" in root or "design" in root:
            continue
        for fn in files:
            if fn.endswith(".rst"):
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    out.append(f.read())
    return "\n".join(out)


def test_every_diagnostic_is_documented():
    """diagnostics.rst is generated from ALL_SPECS, so an ID is documented by
    construction -- but only if the generating directive is actually invoked for
    its severity class."""
    text = _docs_text()
    for severity, directive in (
        (Severity.ERROR, "error"),
        (Severity.WARNING, "warning"),
        (Severity.INFO, "info"),
    ):
        if any(s.severity == severity for s in ALL_SPECS):
            assert ".. pss-diagnostics:: %s" % directive in text, (
                "diagnostics of severity %s exist but no page generates them"
                % severity.name
            )


def test_every_error_has_a_remedy_section():
    """An error page that only restates the message is not worth reading; each
    refusal must say what to do instead."""
    path = os.path.join(DOCS, "unsupported.rst")
    if not os.path.exists(path):
        pytest.skip("unsupported.rst not present")
    text = open(path, encoding="utf-8").read()

    for spec in ALL_SPECS:
        if spec.severity != Severity.ERROR:
            continue
        assert spec.id.lower() in text.lower(), (
            "%s is not covered by unsupported.rst" % spec.id
        )
    assert text.count("**What to do") >= sum(
        1 for s in ALL_SPECS if s.severity == Severity.ERROR
    ), "every error needs a 'What to do' remedy"


def test_every_cli_option_is_documented():
    text = open(os.path.join(DOCS, "cli.rst"), encoding="utf-8").read()
    flags = {
        "--" + name.replace("_", "-")
        for name in ExportOptions.__dataclass_fields__
        if name not in ("package_name", "sidecar_path", "pure_components")
    }
    flags |= {"--package-name", "--sidecar", "--no-pure"}
    missing = sorted(f for f in flags if f not in text)
    assert not missing, "CLI options missing from cli.rst: %s" % missing


def test_no_stale_reference_to_removed_features():
    """Symbolic register names, mnemonics, --pss-level, and --mem-mode were
    removed from scope. A doc that still mentions them sends users looking for
    flags that do not exist."""
    text = _docs_text()
    for removed in ("--mem-mode", "--pss-level", "--symbolic-names",
                    "--mnemonic-style", "use_symbolic_reg_names"):
        assert removed not in text, (
            "%s was removed from scope but is still documented" % removed
        )


def test_documented_diagnostic_ids_all_exist():
    """The reverse direction: a doc referencing PSS-E005 after it was retired
    would send users looking for a check that no longer exists."""
    known = {s.id for s in ALL_SPECS}
    referenced = set(re.findall(r"PSS-[EWI]\d{3}", _docs_text()))
    unknown = sorted(referenced - known)
    assert not unknown, "docs reference nonexistent diagnostics: %s" % unknown

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_rdl  # noqa: E402

from peakrdl_pss import diagnostics as diag  # noqa: E402
from peakrdl_pss.design import DesignScanner  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402


def _scan(name, **kwargs):
    return DesignScanner(ExportOptions(package_name="p", **kwargs)).scan(
        compile_rdl(name).top
    )


def test_every_spec_has_a_unique_id():
    ids = [s.id for s in diag.ALL_SPECS]
    assert len(ids) == len(set(ids))


def test_id_prefix_matches_severity():
    """The ID itself has to tell the truth: users grep for PSS-E before reading
    anything else."""
    for spec in diag.ALL_SPECS:
        prefix = spec.id.split("-")[1][0]
        expected = {"E": diag.Severity.ERROR, "W": diag.Severity.WARNING,
                    "I": diag.Severity.INFO}[prefix]
        assert spec.severity == expected, "%s is severity %s" % (spec.id, spec.severity)


def test_no_gaps_in_the_error_id_range():
    """A missing PSS-E005 reads as a lost check, so if one is ever retired the
    remaining IDs must stay contiguous or the gap must be deliberate."""
    errors = sorted(s.id for s in diag.ALL_SPECS if s.severity == diag.Severity.ERROR)
    assert errors == ["PSS-E001", "PSS-E002", "PSS-E003", "PSS-E004"]


def test_every_spec_has_a_detail_for_the_docs():
    for spec in diag.ALL_SPECS:
        assert spec.detail.strip(), "%s has no detail text" % spec.id
        assert spec.title.strip(), "%s has no title" % spec.id


def test_strict_promotes_warnings_but_not_info():
    warn = diag.Finding(diag.W_MSB0_ORDER, "x")
    info = diag.Finding(diag.I_MANGLED, "x")
    err = diag.Finding(diag.E_MEM, "x")

    assert warn.effective_severity(strict=False) == diag.Severity.WARNING
    assert warn.effective_severity(strict=True) == diag.Severity.ERROR
    assert info.effective_severity(strict=True) == diag.Severity.INFO
    assert err.effective_severity(strict=False) == diag.Severity.ERROR


def test_findings_are_ordered_by_discovery():
    log = diag.FindingLog()
    log.add(diag.I_MANGLED, "first")
    log.add(diag.W_MSB0_ORDER, "second")
    assert [f.message for f in log] == ["first", "second"]


# --- the errors, through real designs ------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("err_width_128", "PSS-E001"),
    ("err_accesswidth", "PSS-E002"),
    ("err_bridge", "PSS-E003"),
    ("err_mem", "PSS-E004"),
])
def test_unsupported_constructs_raise_their_error(name, expected):
    design = _scan(name)
    assert expected in design.findings.ids()
    assert design.findings.has_errors()


def test_all_problems_are_reported_in_one_run():
    """Aborting at the first error would cost a user one round trip per problem."""
    design = _scan("err_multi")
    ids = set(design.findings.ids())
    assert {"PSS-E001", "PSS-E002", "PSS-E004"} <= ids, (
        "expected all three errors in one scan, got %s" % sorted(ids)
    )


@pytest.mark.parametrize("name,expected", [
    ("msb0", "PSS-W105"),
    ("access_matrix", "PSS-W101"),
    ("access_matrix", "PSS-W102"),
    ("alias", "PSS-I203"),
    ("keywords", "PSS-I201"),
])
def test_expected_diagnostics_are_raised(name, expected):
    assert expected in _scan(name).findings.ids()


def test_clean_designs_raise_no_warnings_or_errors():
    """A plain design must be quiet. A generator that warns about everything
    trains users to ignore it."""
    for name in ("scalar_regs", "arrays_1d", "widths", "deep"):
        design = _scan(name)
        noisy = [
            f.id for f in design.findings
            if f.severity != diag.Severity.INFO
        ]
        assert not noisy, "%s produced unexpected diagnostics: %s" % (name, noisy)


def test_error_findings_carry_a_source_reference():
    """Without a src_ref, PeakRDL cannot print file/line and the user is left
    grepping for the construct."""
    design = _scan("err_mem")
    for finding in design.findings.errors():
        assert finding.src_ref is not None, "%s has no src_ref" % finding.id
        assert finding.path, "%s has no RDL path" % finding.id

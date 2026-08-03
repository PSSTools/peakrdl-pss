"""End-to-end through the ``peakrdl pss`` subcommand.

These are the only tests that exercise plugin discovery, argparse wiring, and
process exit codes -- everything a user hits before any of our Python runs.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import rdl_path, run_pssparser  # noqa: E402


def peakrdl(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "peakrdl", *args],
        capture_output=True, text=True, cwd=cwd,
    )


def test_subcommand_is_discovered():
    proc = peakrdl("--help")
    assert proc.returncode == 0
    assert "pss" in proc.stdout


def test_help_lists_every_flag():
    proc = peakrdl("pss", "--help")
    assert proc.returncode == 0
    for flag in (
        "--package-name", "--type-style", "--emit-top", "--base-address",
        "--emit-enums", "--emit-reset-consts", "--emit-index-helpers",
        "--pad-tail", "--rsvd-prefix", "--no-pure", "--offset-mode",
        "--sidecar", "--strict",
    ):
        assert flag in proc.stdout, "%s is missing from --help" % flag


def test_end_to_end_export(tmp_path):
    out = str(tmp_path / "basic.pss")
    proc = peakrdl("pss", rdl_path("basic"), "-o", out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.exists(out)
    assert "package" in open(out).read()


def test_emit_top_writes_both_files(tmp_path):
    out = str(tmp_path / "basic.pss")
    proc = peakrdl("pss", rdl_path("basic"), "-o", out, "--emit-top")
    assert proc.returncode == 0, proc.stderr
    assert os.path.exists(out)
    assert os.path.exists(str(tmp_path / "basic_top.pss"))


def test_base_address_accepts_hex(tmp_path):
    out = str(tmp_path / "basic.pss")
    proc = peakrdl(
        "pss", rdl_path("basic"), "-o", out, "--emit-top", "--base-address", "0x80000000"
    )
    assert proc.returncode == 0, proc.stderr
    assert "0x80000000" in open(str(tmp_path / "basic_top.pss")).read()


def test_package_name_defaults_to_the_output_stem(tmp_path):
    out = str(tmp_path / "my_regs.pss")
    assert peakrdl("pss", rdl_path("basic"), "-o", out).returncode == 0
    assert "package my_regs {" in open(out).read()


def test_sidecar_is_valid_json(tmp_path):
    out = str(tmp_path / "basic.pss")
    side = str(tmp_path / "basic.json")
    proc = peakrdl("pss", rdl_path("basic"), "-o", out, "--sidecar", side)
    assert proc.returncode == 0, proc.stderr
    payload = json.load(open(side))
    assert payload["version"] == 1
    assert payload["registers"]
    assert all("fields" in r for r in payload["registers"])


@pytest.mark.parametrize("name,expected", [
    ("err_width_128", "PSS-E001"),
    ("err_accesswidth", "PSS-E002"),
    ("err_mem", "PSS-E004"),
])
def test_unsupported_constructs_fail_without_strict(name, expected, tmp_path):
    """These are refusals, not warnings: --strict must be irrelevant to them."""
    out = str(tmp_path / "out.pss")
    proc = peakrdl("pss", rdl_path(name), "-o", out)
    assert proc.returncode != 0
    assert expected in proc.stderr + proc.stdout


@pytest.mark.parametrize("name", ["err_width_128", "err_mem", "err_multi"])
def test_failed_export_leaves_no_output_file(name, tmp_path):
    """A partial file is worse than none: a later build step would consume it."""
    out = str(tmp_path / "out.pss")
    proc = peakrdl("pss", rdl_path(name), "-o", out)
    assert proc.returncode != 0
    assert not os.path.exists(out), "a failed export left %s behind" % out


def test_multiple_problems_are_all_reported(tmp_path):
    out = str(tmp_path / "out.pss")
    proc = peakrdl("pss", rdl_path("err_multi"), "-o", out)
    combined = proc.stderr + proc.stdout
    for expected in ("PSS-E001", "PSS-E002", "PSS-E004"):
        assert expected in combined, (
            "%s missing; the export stopped early instead of reporting every "
            "problem in one run" % expected
        )


def test_strict_turns_a_warning_into_a_failure(tmp_path):
    out = str(tmp_path / "out.pss")
    assert peakrdl("pss", rdl_path("msb0"), "-o", out).returncode == 0

    out2 = str(tmp_path / "out2.pss")
    proc = peakrdl("pss", rdl_path("msb0"), "-o", out2, "--strict")
    assert proc.returncode != 0
    assert "PSS-W105" in proc.stderr + proc.stdout


def test_strict_does_not_promote_info(tmp_path):
    """Renaming an identifier is not a defect; --strict must not make it one."""
    out = str(tmp_path / "out.pss")
    proc = peakrdl("pss", rdl_path("keywords"), "-o", out, "--strict")
    assert proc.returncode == 0, proc.stderr


@pytest.mark.pssparser
def test_cli_output_parses(tmp_path):
    out = str(tmp_path / "basic.pss")
    assert peakrdl("pss", rdl_path("basic"), "-o", out).returncode == 0
    assert run_pssparser(out).ok

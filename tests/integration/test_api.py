"""The Python API used directly, without PeakRDL in the picture."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import assert_parses, compile_rdl  # noqa: E402

from peakrdl_pss import PSSExporter, PSSExportError  # noqa: E402


def test_export_accepts_a_root_node(tmp_path):
    root = compile_rdl("basic")
    out = str(tmp_path / "o.pss")
    PSSExporter().export(root, out)
    assert os.path.exists(out)


def test_export_accepts_a_top_addrmap_node(tmp_path):
    root = compile_rdl("basic")
    out = str(tmp_path / "o.pss")
    PSSExporter().export(root.top, out)
    assert os.path.exists(out)


def test_export_rejects_a_non_addrmap(tmp_path):
    root = compile_rdl("basic")
    reg = next(n for n in root.top.descendants() if hasattr(n, "fields"))
    with pytest.raises(TypeError):
        PSSExporter().export(reg, str(tmp_path / "o.pss"))


def test_peakrdl_is_not_required_at_runtime():
    """peakrdl is a plugin host, not a dependency.

    Importing the exporter must work in an environment that has only
    systemrdl-compiler and jinja2 -- otherwise every API user pays for a CLI
    they are not using.
    """
    import importlib
    import subprocess

    script = (
        "import sys;"
        "sys.modules['peakrdl'] = None;"
        "import peakrdl_pss;"
        "print(peakrdl_pss.PSSExporter.__name__)"
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "PSSExporter" in proc.stdout
    importlib.invalidate_caches()


def test_export_error_names_every_failing_construct(tmp_path):
    root = compile_rdl("err_multi")
    with pytest.raises(PSSExportError) as excinfo:
        PSSExporter().export(root, str(tmp_path / "o.pss"))
    message = str(excinfo.value)
    for expected in ("PSS-E001", "PSS-E002", "PSS-E004"):
        assert expected in message
    assert len(excinfo.value.findings) == 3


def test_output_uses_unix_newlines(tmp_path):
    """Generated source is committed; a platform-dependent line ending would make
    every checkout on the other platform look modified."""
    root = compile_rdl("scalar_regs")
    out = str(tmp_path / "o.pss")
    PSSExporter().export(root, out)
    with open(out, "rb") as f:
        data = f.read()
    assert b"\r\n" not in data


def test_user_template_dir_overrides_a_base_template(tmp_path):
    """The documented extension point: override one template, inherit the rest."""
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "reg_component.pss").write_text(
        '{% import "base:utils.pss" as u %}\n'
        "    // OVERRIDDEN\n"
        '    {{ "pure " if pure else "" }}component {{ rt.component_name }}'
        " : reg_c<{{ rt.struct_name }}, {{ rt.access }}, {{ rt.regwidth }}> {}\n"
    )

    root = compile_rdl("scalar_regs")
    out = str(tmp_path / "o.pss")
    PSSExporter(user_template_dir=str(tdir)).export(root, out)
    text = open(out).read()
    assert "// OVERRIDDEN" in text
    # The templates we did *not* override must still come from the package.
    assert "packed_s<LITTLE_ENDIAN>" in text


@pytest.mark.pssparser
def test_user_template_output_still_parses(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "reg_component.pss").write_text(
        "    // custom banner\n"
        '    {{ "pure " if pure else "" }}component {{ rt.component_name }}'
        " : reg_c<{{ rt.struct_name }}, {{ rt.access }}, {{ rt.regwidth }}> {}\n"
    )
    root = compile_rdl("basic")
    out = str(tmp_path / "o.pss")
    PSSExporter(user_template_dir=str(tdir)).export(root, out)
    assert_parses(out)


def test_user_template_context_is_available(tmp_path):
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "reg_component.pss").write_text(
        "    // built by {{ owner }}\n"
        "    pure component {{ rt.component_name }}"
        " : reg_c<{{ rt.struct_name }}, {{ rt.access }}, {{ rt.regwidth }}> {}\n"
    )
    root = compile_rdl("scalar_regs")
    out = str(tmp_path / "o.pss")
    PSSExporter(
        user_template_dir=str(tdir), user_template_context={"owner": "the team"}
    ).export(root, out)
    assert "// built by the team" in open(out).read()


def test_parser_gated_modes_refuse_clearly(tmp_path):
    """Better an explicit NotImplementedError naming the parser requirement than
    output that no available tool can consume."""
    root = compile_rdl("encode")
    for kwargs in ({"emit_enums": "typed"}, {"offset_mode": "path"}):
        with pytest.raises(NotImplementedError) as excinfo:
            PSSExporter().export(root, str(tmp_path / "o.pss"), **kwargs)
        assert "pssparser" in str(excinfo.value)


def test_invalid_option_values_are_rejected(tmp_path):
    root = compile_rdl("scalar_regs")
    with pytest.raises(ValueError):
        PSSExporter().export(root, str(tmp_path / "o.pss"), type_style="nonsense")


def test_sidecar_records_dropped_properties(tmp_path):
    """The sidecar exists so nothing is lost without a trace; check it actually
    carries what the PSS output cannot."""
    root = compile_rdl("access_matrix")
    out = str(tmp_path / "o.pss")
    side = str(tmp_path / "o.json")
    PSSExporter().export(root, out, sidecar_path=side)
    payload = json.load(open(side))

    dropped = {
        note
        for reg in payload["registers"]
        for field in reg["fields"]
        for note in field["dropped"]
    }
    assert any("onread" in d for d in dropped)
    assert any("onwrite" in d for d in dropped)
    assert "singlepulse" in dropped

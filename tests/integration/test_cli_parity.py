"""Keep the CLI and the Python API from drifting apart.

Exporter plugins drift the same way every time: a flag is added to argparse and
the ``export()`` keyword is forgotten, or vice versa, and the two surfaces
silently diverge until a user reports that ``--foo`` does nothing.  Introspecting
both and asserting the mapping is *total in both directions* costs almost
nothing and catches all of it.
"""

import argparse
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peakrdl_pss.__peakrdl__ import Exporter  # noqa: E402
from peakrdl_pss.exporter import PSSExporter  # noqa: E402
from peakrdl_pss.options import ExportOptions  # noqa: E402

#: dests owned by PeakRDL itself, or deliberately renamed on the way through.
_CLI_ONLY = {
    "output",   # PeakRDL supplies -o; export() takes it positionally as `path`
    "no_pure",  # inverted into pure_components
}
_API_ONLY = {
    "pure_components",  # the positive form of --no-pure
}


def _cli_dests():
    parser = argparse.ArgumentParser()
    group = parser.add_argument_group("exporter")
    Exporter().add_exporter_arguments(group)
    return {
        action.dest for action in parser._actions
        if action.dest not in ("help",)
    }


def _export_kwargs():
    sig = inspect.signature(PSSExporter.export)
    return {
        name for name, param in sig.parameters.items()
        if param.kind == inspect.Parameter.KEYWORD_ONLY
    }


def test_every_cli_flag_reaches_the_api():
    missing = _cli_dests() - _export_kwargs() - _CLI_ONLY
    assert not missing, (
        "CLI options with no matching export() keyword: %s" % sorted(missing)
    )


def test_every_api_option_is_reachable_from_the_cli():
    missing = _export_kwargs() - _cli_dests() - _API_ONLY
    assert not missing, (
        "export() keywords with no CLI flag: %s" % sorted(missing)
    )


def test_export_options_matches_the_api():
    """The options dataclass is what everything downstream reads; if it drifts
    from export(), a flag can be accepted and then quietly ignored."""
    fields = set(ExportOptions.__dataclass_fields__)
    kwargs = _export_kwargs()
    assert fields == kwargs, (
        "ExportOptions and export() disagree: only in options=%s, only in export=%s"
        % (sorted(fields - kwargs), sorted(kwargs - fields))
    )


def test_defaults_agree_between_cli_and_api():
    """A default that differs between the two surfaces is the subtlest drift of
    all: both work, and they disagree."""
    parser = argparse.ArgumentParser()
    group = parser.add_argument_group("exporter")
    Exporter().add_exporter_arguments(group)
    cli_defaults = {
        a.dest: a.default for a in parser._actions if a.dest not in ("help",)
    }

    sig = inspect.signature(PSSExporter.export)
    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            continue
        if name in _API_ONLY:
            continue
        assert name in cli_defaults, name
        assert cli_defaults[name] == param.default, (
            "%s defaults to %r on the CLI but %r in export()"
            % (name, cli_defaults[name], param.default)
        )


def test_no_pure_inverts_correctly():
    assert PSSExporter.export.__kwdefaults__["pure_components"] is True
    parser = argparse.ArgumentParser()
    group = parser.add_argument_group("exporter")
    Exporter().add_exporter_arguments(group)
    args = parser.parse_args(["--no-pure"])
    assert args.no_pure is True
    assert (not args.no_pure) is False


def test_unknown_kwarg_is_rejected(tmp_path):
    """Silently ignoring an unrecognized keyword is how a typo becomes a
    long-lived misconfiguration."""
    import pytest
    from util import compile_rdl

    root = compile_rdl("scalar_regs")
    with pytest.raises(TypeError):
        PSSExporter().export(
            root, str(tmp_path / "o.pss"), not_a_real_option=True
        )

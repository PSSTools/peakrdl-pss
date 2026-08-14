"""The exporter: compile -> scan -> validate -> render.

The four stages are deliberately separate.  ``scan`` is the only stage that
touches the SystemRDL model, ``validate`` sees only the IR, and ``render`` sees
only the IR plus options -- so a bug in offset arithmetic is reachable by a unit
test that never constructs a Jinja environment.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import jinja2 as jj
from systemrdl.node import AddrmapNode, Node, RootNode

from . import addressing
from .prose import desc_inline, desc_lines
from .__about__ import __version__
from .design import DesignScanner
from .diagnostics import Finding, PSSExportError, Severity
from .ir import ChildRef, Design, GroupType
from .options import ExportOptions
from .validate import Validator

__all__ = ["PSSExporter", "PSSExportError"]


class PSSExporter:
    def __init__(
        self,
        *,
        user_template_dir: Optional[str] = None,
        user_template_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        package = __name__.rsplit(".", 1)[0]
        base_loader = jj.PackageLoader(package, "templates")
        prefixes: Dict[str, jj.BaseLoader] = {
            "base": jj.PackageLoader(package, "templates")
        }

        # Unprefixed lookups resolve user-first, then base, so overriding one
        # template does not hide the rest.  The prefixed forms stay unambiguous:
        # "base:reg_group.pss" always means ours, which is what an overriding
        # template needs in order to {% extends %} or {% import %} the original.
        loaders: List[jj.BaseLoader] = []
        if user_template_dir:
            loaders.append(jj.FileSystemLoader(user_template_dir))
            prefixes["user"] = jj.FileSystemLoader(user_template_dir)
        loaders.append(base_loader)
        loaders.append(jj.PrefixLoader(prefixes, delimiter=":"))
        loader = jj.ChoiceLoader(loaders)

        self.user_template_context = user_template_context or {}
        self.jj_env = jj.Environment(
            loader=loader,
            undefined=jj.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        # Reflowing a `desc` is presentation, so it lives here rather than in
        # the IR: the IR carries the property's text as the model states it.
        self.jj_env.filters["desc_lines"] = desc_lines
        self.jj_env.filters["desc_inline"] = desc_inline

    # -- public API -------------------------------------------------------

    def export(
        self,
        node: Node,
        path: str,
        *,
        package_name: Optional[str] = None,
        type_style: str = "lexical",
        emit_top: bool = False,
        base_address: int = 0,
        emit_enums: str = "const",
        emit_reset_consts: bool = False,
        emit_index_helpers: bool = False,
        pad_tail: bool = False,
        rsvd_prefix: str = "rsvd_",
        pure_components: bool = True,
        offset_mode: str = "instance",
        sidecar_path: Optional[str] = None,
        strict: bool = False,
    ) -> None:
        """Export *node* as a PSS register package written to *path*.

        Raises :class:`PSSExportError` if the design contains a construct that
        cannot be represented.  Nothing is written in that case -- a partial file
        left behind after a failed export is worse than no file, because a later
        build step would consume it.
        """
        if isinstance(node, RootNode):
            node = node.top
        if not isinstance(node, AddrmapNode):
            raise TypeError("export() requires an AddrmapNode or RootNode, got %r" % type(node))

        if package_name is None:
            package_name = _default_package_name(path)

        options = ExportOptions(
            package_name=package_name,
            type_style=type_style,
            emit_top=emit_top,
            base_address=base_address,
            emit_enums=emit_enums,
            emit_reset_consts=emit_reset_consts,
            emit_index_helpers=emit_index_helpers,
            pad_tail=pad_tail,
            rsvd_prefix=rsvd_prefix,
            pure_components=pure_components,
            offset_mode=offset_mode,
            sidecar_path=sidecar_path,
            strict=strict,
        )
        options.validate()

        design = self.build(node, options)
        self.report(design, node, options)

        text = self.render_package(design, options)
        _write(path, text)

        if options.emit_top:
            top_text = self.render_top(design, options)
            _write(top_path(path), top_text)

        if options.sidecar_path:
            _write(options.sidecar_path, self.render_sidecar(design))

    # -- stages (public so tests can drive them individually) -------------

    def build(self, top: AddrmapNode, options: ExportOptions) -> Design:
        design = DesignScanner(options).scan(top)
        Validator(options).run(design)
        return design

    def report(self, design: Design, node: Node, options: ExportOptions) -> None:
        """Route findings to the compiler's message handler and abort on errors.

        The whole scan has already run, so a design with three problems reports
        all three in one invocation rather than one per run.
        """
        msg = getattr(getattr(node, "env", None), "msg", None)
        errors: List[Finding] = []
        for finding in design.findings:
            severity = finding.effective_severity(options.strict)
            line = finding.render()
            if severity == Severity.ERROR:
                errors.append(finding)
                if msg is not None:
                    msg.error(line, finding.src_ref)
            elif severity == Severity.WARNING:
                if msg is not None:
                    msg.warning(line, finding.src_ref)
            else:
                if msg is not None:
                    # MessageHandler.info() takes no src_ref, unlike error/warning.
                    msg.info(line)
        if errors:
            raise PSSExportError(errors)

    def render_package(self, design: Design, options: ExportOptions) -> str:
        return self._render("top_pkg.pss", design, options)

    def render_top(self, design: Design, options: ExportOptions) -> str:
        return self._render("top_wrapper.pss", design, options)

    def render_sidecar(self, design: Design) -> str:
        """A machine-readable record of everything the PSS output cannot carry.

        Versioned from day one: consumers that read it need to survive schema
        growth, and a schema with no version is a schema that can never change.
        """
        payload = {
            "version": 1,
            "generator": "peakrdl-pss %s" % __version__,
            "package": design.package_name,
            "top": design.top_type_name,
            "registers": [
                {
                    "type": rt.type_name,
                    "instances": rt.instances,
                    "regwidth": rt.regwidth,
                    "accesswidth": rt.accesswidth,
                    "access": rt.access,
                    "reset": rt.reset_value,
                    "signature": rt.signature,
                    "fields": [
                        {
                            "name": f.name,
                            "rdl_name": f.rdl_name,
                            "lsb": f.lsb,
                            "msb": f.msb,
                            "reserved": f.reserved,
                            "sw": f.sw,
                            "hw": f.hw,
                            "reset": f.reset,
                            "reset_is_ref": f.reset_is_ref,
                            "encode": f.enum_type,
                            "dropped": list(f.lossy_notes),
                        }
                        for f in rt.fields
                    ],
                }
                for rt in design.reg_types
            ],
            "renamed": design.mangle_map,
            "findings": [
                {
                    "id": f.id,
                    "severity": f.severity.name,
                    "path": f.path,
                    "message": f.message,
                }
                for f in design.findings
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"

    # -- internals --------------------------------------------------------

    def _render(self, template: str, design: Design, options: ExportOptions) -> str:
        context: Dict[str, Any] = {
            "d": design,
            "opt": options,
            "version": __version__,
            "pure": options.pure_components,
            "index_helpers": _index_helpers_for(options),
        }
        context.update(self.user_template_context)
        return self.jj_env.get_template(template).render(**context)


def _index_helpers_for(options: ExportOptions) -> Any:
    """Return the callable the group template uses to get its index helpers.

    A callable rather than precomputed data because ``reg_group.pss`` is included
    once per group and needs the helpers for *that* group.
    """

    def helpers(gt: GroupType) -> List[Tuple[ChildRef, str, str]]:
        if not options.emit_index_helpers:
            return []
        out = []
        for child in gt.children:
            sig = addressing.index_helper_signature(child)
            body = addressing.index_helper_body(child)
            if sig is not None and body is not None:
                out.append((child, sig, body))
        return out

    return helpers


def _default_package_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    from .identifiers import mangle

    name, _ = mangle(stem or "regs", set())
    return name


def top_path(path: str) -> str:
    stem, ext = os.path.splitext(path)
    return stem + "_top" + (ext or ".pss")


def _write(path: str, text: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    # newline="\n" so output is byte-identical across platforms; the golden tests
    # compare bytes.
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

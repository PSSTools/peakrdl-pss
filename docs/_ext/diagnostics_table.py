"""Generate the diagnostics reference from the code that raises the diagnostics.

A hand-maintained table of diagnostic IDs goes stale the first time someone adds
a check in a hurry, and a stale diagnostics page is worse than none: users search
for the ID they were given and conclude the tool is undocumented.  Generating the
page from ``peakrdl_pss.diagnostics.ALL_SPECS`` makes that impossible, and
``tests/unit/test_docs.py`` asserts every ID is reachable from the docs source.

Usage in a page::

    .. pss-diagnostics:: error
"""

from docutils.parsers.rst import Directive, directives

from peakrdl_pss.diagnostics import ALL_SPECS, Severity

_SEVERITY = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.INFO,
}

_INTRO = {
    Severity.ERROR: (
        "These abort the export. They are not configurable: each one describes a "
        "construct that would produce output which parses cleanly and is wrong, "
        "so emitting it with a warning would ship silent wrongness."
    ),
    Severity.WARNING: (
        "The export succeeds, but something the SystemRDL description says could "
        "not be carried into PSS. Pass ``--strict`` to turn these into errors."
    ),
    Severity.INFO: (
        "Informational only, and never promoted by ``--strict``. These record a "
        "decision the exporter made that you may want to know about."
    ),
}


class DiagnosticsDirective(Directive):
    has_content = False
    required_arguments = 1
    option_spec = {"no-intro": directives.flag}

    def run(self):
        severity = _SEVERITY[self.arguments[0].strip().lower()]
        specs = [s for s in ALL_SPECS if s.severity == severity]

        lines = []
        if "no-intro" not in self.options:
            lines += [_INTRO[severity], ""]

        for spec in specs:
            title = "``%s`` -- %s" % (spec.id, spec.title)
            lines += [
                ".. _%s:" % spec.id.lower(),
                "",
                title,
                "^" * len(title),
                "",
                spec.detail,
                "",
            ]

        # Insert the generated RST back into the document's input stream rather
        # than parsing it into a detached node.  Sections and `.. _label:`
        # targets only register correctly when they are seen at the document
        # level -- a nested parse produces sections the builder treats as
        # misplaced and labels that :ref: cannot resolve.
        self.state_machine.insert_input(lines, "<pss-diagnostics>")
        return []


def setup(app):
    app.add_directive("pss-diagnostics", DiagnosticsDirective)
    return {"version": "1.0", "parallel_read_safe": True}

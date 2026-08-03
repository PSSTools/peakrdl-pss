"""Parse the generated package *together with* code that uses it.

Deliberately separate from ``test_parse_package.py``.  That suite covers our
artifact and is a hard gate.  This one exercises stdlib surface we do not emit --
``write_field``, ``read``, struct literals, handle plumbing -- so a gap in
someone else's stdlib shows up here rather than masquerading as a defect in our
output.

A failure here means "a consumer cannot yet use what we emit", which is real
information but not a reason to block our release; failures are xfail'd with a
comment naming the parser requirement that will fix them.  When a tier lands
upstream, the xfail flips to a pass and can be tightened to ``strict=True``.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import compile_rdl, export_file, run_pssparser  # noqa: E402

# Each snippet is a package that imports the generated one and uses it the way a
# test writer would.  {pkg} is substituted with the generated package name.
CONSUMER_SNIPPETS = {
    "handle_binding": """
package consumer_handle {{
    import addr_reg_pkg::*;
    import std_pkg::*;
    import {pkg}::*;

    component env_c {{
        {top}_c                    regs;
        transparent_addr_space_c<> mem;

        exec init_up {{
            transparent_addr_region_s<> region;
            addr_handle_t h;
            region.size = 0x10000;
            region.addr = 0x0;
            h = mem.add_nonallocatable_region(region);
            regs.set_handle(h);
        }}
    }}
}}
""",
    "read_write_struct": """
package consumer_rw {{
    import addr_reg_pkg::*;
    import std_pkg::*;
    import {pkg}::*;

    component env_c {{
        {top}_c regs;

        exec body {{
            {reg_struct} value;
            value = regs.{path}.read();
            regs.{path}.write(value);
        }}
    }}
}}
""",
    "sized_access": """
package consumer_sized {{
    import addr_reg_pkg::*;
    import std_pkg::*;
    import {pkg}::*;

    component env_c {{
        {top}_c regs;

        exec body {{
            bit[32] raw;
            raw = regs.{path}.read_val();
            regs.{path}.write_val(raw);
            regs.{path}.write_val_masked(0xffff, 0x1234);
        }}
    }}
}}
""",
    "write_field": """
package consumer_field {{
    import addr_reg_pkg::*;
    import std_pkg::*;
    import {pkg}::*;

    component env_c {{
        {top}_c regs;

        exec body {{
            regs.{path}.write_field("{field}", 5);
        }}
    }}
}}
""",
}


def _fixture(tmp_path):
    """Generate a package and report the names a consumer needs to name things."""
    root = compile_rdl("scalar_regs")
    pkg = export_file(root, tmp_path, "regs.pss", package_name="regs")

    from peakrdl_pss.design import DesignScanner
    from peakrdl_pss.options import ExportOptions

    design = DesignScanner(ExportOptions(package_name="regs")).scan(root.top)
    rt = design.reg_types[0]
    child = design.group_types[-1].children[0]
    return {
        "path": pkg,
        "subs": {
            "pkg": "regs",
            "top": design.top_type_name,
            "reg_struct": rt.struct_name,
            "path": child.inst_name,
            "field": rt.fields[0].name,
        },
    }


@pytest.mark.pssparser
@pytest.mark.parametrize("label", sorted(CONSUMER_SNIPPETS))
def test_consumer_snippet_parses(label, tmp_path):
    fixture = _fixture(tmp_path)
    snippet = CONSUMER_SNIPPETS[label].format(**fixture["subs"])

    consumer = str(tmp_path / ("consumer_%s.pss" % label))
    with open(consumer, "w") as f:
        f.write(snippet)

    result = run_pssparser(fixture["path"], consumer)
    if not result.ok:
        pytest.xfail(
            "consumer pattern %r is not accepted by the installed pssparser.\n"
            "This is stdlib surface we do not emit; see the parser requirements "
            "document. Output:\n%s" % (label, result.raw)
        )
    assert result.ok

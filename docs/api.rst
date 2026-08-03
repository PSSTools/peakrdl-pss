Python API
==========

The exporter is usable without PeakRDL installed.

.. code-block:: python

    from systemrdl import RDLCompiler
    from peakrdl_pss import PSSExporter

    rdlc = RDLCompiler()
    rdlc.compile_file("my_design.rdl")
    root = rdlc.elaborate()

    PSSExporter().export(root, "my_regs.pss", emit_reset_consts=True)

.. autoclass:: peakrdl_pss.PSSExporter
    :members: export, build, render_package, render_top, render_sidecar

.. autoexception:: peakrdl_pss.PSSExportError

Stages
------

``export()`` is a thin sequence over four stages, each of which can be driven
independently:

.. code-block:: python

    from peakrdl_pss.exporter import PSSExporter
    from peakrdl_pss.options import ExportOptions

    options = ExportOptions(package_name="regs")
    exporter = PSSExporter()

    design = exporter.build(root.top, options)   # compile -> scan -> validate
    text   = exporter.render_package(design, options)

``build()`` returns the intermediate representation: plain dataclasses describing
exactly what will be emitted. Working against it is the supported way to build
tooling on top of the exporter -- offsets, layouts, and diagnostics are all
inspectable without rendering anything.

.. code-block:: python

    for rt in design.reg_types:
        print(rt.type_name, rt.access, rt.reset_value)
        for row in rt.fields:
            print("   ", row.name, row.lsb, row.msb, row.lossy_notes)

    for finding in design.findings:
        print(finding.id, finding.message, finding.path)

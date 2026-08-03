Introduction
============

``peakrdl-pss`` is a `PeakRDL <https://peakrdl.readthedocs.io>`_ exporter plugin
that converts a SystemRDL register description into a **PSS register package** --
a ``.pss`` source file containing:

* a ``packed_s<>`` struct describing each register type's fields,
* a ``pure component ... : reg_c<>`` per register type,
* a ``pure component ... : reg_group_c`` per ``addrmap`` / ``regfile``, with the
  offset functions a PSS tool uses to resolve addresses,
* optionally, a wrapper that binds the model to a concrete address region.

The output is a *register model only*. Generating test intent -- actions,
activities, flows -- is out of scope: this gives you the register layer that such
intent is written against.

.. code-block:: bash

    peakrdl pss my_design.rdl -o my_regs.pss

What it will not do quietly
---------------------------

Some SystemRDL constructs have no PSS representation. Where a faithful export is
impossible, ``peakrdl-pss`` **fails rather than emitting something plausible** --
see :doc:`unsupported`. Where the mapping is possible but lossy, it emits the
mapping and tells you what it dropped -- see :doc:`mapping/limitations` and
:doc:`diagnostics`.

That distinction is the main design commitment of this tool. A 128-bit register
emitted as a ``reg_c`` parses cleanly, links cleanly, and is wrong; a warning
buried in a build log is not enough protection against that.

.. toctree::
    :hidden:

    self
    installation
    quickstart
    cli
    using-the-output

.. toctree::
    :hidden:
    :caption: The mapping

    mapping/index
    mapping/groups
    mapping/registers
    mapping/fields
    mapping/arrays
    mapping/naming
    mapping/limitations

.. toctree::
    :hidden:
    :caption: Reference

    diagnostics
    unsupported
    compatibility
    api
    templates

.. toctree::
    :hidden:
    :caption: Project

    contributing
    changelog

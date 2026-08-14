Installation
============

.. code-block:: bash

    python3 -m pip install peakrdl-pss

This installs the ``pss`` subcommand into PeakRDL. Confirm it is discovered:

.. code-block:: bash

    peakrdl pss --help

Requirements
------------

* Python 3.9 or newer
* ``systemrdl-compiler`` 1.27 or newer
* ``jinja2`` 3.0 or newer

``peakrdl`` itself is **not** a runtime dependency. The exporter is usable
directly from Python without the CLI installed -- see :doc:`api`. If you want
the CLI pulled in as well:

.. code-block:: bash

    python3 -m pip install "peakrdl-pss[cli]"

Consuming the output
--------------------

The generated package imports ``addr_reg_pkg`` and ``std_pkg`` from the PSS
core library, so any PSS 3.1 tool can consume it. See :doc:`compatibility` for
what is verified in CI.

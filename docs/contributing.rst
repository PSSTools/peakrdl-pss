Contributing
============

Development setup
-----------------

This repository uses `IVPM <https://github.com/fvutils/ivpm>`_ to manage its
dependencies, including the sibling projects the test suite cross-checks against.

.. code-block:: bash

    ivpm update
    source .envrc          # or use direnv

That gives you a Python environment with ``systemrdl-compiler``, ``peakrdl``,
``peakrdl-uvm``, ``pssparser``, ``pytest``, and ``sphinx``.

Install the exporter itself in editable mode:

.. code-block:: bash

    python -m pip install -e . --no-deps

Running the tests
-----------------

.. code-block:: bash

    pytest                      # everything
    pytest -m "not slow"        # skip the 4096-register benchmark
    pytest tests/unit           # fast, no I/O
    pytest tests/property       # the oracles

Tests that need an external tool **skip** rather than fail when it is missing, so
the suite is usable outside this workspace. CI pins those tools so the skips
cannot hide a regression.

.. list-table::
    :header-rows: 1

    * - Marker
      - Requires
    * - ``pssparser``
      - the ``pssparser`` CLI
    * - ``uvm``
      - ``peakrdl-uvm``
    * - ``slow``
      - nothing; just long-running

How the suite is organized
--------------------------

``tests/unit``
    Pure functions: identifiers, access derivation, layout, addressing,
    diagnostics. No Jinja, no filesystem.

``tests/property``
    The oracles. Two are worth knowing about:

    The **offset oracle** interprets the offsets each generated package declares,
    walks them down every instance path, and compares the result against
    ``node.absolute_address``. Array and stride bugs are the most likely source
    of silent wrongness, and this is what catches them.

    The **signature-fidelity** suite mutates real descriptions one property at a
    time and asserts the structural signature moves exactly when the rendered
    text moves. It uses the output as the oracle, so it cannot drift from what
    the templates actually emit.

``tests/golden``
    Byte-for-byte expectations, plus the ``pssparser`` gate.

``tests/integration``
    The CLI, plugin discovery, and the Python API.

Updating goldens
----------------

.. code-block:: bash

    PEAKRDL_PSS_UPDATE_GOLDEN=1 pytest tests/golden

This is the **only** supported way to update an expectation. Editing a golden by
hand to match new behavior turns a regression test into a transcript of whatever
the code happens to do -- review the regenerated diff like any other change.

Goldens record the generator version stamp as the literal ``<version>``, and the
comparison substitutes it in. A release therefore does not touch a single
expectation. The stamp is covered directly by ``tests/unit/test_header.py``.

Adding a diagnostic
-------------------

Add a ``DiagSpec`` to ``peakrdl_pss/diagnostics.py`` and list it in
``ALL_SPECS``. The documentation page is generated from that tuple, so the
diagnostic is documented automatically -- and a test asserts the reverse, that
every ID in the code appears in the docs.

Give it a corpus case in ``tests/golden/rdl``. Files named ``err_*.rdl`` are
expected to fail: their assertion is nonzero exit, the expected IDs, and no
output file left behind.

Adding an option
----------------

Add it in three places, all of which are checked against each other by
``tests/integration/test_cli_parity.py``:

#. a field on ``ExportOptions``,
#. a keyword parameter of ``PSSExporter.export`` with the same name and default,
#. an ``add_argument`` in ``__peakrdl__.py``.

The parity test asserts the mapping is total in both directions, including
defaults, so the CLI and the Python API cannot drift apart.

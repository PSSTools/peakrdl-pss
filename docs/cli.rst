Command-line reference
======================

.. code-block:: bash

    peakrdl pss <input.rdl> -o <output.pss> [options]

Every option below maps to exactly one keyword argument of
:class:`~peakrdl_pss.PSSExporter.export` with the same name, and a test asserts
that mapping stays total in both directions -- so anything you can do from the
CLI you can do from Python, and vice versa.

Output and naming
-----------------

``-o, --output PATH``
    The generated ``.pss`` file. Required.

``--package-name NAME``
    PSS package name. Defaults to the output file's stem, sanitized into a legal
    PSS identifier.

``--type-style {lexical,hier}``
    How emitted type names are derived. Default ``lexical``.

    ``lexical`` names types after their SystemRDL *type*, so one type is emitted
    however many times it is instantiated. ``hier`` names them after the
    instance path, which produces one type per instance -- more verbose, but
    easier to trace back to the description. See :doc:`mapping/naming`.

Emission
--------

``--emit-top``
    Also write ``<output>_top.pss``, a wrapper component that binds the top group
    to an address region via ``set_handle()``.

``--base-address ADDR``
    Base address used by the ``--emit-top`` wrapper. Accepts ``0x`` notation.
    Default ``0``.

``--emit-enums {const,typed,off}``
    How SystemRDL ``encode`` enumerations are emitted. Default ``const``, which
    emits ``static const`` values. ``typed`` emits real PSS enums and requires a
    ``pssparser`` release with typed enum base types (see :doc:`compatibility`).
    ``off`` omits them.

``--emit-reset-consts``
    Emit a ``static const`` reset value beside each register instance inside its
    group. Off by default: it is useful for reset checks but inflates large
    memory maps. See :ref:`reset-constants`.

``--emit-index-helpers``
    Emit an index-flattening helper function for each multi-dimensional array, so
    model code does not open-code the arithmetic. See :doc:`mapping/arrays`.

``--pad-tail``
    Pad each register struct with a reserved field up to ``regwidth``. Off by
    default -- ``SZ`` is emitted explicitly, so PSS's own reserved-tail rule
    already covers the remainder, and padding adds members describing bits nobody
    can access.

``--rsvd-prefix PREFIX``
    Name prefix for generated reserved fields. Default ``rsvd_``.

``--no-pure``
    Emit components without the ``pure`` qualifier.

``--offset-mode {instance,path}``
    Which ``get_offset_of_*`` functions to implement. Default ``instance``.
    Implementing all three is an error in PSS, so this is a choice, not a
    combination. ``path`` requires parser support for ``node_s``.

``--sidecar PATH``
    Write a JSON record of everything the PSS output cannot represent -- dropped
    side-effect properties, renamed identifiers, every diagnostic. See
    :ref:`sidecar`.

Diagnostics
-----------

``--strict``
    Treat warnings as errors. Has no effect on the errors in :doc:`unsupported`
    (they always fail) or on informational messages (they never fail). See
    :doc:`diagnostics`.

Configuration file
------------------

Two settings are read from PeakRDL's configuration file:

.. code-block:: toml

    [pss]
    user_template_dir = "path/to/templates"
    user_template_context.owner = "my team"

See :doc:`templates`.

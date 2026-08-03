Compatibility
=============

Language level
--------------

The output targets **PSS 3.1**. There is no version selector: the constructs the
exporter depends on -- ``reg_c``, ``reg_group_c``, ``packed_s``, the
``get_offset_of_*`` functions -- are what make a register package expressible at
all.

Every generated file imports ``addr_reg_pkg`` and ``std_pkg`` from the PSS core
library and uses nothing outside it.

What CI verifies
----------------

Every generated package, across the whole test corpus and every option
combination that changes the output's shape, is parsed and linked by
``pssparser`` as a hard gate. Nothing ships that a parser rejects.

That gate covers **100% of the default output**. There is no emitted construct
that CI cannot check -- including the ``--emit-reset-consts`` constants and the
``--emit-top`` wrapper. It is what this project guarantees: the *package* is
always accepted, whatever the state of the consumer-side surface below.

A second, separate suite parses the generated package *together with* consumer
code exercising ``read``/``write``, ``read_val``/``write_val``,
``write_val_masked``, ``write_field``, and handle binding. Keeping the two apart
matters: the first covers our artifact and must always pass, while the second
exercises core-library surface we do not emit, so a gap there is information
rather than a defect in the output.

Two of those consumer patterns -- the ``reg_sized_c`` untyped accessors
(``read_val``/``write_val``/``write_val_masked``) and ``write_field`` -- are
currently ``xfail`` against a released parser. Both depend on ``reg_sized_c``,
which is not yet in a published ``pssparser`` core library. Typed access
(``read()``/``write()`` through the register's own struct) and handle binding
work today, and are the forms :doc:`using-the-output` leads with.

Optional modes awaiting tool support
------------------------------------

Two modes are gated on parser capability rather than on the language:

.. list-table::
    :header-rows: 1
    :widths: 25 40 35

    * - Mode
      - Needs
      - Default instead
    * - ``--emit-enums=typed``
      - enum declarations with an explicit base type, so an enum can be a
        ``packed_s`` member
      - ``--emit-enums=const``, which emits ``static const`` values
    * - ``--offset-mode=path``
      - ``node_s`` and ``get_offset_of_path``
      - ``--offset-mode=instance``

Both refuse with a clear message naming the requirement rather than emitting
something no available tool can consume. Neither default loses information --
they are different spellings of the same content -- so there is no reason to wait
for either.

Registers
=========

Each register type becomes two declarations: a ``packed_s`` struct describing its
value, and a ``reg_c`` component binding that struct to an access policy and size.

.. code-block:: text

    struct my__ctrl_s : packed_s<LITTLE_ENDIAN> {
        bit[16] f1;       // [15:0] sw=rw hw=r reset=0x4d2
        bit     f2;       // [16] sw=rw hw=r reset=0x0
        bit[15] rsvd_17;  // [31:17] reserved
    }
    pure component my__ctrl_c : reg_c<my__ctrl_s, READWRITE, 32> {}

``SZ`` is always explicit
-------------------------

The third parameter is emitted as the declared ``regwidth``, never left to
default. The default would be derived from ``sizeof_s`` of the struct, which is
*byte-rounded*: a register whose fields occupy 17 bits would get a 24-bit access
size. Emitting ``SZ`` explicitly decouples the access size from the struct's
rounding, and keeps ``read8``/``read16``/``read32``/``read64`` selection matching
the hardware.

Access policy derivation
------------------------

PSS has three access values. SystemRDL has considerably more, plus orthogonal
side-effect properties. The register's ``ACC`` is derived from the union of its
fields' ``sw`` policies:

.. list-table::
    :header-rows: 1

    * - Fields are...
      - ``ACC``
    * - all readable, none writable
      - ``READONLY``
    * - all writable, none readable
      - ``WRITEONLY``
    * - both, or mixed
      - ``READWRITE``

``sw=na`` fields are excluded from the derivation rather than counted as
inaccessible: an ``na`` field beside a writable one must not drag the register
away from ``WRITEONLY``.

A register with no software-accessible field derives ``READONLY``. That is the
conservative direction -- generating writes to a register software cannot write
is the worse failure.

What derivation loses
---------------------

``sw=rw1`` and ``sw=w1`` mean "writable once". PSS cannot express that, so they
collapse to the nearest value and raise :ref:`pss-w102`.

Side-effect properties -- ``onread``, ``onwrite``, ``singlepulse``, ``swmod``,
``swacc``, counters, interrupts -- have **no PSS representation at all**. They
are preserved as a comment on the field, reported as :ref:`pss-w101`, and
recorded in the :ref:`sidecar`:

.. code-block:: text

    bit[8] a;  // [7:0] sw=rw hw=r dropped: onread=rclr

This matters more than it looks. A register that clears on read behaves
differently from one that does not, and a generated model that presents both
identically will produce test intent that is wrong in a way no parser can catch.
The comment and the sidecar exist so the information is recoverable.

Widths
------

``regwidth`` must be 8, 16, 32, or 64. Wider is :ref:`pss-e001`; narrower or
non-power-of-2 widths are rejected by ``systemrdl-compiler`` before the exporter
sees them.

``accesswidth`` must equal ``regwidth`` -- see :ref:`pss-e002`.

Type reuse
----------

Two registers share an emitted type only when they are *structurally identical*,
not merely when they share a SystemRDL type name. See :doc:`naming` for why that
distinction is load-bearing.

Fields
======

Each field becomes one member of the register's ``packed_s`` struct, in ascending
bit order.

Gaps are materialized
---------------------

``packed_s<LITTLE_ENDIAN>`` assigns bits to members **in declaration order**,
starting at bit 0. It has no way to skip. So every gap in the SystemRDL field
layout becomes an explicit reserved member:

.. code-block:: systemrdl

    reg {
        field {sw=rw; hw=r;} a[7:4];    // gap at [3:0]
        field {sw=rw; hw=r;} b[15:12];  // gap at [11:8]
    } r @ 0x0;

.. code-block:: text

    struct r_s : packed_s<LITTLE_ENDIAN> {
        bit[4] rsvd_0;   // [3:0] reserved
        bit[4] a;        // [7:4] sw=rw hw=r
        bit[4] rsvd_8;   // [11:8] reserved
        bit[4] b;        // [15:12] sw=rw hw=r
    }

Omitting a gap would place ``a`` at bit 0 and ``b`` at bit 4 -- output that
parses perfectly and puts every field in the wrong place. Reserved members are
named ``rsvd_<lsb>`` by default; ``--rsvd-prefix`` changes the prefix.

The trailing gap
----------------

Bits between the last field and ``regwidth`` are **not** padded by default. Since
``SZ`` is emitted explicitly, PSS's own "``SZ`` greater than ``sizeof_s<R>``"
reserved-tail rule already covers them, and padding would add a member claiming
to describe bits nobody can access. ``--pad-tail`` adds it if your consumer
prefers a struct whose size matches the register exactly.

Field names matter
------------------

``write_field("name", value)`` is keyed by the *string* name of the struct
member, so field names are part of the interface, not just documentation. When a
name has to be renamed (see :doc:`naming`), the comment records the original:

.. code-block:: text

    bit[4] component_;  // [3:0] sw=rw hw=r rdl_name=component

Encodings
---------

A field with ``encode`` produces named constants alongside the package
(``--emit-enums=const``, the default):

.. code-block:: text

    // encoding mode_e
    static const bit[2] mode_e__off = 0x0;
    static const bit[2] mode_e__slow = 0x1;
    static const bit[2] mode_e__fast = 0x2;

A real PSS ``enum`` would be the natural mapping, but a packed-struct member
needs an enum with an explicit base type, which is not yet accepted by every
tool. ``--emit-enums=typed`` emits that form once your parser supports it; see
:doc:`../compatibility`. ``--emit-enums=off`` omits encodings entirely.

msb0 ordering
-------------

In ``msb0`` mode a field's most significant bit sits at its *low* register bit
position -- which implies a bit swap **within** the field. ``packed_s`` cannot
express that.

The generated member occupies the correct bit span, so addresses and masks are
right; only the within-field bit order is lost, and the exporter raises
:ref:`pss-w105` to say so. Consumers of an msb0 register must swap the field
value themselves.

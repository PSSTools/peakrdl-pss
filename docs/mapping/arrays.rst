Arrays
======

PSS component arrays are one-dimensional. SystemRDL permits any rank. The
exporter flattens row-major.

One dimension
-------------

Nothing interesting happens: the array is emitted as-is, and the offset function
is affine in the index.

.. code-block:: text

    my__data_c data[8];

    ["data"]: return 0x100 + index*0x4;

The stride, not the element size, drives the expression, so sparse arrays
(``+= 0x20`` on a 4-byte register) fall out for free.

More than one dimension
-----------------------

``bar[4][3]`` becomes ``bar[12]``, with index ``i0*3 + i1``:

.. code-block:: text

    my__bar_c bar[12];   // bar[4][3] flattened row-major

    ["bar"]: return 0x1000 + index*0x100;

So ``bar[2][1]`` is ``bar[7]``, at ``0x1000 + 7*0x100``.

This works because SystemRDL's stride applies uniformly to the innermost element
and outer dimensions multiply through, which makes the flattened form a single
affine expression rather than a nested one. The correctness of this equivalence
is checked index-by-index in the test suite against an independent
implementation, because it is the least obvious thing the exporter does.

Index helpers
-------------

Open-coding ``i0*3 + i1`` at every call site is a reliable source of off-by-one
bugs, especially when a dimension changes. ``--emit-index-helpers`` generates the
arithmetic:

.. code-block:: text

    // bar[4][3] -> flat index
    pure static function int bar_index(int i0, int i1) {
        return i0*3 + i1;
    }

    // used as:
    regs.blk.bar[my__blk_c::bar_index(2, 1)].write(value);

No helper is emitted for one-dimensional arrays, where it would be the identity
function.

The ergonomics
--------------

Flattening is lossless but not free: ``bar[7]`` reads less clearly than
``bar[2][1]``. The helpers recover most of that. If your descriptions lean
heavily on multi-dimensional arrays, ``--emit-index-helpers`` is worth turning on
by default.

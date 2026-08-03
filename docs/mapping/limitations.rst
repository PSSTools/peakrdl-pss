Limitations
===========

Constructs that *can* be exported, at a cost. Each is emitted, reported as a
diagnostic, and recorded in the :ref:`sidecar` so nothing is lost without a
trace. For constructs that cannot be exported at all, see :doc:`../unsupported`.

Side-effect access semantics
----------------------------

SystemRDL's ``onread``, ``onwrite``, ``singlepulse``, ``swmod``, ``swacc``,
counter and interrupt properties describe what happens *as a result of* an
access. PSS's three ``reg_access`` values describe only what accesses are
permitted.

There is no mapping. The properties are emitted as a comment on the field,
reported as :ref:`pss-w101`, and listed in the sidecar. A model built on the
generated package will treat a read-to-clear register like an ordinary one.

Write-once policies
-------------------

``sw=rw1`` and ``sw=w1`` collapse to ``READWRITE`` and ``WRITEONLY``
respectively. :ref:`pss-w102`.

Reset values
------------

PSS has no notion of a register reset value. ``--emit-reset-consts`` synthesizes
one as a ``static const`` beside the instance (see :ref:`reset-constants`), but it
is a constant your code must choose to compare against -- nothing in PSS applies
it.

A reset driven by a signal or field reference has no constant value at all;
no constant is emitted and :ref:`pss-w103` is raised. **Absence is not zero**: a
register with no specified reset emits no constant rather than ``0``, because
inventing a zero would put a value nobody wrote into something consumers trust.

Alias registers
---------------

An ``alias`` register accesses the same storage through a second address. PSS has
no way to say that, so the alias is emitted as an independent register at its own
offset and :ref:`pss-i203` is raised. Reads and writes through it will behave
correctly against hardware; what is lost is the *knowledge* that the two are
connected.

Endianness
----------

The generated structs are ``LITTLE_ENDIAN`` throughout. A ``bigendian`` subtree
raises :ref:`pss-w104`.

Multi-dimensional array ergonomics
----------------------------------

Flattening is lossless but costs readability. See :doc:`arrays`.

msb0 bit order
--------------

The bit *span* is preserved; the within-field bit swap is not. See
:doc:`fields`.

.. _sidecar:

The sidecar file
----------------

``--sidecar PATH`` writes a JSON record of everything above:

.. code-block:: json

    {
      "version": 1,
      "package": "my_block",
      "registers": [
        {
          "type": "my_block__ctrl_c",
          "instances": ["my_block.ctrl"],
          "access": "READWRITE",
          "fields": [
            {
              "name": "a", "rdl_name": "a", "lsb": 0, "msb": 7,
              "sw": "rw", "reset": 0,
              "dropped": ["onread=rclr"]
            }
          ]
        }
      ],
      "renamed": {"my_block.state": "state_"},
      "findings": [{"id": "PSS-W101", "severity": "WARNING", "...": "..."}]
    }

The schema is versioned from the first release. It is the intended way to build
tooling that needs the semantics PSS cannot carry -- a checker that knows which
registers clear on read, for instance.

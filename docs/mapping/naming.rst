Naming and type reuse
=====================

Type names
----------

``--type-style=lexical`` (the default) names each emitted type after its
SystemRDL *type*, joined with ``__``:

.. code-block:: text

    basic__foo__reg_t_s    // the struct
    basic__foo__reg_t_c    // the reg_c component
    basic__foo_c           // the reg_group_c component

One type is emitted however many times it is instantiated. ``--type-style=hier``
names types after the instance *path* instead, producing one type per instance:
more verbose, and more output, but every type traces to exactly one place in the
description.

Suffixes are consistent: ``_s`` for a register value struct, ``_c`` for a
component.

Reuse keys on structure, not on the name
----------------------------------------

This is the part worth understanding, because getting it wrong is silent.

SystemRDL lets you modify an instance after instantiating it:

.. code-block:: systemrdl

    reg_t r1;
    reg_t r2;
    reg_t r3;
    r3.f1->sw    = w;      // r3 is no longer the same register as r1
    r3.f1->reset = 200;

All three report the type name ``reg_t``. An exporter that caches emitted types
by name emits **one** definition and gives ``r3`` ``r1``'s access policy -- in
output that parses cleanly, links cleanly, and is wrong.

``peakrdl-pss`` therefore keys type reuse on a *structural signature*: a digest of
everything that reaches the emitted text -- field names, widths, bit positions,
derived access, reset values, encoding identity, and for groups, child names,
offsets, strides, and the children's own signatures. Two components share a type
only when that digest matches.

The signature covers comments as well as code, because a comment that describes
the wrong field is its own kind of wrong.

Structural variants
-------------------

When two components share a SystemRDL type name but differ structurally, the
second gets a ``__v2`` suffix (then ``__v3``, and so on) and the exporter reports
:ref:`pss-i202`. In practice ``systemrdl-compiler`` often disambiguates such
types itself, so the suffix is a safety net rather than a common sight -- but it
is the net that makes the guarantee unconditional.

Identifier mangling
-------------------

SystemRDL names can collide with PSS keywords (``component``, ``action``,
``pool``, ``state``, ``buffer``, ...) or with identifiers imported from
``addr_reg_pkg`` (``reg_c``, ``reg_group_c``, ``READWRITE``, ...). Colliding with
the first is a syntax error; colliding with the second produces a package that
fails to link.

The rule: append ``_``; if that also collides, append ``_1``, ``_2``, and so on.
Escaped SystemRDL identifiers (``\reg``) drop the backslash first -- the escape is
a SystemRDL lexical device, and PSS's own ``write_field()`` convention treats the
name as unescaped.

Every rename is reported as :ref:`pss-i201`, recorded in a comment on the
declaration, and listed in the :ref:`sidecar`.

Instance names always win
-------------------------

Generated names -- reserved fields, reset constants, index helpers -- are
allocated *after* every real instance name in the same scope. A register named
``ctrl_reset`` sitting next to ``ctrl`` keeps its name; ``ctrl``'s generated
constant is the one that gets renamed.

The alternative would silently change the key of ``get_offset_of_instance``,
breaking every consumer that looks the register up by name -- to make room for a
convenience feature.

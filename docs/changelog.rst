Changelog
=========

0.1.0 (unreleased)
------------------

First release.

* ``addrmap`` / ``regfile`` to ``reg_group_c``, with both offset functions.
* ``reg`` to ``packed_s`` + ``reg_c``, with explicit ``SZ`` and derived access.
* Gap and reserved-field synthesis; ``--pad-tail``, ``--rsvd-prefix``.
* N-dimensional arrays flattened row-major; ``--emit-index-helpers``.
* Structural-signature type reuse, so dynamic property assignment cannot cause
  two different registers to share one emitted type.
* Identifier mangling against PSS keywords and core-library names.
* Field and enum-member ``desc`` emitted as a comment above the member, reflowed
  to the output width. Lexical ``//`` comments in the ``.rdl`` are not carried:
  the compiler discards them and the elaborated model has no record of them.
  ``desc`` is a property, so it is unambiguous about what it documents.
* ``--emit-top`` wrapper, ``--emit-reset-consts``, ``--emit-enums``,
  ``--sidecar``, ``--type-style``, ``--no-pure``, ``--strict``.
* Hard errors for the four unrepresentable constructs -- see
  :doc:`unsupported`.

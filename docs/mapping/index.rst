The mapping
===========

How each SystemRDL construct becomes PSS.

.. list-table::
    :header-rows: 1
    :widths: 30 40 30

    * - SystemRDL
      - PSS
      - Details
    * - ``addrmap``, ``regfile``
      - ``pure component ... : reg_group_c``
      - :doc:`groups`
    * - ``reg``
      - ``packed_s<>`` struct + ``pure component ... : reg_c<>``
      - :doc:`registers`
    * - ``field``
      - a ``packed_s`` member
      - :doc:`fields`
    * - arrays (any rank)
      - one-dimensional component arrays
      - :doc:`arrays`
    * - ``encode``
      - ``static const`` values, or a typed enum
      - :doc:`fields`
    * - ``mem``
      - *nothing* -- the export fails
      - :doc:`../unsupported`

``addrmap`` and ``regfile`` map identically: the distinction is not observable in
PSS, since both become a group whose children carry offsets.

.. toctree::
    :hidden:

    groups
    registers
    fields
    arrays
    naming
    limitations

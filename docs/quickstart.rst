Quickstart
==========

Start with a small SystemRDL description:

.. code-block:: systemrdl

    addrmap my_block {
        reg {
            field {sw=rw; hw=r;} enable[0:0]  = 0;
            field {sw=rw; hw=r;} mode[3:1]    = 0;
        } ctrl @ 0x0;

        reg {
            field {sw=r;  hw=w;} busy[0:0];
        } status @ 0x4;
    };

Export it:

.. code-block:: bash

    peakrdl pss my_block.rdl -o my_block.pss

The result:

.. code-block:: text

    package my_block {
        import addr_reg_pkg::*;
        import std_pkg::*;

        // ---- register types ----

        // my_block.ctrl
        struct my_block__ctrl_s : packed_s<LITTLE_ENDIAN> {
            bit enable;      // [0] sw=rw hw=r reset=0x0
            bit[3] mode;     // [3:1] sw=rw hw=r reset=0x0
        }
        pure component my_block__ctrl_c : reg_c<my_block__ctrl_s, READWRITE, 32> {}

        // my_block.status
        struct my_block__status_s : packed_s<LITTLE_ENDIAN> {
            bit busy;        // [0] sw=r hw=w
        }
        pure component my_block__status_c : reg_c<my_block__status_s, READONLY, 32> {}

        // ---- register groups ----

        // my_block
        pure component my_block_c : reg_group_c {
            my_block__ctrl_c   ctrl;
            my_block__status_c status;

            pure function bit[64] get_offset_of_instance(string name) {
                match (name) {
                    ["ctrl"]: return 0x0;
                    ["status"]: return 0x4;
                    default: return -1;
                }
            }

            pure function bit[64] get_offset_of_instance_array(string name, int index) {
                match (name) {
                    default: return -1;
                }
            }
        }
    }

Three things to notice
----------------------

**Offsets live in the parent, not the register.** ``get_offset_of_instance``
returns the offset relative to the group. This is why register types are more
reusable in PSS than in most register-model formats: the same ``reg_c`` type can
appear at any address.

**Access policy is derived, not copied.** ``ctrl`` became ``READWRITE`` and
``status`` became ``READONLY``, derived from the union of their fields' ``sw``
policies. PSS has exactly three access values; SystemRDL has many more. See
:doc:`mapping/registers`.

**Both offset functions are always emitted.** PSS requires the scalar and array
forms to be implemented as a pair, even when one of them has no entries.

Getting a usable handle
-----------------------

The package above is environment-agnostic: it describes registers but does not
say where they live. Add ``--emit-top`` to also generate a wrapper that binds it
to an address region:

.. code-block:: bash

    peakrdl pss my_block.rdl -o my_block.pss --emit-top --base-address 0x40000000

See :doc:`using-the-output` for reading and writing through the result.

Using the generated package
===========================

Binding to an address space
---------------------------

The register package describes registers but not where they live. Something has
to give the top group an address handle, and PSS allows that only on the
top-level group, inside ``exec init_up``.

``--emit-top`` generates it:

.. code-block:: text

    package my_block_top {
        import addr_reg_pkg::*;
        import std_pkg::*;
        import my_block::*;

        component my_block_wrapper_c {
            my_block_c                 regs;
            transparent_addr_space_c<> sys_mem;

            exec init_up {
                transparent_addr_region_s<> region;
                addr_handle_t h;
                region.size = 0x1000;
                region.addr = 0x40000000;
                h = sys_mem.add_nonallocatable_region(region);
                regs.set_handle(h);
            }
        }
    }

It is a separate file on purpose: the address a block sits at is a property of
the system, not of the registers, and keeping the two apart lets one register
package serve several environments. Write your own equivalent if your
environment already owns its address space -- the only requirement is that
``set_handle()`` is called on the top group during ``init_up``.

Reading and writing
-------------------

Typed access, through the register's own struct:

.. code-block:: text

    my_block__ctrl_s value;

    value = regs.ctrl.read();
    value.enable = 1;
    regs.ctrl.write(value);

Untyped access, through ``reg_sized_c``, when the field layout does not matter:

.. code-block:: text

    bit[32] raw;

    raw = regs.ctrl.read_val();
    regs.ctrl.write_val(0x1234);
    regs.ctrl.write_val_masked(0xffff, 0x1234);

By field name -- note that the string is the *emitted* member name, which is why
renames are documented rather than silent:

.. code-block:: text

    regs.ctrl.write_field("enable", 1);

Nested groups and arrays
------------------------

Groups nest as ordinary component instances:

.. code-block:: text

    regs.blk0.sub.ctrl.write(value);

Arrays are one-dimensional after flattening. With ``--emit-index-helpers``:

.. code-block:: text

    regs.blk.bar[my_blk_c::bar_index(2, 1)].write(value);

.. _reset-constants:

Reset constants
---------------

``--emit-reset-consts`` puts each register's reset value beside its instance:

.. code-block:: text

    pure component my_block_c : reg_group_c {
        my_block__ctrl_c ctrl;

        static const bit[32] ctrl_reset = 0x000004d2;
        ...
    }

which supports the check you actually want to write after reset:

.. code-block:: text

    assert(regs.ctrl.read_val() == my_block_c::ctrl_reset);

The constants are instance-scoped rather than per-type because reset is an
*instance* property in SystemRDL -- a dynamic assignment can retarget it, so the
value belongs where the instance is.

Two rules worth knowing:

* An array gets **one** constant, not one per element: array elements share a
  type and therefore a reset.
* A register with no specified reset gets **no** constant. Absence and zero are
  different, and a fabricated zero in a value used for assertions would be worse
  than nothing.

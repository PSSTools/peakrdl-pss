Groups: ``addrmap`` and ``regfile``
====================================

Each ``addrmap`` and ``regfile`` becomes one ``reg_group_c`` component:

.. code-block:: text

    pure component my_block_c : reg_group_c {
        my_block__ctrl_c ctrl;
        my_block__data_c data[4];

        pure function bit[64] get_offset_of_instance(string name) {
            match (name) {
                ["ctrl"]: return 0x0;
                default: return -1;
            }
        }

        pure function bit[64] get_offset_of_instance_array(string name, int index) {
            match (name) {
                ["data"]: return 0x10 + index*0x4;
                default: return -1;
            }
        }
    }

Offsets are relative to the group
---------------------------------

The returned values are ``raw_address_offset`` -- the offset relative to the
containing group, not an absolute address. This matches PSS's definition, and it
is what makes register and group types genuinely reusable: the same type can be
instantiated at any address, because nothing inside it knows its own address.

Absolute addresses are never emitted. They are reconstructed by the PSS tool as
it walks from the group that holds the address handle down to the register.

Both functions are always emitted
---------------------------------

PSS requires ``get_offset_of_instance`` and ``get_offset_of_instance_array`` to
be implemented as a pair, so a group with no arrays still emits the array
function with only its ``default`` arm.

``get_offset_of_path`` is *not* emitted: implementing all three in one group is
an error in PSS. ``--offset-mode=path`` selects the other choice.

Match keys are the emitted names
--------------------------------

The strings in the ``match`` arms are the names as declared in the generated
component, which is what a PSS tool looks up. If an identifier had to be renamed
(see :doc:`naming`), the match key is the *renamed* one -- the two are always
consistent with each other, and the original SystemRDL name is recorded in a
comment and in the :ref:`sidecar`.

Nesting
-------

Groups nest by instantiating each other, and offsets accumulate down the path.
A register three levels deep is reached by summing three offsets, each returned
by its own group.

Traversal is post-order, so a group is emitted after every type it instantiates.
That satisfies PSS's define-before-use rule without a separate ordering pass.

Bridges
-------

An addrmap with ``bridge = true`` is an error -- see :doc:`../unsupported`.
Non-bridge sub-addrmaps, including ``external`` ones, are ordinary groups: they
live in the same address space, so they are representable.

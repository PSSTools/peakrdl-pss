Unsupported constructs
======================

Four SystemRDL constructs cause the export to **fail**. They are refusals, not
tradeoffs: for each one, any output the exporter could produce would parse
cleanly, link cleanly, and be wrong.

That last point is why these are errors rather than warnings. A 128-bit register
emitted as a ``reg_c<..., 128>`` is accepted by a PSS parser without complaint --
the wrongness only surfaces as failed transactions much later, by which time the
generated file is several steps removed from the problem. A warning in a build
log is not adequate protection against a failure mode that silent.

All problems are reported in one run: the export completes its analysis before
aborting, so a description with three problems needs one round trip, not three.
Nothing is written when the export fails -- a partial file would be picked up by
whatever build step runs next.

.. _regwidth-too-wide:

``regwidth`` greater than 64 -- :ref:`pss-e001`
-----------------------------------------------

PSS register access is defined over integer types of at most 64 bits.

**What to do.** Split the register in the SystemRDL description into 64-bit or
narrower registers. If the hardware genuinely presents a single wider register,
the split is a modelling decision you need to make explicitly -- the exporter
cannot make it for you without guessing at the access order.

``accesswidth`` less than ``regwidth`` -- :ref:`pss-e002`
---------------------------------------------------------

A register that is accessed in several bus transactions has no PSS
representation: ``reg_c`` models a single access of the full register width.

**What to do.** Model the sub-accesses as separate registers, or raise
``accesswidth`` if the narrower access width was incidental rather than a
hardware property.

Bridge address maps -- :ref:`pss-e003`
--------------------------------------

A ``bridge`` addrmap introduces a second address space. The generated package
models exactly one, because only the top-level group may call ``set_handle()``.

**What to do.** Export each side separately, using PeakRDL's ``--top`` to select
the sub-addrmap:

.. code-block:: bash

    peakrdl pss design.rdl --top side_a -o side_a.pss
    peakrdl pss design.rdl --top side_b -o side_b.pss

Each output then gets its own address space in the consuming environment, which
is what the bridge was describing in the first place.

Memories -- :ref:`pss-e004`
---------------------------

``mem`` components have no ``reg_group_c`` analog, and virtual registers inside
them are not addressable the way real registers are.

**What to do.** A memory anywhere in the description currently blocks the whole
export, even when the registers around it are perfectly representable. If that
is too strict for your design, export a subtree that excludes the memory with
``--top``, and model the memory's address range directly in your PSS environment
as a ``transparent_addr_region_s<>``.

Lossy but supported
-------------------

Constructs that *can* be mapped, at a cost, are not here -- see
:doc:`mapping/limitations`. The distinction is deliberate: this page is things
that stop you, that page is things you should know about.

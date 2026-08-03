Customizing the output
======================

The generated text comes from Jinja2 templates that ship with the package. You
can override any of them without forking.

.. code-block:: toml

    # peakrdl.toml
    [pss]
    user_template_dir = "my_templates"

Or from Python:

.. code-block:: python

    PSSExporter(user_template_dir="my_templates")

A file in that directory replaces the shipped template of the same name.
Everything you do not override still comes from the package.

The templates
-------------

.. list-table::
    :header-rows: 1

    * - Template
      - Renders
    * - ``top_pkg.pss``
      - the whole package, and the order things appear in
    * - ``reg_struct.pss``
      - one register's ``packed_s`` struct
    * - ``reg_component.pss``
      - one register's ``reg_c`` component
    * - ``reg_group.pss``
      - one ``reg_group_c`` component, including the offset functions
    * - ``enums.pss``
      - one ``encode`` enumeration
    * - ``top_wrapper.pss``
      - the ``--emit-top`` wrapper
    * - ``utils.pss``
      - shared macros

Reaching the original
---------------------

Prefix a template name with ``base:`` to name the shipped version explicitly --
which is what you need in order to extend rather than replace it:

.. code-block:: jinja

    {% extends "base:reg_group.pss" %}

Without the prefix, ``reg_group.pss`` resolves to *your* file, so extending it
unprefixed would recurse.

What templates receive
----------------------

Templates get plain data, never the SystemRDL model:

.. list-table::
    :header-rows: 1

    * - Name
      - What it is
    * - ``d``
      - the whole design (``package_name``, ``reg_types``, ``group_types``, ...)
    * - ``rt``
      - the current register type, inside ``reg_struct``/``reg_component``
    * - ``gt``
      - the current group type, inside ``reg_group``
    * - ``et``
      - the current encoding, inside ``enums``
    * - ``opt``
      - the resolved export options
    * - ``pure``
      - whether components carry the ``pure`` qualifier
    * - ``version``
      - the generator version
    * - ``index_helpers(gt)``
      - the index helpers for a group, if enabled

Anything you pass as ``user_template_context`` is added to that namespace.

The separation is deliberate: by the time rendering starts, the compiled
SystemRDL model is no longer consulted. A template cannot reach back into it,
which is what keeps the output reproducible and the structural signatures honest.

Undefined variables are errors
------------------------------

The Jinja environment uses ``StrictUndefined``, so a typo in a template name
fails loudly instead of rendering an empty string into your PSS source.

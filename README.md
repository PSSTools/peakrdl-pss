# peakrdl-pss

Generate a **PSS (Portable Test and Stimulus) register package** from a
SystemRDL register description.

```bash
python3 -m pip install peakrdl-pss
peakrdl pss my_design.rdl -o my_regs.pss
```

The output is a `.pss` file containing a `packed_s<>` struct and a
`pure component ... : reg_c<>` per register type, and a
`pure component ... : reg_group_c` per `addrmap`/`regfile` implementing the
offset functions a PSS tool uses to resolve addresses.

Where a construct has no PSS representation, the export **fails** rather than
emitting something plausible — a 128-bit register emitted as a `reg_c` parses
cleanly and is wrong. Where the mapping is possible but lossy, the exporter emits
it and reports exactly what it dropped.

## Documentation

See `docs/` (Sphinx): the mapping, the CLI, diagnostics by ID, and what is not
supported.

## Development

```bash
ivpm update && source .envrc
python -m pip install -e . --no-deps
pytest
```

See the contributing page in the docs for how the test suite is organized.

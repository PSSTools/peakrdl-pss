# PeakRDL-PSS: Implementation, Test, and Documentation Plan

**Status:** M0–M5 and M7 implemented; M6 deferred (parser-gated). 0.0.1 released 2026-08-05
**Date:** 2026-08-02, implementation record added 2026-08-03
**Design input:** `docs/design/systemrdl-to-pss.md` (the "design doc" below), *including the
`MSB:` review comments*, which are resolved here and summarized in §0.1
**Companion input:** `docs/design/pssparser-3.1-requirements.md` (the "parser doc")
**Repo state assumed at start:** `src/` and `tests/` empty; `packages/` populated by IVPM
(`peakrdl`, `peakrdl-uvm`, `pssparser`, `python` venv with `systemrdl-compiler` 1.32.2).

---

## Implementation record (2026-08-03)

Milestones **M0 through M5 and M7 are implemented**. M6 is deferred by design
(both items are parser-gated and both defaults are complete).

| Milestone | State | Evidence |
|---|---|---|
| M0 skeleton & harness | done | `pip install -e .` works, `peakrdl pss --help` lists the subcommand, `sphinx-build -W` is clean |
| M1 core emission | done | every corpus design exports and is accepted by `pssparser` |
| M2 correctness core | done | signature dedup, N-D flattening, gaps, mangling, access derivation, `--type-style=hier` |
| M3 validation | done | `PSS-E001..E004`, warnings/info, `--strict`, routed through `node.env.msg` |
| M4 optional features | done | every flag in §4.7 except the two M6 modes, which refuse with a message naming the parser requirement |
| M5 cross-check | done | offset oracle, layout oracle, signature fidelity, determinism, naming, UVM cross-check |
| M6 parser-gated | deferred | `--emit-enums=typed`, `--offset-mode=path` raise `NotImplementedError` |
| M7 release | done | tag-gated `publish-pypi` job; **0.0.1 published to PyPI** on 2026-08-05 from tag `v0.0.1` |

**Current gate:** 498 tests pass; 95% line coverage (gate is 85%); `ruff` and
`mypy --strict` clean; `sphinx-build -W` clean; all 144 parser-gate cases pass.

### What the plan got wrong, and what the corpus caught

Six things were wrong in the plan or in the first implementation. Each is worth
recording because each was found by a test rather than by reading:

1. **`PSS-E005` cannot fire — removed.** The plan promoted "regwidth not in
   {8,16,32,64}" to an error. But `systemrdl-compiler` already *fatals* on
   `regwidth < 8` and on non-powers-of-2, so the only width that can reach the
   exporter outside that set is `> 64`, which `PSS-E001` owns. The ID was
   removed rather than shipped as a phantom entry in the diagnostics page. The
   `err_width_24.rdl` corpus case went with it.
2. **`PSS-W107` is unreachable through SystemRDL.** `sw=na` on a field in a
   register is a compiler error, so "no software-accessible field" cannot be
   produced from RDL. The check is kept (a register with no fields at all would
   hit it) but is covered by a unit test against the IR rather than by a corpus
   file, and `access_matrix.rdl` says so.
3. **msb0 was described incorrectly.** The plan said "reverse the physical
   mapping". The truth, confirmed against `systemrdl-compiler` and PeakRDL's own
   `rdl_gotchas`: in msb0 mode a field's *span* is unchanged and its **bits are
   swapped within the field**. `packed_s` cannot express that. The emitted member
   therefore occupies the correct bits and `PSS-W105` states precisely what is
   lost. Getting this backwards would have relocated every field in an msb0
   register while the output still parsed.
4. **`basic.rdl` cannot be copied verbatim.** The UVM testcase contains an
   `external mem`, which is now a hard error — a verbatim copy could only ever
   exercise the failure path. The mem was moved to `err_mem.rdl`; the construct
   the file exists for (`r3.f1->sw = w`) is preserved exactly.
5. **The reset-const naming hazard was real, and worse than described.** §4.9
   assumed mangling the constant against sibling names was enough. It was not:
   allocating the constant inside the child loop let `ctrl`'s constant claim the
   name of the *later* sibling register `ctrl_reset`, silently renaming a
   register and thereby changing the key of `get_offset_of_instance`. Fixed by
   deferring all constants to a second pass, so **instance names always win**.
   `reset.rdl` was written to catch exactly this and did.
6. **The goldens were version-coupled.** Every generated file stamps the
   generator version into its header, and the goldens recorded it literally, so
   the first version bump after CI went green (`0.1.0` → `0.0.1`, commit
   `772c326`) failed 25 goldens in both jobs while changing no behaviour. A
   26-file diff on a release is a diff nobody reads, and one that trains
   reviewers to regenerate goldens without looking. Goldens now record the stamp
   as `<version>` and `assert_golden` substitutes it in; `tests/unit/test_header.py`
   covers the real stamp in both the package header and the sidecar, so
   normalizing it away does not leave it untested.

Three further defects were found by tests during implementation: the Jinja loader
chain made non-overridden templates unfindable whenever `user_template_dir` was
set; the shipped templates' `base:` include prefix defeated user overrides
entirely; and `--emit-enums=off` was accepted and ignored.

### Structural deviations from §2

| Plan | Built | Why |
|---|---|---|
| `design.py` holds the IR *and* the scanner | `ir.py` (dataclasses) + `design.py` (scanner) | `layout.py`/`addressing.py` build IR objects and `design.py` calls them — one module would be an import cycle |
| `validate.py` owns `Finding` and the ID table | `diagnostics.py` owns them | the *scanner* raises most findings, and `validate.py` imports the IR |
| options passed as kwargs | `options.py` with `ExportOptions` | one object threaded through all four stages; the parity test checks it against both surfaces |
| §7.4 asserts the keyword table *equals* the parser's | asserts it is a *superset* of both the parser grammar and spec Table 3 | the two sources genuinely disagree (the parser has `mutable`/`pyimport`; the spec has `this`/`pre_body`); the union is strictly safer, and subset assertions still catch drift |

### Parser status — and a measurement error worth recording

An earlier draft of this record claimed the installed `pssparser` already provided
Tier 1.2 (`reg_base_c`/`reg_sized_c`), Tier 1.3 (`node_s`) and the whole Tier 3
consumer surface, and that the consumer suite had **zero xfails**. That was
measured against the *local working tree* of `packages/pssparser`, which has ~20
uncommitted modifications — including additions to `src/stdlib/addr_reg_pkg.pss`
that introduce `reg_sized_c`, `write_val_masked`, `write_field`, `write_fields`
and `node_s`. The `.so` files in that tree were built from those edits, not from
committed HEAD.

CI caught it immediately: building `pssparser` from committed `05e7057` gives
**196 passed, 2 xfailed**. The two are `sized_access` and `write_field` — exactly
the `reg_sized_c` members that exist only in the uncommitted tree.

The lesson generalizes past this instance: *a dependency's working tree is not its
released behavior*, and validating against a dirty sibling checkout silently
overstates what consumers can do. CI building from a committed ref is what makes
that distinction observable.

Corrected status:

| Tier | Committed `pssparser` HEAD | Gates |
|---|---|---|
| 1.1 — enum base type | absent | `--emit-enums=typed` (M6) |
| 1.2 — `reg_sized_c`/`reg_base_c` | **absent** (uncommitted WIP) | the two consumer xfails |
| 1.3 — `node_s` | **absent** (uncommitted WIP) | `--offset-mode=path` (M6) |
| 3 — `write_field` etc. | **absent** (rides on 1.2) | the two consumer xfails |
| 2 — mnemonics | n/a | nothing; dropped |

What does *not* change: **every package this exporter generates parses and links
against committed `pssparser` HEAD.** All 144 parser-gate cases pass. The gap is
entirely consumer-side, which is exactly the split §7.5 was designed around — and
the reason the two suites are kept separate rather than merged.

---

## 0. How to read this plan

Three tracks run in parallel after M0:

| Track | Deliverable | Sections |
|---|---|---|
| **I** — Implementation | `src/peakrdl_pss/**` | §2–§5 |
| **T** — Test | `tests/**` | §6–§8 |
| **D** — Documentation | `docs/**` (Sphinx) | §9–§10 |

Milestones (§1) cut across all three: each milestone lands code + its tests + its doc page
together. Nothing is "done" with a missing test or a missing doc section.

All six of the design doc's §13 open decisions are now **closed** by the `MSB:` review
comments; §12 records the resolutions and their consequences. Nothing in this plan is
blocked on a pending decision.

### 0.1 Delta from the design doc (from the `MSB:` review)

The review resolved every open decision and removed one feature outright. Net effect on
scope — **the plan gets smaller and sharper**:

| Design doc said | Review says | Consequence for this plan |
|---|---|---|
| §11.1 `regwidth > 64`: warn and emit | **Unsupported** | Hard error, always. No `--strict` dependency. |
| §11.2 `accesswidth < regwidth`: ignore + warn | **Unsupported** | Hard error, always. |
| §11.5 multi-address-space: detect + `--split-at` | **Unsupported** | Hard error on `bridge=true`. No `--split-at`. |
| §11.4 `mem`: warn/skip, `--mem-mode=region` | **Unsupported** | Hard error. `--mem-mode` flag deleted. |
| §12.3 symbolic names / mnemonics (the "standout opportunity") | **Ignore — PSS already has enough mnemonic support** | Feature deleted. `--symbolic-names`, `--mnemonic-style` deleted. Removes the one feature with no local test coverage. |
| §13.6 PSS floor: `--pss-level={3.0,3.1}` | **Assume 3.1, no symbolic names** | `--pss-level` flag deleted. Target 3.1 unconditionally. |
| §12.2 reset consts at package scope, per register *type* | **Companion const in the group component**, next to the instance | Reset consts become instance-scoped members of the group. See §4.9. |

Four features and three CLI flags leave the plan; one feature changes shape. The
milestone list, CLI surface, corpus, validation table, and docs tree below reflect this,
**not** the design doc's §8/§13 tables, which are now stale in those rows.

### 0.2 "Unsupported" means hard error

The four `Unsupported` answers are implemented uniformly: the construct is **detected in
the validator and fails the export with a nonzero exit and a `PSS-Exxx` diagnostic**. It is
never silently skipped and never emitted in degraded form. Rationale: each of these
produces output that *parses* but is wrong (a 128-bit `reg_c` links clean — design §10.1),
so a warning would ship silent wrongness, which is exactly what the design doc argues
against.

One consequence worth flagging: a design containing **any** `mem` becomes un-exportable in
its entirety, even if the register content is perfectly representable. That is the strict
reading of "Unsupported" and what this plan implements. If a friendlier
warn-and-skip-the-mem is wanted later, it is a one-line severity change in `validate.py`
plus a golden — noted, not assumed.

---

## 1. Milestones

| M | Name | Exit criteria | Depends on |
|---|---|---|---|
| **M0** | Skeleton & harness | `pip install -e .` works; `peakrdl pss --help` lists the subcommand; `pytest` runs (0 tests); `sphinx-build docs` succeeds | — |
| **M1** | Core emission (walking skeleton) | `basic.rdl` → a `.pss` that `pssparser` accepts, containing packed structs, `reg_c`, `reg_group_c` with both offset functions, scalar + 1-D arrays | M0 |
| **M2** | Correctness core | signature-based dedup (§5.2 of design), N-D array flattening, gap/reserved synthesis, identifier mangling, access derivation | M1 |
| **M3** | Validation & diagnostics | the four hard-unsupported errors (§0.2) + the remaining checks of design §9, `--strict`, message routing through `node.env.msg` | M2 |
| **M4** | Optional emission features | `--emit-top`, `--emit-reset-consts`, `--emit-enums`, `--emit-index-helpers`, `--pad-tail`, `--rsvd-prefix`, `--no-pure`, `--sidecar` | M2 |
| **M5** | Cross-check & property tests | offset-oracle test, layout test, UVM cross-check, determinism suite in CI | M2 |
| **M6** | Parser-gated extras | `--emit-enums=typed` (parser Tier 1.1), `--offset-mode=path` (parser Tier 1.3) | those parser tiers landed |
| **M7** | Release 1.0 | Docs complete, CI green on 3.9–3.13, packaged, `CHANGELOG` written | M3, M4, M5 |

M6 is explicitly *not* on the 1.0 critical path — both items are gated on `pssparser` work
in another repo, and both are optional emission modes with working defaults
(`--emit-enums=const`, `--offset-mode=instance`). M7 ships without them if they are not
ready.

The output targets **PSS 3.1 unconditionally** (review decision). There is no version knob:
the two features above are gated on *parser availability*, which is a tool-support
question, not a language-level one, and is tracked in `compatibility.rst` (§9.1).

---

## 2. Repository layout to create

```
pyproject.toml                  # setuptools, entry points, ruff/mypy/pytest config
README.md                       # short; points at docs
CHANGELOG.md
src/peakrdl_pss/
    __about__.py                # __version__ = "0.1.0"
    __init__.py                 # re-export PSSExporter
    __peakrdl__.py              # ExporterSubcommandPlugin  (§4.7)
    exporter.py                 # PSSExporter               (§4.1)
    design.py                   # DesignScanner + Design IR (§4.2)  <-- new vs. design doc
    signature.py                # structural digest         (§4.3)
    identifiers.py              # keyword table + mangling  (§4.4)
    access.py                   # sw/onread/onwrite -> reg_access + lossiness (§4.5)
    layout.py                   # field ordering, gaps, msb0 (§4.6)
    addressing.py               # offsets, N-D flattening, strides (§4.6)
    validate.py                 # validation checks         (§4.8)
    sidecar.py                  # JSON lossiness sidecar    (§4.10, M4)
    templates/
        top_pkg.pss             # package wrapper, imports, ordering
        reg_struct.pss          # packed_s per register type
        reg_component.pss       # pure component : reg_c<>
        reg_group.pss           # pure component : reg_group_c
        enums.pss               # encode enums / const encodings
        top_wrapper.pss         # --emit-top
        utils.pss               # macros/filters shared by the above
tests/
    conftest.py
    util/                       # helpers: compile RDL, run pssparser, golden compare
    unit/                       # per-module unit tests
    golden/
        rdl/                    # input .rdl
        expect/                 # expected .pss
    property/                   # offset oracle, layout oracle, determinism
    integration/                # CLI, plugin discovery, consumer snippets
docs/
    conf.py  index.rst  Makefile  requirements.txt
    ... (§9)
```

### 2.1 Why `design.py` is added

The design doc has templates receiving "precomputed context" but does not name the thing
that holds it. Introducing an explicit intermediate representation (IR) is the single
highest-leverage structural decision in this plan:

* it makes the offset/layout logic testable **without** rendering Jinja,
* it makes the golden tests diff a data structure when a template bug is suspected,
* it gives `--emit-enums`, sidecar, and the property tests one shared source of truth,
* it removes any temptation to call `get_property()` from a template.

The pipeline becomes: **compile → scan (build IR) → validate (IR) → render (IR)**.

---

## 3. M0 — Skeleton and harness

### 3.1 `pyproject.toml`

* build backend: `setuptools>=64`, `src` layout, version read from `__about__.py`.
* runtime deps: `systemrdl-compiler>=1.27,<2`, `jinja2>=3.0`.
* `[project.optional-dependencies]`: `test = [pytest, pytest-cov]`, `docs = [sphinx,
  sphinx-book-theme, sphinxemoji, pygments-systemrdl]`, `dev = [ruff, mypy]`.
* `peakrdl` itself is **not** a runtime dep (matching `peakrdl-uvm`) — the plugin module
  imports it lazily and `PSSExporter` is usable standalone.
* entry point:
  ```toml
  [project.entry-points."peakrdl.exporters"]
  pss = "peakrdl_pss.__peakrdl__:Exporter"
  ```
* pytest config: `testpaths = ["tests"]`, markers `pssparser`, `slow`, `uvm`.

**Note on `peakrdl`:** it is checked out under `packages/peakrdl` but is *not* installed in
`packages/python` (verified). M0 must add it (and `pytest`, `sphinx`, `jinja2`) to the venv
via IVPM before the plugin-discovery tests can run. This is a real, current blocker for
M0's exit criteria.

### 3.2 Skeleton content

* `PSSExporter.export()` present with the full signature (§4.1) but emitting only a
  `package <name> { }` shell — enough to prove the entry point, the Jinja loader, and the
  output path plumbing.
* `tests/util/` helpers written first (§6.1) — every later test depends on them.
* `docs/` Sphinx project builds with `index.rst` + stub pages.

---

## 4. Track I — Implementation detail

### 4.1 `exporter.py` — `PSSExporter`

```python
class PSSExporter:
    def __init__(self, *, user_template_dir=None, user_template_context=None): ...

    def export(self, node, path, *,
               package_name=None,          # default: sanitized output basename
               type_style="lexical",       # {lexical, hier}
               emit_top=False,
               base_address=0,
               emit_enums="const",         # {const, typed, off}  (typed: M6)
               emit_reset_consts=False,
               emit_index_helpers=False,
               pad_tail=False,
               rsvd_prefix="rsvd_",
               pure_components=True,
               offset_mode="instance",     # {instance, path}   (path: M6)
               sidecar_path=None,
               strict=False) -> None
```

Behavior:

1. `RootNode` → `node.top`, as UVM does.
2. Build an `ExportOptions` dataclass from the kwargs — one object threaded through
   scanner/validator/renderer instead of a dozen parameters. Unknown kwargs raise `TypeError`
   (UVM's convention).
3. `DesignScanner(options).scan(top)` → `Design`.
4. `Validator(options).run(design)` → emits messages; raises `PSSExportError` if `strict`
   and any error-level finding.
5. Render `top_pkg.pss` → `path`. If `emit_top`, render `top_wrapper.pss` →
   `<stem>_top.pss`. If `sidecar_path`, write JSON.
6. Rendering is done to a string then written in one `open(..., "w", newline="\n")` so
   output is byte-identical across platforms (UVM's `stream.dump` is not newline-stable).

Jinja env: `ChoiceLoader` + `PrefixLoader` (`base:`/`user:`) exactly as UVM, plus
`undefined=StrictUndefined`, `trim_blocks=True`, `lstrip_blocks=True`,
`keep_trailing_newline=True`.

### 4.2 `design.py` — the IR and the scanner

```python
@dataclass(frozen=True)
class FieldRow:
    name: str            # mangled, PSS-legal
    rdl_name: str        # original, for the comment
    width: int
    lsb: int; msb: int
    reserved: bool
    sw: str; hw: str
    reset: int | None
    reset_is_ref: bool
    enum_type: str | None      # name of emitted enum, if any
    lossy_notes: tuple[str, ...]   # onread/onwrite/counter/intr descriptions

@dataclass
class RegType:
    type_name: str       # e.g. basic__foo__reg_t   (no suffix)
    friendly: str        # for the header comment
    regwidth: int
    accesswidth: int
    access: str          # READWRITE | READONLY | WRITEONLY
    fields: list[FieldRow]
    reset_value: int | None
    signature: str
    is_msb0: bool

@dataclass
class ChildRef:
    inst_name: str       # mangled
    rdl_name: str
    type_name: str
    is_array: bool
    flat_count: int | None
    dims: tuple[int, ...] | None
    stride: int | None
    offset: int          # raw_address_offset
    kind: Literal["reg", "group", "mem"]

@dataclass
class GroupType:
    type_name: str; friendly: str
    children: list[ChildRef]
    signature: str

@dataclass
class Design:
    package_name: str
    reg_types: list[RegType]      # emission order = definition-before-use
    group_types: list[GroupType]
    enums: list[EnumType]
    top_type_name: str
    top_size: int
    findings: list[Finding]
    mangle_map: dict[str, str]
```

`DesignScanner` walks `top.descendants(in_post_order=True)` then `top`:

* per `RegNode`: build `FieldRow`s via `layout.build_rows()`, derive access via
  `access.derive()`, compute `signature.of_reg()`, then intern into `reg_types` keyed by
  `(type_name, signature)`. On name-hit/signature-miss, allocate `__v2`, `__v3`, … and
  record an info finding.
* per `AddrmapNode`/`RegfileNode`: build `ChildRef`s from `child.raw_address_offset`,
  `array_dimensions`, `array_stride`; intern by `(type_name, signature)`.
* per `MemNode`: record a `PSS-E004` error finding and stop building that subtree
  (§0.2). No `mem` output mode exists.
* per `AddrmapNode` with `bridge=true`: record `PSS-E003` (§0.2). Non-bridge sub-addrmaps,
  including `external` ones, are traversed like any other group — they live in the same
  address space, so they are representable.

The scanner is the *only* place `get_property()` is called. It catches
`RDLCompileError`-adjacent issues (reference-valued `reset`, unresolvable `encode`) and
converts them into findings rather than exceptions.

**Determinism rule:** every collection in the IR is a `list` built in traversal order; no
`set` iteration ever reaches output. `namespace_db` is a `dict` used only for membership.

### 4.3 `signature.py`

```python
def of_field(f: FieldRow) -> str
def of_reg(r: RegType) -> str
def of_group(children: list[ChildRef]) -> str
```

Implementation: build a canonical, ordered tuple of exactly the values the templates
consume, `repr()` it deterministically, and `sha1()` it to 16 hex chars. Groups include
child *signatures* (already computed, post-order guarantees availability), inst names,
offsets, strides, dims. Registers include field name/width/lsb/sw/reset/enum-identity,
`regwidth`, `access`, `is_msb0`.

Key property to test: a signature must change when — and only when — the emitted text for
that type would change. §7.2 makes this a mechanized test rather than a claim.

### 4.4 `identifiers.py`

* `PSS_KEYWORDS: frozenset[str]` — sourced by scraping the reserved-word list from
  `PSS 3.1 Draft 19 2026.07.14 clean.md`, cross-checked against
  `packages/pssparser` grammar tokens. A test asserts the two sources agree (§7.4), so the
  table cannot silently rot.
* `mangle(name, taken) -> tuple[str, bool]`: strip a leading `\`, then if the result is a
  keyword or collides in `taken`, append `_`, then `_1`, `_2`, …
* Also mangles names that are not PSS-identifier-legal at all (leading digit, `$`).

### 4.5 `access.py`

* `derive(fields) -> (access, findings)` implementing the design's 3-row table.
* `lossiness(field) -> list[str]` naming every dropped property: `onread`, `onwrite`,
  `singlepulse`, `swmod`, `swacc`, `counter`, `incr`/`decr`, `intr`, `enable`, `mask`,
  `haltmask`, `hdl_path*`, `alias`, `precedence`.
* Access derivation ignores `reserved` rows and `sw=na` rows; a register whose fields are
  *all* `na` derives `READONLY` plus a finding.

### 4.6 `layout.py` + `addressing.py`

`layout.build_rows(reg, options) -> list[FieldRow]`:

1. `reg.fields()` (low-to-high), mangle names against a per-register `taken` set.
2. Insert `rsvd_<lsb>` rows for every gap between rows.
3. Insert a leading reserved row if `fields[0].lsb > 0`.
4. Trailing row only when `pad_tail`.
5. `is_msb0_order`: reverse the *physical* mapping per design §11.8, emit ascending-lsb
   rows computed from the reversed positions, and attach a finding + a comment. Locked
   down by a dedicated golden + layout-oracle case, since this is the easiest thing to get
   silently wrong.

`addressing.flat_offset_expr(child) -> str`: `"0x%x + index*0x%x"`, plus
`index_helper(child) -> str | None` for `--emit-index-helpers`. Also
`total_size(top) -> int` for the wrapper region.

### 4.7 `__peakrdl__.py`

`Exporter(ExporterSubcommandPlugin)` with `short_desc = "Generate a PSS register package"`,
the `cfg_schema` from the design doc, and one `add_argument` per row of the design's §8
table **minus `--symbolic-names`, `--mnemonic-style`, `--mem-mode`** (§0.1), plus
`--offset-mode` and `--sidecar`. `do_export()` maps `options.*` →
`PSSExporter.export()` kwargs, one-to-one, no logic.

Final CLI surface (this table supersedes design §8):

| Option | Default | M |
|---|---|---|
| `-o, --output` | — | M0 |
| `--package-name` | from filename | M0 |
| `--type-style {lexical,hier}` | `lexical` | M2 |
| `--emit-top` | off | M4 |
| `--base-address` | `0` | M4 |
| `--emit-enums {const,typed,off}` | `const` | M4 (`typed`: M6) |
| `--emit-reset-consts` | off | M4 |
| `--emit-index-helpers` | off | M4 |
| `--pad-tail` | off | M2 |
| `--rsvd-prefix` | `rsvd_` | M2 |
| `--no-pure` | off | M4 |
| `--offset-mode {instance,path}` | `instance` | M6 |
| `--sidecar` | off | M4 |
| `--strict` | off | M3 |

Rule: **every CLI flag maps to exactly one `export()` kwarg with the same name.** A test
enumerates the argparse actions and asserts the mapping is total (§7.6) — this is how the
CLI and API stay in sync as flags are added.

### 4.8 `validate.py`

One function per check, each returning `Finding(id, severity, node, message)`. IDs are
stable strings so docs and tests reference them rather than message text.

The review splits design §9's flat warning list into two severity classes:

**Unconditional errors** (§0.2) — always fatal, `--strict` irrelevant:

| ID | Check | Design ref |
|---|---|---|
| `PSS-E001` | `regwidth > 64` | §11.1 |
| `PSS-E002` | `accesswidth < regwidth` | §11.2 |
| `PSS-E003` | `addrmap` with `bridge = true` | §11.5 |
| `PSS-E004` | `mem` encountered | §11.4 |

**Retired:** the plan originally added `PSS-E005` for `regwidth` outside {8,16,32,64}.
It cannot fire — `systemrdl-compiler` fatals on `regwidth < 8` and on non-powers-of-2,
leaving only `> 64`, which `PSS-E001` already owns. See the implementation record.

**Warnings** (promoted to errors under `--strict`): field side-effect semantics
(`onread`/`onwrite`/`singlepulse`/counter/interrupt), `sw=rw1`/`w1`, reference-valued reset,
mixed endianness, `is_msb0_order`, unaligned offset.

**Info** (never promoted): identifier mangled, `__vN` signature variant emitted, `alias`
relationship dropped.

An error aborts the export **after** the full scan, so a design with three problems reports
all three in one run rather than one per invocation. Findings are emitted through
`node.env.msg.error/warning` with the right `src_ref` so PeakRDL prints file/line; the
exporter then raises `PSSExportError`.

### 4.9 Reset constants — instance-scoped (review change)

The review asks for the reset value as a companion const *in the group component*, beside
the instance, rather than a package-scope const per register type:

```pss
pure component basic__foo_c : reg_group_c {
    basic__foo__reg_t_c      r1;
    basic__foo__reg_t_c__v2  r3;

    static const bit[32] r1_reset = 0x000004d2;
    static const bit[32] r3_reset = 0x000000c8;
    ...
}
```

This is better than the design doc's package-scope form: reset is an *instance* property in
SystemRDL (dynamic assignment retargets it — that is the very `r3` case §5.2 exists for), so
the value belongs where the instance is, and the name is unambiguous without hierarchical
prefixing.

**Verified against `pssparser` while writing this plan:**

* plain `const` in a component body → **rejected**, and correctly so: the PSS 3.1 BNF has
  `component_data_decl_qualifier ::= static const | mutable`, so `const` alone is not a
  legal component member.
* `static const bit[32] r1_reset = 0x4d2;` inside a `pure component ... : reg_group_c`,
  alongside scalar and array child instances → **parses and links clean, exit 0**.

So the feature is implementable today with no parser work. Details:

* Name is `<inst_name>_reset`, allocated from the group's member namespace **after every
  child instance name is reserved**. Allocating it inline (the obvious implementation, and
  the first one written) lets an earlier register's constant claim the name of a *later*
  sibling register — silently renaming that register and changing the key of
  `get_offset_of_instance`. Instance names always win; the constant is what gets renamed.
* Width is `regwidth`, matching the register's `packed_s` size.
* Array instances get **one** const (`r2_reset`) — array elements share a type and therefore
  a reset; a per-element const would be N copies of one value.
* A register whose reset is unspecified emits no const (not `0`) — absence and zero are
  different, and inventing a zero would be a silent lie.
* A register with a reference-valued reset emits no const and raises the existing warning.
* Emitted only under `--emit-reset-consts`; the flag stays opt-in because it inflates large
  maps and not every consumer wants it.
* The consts are part of the group's structural signature, so two otherwise-identical groups
  whose instances differ only in reset value correctly get distinct `__vN` types.

### 4.10 `sidecar.py`

`{"version": 1, "package": ..., "registers": [{"type": ..., "path": ..., "fields": [
{"name":..., "rdl_name":..., "sw":..., "onread":..., "counter":..., ...}]}], "findings":
[...]}`. Written only when `--sidecar` is given. Schema versioned from day one and pinned
by a golden JSON test.

### 4.11 Templates

Each template consumes only IR objects and plain scalars. `top_pkg.pss` owns ordering:

```
package {{ d.package_name }} {
    import addr_reg_pkg::*;      // mandatory (design §10.1)
    import std_pkg::*;
    {enums}  {reg structs + components}  {groups, post-order}
    // reset consts live inside each group component (§4.9), not here
}
```

Whitespace/formatting is fixed by the templates and asserted by golden files; there is no
post-format step.

---

## 5. Feature-by-milestone breakdown (Track I)

| Feature | M | Modules touched |
|---|---|---|
| Package shell, loader, entry point | M0 | exporter, `__peakrdl__` |
| packed struct + `reg_c` for scalar regs | M1 | layout, design, templates |
| `reg_group_c` + both `get_offset_of_*` | M1 | addressing, templates |
| 1-D arrays | M1 | addressing |
| N-D flattening + comment | M2 | addressing |
| Gap/reserved synthesis, `--pad-tail`, `--rsvd-prefix` | M2 | layout |
| Access derivation | M2 | access |
| Signature dedup + `__vN` | M2 | signature, design |
| Identifier mangling | M2 | identifiers |
| `--type-style=hier` | M2 | design |
| `PSS-E001..E004` hard-unsupported errors (§0.2) | M3 | validate |
| Warning/info checks, `--strict` | M3 | validate |
| `--emit-top`, `--base-address` | M4 | templates, addressing |
| `--emit-enums={const,off}` | M4 | design, templates |
| `--emit-reset-consts` (instance-scoped `static const`, §4.9) | M4 | design, signature, templates |
| `--emit-index-helpers` | M4 | addressing, templates |
| `--no-pure` | M4 | templates |
| `--sidecar` | M4 | sidecar |
| `--emit-enums=typed` | M6 | templates |
| `--offset-mode=path` | M6 | addressing, templates |

---

## 6. Track T — Test infrastructure

### 6.1 `tests/util/` (built in M0, before any feature test)

* `compile_rdl(*sources, top=None) -> RootNode` — thin `RDLCompiler` wrapper that
  captures messages into a list instead of printing, so tests can assert on diagnostics.
* `export_str(root, **kwargs) -> str` — run `PSSExporter` to a temp file, return text.
  Every test uses this; no test writes into the repo tree.
* `run_pssparser(path_or_text) -> ParseResult` — invokes `pssparser --json`, returns
  `(exit_code, diagnostics)`. Skips (not fails) with a clear reason if the binary is
  absent, so the suite is usable outside this workspace.
* `assert_golden(text, name)` — compares against `tests/golden/expect/<name>.pss`;
  regenerates when `PEAKRDL_PSS_UPDATE_GOLDEN=1`. **The update mechanism is mandatory** —
  without it, golden tests get "fixed" by hand-editing expectations, which defeats them.
* `MessageCapture` — asserts findings by ID, not by message text.

### 6.2 Corpus (`tests/golden/rdl/`)

| File | Exercises |
|---|---|
| `basic.rdl` | copied from `packages/peakrdl-uvm/test/testcases/basic.rdl` — the dynamic-override case that breaks name-keyed dedup |
| `scalar_regs.rdl` | one reg, one field, minimal output (readability baseline) |
| `gaps.rdl` | leading/interior/trailing gaps, `--pad-tail` on and off |
| `arrays_1d.rdl`, `arrays_nd.rdl` | strides, sparse strides, `[4][3][2]` |
| `access_matrix.rdl` | every `sw`/`onread`/`onwrite` combination |
| `widths.rdl` | legal 8/16/32/64 (golden) |
| `err_width_128.rdl` | `regwidth=128` → `PSS-E001` |
| `err_accesswidth.rdl` | `accesswidth < regwidth` → `PSS-E002` |
| `keywords.rdl` | RDL names colliding with PSS keywords, `\reg` escapes |
| `encode.rdl` | `encode`d fields, shared and inline enums |
| `msb0.rdl` | `is_msb0_order` |
| `err_mem.rdl` | `mem` + virtual registers → `PSS-E004` |
| `err_bridge.rdl` | `bridge=true` addrmap → `PSS-E003` |
| `err_multi.rdl` | three distinct problems in one design → all three reported in one run |
| `reset.rdl` | scalar/array/absent/reference-valued resets, plus a field named `r1_reset` (const-name collision) |
| `params.rdl` | parameterized addrmap instantiated twice (design §11.11) |
| `alias.rdl` | `alias` registers, overlapping offsets |
| `endian.rdl` | mixed `bigendian`/`littleendian` |
| `deep.rdl` | 4-level hierarchy, ~500 regs — perf + `--offset-mode=path` |
| `wide.rdl` | 4096 registers — the §11.9 benchmark input (marked `slow`) |

Each RDL file carries a header comment naming the checks and features it targets, so the
corpus stays legible as it grows.

The `err_*.rdl` cases have **no golden `.pss`** — their expectation is
`(nonzero exit, exactly these finding IDs, no output file written)`. A test asserts the
exporter leaves no partial file behind when it aborts.

---

## 7. Track T — Test suites

### 7.1 Unit tests (`tests/unit/`)

`test_identifiers.py`, `test_access.py`, `test_layout.py`, `test_addressing.py`,
`test_signature.py`, `test_validate.py`, `test_sidecar.py`. Pure-function tests, no Jinja,
no filesystem. Target: **90% line coverage on these six modules** (they hold all the
logic that can be silently wrong).

### 7.2 Signature-fidelity test (the important one)

For every RDL in the corpus, and for a set of ~30 targeted mutations (change one field's
`sw`, one `reset`, one offset, one array dim, one name):

* assert `signature(before) != signature(after)` whenever the rendered text differs, and
* assert `signature(before) == signature(after)` whenever it does not.

Rendered text is the oracle. This mechanizes the §4.3 invariant and is what prevents the
`peakrdl-uvm` defect the design doc calls out from being reintroduced in a subtler form.

### 7.3 Golden-file tests (`tests/golden/`)

Per corpus file × relevant option sets, byte-for-byte. Roughly 35 goldens. Each golden
test also runs the §7.5 parser gate on its own output, so a golden can never be "correct
but unparseable".

### 7.4 Keyword-table test

Assert `PSS_KEYWORDS` equals the reserved words extractable from the pssparser grammar
(skip if the grammar file is unavailable). Prevents a stale table from letting an illegal
identifier through.

### 7.5 `pssparser` gate

Two suites, kept separate exactly as the design doc requires:

* `test_parse_package.py` — every generated `.pss` must exit 0. **Hard CI gate.**
* `test_parse_consumer.py` — package + hand-written consumer snippets exercising
  `write_val`, `write_field`, `read`, struct literals. Expected failures for stdlib gaps
  are `xfail(strict=False)` with a comment naming the parser-doc item that will fix them.
  When a Tier lands upstream, the xfail flips to a pass and `strict=True` locks it in.

With symbolic names removed, **the entire default emission — including the
`--emit-reset-consts` form of §4.9, verified while writing this plan — is inside the
subset `pssparser` validates today.** Suite 1 therefore covers 100% of v1 output; there is
no longer any shipped feature that CI cannot check. That was the design doc's main worry
(§12.3 "no local regression test") and the review eliminates it rather than mitigating it.
The only remaining xfails are consumer-side stdlib gaps (parser doc Tier 3), which are not
our artifact.

### 7.6 CLI/API parity test

Introspect the argparse parser built by `Exporter.add_exporter_arguments`, assert every
dest maps to a keyword parameter of `PSSExporter.export`, and vice versa (modulo an
explicit allowlist for `output`). Cheap; catches the most common drift in exporter plugins.

### 7.7 Property tests (`tests/property/`)

* **Offset oracle** — for every leaf register in every corpus design, interpret the
  emitted `get_offset_of_*` bodies (a small Python evaluator over the IR, ~50 lines) down
  the instance path and assert the accumulated sum equals `node.absolute_address -
  top.absolute_address`. This is the single most valuable test in the plan: array/stride
  bugs are the most likely source of silent wrongness, and this catches all of them.
* **Layout oracle** — independently reconstruct each packed struct's bit assignment from
  the emitted rows under `packed_s` LITTLE_ENDIAN rules and assert each non-reserved row
  lands at its RDL `[msb:lsb]`; assert rows are contiguous and cover `[0, last_msb]`.
* **Determinism** — export twice, assert identical; export under
  `PYTHONHASHSEED` ∈ {0, 1, 42}, assert identical; export from a re-compiled model, assert
  identical.
* **Idempotent naming** — assert no two emitted types share a name, no emitted identifier
  is a PSS keyword (regex + keyword table over the output), and no `<inst>_reset` const
  collides with a sibling instance name.
* **Reset-const fidelity** — for every register with a literal reset, assert the emitted
  `static const` value equals the reset reconstructed field-by-field from the RDL model,
  and that registers with absent or reference-valued resets emit no const at all.

### 7.8 Integration tests (`tests/integration/`)

* Plugin discovery: `peakrdl pss --help` exits 0 and mentions each flag.
* End-to-end CLI: `peakrdl pss basic.rdl -o out.pss --emit-top` produces both files.
* `--strict` turns a corpus warning into a nonzero exit.
* Each `err_*.rdl` corpus case fails with its expected `PSS-Exxx` **without** `--strict`,
  writes no output file, and reports every problem in the design in a single run.
* Standalone API use without `peakrdl` importable (simulate via `sys.modules` blocking).
* User template override: a `user_template_dir` with `{% extends "base:reg_group.pss" %}`
  changes the output.

### 7.9 UVM cross-check (design §12.9)

Generate both the UVM model and the PSS package from each corpus design; parse the UVM
output's `add_reg(..., offset)` calls and assert the absolute addresses agree with the PSS
offset oracle. Marked `uvm`, skipped when `peakrdl-uvm` is unavailable. Cheap, and it
validates our address math against an independent implementation.

### 7.10 Benchmark (`tests/property/test_perf.py`, `slow`)

Export `wide.rdl` (4096 regs) and record wall-clock + output size; assert a generous
ceiling (e.g. < 30 s) so a pathological regression is caught. Records the number for the
design doc's §11.9 open question rather than deciding it.

### 7.11 CI

GitHub Actions matrix: Python 3.9–3.13 × {min, latest} `systemrdl-compiler`.
Jobs: `lint` (ruff + mypy strict on `src/`), `test` (pytest + coverage gate 85% overall),
`parser-gate` (§7.5 suite 1, must pass), `docs` (`sphinx-build -W`).

---

## 8. Test-writing order

Tests are written **with** their feature, not after, with one exception: §7.1's
`test_layout.py` and §7.7's layout oracle are written *before* `layout.py`, because the
gap/msb0 rules are the part of the spec most likely to be misread, and a failing test
written from the design doc is the cheapest way to find that out.

---

## 9. Track D — Sphinx documentation plan

Sphinx project at `docs/`, matching the PeakRDL ecosystem's conventions (verified against
`packages/peakrdl/docs`): `sphinx_book_theme`, `sphinx.ext.autodoc`,
`sphinx.ext.napoleon`, `sphinxemoji`, `pygments-systemrdl` for RDL highlighting.

`docs/design/*.md` stays where it is — design records, not user docs, excluded from the
Sphinx build via `exclude_patterns`.

### 9.1 Page structure

```
docs/
    conf.py, Makefile, requirements.txt, index.rst
    installation.rst
    quickstart.rst
    cli.rst                 # every flag, with the §4.7 table + examples
    api.rst                 # autodoc for PSSExporter
    mapping/
        index.rst
        groups.rst          # addrmap/regfile -> reg_group_c, offsets
        registers.rst       # reg -> packed_s + reg_c, SZ, access derivation
        fields.rst          # gaps, reserved, msb0, encode
        arrays.rst          # N-D flattening, index helpers, the bar[2][1] -> bar[7] rule
        naming.rst          # type naming, signatures/__vN, identifier mangling
        limitations.rst     # what PSS cannot represent, and what we do instead
    diagnostics.rst         # every PSS-Exxx / PSS-Wxxx / PSS-Ixxx by ID: cause, fix, strict behavior
    unsupported.rst         # the four hard-unsupported constructs (§0.2): what, why, what to do
    using-the-output.rst    # consumer-side: set_handle, read/write, write_field, wrapper
    templates.rst           # user_template_dir override guide
    compatibility.rst       # targets PSS 3.1; pssparser stdlib gaps; what CI can/cannot check
    contributing.rst        # dev setup via ivpm, running tests, updating goldens
    changelog.rst
```

### 9.2 Content rules

* **Every generated construct in `mapping/` shows real generator output**, not
  hand-written PSS. Achieved with a small `docs/_ext/rdl_example.py` directive (or, if that
  proves fiddly, a `make docs-examples` step) that compiles an inline RDL snippet and
  inlines the emitted `.pss`. This keeps docs from drifting, which is otherwise guaranteed.
  Snippets live in `docs/examples/*.rdl` and are also fed to the golden suite, so a doc
  example that stops parsing fails CI.
* `diagnostics.rst` is generated from the `Finding` ID table in `validate.py` (one
  autogenerated section per ID) so a new check cannot ship undocumented. A test asserts
  every ID defined in code appears in the docs source.
* `limitations.rst` covers what PSS *can* express but only lossily — side-effect access
  policies, `alias` relationships, N-D array ergonomics — and points at the sidecar for
  recovering the dropped semantics. Each entry links to its design-doc §11 item.
* `unsupported.rst` is separate from `limitations.rst` on purpose. The four review-decided
  `Unsupported` constructs (`regwidth>64`, `accesswidth<regwidth`, `bridge`, `mem`) are not
  tradeoffs, they are refusals: the page states the construct, the error ID, why PSS cannot
  represent it, and the practical workaround (e.g. restructure the RDL, or export a subtree
  with `--top`). Users will hit these as a *failed export*, so the page must be findable by
  error ID from the message text itself.
* `compatibility.rst`: the output targets PSS 3.1. The page carries the parser-doc tier
  table and states which optional modes are waiting on `pssparser`
  (`--emit-enums=typed`, `--offset-mode=path`) — and that everything shipped by default is
  parser-validated in CI.

### 9.3 Doc milestones

| M | Docs delivered |
|---|---|
| M0 | project builds; `index`, `installation` stubs |
| M1 | `quickstart`, `mapping/registers`, `mapping/groups` |
| M2 | `mapping/{fields,arrays,naming}` |
| M3 | `diagnostics` (generated), `unsupported`, `mapping/limitations` |
| M4 | `cli` complete, `using-the-output`, `templates` |
| M5 | `contributing` |
| M6 | `compatibility` updated as parser tiers land |
| M7 | `api`, `changelog`, full `-W` clean build, README rewritten to point at docs |

---

## 10. Documentation of the design record

`docs/design/systemrdl-to-pss.md` and `pssparser-3.1-requirements.md` are kept as-is and
gain a short "Status" update when decisions in §12 are resolved — the plan does not
rewrite them. A new `docs/design/decisions.md` (ADR-lite, one entry per §12 row) records
what was chosen and why, since those choices will be re-litigated later.

---

## 11. Cross-repo dependency: `pssparser`

With mnemonics removed, **`peakrdl-pss` no longer needs parser Tier 2 at all**, and nothing
on the 1.0 path depends on the parser changing. Remaining relationship:

| Parser item | Gates | Priority for us |
|---|---|---|
| Tier 1.1 — `enum` base type (the one grammar change) | `--emit-enums=typed` (M6) | Low. `--emit-enums=const` is the default and needs nothing. |
| Tier 1.3 — `node_s` | `--offset-mode=path` (M6) | Low. `instance` mode is the default. Present in the parser's working tree, not in a release. |
| Tier 3 — `write_field`/`write_masked`/struct access | §7.5 consumer suite only | **Highest for us** — the two consumer xfails ride on it. Rides on Tier 1.2. |
| Tier 1.2 — `reg_sized_c`/`reg_base_c` chain | the untyped consumer accessors | Present in the parser's working tree, not in a release; landing it clears both xfails. |
| **Tier 2 — mnemonics, `use_symbolic_reg_names`, `format()`** | **Nothing** | **Dropped as a `peakrdl-pss` requirement.** Worth telling the parser project: the consumer that motivated Tier 2 no longer needs it, so it can be reprioritized on its own merits. |

Recommended: land Tier 1.2 + Tier 3 (they are one change — `reg_sized_c` and its
members are already written, just uncommitted), which clears both consumer xfails.
Treat Tier 1.1/1.3 as opportunistic; both gate optional modes with complete
defaults. De-prioritize Tier 2. Nothing here blocks on any of it: the *package*
gate is green against committed parser HEAD today.

The parser doc (`docs/design/pssparser-3.1-requirements.md`) should get a short status note
recording that its Tier 2 consumer went away — otherwise that work gets done on a stale
justification.

---

## 12. Decisions — resolved

All six design-doc §13 questions are answered by the `MSB:` review. Recorded here (and, per
§10, in `docs/design/decisions.md`) so they are not re-litigated:

| # | Question | Resolution | Implementation |
|---|---|---|---|
| 1 | `regwidth > 64` (§11.1) | **Unsupported** | `PSS-E001`, unconditional error |
| 2 | `accesswidth < regwidth` (§11.2) | **Unsupported** | `PSS-E002`, unconditional error |
| 3 | Multi-address-space (§11.5) | **Unsupported** | `PSS-E003` on `bridge=true`; no `--split-at`; single tree only |
| 4 | `mem` in v1 (§11.4) | **Unsupported** | `PSS-E004`; `--mem-mode` deleted |
| 5 | §12.1 enums / §12.2 reset / §12.3 mnemonics | enums `const` by default (`typed` in M6); **reset consts opt-in, instance-scoped `static const` (§4.9)**; **mnemonics dropped entirely** | §4.9, §5 |
| 6 | PSS version floor (§13.6) | **Target PSS 3.1 unconditionally, no symbolic names** | `--pss-level` deleted; optional modes gated on parser availability, not language level |

Two knock-on effects worth stating plainly, since they change the shape of the project
rather than just its flag list:

1. **v1 is a strictly smaller, fully-testable artifact.** Every construct it emits is inside
   the subset `pssparser` validates today (§7.5), including the reset consts — verified in CI
   against committed parser HEAD, not against a local working tree. The design doc's one
   untestable feature is gone.
2. **The generator now refuses rather than degrades.** Four constructs that the design doc
   would have emitted with warnings are now hard errors, which shifts effort from "emit
   something plausible" to "detect precisely and explain well." That makes `validate.py`
   and `unsupported.rst` more load-bearing than the design doc implied, and it is why the
   corpus grows a dedicated `err_*.rdl` family (§6.2).

---

## 13. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Hard errors make real designs un-exportable (§0.2) — a single `mem` blocks the whole map | Users bounce off the tool on first contact | `unsupported.rst` findable by error ID; all problems reported in one run; per-construct severity is a one-line change if the strict reading proves too harsh in practice |
| Golden churn makes reviews unreadable | Real bugs hide in a 3000-line diff | Small focused corpus files; goldens regenerated only via the env-var path; formatting frozen early in M1 |
| Signature scheme too coarse or too fine | Wrong reuse (silent bug) or `__v2` noise | §7.2 mechanizes the invariant against rendered text |
| msb0 handling misread | Silently wrong bit positions | Tests written before implementation (§8); dedicated golden + oracle case |
| ~~`peakrdl` not installed in the workspace venv~~ | resolved in M0 | Installed editable from `packages/peakrdl/peakrdl-cli`; IVPM does not pick it up because the Python package sits in a subdirectory of that repo |
| N-D flattening ergonomics rejected by users (§11.3) | Rework of array emission | Confirm with the intended users during M2, when `--emit-index-helpers` is cheap to reshape |
| Reset-const naming collides in ways the mangler mishandles | Uncompilable output | `reset.rdl` corpus case includes a field literally named `r1_reset`; §7.7 naming property test covers it |

---

## 14. Suggested first three work items

1. **M0 skeleton** — `pyproject.toml`, `__about__.py`, empty-package export, entry point,
   `tests/util/`, Sphinx shell; install `peakrdl`/`pytest`/`sphinx`/`jinja2` into the venv.
2. **Corpus + oracles** — `tests/golden/rdl/*.rdl` and the offset/layout oracles, written
   against the design doc alone. They will fail; that is the point.
3. **M1 walking skeleton** — scanner + three templates until `basic.rdl` passes the parser
   gate and its offset oracle.

Suggested fourth, out of band: send the parser project the §11 note that Tier 2 lost its
consumer.

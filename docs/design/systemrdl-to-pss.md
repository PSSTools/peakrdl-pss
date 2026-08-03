# PeakRDL-PSS: SystemRDL → PSS Register Package Converter

**Status:** design draft, for review
**Date:** 2026-08-02
**Reference inputs:** `packages/peakrdl-uvm` (structural template), PSS 3.1 Draft 19 §21.13 (`packed_s`, `sizeof_s`, address handles), §21.14 (Registers), PeakRDL exporter-plugin & `rdl_gotchas` docs.

---

## 1. Purpose and scope

`peakrdl-pss` is a PeakRDL exporter plugin that consumes a compiled SystemRDL model and
emits a **PSS register package**: a `.pss` source file containing

* a packed struct (`packed_s<>`) per register type, describing its fields,
* a `pure component ... : reg_c<...>` per register type,
* a `pure component ... : reg_group_c` per `addrmap`/`regfile`, implementing the
  `get_offset_of_instance()` / `get_offset_of_instance_array()` offset functions,
* optionally, mnemonic (`get_mnemonic_of_*`) implementations for PSS 3.1 symbolic
  register access, and a ready-to-use top wrapper component that binds the top group to
  an address region via `set_handle()`.

The output is *declarative register-model-only*. Generating test intent (actions,
activities, flows) is explicitly **out of scope** for v1, though §12 notes where it could
be layered on.

Non-goals for v1: importing PSS, round-tripping, generating C/SV target code (that is
the PSS tool's job).

---

## 2. Why the UVM exporter is the right structural template — and where it stops being one

`peakrdl-uvm` is a good architectural model and a poor semantic model.

**Reuse the architecture:**

| peakrdl-uvm mechanism | Reuse verdict |
|---|---|
| `ExporterSubcommandPlugin` in `__peakrdl__.py` + `peakrdl.exporters` entry point | Reuse as-is |
| Jinja2 `ChoiceLoader` with `user_template_dir` + `base:`/`user:` prefixes | Reuse as-is |
| `RDLWalker` pre-export listener collecting a `bus_width_db` | Reuse the *pattern*, collect different facts (§7.2) |
| `_get_class_name()` via `get_global_type_name("__")` with `namespace_db` de-dup | Reuse, but the de-dup key must change — see §5.2 |
| Emit definitions in `descendants(in_post_order=True)` then the top node | Reuse as-is |
| `_get_array_address_offset_expr()` N-D offset expression | Reuse the arithmetic, retarget the syntax (§4.4) |

**Where the analogy breaks:**

| Aspect | UVM | PSS |
|---|---|---|
| Model construction | Runtime: `new()` + `build()` + `add_reg(offset)` | Static: offsets returned by `pure` functions; components are elaborated |
| Field description | `uvm_reg_field.configure(width, lsb, access, volatile, reset, ...)` | Positional fields in a `packed_s<>` struct — **gaps must be materialized as reserved fields** |
| Access policy | 25 UVM access strings incl. side effects (`W1C`, `RC`, `W1SRC`…) | 3 values: `READWRITE`, `READONLY`, `WRITEONLY` — **side-effect semantics are not representable** |
| Reset value | First-class (`configure(..., reset, has_reset, ...)`) | **No concept.** Must be synthesized (§12.2) |
| Memories | `uvm_mem` + `uvm_vreg` | No analog. Address-space regions only (§11.4) |
| Multiple address maps | Multiple `uvm_reg_map`s in one block | Only the *top-level* group may `set_handle()` → one group per address space (§11.5) |
| Type reuse | Class type name from lexical scope | Same idea works, and works *better*: offsets live in the parent group, so a register type is genuinely offset-independent |

That last row is the key insight: because PSS puts offsets in the *parent* group's offset
functions rather than in the child, PSS register types are more reusable than UVM classes.
The lexical-scope type-naming strategy from `peakrdl-uvm` therefore carries over cleanly.

---

## 3. Target PSS constructs (3.1 Draft 19)

```pss
enum reg_access {READWRITE, READONLY, WRITEONLY};

pure component reg_c <type R, reg_access ACC = READWRITE,
                      int SZ = (8*sizeof_s<R>::nbytes)> : reg_sized_c<SZ> {
    target function R    read();
    target function void write(R r);
    target function void write_masked(R mask, R val);
};

pure component reg_group_c {
    pure  function bit[64] get_offset_of_instance(string name);
    pure  function bit[64] get_offset_of_instance_array(string name, int index);
    pure  function bit[64] get_offset_of_path(list<node_s> path);
    solve function void    set_handle(addr_handle_t addr);
    function addr_handle_t get_handle();
    // PSS 3.1 §21.14.6:
    solve pure function string get_mnemonic_of_instance(string name);
    solve pure function string get_mnemonic_of_instance_array(string name, int index);
    solve pure function string get_mnemonic_of_path(list<node_s> path);
    solve function void        set_mnemonic(string prefix);
};
```

Constraints the generator must respect:

* It is an **error to implement all three** `get_offset_of_*` functions in one group.
  We implement exactly `get_offset_of_instance` + `get_offset_of_instance_array`
  (same rule applies to the mnemonic trio).
* `packed_s` field ordering is C-like: **first-declared field occupies the low bits**
  (LITTLE_ENDIAN) or high bits (BIG_ENDIAN). Gaps are not implicit.
* `SZ` must be ≥ `sizeof_s<R>::nbits`; trailing bits are reserved and undefined.
* Register read/write lowers to `read8/16/32/64` selected by `SZ` (§21.14.5).
* `set_handle()` / `set_mnemonic()` / `use_symbolic_reg_names()` are legal only in
  `exec init_up`/`init_down`, and only on the top-level group.

---

## 4. Mapping specification

### 4.1 `addrmap` / `regfile` → `pure component ... : reg_group_c`

```pss
pure component <TypeName>_c : reg_group_c {
    <child_type>_c  <inst>;          // scalar child
    <child_type>_c  <inst>[N];       // array child (flattened, §4.4)

    pure function bit[64] get_offset_of_instance(string name) {
        match (name) {
            ["r1"]: return 0x0;
            ["sub"]: return 0x20;
            default: return -1;
        }
    }
    pure function bit[64] get_offset_of_instance_array(string name, int index) {
        match (name) {
            ["r2"]: return 0x10 + index*0x4;
            default: return -1;
        }
    }
}
```

* Offsets are `Node.raw_address_offset` — i.e. relative to the parent group, matching
  PSS's "offset relative to the notional base address of the group" semantics.
* If a group has no scalar (resp. array) children, still emit the function with only
  `default: return -1;` — PSS requires the pair to be implemented together.
* `addrmap` and `regfile` map identically; the distinction is not observable in PSS.

### 4.2 `reg` → `packed_s` struct + `reg_c` component

```pss
struct <TypeName>_s : packed_s<LITTLE_ENDIAN> {
    bit[16] f1;          // [15:0]
    bit     f2;          // [16]
    bit     f3;          // [17]
    bit[10] rsvd_18;     // [27:18]  (generated)
    bit[2]  f5;          // [29:28]
    bit[2]  f4;          // [31:30]
}
pure component <TypeName>_c : reg_c<<TypeName>_s, READWRITE, 32> {}
```

Rules:

1. Fields are emitted in **ascending `lsb` order**, which is what `packed_s`
   positional packing requires. `RegNode.fields()` already yields low-to-high.
2. **Every gap becomes an explicit reserved field** named `rsvd_<lsb>` (configurable
   prefix). This includes a trailing gap up to `sizeof_s` byte rounding — but see rule 4.
3. `SZ` is always emitted **explicitly** as `regwidth`, never left to default. This
   decouples the struct's byte-rounded size from the declared register width and makes
   the generated code robust to `sizeof_s` rounding.
4. Trailing bits between the last field's msb and `regwidth` are left to PSS's
   "SZ > sizeof_s<R>" reserved-tail rule (§21.14.1) rather than padded, *unless*
   `--pad-tail` is given. Rationale: the tail is unreadable/unwritable either way, and
   omitting it keeps the struct honest about which bits are real.
5. `encode`d fields become PSS enums when `--emit-enums=typed`; the default
   `--emit-enums=const` emits a `bit[N]` field plus `const` encoding values. See §12.1 —
   the base-type enum syntax the spec requires for packed-struct members does not parse
   in `pssparser` today (§10.2).
6. `is_msb0_order` registers: emit fields in the bit-reversed order that reproduces the
   correct physical layout, and emit a comment; warn once per register (§11.8).

**Access derivation** (`ACC`), from the union of field `sw` policies:

| Field `sw` set | `ACC` |
|---|---|
| all `r` (or `na` only) | `READONLY` |
| all `w` / `w1` | `WRITEONLY` |
| anything else (incl. `rw`, `rw1`, mixed) | `READWRITE` |

Side-effect properties (`onread`, `onwrite`, `singlepulse`, `swmod`, `swacc`, counters,
interrupts) have **no PSS representation**. They are preserved as generated comments and,
optionally, as a machine-readable sidecar (§12.5).

### 4.3 `field` → packed struct member

`bit[width] <name>;` with a trailing comment `// [msb:lsb] sw=<..> hw=<..> reset=<..>`.
Field names must survive to PSS source verbatim where possible, because
`write_field("name")` / `write_fields({...})` are string-keyed against these very names.
Name mangling (§5.3) is therefore a *documented, deterministic* transform, and the
generator emits a comment recording the original RDL name whenever mangling occurs.

### 4.4 Arrays

PSS component arrays are **one-dimensional**. SystemRDL permits N-D. The generator
flattens row-major:

```
idx = i0*D1*D2 + i1*D2 + i2
offset = raw_address_offset + i0*(stride*D1*D2) + i1*(stride*D2) + i2*stride
```

which, expressed against the flattened index alone, is simply
`raw_address_offset + idx*stride` **only when the array is dense in the same order** —
which it is, since SystemRDL's stride applies uniformly per innermost element and outer
dimensions multiply. So the emitted body is:

```pss
["bar"]: return 0x1000 + index*0x100;   // bar[4][3] flattened to bar[12]
```

The exporter emits a comment giving the original dimensions and the index formula, and
optionally (`--emit-index-helpers`) a `static function int bar_idx(int i0, int i1)`
helper so model code does not open-code the arithmetic. Sparse arrays (stride >
element size) fall out for free.

### 4.5 `mem` and virtual registers

No PSS analog. v1 behavior:

* Default: **warn and skip**, mirroring how `peakrdl-uvm` warns about bridges.
* `--mem-mode=region`: emit a commented-out / helper `transparent_addr_region_s<>`
  declaration sized `mementries * memwidth/8` plus a `get_offset_of_instance()` entry, so
  the memory's base is reachable via `get_handle()` + `make_handle_from_handle()`.
* Virtual registers inside a `mem` are not emitted (see §11.4).

### 4.6 Top-level wrapper (`--emit-top`)

```pss
component <top>_regs_wrapper_c {
    <top>_c                     regs;
    transparent_addr_space_c<>  sys_mem;

    exec init_up {
        transparent_addr_region_s<> mmio_region;
        addr_handle_t h;
        mmio_region.size = 0x<computed size>;
        mmio_region.addr = 0x<--base-address>;
        h = sys_mem.add_nonallocatable_region(mmio_region);
        regs.set_handle(h);
        // --symbolic-names:
        // regs.set_mnemonic("");
        // use_symbolic_reg_names(regs, true);
    }
}
```

Region size = top node's `size` property from the compiler. This wrapper is generated
into a separate `_top.pss` file (or omitted) so the register package stays a pure,
environment-agnostic artifact.

---

## 5. Naming, namespacing, and type reuse

### 5.1 Type naming

Same two strategies as `peakrdl-uvm`, selected by `--type-style`:

* `lexical` (default): `node.get_global_type_name("__")`, falling back to
  `xtern__<relative hierarchical path>` when the type is anonymous/unresolvable.
* `hier`: `node.get_rel_path(top.parent, hier_separator="__", array_suffix="")`.

Suffixes: `_s` for the register-value struct, `_c` for `reg_c`/`reg_group_c` components,
`_e` for encode enums. All types land in one PSS package, so the flat namespace must be
collision-free — the generator keeps a `namespace_db` and hard-errors (not silently
renames) on a collision it cannot attribute to genuine type identity.

### 5.2 De-duplication must key on *resolved content*, not the type name

This is a real defect worth not inheriting. `peakrdl-uvm`'s `_class_needs_definition()`
keys purely on the lexical type name. But SystemRDL dynamic property assignments mutate
instances after instantiation:

```systemrdl
reg_t r1, r2, r3;
r3.f1->sw   = w;      // r3 no longer matches reg_t
r3.f1->reset = 200;
```

`r1`, `r2`, `r3` all report global type name `reg_t`, so a name-keyed cache emits one
class and silently gives `r3` the wrong access policy. (`basic.rdl` in the UVM test suite
contains exactly this construct.)

**Design:** compute a *structural signature* per node — an ordered digest of everything
the generator actually emits (field names, widths, lsbs, derived `sw`, reset values,
`regwidth`, encode enum identity; for groups: child inst names, child signatures,
offsets, strides). Cache key = `(type_name, signature)`. On a name hit with a signature
miss, emit a distinct type named `<name>__v2`, `__v3`, … and record the reason in a
comment. Deterministic, order-stable, and correct.

### 5.3 Identifier mangling

RDL identifiers can collide with PSS keywords (`component`, `action`, `activity`, `pool`,
`state`, `stream`, `buffer`, `resource`, `pure`, `target`, `solve`, `bit`, `int`, `bool`,
`struct`, `enum`, `import`, `package`, `ref`, `rand`, `constraint`, `exec`, `body`,
`share`, `lock`, `symbol`, `type`, …). Mangling rule: append `_`; if that collides, append
`_1`, `_2`. Escaped RDL identifiers (`\reg`) drop the backslash first — PSS §21.14.1
note 5 says the leading backslash is not part of the name for `write_field()` purposes,
so our struct field name must match that convention. Every mangled name gets a comment
carrying the original.

---

## 6. Worked example

Input (`packages/peakrdl-uvm/test/testcases/basic.rdl`, abridged):

```systemrdl
addrmap basic {
    regfile {
        reg reg_t {
            field {sw=rw; hw=r;} f1[15:0] = 1234;
            f2_t f2[16:16] = 0;  f2_t f3[17:17] = 0;
            field {sw=rw; hw=r;} f4[31:30] = 0;
            field {sw=rw; hw=r;} f5[29:28] = 0;
        };
        reg_t r1 @ 0x0;  reg_t r2 @ 0x4;  reg_t r3 @ 0x8;
        r3.f1->sw = w;   r3.f1->reset = 200;
        reg { field {sw=rw; hw=r;} f; } r4 @ 0xc;
    } foo @ 0x0;
    regfile bar_t { reg {field {sw=rw;hw=r;} f[15:0]=1234;} r1[4] @ 0x0 += 4; };
    bar_t bar[4][3] @ 0x1000 += 0x100;
    bar_t bar2 @ 0x8000;
}
```

Output (`basic_reg_pkg.pss`, abridged):

```pss
package basic_reg_pkg {
    import addr_reg_pkg::*;
    import std_pkg::*;

    // reg - basic::foo::reg_t
    struct basic__foo__reg_t_s : packed_s<LITTLE_ENDIAN> {
        bit[16] f1;        // [15:0]  sw=rw reset=0x4d2
        bit     f2;        // [16]    sw=rw reset=0x0
        bit     f3;        // [17]    sw=rw reset=0x0
        bit[10] rsvd_18;   // [27:18] reserved
        bit[2]  f5;        // [29:28] sw=rw reset=0x0
        bit[2]  f4;        // [31:30] sw=rw reset=0x0
    }
    pure component basic__foo__reg_t_c : reg_c<basic__foo__reg_t_s, READWRITE, 32> {}

    // reg - basic::foo::reg_t  (variant: dynamic property override on 'f1')
    struct basic__foo__reg_t_s__v2 : packed_s<LITTLE_ENDIAN> {
        bit[16] f1;        // [15:0]  sw=w  reset=0xc8   <-- overridden
        ...
    }
    pure component basic__foo__reg_t_c__v2 : reg_c<basic__foo__reg_t_s__v2, READWRITE, 32> {}

    pure component basic__foo_c : reg_group_c {
        basic__foo__reg_t_c      r1;
        basic__foo__reg_t_c      r2;
        basic__foo__reg_t_c__v2  r3;
        basic__foo__r4_c         r4;

        pure function bit[64] get_offset_of_instance(string name) {
            match (name) {
                ["r1"]: return 0x0;   ["r2"]: return 0x4;
                ["r3"]: return 0x8;   ["r4"]: return 0xc;
                default: return -1;
            }
        }
        pure function bit[64] get_offset_of_instance_array(string name, int index) {
            match (name) { default: return -1; }
        }
    }

    pure component basic__bar_t_c : reg_group_c {
        basic__bar_t__r1_c r1[4];
        pure function bit[64] get_offset_of_instance(string name) {
            match (name) { default: return -1; }
        }
        pure function bit[64] get_offset_of_instance_array(string name, int index) {
            match (name) { ["r1"]: return 0x0 + index*0x4; default: return -1; }
        }
    }

    pure component basic_c : reg_group_c {
        basic__foo_c  foo;
        basic__bar_t_c bar[12];   // flattened from bar[4][3], stride 0x100
        basic__bar_t_c bar2;
        // static function int bar_idx(int i0, int i1) { return i0*3 + i1; }

        pure function bit[64] get_offset_of_instance(string name) {
            match (name) {
                ["foo"]:  return 0x0;
                ["bar2"]: return 0x8000;
                default: return -1;
            }
        }
        pure function bit[64] get_offset_of_instance_array(string name, int index) {
            match (name) { ["bar"]: return 0x1000 + index*0x100; default: return -1; }
        }
    }
}
```

Note how `r3` correctly picks up a distinct type — the thing a name-keyed cache gets wrong.

---

## 7. Implementation architecture

### 7.1 Layout

```
src/peakrdl_pss/
    __about__.py
    __init__.py
    __peakrdl__.py          # ExporterSubcommandPlugin: subcommand "pss"
    exporter.py             # PSSExporter — public API, usable without PeakRDL CLI
    pre_export_listener.py  # RDLWalker listener: signatures, widths, validation
    signature.py            # structural digest (§5.2)
    identifiers.py          # PSS keyword table + mangling (§5.3)
    access.py               # sw/onread/onwrite → reg_access + lossiness report
    layout.py               # field ordering, gap synthesis, msb0 handling
    templates/
        top_pkg.pss   main.pss   reg_group.pss   reg.pss
        top_wrapper.pss   utils.pss
```

Public API mirrors `UVMExporter` so downstream users find it familiar:

```python
PSSExporter(user_template_dir=None, user_template_context={})
  .export(node, path, *, package_name=None, type_style="lexical",
          symbolic_names=False, emit_top=False, base_address=0,
          emit_enums=True, mem_mode="skip", pure_components=True)
```

### 7.2 Pre-export pass

One `RDLWalker` traversal, collecting:

* structural signatures (post-order, so children are signed before parents),
* per-group max `accesswidth`/`regwidth` (for validation, and for the region-size calc),
* the validation findings of §9, accumulated and reported through
  `node.env.msg.warning/error` so they integrate with PeakRDL's message plumbing,
* mangled-name maps, so templates never mangle inline.

### 7.3 Templates

Jinja2 with `StrictUndefined`, same `ChoiceLoader`/`PrefixLoader` scheme as
`peakrdl-uvm` (so `{% extends "base:reg.pss" %}` overrides work). Emission order:
`descendants(in_post_order=True)` then the top node — definition-before-use, which PSS
requires within a package.

Templates receive **precomputed** context (offsets as hex strings, field rows as tuples,
access as a string). No `get_property()` calls in templates — that keeps the RDL-gotcha
handling (reference-valued properties, msb0, etc.) in Python where it can be tested.

### 7.4 Plugin descriptor

```toml
[project.entry-points."peakrdl.exporters"]
pss = "peakrdl_pss.__peakrdl__:Exporter"
```

with `cfg_schema = {"user_template_dir": DirectoryPath(), "user_template_context": UserMapping(String())}`.

---

## 8. CLI surface

| Option | Default | Purpose |
|---|---|---|
| `-o, --output` | — | Output `.pss` file; package name derived from basename |
| `--package-name` | from filename | Override PSS package name |
| `--type-style {lexical,hier}` | `lexical` | Type naming / reuse strategy |
| `--symbolic-names` | off | Emit `get_mnemonic_of_*` (PSS 3.1 §21.14.6) |
| `--mnemonic-style {upper-path,cheader}` | `upper-path` | Mnemonic fragment format |
| `--emit-top` | off | Also emit the address-space wrapper component |
| `--base-address` | `0` | Base address used by the wrapper's region |
| `--mem-mode {skip,region}` | `skip` | `mem` handling |
| `--emit-enums {const,typed,off}` | `const` | `encode`d field handling (§12.1) |
| `--emit-reset-consts` | off | Emit per-register reset-value constants (§12.2) |
| `--emit-index-helpers` | off | Emit N-D → flat index helper functions |
| `--pad-tail` | off | Materialize the trailing reserved field |
| `--rsvd-prefix` | `rsvd_` | Reserved-field name prefix |
| `--no-pure` | off | Emit `component` instead of `pure component` |
| `--strict` | off | Promote the §9 warnings to errors |

---

## 9. Validation and diagnostics

The generator must be loud about what it cannot represent. Each item below is a
warning by default, an error under `--strict`:

1. `regwidth` > 64 → no `readN`/`writeN` primitive exists (§11.1).
2. `regwidth` not in {8,16,32,64} → the PSS access-size selection rule has no answer.
3. `accesswidth` < `regwidth` → PSS models one access per register (§11.2).
4. Field with `onread`/`onwrite`/`singlepulse`/counter/interrupt semantics → access
   policy is lossy.
5. `sw = rw1` / `w1` → mapped to `READWRITE`/`WRITEONLY`, write-once-ness lost.
6. `mem` encountered (per `--mem-mode`).
7. `addrmap` with `bridge = true` → same caveat `peakrdl-uvm` warns about.
8. `is_msb0_order` register.
9. Reset value that is a *reference* (signal/field) rather than a literal → dropped.
10. Mixed endianness within one top group (`bigendian`/`littleendian` differing between
    an addrmap and its descendants).
11. Identifier mangled (info-level, not warning).
12. Signature-variant type emitted (info-level) — tells the user why they got `__v2`.
13. Unaligned register offset — permitted, but flagged since many PSS backends assume
    natural alignment.

---

## 10. Test plan

* **Golden-file tests** (`tests/golden/`): reuse `basic.rdl` from the UVM test suite plus
  new cases for each §11 open issue. Compare generated `.pss` byte-for-byte.
* **Property-based offset check:** for a set of RDL designs, walk the unrolled model with
  PeakRDL's own address computation and assert that evaluating the generated offset
  functions (interpreted in Python from the same data model) reproduces
  `node.absolute_address` for every leaf register. This catches array/stride bugs, which
  are the most likely source of silent wrongness.
* **Layout check:** independently recompute each packed struct's bit layout from the
  emitted field list under the `packed_s` rules and assert every field lands at its RDL
  `[msb:lsb]`.
* **Syntax + link check (mandatory gate):** run `pssparser` over every generated file.
  See §10.1 — this is now a hard CI gate, not an optional nicety.
* **Determinism:** generate twice, assert identical output; generate with shuffled
  dict-iteration seeds, assert identical output.

### 10.1 `pssparser` as the validation gate — measured results

`pssparser` 3.0.0 is installed in `packages/python`. It does real work: it parses **and
links**, resolving types and identifiers against a built-in core library
(`src/stdlib/{addr_reg_pkg,packed_s,std_pkg}.pss`). A deliberately bogus probe produces
`unknown type 'totally_bogus_base_c'` / `unknown identifier ...` with exit 1, so a clean
run is meaningful signal. Usage:

```bash
pssparser out.pss            # exit 0 = parsed + linked clean
pssparser --json out.pss     # machine-readable diagnostics for pytest
```

Note: `"0 errors in 0 files"` is the success message — the file count is
*files-with-diagnostics*, not files parsed. Tests must assert on exit code / JSON summary,
not on that string.

I ran the §6 example output and a set of construct probes through it. **The entire v1
emission plan links clean.** Verified working:

| Construct | Result |
|---|---|
| `struct S : packed_s<LITTLE_ENDIAN>` / `packed_s<>` | ✅ |
| `pure component C : reg_c<S, READWRITE, 32> {}` | ✅ |
| `pure component G : reg_group_c` + both `get_offset_of_*` impls | ✅ |
| `match (name) { ["r1"]: return 0x0; default: return -1; }` in a function | ✅ |
| Component arrays `C r[4];` + `index*stride` offset arithmetic | ✅ |
| `pure function` **and** plain `function` for the offset impls (spec examples use plain) | ✅ both |
| `static function int idx(int i0, int i1)` inside a group (§4.4 helpers) | ✅ |
| `const bit[32] R_RESET = 0x4d2;` at package scope (§12.2) | ✅ |
| Enum-typed field in a packed struct (`enum mode_e {...}` form) | ✅ |
| `reg_c<bit[128], READWRITE, 128>` (§11.1) | ✅ parses — the parser will *not* catch this |
| Top wrapper: `transparent_addr_space_c<>`, `transparent_addr_region_s<>`, `add_nonallocatable_region()`, `set_handle()` in `exec init_up` | ✅ |
| Consumer side: `comp.grp.regs[2].write_val(0)`, `write({.f1=1, .f2=2})` | ✅ |
| **`import addr_reg_pkg::*;` is required** — `reg_c` is not visible without it | ⚠️ mandatory |

### 10.2 What `pssparser` cannot validate (its stdlib is a PSS-3.0 subset)

Its `addr_reg_pkg` declares `reg_c` with only `read/write/read_val/write_val/get_handle`
(third parameter named `SZ2`, and **not** derived from `reg_sized_c`), and `reg_group_c`
with only the two `get_offset_of_*` functions plus `set_handle`. Everything below is
absent, so it produces `unknown identifier` / `Failed to find elem` errors that are
*parser gaps, not model errors*:

| Missing | Blocks |
|---|---|
| `write_masked` / `write_val_masked` / `write_field` / `write_fields` | Consumer-side examples & §12.4 tests — **not** our emitted package |
| `reg_sized_c` / `reg_base_c` base components | Generic sized-register access (§3) |
| `node_s` type → `get_offset_of_path()` unusable (`unknown type 'node_s'`) | §12.7 alternate emission mode |
| `get_mnemonic_of_*`, `set_mnemonic`, `use_symbolic_reg_names` | **All of §12.3 symbolic names** |
| `std_pkg::format()` (`unknown identifier 'format'`) | Mnemonic fragments for array elements |
| `enum X : bit[4] {...}` — base-type syntax rejected by the grammar, though it *is* legal PSS (BNF: `enum enum_identifier [ : data_type ] { ... }`) | §12.1 typed enum fields |

Consequences for the design:

1. **The v1 core emission is fully inside the validated subset.** Good — the gate is real
   for the artifact that matters.
2. **§12.1 needs a fallback.** A packed-struct member must be an enum *with a base type*
   (§21.13.1), but that syntax doesn't parse here. Emit typed enums behind
   `--emit-enums=typed`, and default to `--emit-enums=const` (a `bit[N]` field plus
   `const` encoding values), which validates today and is portable to PSS 2.1 tools.
3. **§12.3 cannot be regression-tested locally at all.** It must be gated behind
   `--symbolic-names` (off by default), and its golden tests must be marked
   `xfail`/skip-on-`pssparser`. This raises the value of the decision in §13.6.
4. Tests must run the parser **twice** — once over the register package (must pass), once
   over package + a hand-written consumer snippet (expected to hit stdlib gaps until
   `pssparser`'s stdlib catches up). Keep these as separate suites so a stdlib gap never
   masks a real generator bug.
5. Filing the stdlib gaps upstream against `pssparser` is cheap and unblocks items 2–3.

---

## 11. Open issues

**11.1 Registers wider than 64 bits.**
PSS §21.14.5 selects the primitive by register size, and `addr_reg_pkg` provides only
`read8/16/32/64`. A 128-bit RDL register has no lowering. Options: (a) warn and emit
anyway, letting the PSS tool reject it; (b) auto-split into an array of 64-bit
`reg_c<bit[64]>` with a naming convention; (c) refuse. **Recommendation: (a) with a loud
warning in v1, (b) behind a flag later.** Needs a decision. Note that
`reg_c<bit[128], READWRITE, 128>` parses and links cleanly (§10.1) — the parser gives us
no safety net here, so our own §9 validation is the only guard.

**11.2 `accesswidth` < `regwidth`.**
A 64-bit register with `accesswidth=32` is physically two 32-bit accesses, and RDL
attaches ordering semantics to that. PSS's model is one access per register object. Do we
(a) ignore accesswidth, (b) split the register into two `reg_c<bit[32]>` siblings at
+0/+4, losing the single-value view? **Recommendation: (a) + warning**, since (b) breaks
`write_field()` across the split. Open.

**11.3 N-dimensional arrays are flattened.**
Model code written against the RDL will say `bar[2][1]`; the generated PSS requires
`bar[7]`. The index-helper functions mitigate but do not eliminate the ergonomic hit.
No alternative exists within PSS's 1-D component arrays. Worth confirming this is
acceptable to the intended users.

**11.4 Memories and virtual registers.**
`mem` with `mementries`/`memwidth` and register-typed contents (the `uvm_vreg` case) has
no PSS register-model analog. The honest mapping is an address-space region plus
`read_struct`/`write_struct` on `make_handle_from_handle(base, i*stride)`. That is a
*different kind of artifact* from a register package — it needs its own design pass, and
possibly its own generated component. Deferred; currently just a warning.

**11.5 Multiple address spaces / bridges / `external` addrmaps.**
PSS permits `set_handle()` only on a top-level group. A design where a sub-`addrmap`
lives in a different address space cannot be one PSS tree. Proposal: detect such
sub-addrmaps (via `bridge`, or a user-supplied `--split-at <path>` list), emit each as its
own top-level `reg_group_c`, and have the wrapper bind each to its own region. Not
designed in detail yet — this is the largest structural unknown.

**11.6 Side-effect access semantics are unrepresentable.**
`W1C`, `RC`, `RS`, `W1S`, write-once — all collapse to `READWRITE`. A PSS model that
wants to *clear an interrupt* has no way to express "write 1 to clear" beyond
`write_field(name, 1)`, which is correct by accident. §12.5 proposes a sidecar; the open
question is whether that is enough or whether generated helper functions are warranted.

**11.7 Reserved-field naming stability.**
`rsvd_<lsb>` is stable under field edits only if the gap's lsb doesn't move. Any scheme
has this property or worse. Alternative: `rsvd_<index>` (worse) or name-from-neighbors
(worse still). Flagging it because generated-file diffs will be reviewed by humans.

**11.8 msb0 registers.**
`RegNode.is_msb0_order` implies a bit-reversed field layout. Reversing the emission order
in a `packed_s` reproduces the physical bits, but `write_field("x", v)` then operates on
the reversed position — which is correct, but confusing to read. Needs a test case and a
documented example before we commit.

**11.9 Solve-time cost of large maps.**
A 4096-register map produces 4096-arm `match` statements and 4096 `pure component`
instances. PSS §21.14.1 explicitly recommends `pure` "to optimally handle large static
register components", which we do — but we should benchmark, and consider
`get_offset_of_path()` (one function, one traversal) as an alternative emission mode for
deep hierarchies. Currently unmeasured.

**11.10 `alias` registers.**
RDL `alias` and legal RO/WO offset overlap map fine onto PSS (two group entries may
return the same offset — explicitly blessed by §21.14.2 note 5). But the *aliased-ness*
is lost. Probably acceptable; noting it.

**11.11 Parameterized addrmaps.**
Two instances of the same parameterized `addrmap` type with different parameter values
share a global type name but differ structurally. §5.2's signature-based cache handles
this correctly — but produces `__v2` type names rather than something readable like
`fifo_c__DEPTH_8`. Encoding parameter values into the type name would be nicer; needs the
compiler's parameter introspection to be checked.

**11.12 Toolchain floor vs. spec floor.**
Measurement (§10.2) shows a concrete gap: the PSS 3.1 Draft 19 register model we design
against is meaningfully ahead of the PSS 3.0-era core library our local parser implements.
The generator's *core* output sits in the intersection and is safe. But three designed
features (§12.3 symbolic names, §12.7 path-based offsets, §12.1 typed enums) live only in
the newer half. Proposal: define an explicit `--pss-level {3.0,3.1}` knob that gates
these as a set, defaulting to `3.0`, rather than letting each feature drift its own
compatibility story. Needs agreement.

**11.13 Where does `sizeof_s` rounding bite?**
We always pass `SZ` explicitly, so the default-parameter rounding path is never taken.
Should be safe, but should be verified against a real PSS tool before we rely on it.

---

## 12. Overlooked opportunities

**12.1 Encode enums → PSS enums (high value, low cost — with a caveat).**
`encode`d fields carry a full enumeration. PSS packed structs allow "enumerated types that
have a base type" as members (§21.13.1). Emitting

```pss
enum basic__mode_e : bit[4] { IDLE = 0, RUN = 1, HALT = 2 }
```

and typing the field as `basic__mode_e` gives model authors type-safe, self-documenting,
*randomizable* register programming. The UVM exporter throws this information away
entirely.

**Caveat found while validating (§10.2):** `pssparser` rejects the `enum X : <type>`
base-type syntax, even though the PSS BNF allows it. A base-type-less enum *does* parse
and *does* work as a packed-struct member in `pssparser` — but the spec's packing rules
only bless enums that have a base type, so relying on that is relying on a parser
lenience. Hence `--emit-enums=const` (a `bit[N]` field plus `const` encoding values) is
the default: it is spec-clean, validates today, and works on PSS 2.1 tools.
`--emit-enums=typed` gets us the good version once the parser catches up.

**12.2 Reset values → constants and a `reset_s` literal.**
PSS has no reset concept, so the information is currently discarded — but it is trivially
useful. Emit per register:

```pss
const bit[32] basic__foo__reg_t_RESET = 0x000004d2;
```

and optionally a struct literal. Enables "restore defaults" sequences, post-reset checks,
and read-back comparisons in generated tests, none of which are expressible today.

MSB: What about a companion const in the group component? In other words reg_c<> reg1; const bit[32] reg1_reset = ...;?

**12.3 Symbolic register names (PSS 3.1 §21.14.6) — the standout opportunity.**
This is brand-new in 3.1 and is *tailor-made* for a generator. A hand-written PSS model
almost never bothers implementing `get_mnemonic_of_*`; a generator can do it perfectly and
for free, producing target code that references `DMA0_DMA_REG_A` instead of a raw address.
Even better: PeakRDL already ships a **C header exporter** (`peakrdl-cheader`) — we can
generate mnemonics that *exactly match* the symbols that exporter emits, so a PSS test and
the firmware's own header agree on register names by construction. That is a genuinely
differentiating capability and argues for `--mnemonic-style=cheader`.
MSB: Let's ignore mnemonics. We already have more than enough mnemonic support in PSS without this remapping capability

**Reality check (§10.2):** none of this exists in `pssparser`'s stdlib —
`get_mnemonic_of_*`, `set_mnemonic`, `use_symbolic_reg_names`, and even `std_pkg::format`
all fail to resolve. So this feature ships **off by default**, and it is the one part of
the design with no local regression test. Treat it as a bet on tool availability, and
decide it explicitly (§13.6).

**12.4 Randomizable register-configuration structs with RDL-derived constraints.**
Because register-value types are ordinary PSS packed structs, they can be `rand` fields in
actions. We can emit a companion *non-packed* `rand` struct per register whose constraints
encode what the RDL already knows: reserved fields == 0, enum-encoded fields restricted to
legal encodings, read-only fields excluded, field width bounds. That turns a register map
into constrained-random programming stimulus with zero hand-written constraints — a use
case UVM RAL only reaches via `uvm_reg_field` rand modes and considerable glue.

**12.5 A machine-readable lossiness sidecar.**
Everything PSS cannot express (`onread`/`onwrite`, counters, interrupts, `swmod`, HDL
paths, `alias` relationships, accesswidth) can be emitted to a JSON sidecar alongside the
`.pss`. Cheap to produce, and it lets downstream tooling — checkers, scoreboards, or a
future action generator — recover the semantics without re-parsing RDL.

**12.6 Interrupt/counter register helper actions.**
RDL marks interrupt registers (`intr`, `enable`, `mask`, `haltmask`) and counters
(`counter`, `incr`, `decr`) structurally. A generator could emit ready-made PSS actions —
`clear_interrupt`, `enable_interrupt`, `read_counter` — that encode the correct
write-1-to-clear / mask-then-read sequences. This is the natural v2 feature and the main
reason to keep the §12.5 sidecar around.

**12.7 Emit `get_offset_of_path()` mode for deep hierarchies.**
PSS lets a group answer for its whole subtree in one function. For deep, regular
hierarchies this collapses N nested string matches into one, which likely helps both
readability and solve time (§11.9). Cheap to add as an alternate template — but currently
unvalidatable: `pssparser` has no `node_s` type, so `list<node_s>` fails to link (§10.2).

**12.8 Address-space claims, not just fixed regions.**
The wrapper currently hardcodes a base address. PSS's real strength is
`transparent_addr_space_c` + claims; exposing `--region-mode={fixed,claim}` would let
generated register models participate in address-space allocation rather than assuming a
fixed MMIO base.

**12.9 Cross-check against the UVM output.**
Since both exporters run from the same compiled model, a CI job can generate the UVM
model and the PSS package from the same RDL and assert the absolute addresses agree. Free,
high-value regression protection against offset bugs.

---

## 13. Decisions needed before implementation

1. §11.1 — behavior for `regwidth > 64`.
MSB: Unsupported
2. §11.2 — behavior for `accesswidth < regwidth`.
MSB: Unsupported
3. §11.5 — multi-address-space strategy (this shapes the top-level architecture).
MSB: Unsupported
4. §11.4 — is `mem` in scope for v1 at all?
MSB: Unsupported
5. §12.1/§12.2/§12.3 — which of these ship in v1 and which are opt-in flags.
6. Target PSS version floor — now backed by measurement (§10.2, §11.12): default to the
   PSS 3.0-era subset that `pssparser` can actually validate, with `--pss-level=3.1`
   opting into symbolic names / path offsets / typed enums? Or lead with 3.1 and accept
   an untestable core?
MSB: Assume PSS 3.1, but don't support symbolic names. 

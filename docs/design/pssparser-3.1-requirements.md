# pssparser: PSS 3.1 features required by `peakrdl-pss`

**Status:** requirements list, ready to implement
**Date:** 2026-08-02
**Consumer:** `peakrdl-pss` (see `docs/design/systemrdl-to-pss.md`)
**Target repo:** `/home/mballance/projects/psstools/pssparser`
**Spec:** PSS 3.1 Draft 19 2026.07.14, §21.13 (`packed_s`, `sizeof_s`, address handles) and §21.14 (Registers)
**Parser version measured:** `pssparser` 3.0.0 (editable install in `peakrdl-pss/packages/python`)

---

## 0. Executive summary

I probed the parser with ~20 targeted snippets. **The headline: almost every gap is a
missing *declaration* in `src/stdlib/*.pss`, not a grammar or semantic-analysis gap.**

Confirmed already working (no work needed): `list<T>`, `type... args` varargs,
`solve pure function`, `target function`, `pure component`, template components/structs
with defaults, `match` statements in function bodies, struct literals (`{.f=1}`),
component arrays, `static function` in a component, package-scope `const`, and a
user-defined `node_s` + `list<node_s>` parameter.

That means the work splits as:

| Kind | Count | Effort |
|---|---|---|
| Missing stdlib declarations (edit `src/stdlib/*.pss`) | 15 | Low — mostly typing in spec syntax |
| Real grammar gap | **1** (§1.1 enum base type) | Medium — ANTLR grammar + AST |
| Semantic/elaboration behavior | 0 required for v1 | — |

I verified each stdlib item by pasting the spec's own declaration into user code and
confirming it parses+links — including the three declarations the stdlib currently
carries `TODO` markers against (`list<node_s>`, `list<bit[8]>`, `struct packed_struct`).
Those TODOs are stale; the underlying support landed. **§1.1 is the only item that needs
grammar work.**

Reproduction probes live in
`/tmp/claude-1000/-home-mballance-projects-psstools-peakrdl-pss/5337ffcb-76aa-4dbe-a4b5-db80977233ff/scratchpad/probes/`.
Every item below carries an acceptance snippet that must parse+link clean (`pssparser
FILE` → exit 0).

**Suggested order:** Tier 1 → Tier 2 → Tier 3 → Tier 4. Tier 1 unblocks the converter's
optional emission modes; Tier 2 unblocks its highest-value feature; Tier 3 unblocks
consumer-side testing; Tier 4 is spec fidelity.

---

## Tier 1 — Blocks generated-package features

### 1.1 `enum` with a base type — **the one real grammar gap**

**Spec:** BNF line 3286: `enum_declaration ::= enum enum_identifier [ : data_type ] { [ enum_item { , enum_item } ] }`
Required because §21.13.1 permits only "enumerated types that have a base type" as
members of a packed struct.

**Current:** rejected at parse time.

```
enum mode_e : bit[4] { IDLE = 0, RUN = 1, HALT = 2 };
            ^ error: unexpected ':' expecting '{'
```

Note the failure cascades — the parse error desynchronizes and produces a bogus
follow-on `unexpected '}'` at the package close.

**Needed:** accept the optional `: data_type` clause; carry the base type on the enum AST
node so it is visible to type checking and to packed-struct layout.

**Acceptance:**
```pss
package t1_1 {
    import std_pkg::*;
    enum mode_e : bit[4] { IDLE = 0, RUN = 1, HALT = 2 };
    enum kind_e : int { A = 0, B = 1 };
    enum plain_e { X = 0, Y = 1 };                       // must still work
    struct s : packed_s<LITTLE_ENDIAN> { mode_e mode; bit[28] rsvd_4; }
}
```

**Unblocks:** `peakrdl-pss --emit-enums=typed` — typed, self-documenting, randomizable
register fields derived from SystemRDL `encode` properties.

---

### 1.2 `reg_base_c` / `reg_sized_c` base-component chain

**Spec:** §21.14.1 Syntax158/159/160. The real hierarchy is
`reg_c<R,ACC,SZ>` → `reg_sized_c<SZ>` → `reg_base_c`.

**Current:** `reg_c` is declared standalone with no base; `reg_sized_c` and `reg_base_c`
do not exist. `get_handle()` is on `reg_c` directly, marked in-source as
"Zuspec extension, as of PSS 3.0".

**Needed** (in `src/stdlib/addr_reg_pkg.pss`, replacing the current `reg_c`):
```pss
pure component reg_base_c {
    function addr_handle_t get_handle();
}

pure component reg_sized_c<int SZ> : reg_base_c {
    target function bit[SZ] read_val();
    target function void    write_val(bit[SZ] r);
    target function void    write_val_masked(bit[SZ] mask, bit[SZ] val);
    target function void    write_field(string name, bit[SZ] val);
    target function void    write_fields(list<string> names, list<bit[SZ]> vals);
}

pure component reg_c<type R, reg_access ACC = READWRITE,
                     int SZ = (8*sizeof_s<R>::nbytes)> : reg_sized_c<SZ> {
    target function R    read();
    target function void write(R r);
    target function void write_masked(R mask, R val);
}
```
(Note: also renames the third parameter `SZ2` → `SZ` to match the spec — see §4.4.)

**Acceptance:**
```pss
package t1_2 {
    import addr_reg_pkg::*;
    struct CR : packed_s<> { bit en; bit[11] pad; bit[4] mode; bit[16] coeff; }
    pure component regs_c : reg_group_c { reg_c<CR> cr1; reg_c<bit[32]> cr2; }
    // §21.14.1 Example355: generic access across same-width registers
    target function void zero_r32(list<ref reg_sized_c<32>> regs) {
        foreach (r : regs) { r.write_val(0); }
    }
}
```

**Unblocks:** generic same-width register access; also a prerequisite for Tier 3.

---

### 1.3 `node_s` + `get_offset_of_path()`

**Spec:** §21.14.2 Syntax161. Currently `#if 0`-style commented out in the stdlib with a
`/** TODO: list */` marker — but `list<T>` works fine now, so the blocker is stale.

**Current:**
```
pure function bit[64] get_offset_of_path(list<node_s> path) { ... }
                                              ^ error: unknown type 'node_s'
```
A *user-defined* `struct node_s` + `list<node_s>` parameter parses clean, confirming this
is purely a missing declaration.

**Needed:** uncomment/add in `addr_reg_pkg`:
```pss
struct node_s { string name; int index; };
// and inside reg_group_c:
pure function bit[64] get_offset_of_path(list<node_s> path);
```

**Acceptance:**
```pss
package t1_3 {
    import addr_reg_pkg::*;
    pure component g : reg_group_c {
        pure function bit[64] get_offset_of_path(list<node_s> path) { return 0; }
    }
}
```

**Unblocks:** `peakrdl-pss` alternate offset-emission mode for deep hierarchies (one
function per group instead of N nested string matches).

**Out of scope for the parser:** §21.14.2 makes it an *error* to implement all three
`get_offset_of_*` functions in one group. Enforcing that is a nice checker rule
(see §5), not a blocker.

---

## Tier 2 — Blocks symbolic register names (§21.14.6)

This is the highest-value feature for `peakrdl-pss`: a generator can emit
`get_mnemonic_*` implementations perfectly and for free, producing target code that
references `DMA0_DMA_REG_A` instead of a raw address — and can match the symbols
`peakrdl-cheader` emits, so a PSS test and the firmware header agree by construction.
None of it exists in the parser today, so it is currently untestable end-to-end.

### 2.1 Mnemonic functions on `reg_group_c`

**Spec:** §21.14.6.1 Syntax162.

**Needed** (add to `reg_group_c`):
```pss
solve pure function string get_mnemonic_of_instance(string name);
solve pure function string get_mnemonic_of_instance_array(string name, int index);
solve pure function string get_mnemonic_of_path(list<node_s> path);
solve function void        set_mnemonic(string prefix);
```
`solve pure function` already parses, so this is declaration-only.

**Current:** `error: Failed to find elem set_mnemonic`.

### 2.2 `use_symbolic_reg_names()`

**Spec:** §21.14.6.2 Syntax163.

**Needed** (package-level function in `addr_reg_pkg`):
```pss
solve function void use_symbolic_reg_names(ref reg_group_c grp, bool enable);
```

**Current:** `error: unknown identifier 'use_symbolic_reg_names'`.

### 2.3 `std_pkg::format()`

**Spec:** line 20859 / 27027: `solve pure function string format(string format_str, type... args);`
Used by the spec's own mnemonic examples (Example362, Example365) to build indexed
fragments like `format("DMA_REG_C[%d]", index)`. Spec line 6427 confirms it is
`std_pkg::format`.

**Current:** `error: unknown identifier 'format'`. `std_pkg` has `print` and `message`
with their varargs *commented out* (`/*, type ... args*/`) — but `type... args` parses
fine in user code, so those can be uncommented at the same time.

**Needed** (in `src/stdlib/std_pkg.pss`):
```pss
solve pure function string format(string format_str, type... args);
function void print(string fmt, type... args);
function void message(message_verbosity_e vrb_level, string format_str, type... args);
```

**Also present in spec (line 19122), currently missing:**
`function string format_string(string format, type ... args);`

**Tier 2 acceptance** (all of 2.1–2.3 together — this is spec Example365, condensed):
```pss
package t2 {
    import addr_reg_pkg::*;
    import std_pkg::*;
    struct R1_s : packed_s<> { bit[32] fld; }
    pure component dma_reg_group_c : reg_group_c {
        reg_c<R1_s, READWRITE, 32> reg_a;
        reg_c<R1_s, READWRITE, 32> reg_c_arr[3];
        solve pure function string get_mnemonic_of_instance(string name) {
            if (name == "reg_a") { return "DMA_REG_A"; }
            return "";
        }
        solve pure function string get_mnemonic_of_instance_array(string name, int index) {
            if (name == "reg_c_arr") { return format("DMA_REG_C[%d]", index); }
            return "";
        }
    }
    component pss_top {
        dma_reg_group_c regs;
        transparent_addr_space_c<> mem;
        exec init_down {
            transparent_addr_region_s<> mmio;
            addr_handle_t h;
            mmio.size = 0x80000;
            mmio.addr = 0xA0000000;
            h = mem.add_nonallocatable_region(mmio);
            regs.set_handle(h);
            regs.set_mnemonic("");
            use_symbolic_reg_names(regs, true);
        }
    }
}
```

---

## Tier 3 — Blocks consumer-side testing

These are not emitted by `peakrdl-pss`, but every realistic *test* of a generated register
package uses them, and §12.4 of the converter design (rand register-config structs) leans
on them directly.

### 3.1 Masked and field-wise register writes

**Spec:** §21.14.1 Syntax158/159 (declarations land via Tier 1.2), semantics §21.14.1.

**Current:** all four fail with `Failed to find elem`:
`write_masked`, `write_val_masked`, `write_field`, `write_fields`.

**Acceptance** (spec Example356, condensed):
```pss
package t3_1 {
    import addr_reg_pkg::*;
    struct CR : packed_s<> { bit en; bit[11] pad; bit[4] mode; bit[16] coeff; }
    pure component regs_c : reg_group_c { reg_c<CR> cr; }
    component dut_c {
        regs_c regs;
        action cfg_a {
            rand bit[4] mode;
            rand bit[16] coeff;
            exec body {
                comp.regs.cr.write_masked({.mode=~0, .coeff=~0}, {.mode=mode, .coeff=coeff});
                comp.regs.cr.write_val_masked(0xFFFFF000, (coeff << 16) | (mode << 12));
                comp.regs.cr.write_fields({"mode", "coeff"}, {mode, coeff});
                comp.regs.cr.write_field("en", 1);
            }
        }
    }
}
```

### 3.2 Struct/byte-granular address-space access

**Spec:** §21.13.9 (line 23856):
```pss
target function void read_struct (addr_handle_t hndl, struct packed_struct);
target function void write_struct(addr_handle_t hndl, struct packed_struct);
function void read_bytes (addr_handle_t hndl, list<bit[8]> data, int size);
function void write_bytes(addr_handle_t hndl, list<bit[8]> data);
```

**Current:** all four commented out in `addr_reg_pkg.pss` behind
`/* TODO: generic type */`. **Verified: the TODO is stale — all four declarations parse
and link clean as written when pasted into user code**, including both `list<bit[8]>` and
the `struct packed_struct` generic-struct parameter form. This item is pure uncommenting;
no grammar work.

**Unblocks:** the converter's `--mem-mode=region` path for SystemRDL `mem` components,
which has no register-model analog and must be expressed as struct access over an
address region.

---

## Tier 4 — Spec fidelity (low priority, low risk)

### 4.1 `sizeof_s` should live in `std_pkg`
**Spec:** §21.13.2 — `sizeof_s` is declared in `std_pkg`; PSS 2.0 had it in
`addr_reg_pkg`, and tools "shall support referencing these declarations in either as if
they were the same types." Currently only in `addr_reg_pkg`. Same footnote applies to
`packed_s` / `endianness_e`, which are correctly in `std_pkg` — but should *also* resolve
via `addr_reg_pkg` for back-compat.

### 4.2 `addr_handle_t` should be `typedef chandle`
**Spec:** §21.13.3 Syntax145: `typedef chandle addr_handle_t;`. Currently declared as
`struct addr_handle_t { }` with the correct line commented out directly above it.
Cosmetic unless something depends on chandle semantics.

### 4.3 `make_handle_from_claim()` missing the `sub` parameter
**Spec:** §21.13.4.1 Syntax146:
`function addr_handle_t make_handle_from_claim(addr_claim_base_s claim, bit[64] offset = 0, bool sub = false);`
Current declaration omits `bool sub = false`.

### 4.4 `reg_c` third parameter named `SZ2`, not `SZ`
Cosmetic, but it leaks into diagnostics and docs. Fold into Tier 1.2.

### 4.5 `packed_s.pss` is an empty stub
The file contains only a commented-out `struct packed<type T>`. The live declaration is in
`std_pkg.pss`. Either delete the stub or make it the home — right now it's a decoy.

---

## 5. Optional: checker rules worth having

Not blockers, but cheap given the parser already has a checker plug-in framework, and
they catch exactly the mistakes a register generator could make:

* **Error** if a `reg_group_c` implements all three `get_offset_of_*` functions (§21.14.2)
  — or all three `get_mnemonic_of_*` (§21.14.6.1 rule a).
* **Error** if `set_handle()` / `set_mnemonic()` / `use_symbolic_reg_names()` is called on
  a non-top-level group, or outside `exec init_up`/`init_down` (§21.14.3, §21.14.6.1 d).
* **Error** if `reg_c`'s `SZ` < `sizeof_s<R>::nbits` (§21.14.1).
* **Warning** if a register's `SZ` is not in {8,16,32,64} — §21.14.5 selects the primitive
  `readN`/`writeN` by size, so there is no lowering otherwise. Today
  `reg_c<bit[128], READWRITE, 128>` parses and links clean with no complaint, which means
  the parser silently accepts a model no tool can generate code for.
* **Error** on a `packed_s` member whose type is an enum *without* a base type (§21.13.1)
  — currently accepted. Depends on 1.1 landing first.

---

## 6. Verification

After each tier, run the acceptance snippets plus the existing converter sample:

```bash
source packages/python/bin/activate
pssparser <acceptance>.pss                 # exit 0 required
pssparser --json <acceptance>.pss          # for pytest assertions
```

Two gotchas for whoever writes the tests:

1. `"0 errors in 0 files"` is the **success** message — the count is
   *files-with-diagnostics*, not files parsed. Assert on exit code or the `--json`
   `summary.errors` field, never on that string.
2. `import addr_reg_pkg::*;` is mandatory for `reg_c`/`reg_group_c` visibility; a missing
   import surfaces as `unknown type 'reg_c'`, which reads like a stdlib bug but isn't.

A useful regression backstop: the `peakrdl-pss` sample package at
`scratchpad/basic_reg_pkg.pss` links clean today and must keep doing so — it exercises
`packed_s`, `reg_c`, `reg_group_c`, `match`-based offset functions, and component arrays
in one file.

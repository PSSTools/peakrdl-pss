# `pssparser` segfault on multiple component arrays in one scope

**Found:** 2026-08-03, while setting up `peakrdl-pss` CI
**Affects:** `pssparser 3.0.0.28334693244` (the current PyPI release)
**Not affected:** local build at `05e7057` ("Better checking for function signature")

## Symptom

`pssparser` terminates with SIGSEGV (exit 139), no diagnostic, on input containing
**two or more array instances of a template-parameterized component type in the
same component scope**.

## Minimal reproducer

```pss
package p {
    import addr_reg_pkg::*;
    import std_pkg::*;
    struct r_s : packed_s<LITTLE_ENDIAN> { bit[32] f; }
    pure component r_c : reg_c<r_s, READWRITE, 32> {}
    component g_c {
        r_c a[8];
        r_c b[4];      // <-- one array parses; a second one segfaults
    }
}
```

```
$ pssparser min.pss
Segmentation fault (core dumped)
```

## Narrowing

| Case | Published 3.0.0.28334693244 |
|---|---|
| One array of `reg_c<...>` | OK |
| One array, two `match` arms naming a second (nonexistent) instance | OK |
| **Two arrays of `reg_c<...>`** | **SIGSEGV** |
| Two arrays of a plain, non-template component | OK |

So it is specific to *arrays of a template-instantiated component type*, and the
trigger is the second such array in a scope — not array size, not the offset
functions, and not the `match` statement.

## Why this matters here

This shape is not exotic in generated output; it is the *normal* shape. Any
SystemRDL `addrmap` with two register arrays produces it. Seven of the twenty-six
`peakrdl-pss` golden files crash the published parser, including `basic.pss`.

The practical consequence for CI: the parser gate cannot install `pssparser` from
PyPI, because the gate would crash rather than check. `.forgejo/workflows/ci.yml`
builds the parser from source instead, and says so at the job. That workaround
should be removed once a fixed release is published.

## Suggested regression test

The reproducer above belongs in `pssparser`'s own suite: it is four lines, needs
no fixture, and the failure mode is a crash rather than a wrong answer, so it
cannot be caught by any test that only inspects diagnostics.

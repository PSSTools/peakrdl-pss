"""PSS identifier legality and name mangling.

The keyword table is the *union* of two sources:

* Table 3 ("PSS keywords") of the PSS 3.1 Draft 19 specification, and
* the single-quoted lowercase keyword tokens of ``pssparser``'s ``PSSLexer.g4``.

The two sources do not agree exactly -- the lexer accepts several words the
spec table omits (``mutable``, ``pyimport``, ...) and the spec reserves two the
lexer does not tokenize as keywords (``this``, ``pre_body``).  Mangling against
the union is strictly safer than either source alone, so ``tests/unit`` asserts
each source is a *subset* of this table rather than equal to it; that way the
table cannot silently rot, and a parser upgrade that adds a keyword is a test
failure rather than a mystery syntax error in generated output.
"""

import re
from typing import Dict, FrozenSet, Set, Tuple

PSS_KEYWORDS: FrozenSet[str] = frozenset(
    """
    abstract action activity annotation array as assert atomic bind bins bit
    body bool break buffer chandle class compile component concat const
    constraint continue cover covergroup coverpoint cross declaration default
    disable dist do dynamic else enum eventually exec export extend false file
    float32 float64 forall foreach from function has header if iff ignore_bins
    illegal_bins import in init init_down init_up inout input instance int
    join_branch join_first join_none join_select list lock map match monitor
    mutable null numeric option output overlap override package parallel pool
    post_solve pre_body pre_solve private protected public pure pyimport pyobj
    rand randomize ref repeat replicate resource return run_end run_start
    schedule select sequence set share solve state static stream string struct
    super symbol target this true type typedef unique void while with yield
    """.split()
)

#: Identifiers brought into scope by the packages every generated file imports.
#: Colliding with one of these is legal PSS but produces a package that fails to
#: link, so they are mangled exactly like keywords.
PSS_IMPORTED_NAMES: FrozenSet[str] = frozenset(
    """
    addr_reg_pkg std_pkg
    packed_s sizeof_s
    reg_c reg_group_c reg_base_c reg_sized_c
    reg_access READWRITE READONLY WRITEONLY
    transparent_addr_space_c transparent_addr_region_s
    addr_space_base_c addr_handle_t addr_claim_s addr_region_s
    endianness_e LITTLE_ENDIAN BIG_ENDIAN
    """.split()
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")


def is_legal_identifier(name: str) -> bool:
    """True if *name* is lexically a PSS identifier and not a reserved word."""
    return bool(_IDENT_RE.match(name)) and name not in PSS_KEYWORDS


def _sanitize(name: str) -> str:
    """Force *name* into the PSS identifier character set."""
    # SystemRDL escaped identifiers arrive as ``\foo``.
    if name.startswith("\\"):
        name = name[1:]
    name = re.sub(r"[^A-Za-z_0-9]", "_", name)
    if not name or name[0].isdigit():
        name = "_" + name
    return name


def mangle(name: str, taken: Set[str]) -> Tuple[str, bool]:
    """Return a PSS-legal name for *name* that is not in *taken*.

    Returns ``(mangled, was_changed)``.  *taken* is **not** mutated; callers
    decide whether to reserve the result (a caller emitting two independent
    namespaces should not share one set).
    """
    base = _sanitize(name)
    candidate = base
    if candidate in PSS_KEYWORDS or candidate in PSS_IMPORTED_NAMES:
        candidate = base + "_"
    if candidate not in taken:
        return candidate, candidate != name
    # Collision: suffix until free.  ``_`` first so the common single-collision
    # case reads naturally, then numbered.
    if base + "_" not in taken and base + "_" not in PSS_KEYWORDS:
        return base + "_", True
    i = 1
    while True:
        candidate = "%s_%d" % (base, i)
        if candidate not in taken:
            return candidate, True
        i += 1


class Namespace:
    """A set of names allocated together, e.g. the members of one component."""

    def __init__(self) -> None:
        self._taken: Set[str] = set()
        self.mangled: Dict[str, str] = {}

    def allocate(self, name: str) -> Tuple[str, bool]:
        out, changed = mangle(name, self._taken)
        self._taken.add(out)
        if changed:
            self.mangled[name] = out
        return out, changed

    def reserve(self, name: str) -> None:
        self._taken.add(name)

    def __contains__(self, name: str) -> bool:
        return name in self._taken

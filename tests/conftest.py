import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from util import RDL_DIR, compile_rdl  # noqa: E402


def corpus_names(prefix: str = "", exclude_errors: bool = True):
    """Every corpus RDL file, as bare names.

    ``err_*`` files are excluded by default: they are expected to fail, so
    feeding them to a golden or parser test would assert the wrong thing.
    """
    names = []
    for fn in sorted(os.listdir(RDL_DIR)):
        if not fn.endswith(".rdl"):
            continue
        name = fn[:-4]
        if exclude_errors and name.startswith("err_"):
            continue
        if prefix and not name.startswith(prefix):
            continue
        names.append(name)
    return names


@pytest.fixture(scope="session")
def corpus():
    return corpus_names()


@pytest.fixture
def root(request):
    """Compile the corpus design named by an ``indirect`` parameter."""
    return compile_rdl(request.param)

# Configuration file for the Sphinx documentation builder.
#
# Conventions follow the rest of the PeakRDL ecosystem (sphinx_book_theme,
# autodoc, napoleon, sphinxemoji, pygments-systemrdl) so these docs read like
# the neighbouring exporters' docs.

import datetime
import os
import sys

sys.path.insert(0, os.path.abspath("../src"))
sys.path.insert(0, os.path.abspath("_ext"))

from peakrdl_pss.__about__ import __version__  # noqa: E402

project = "PeakRDL-PSS"
copyright = "%d, Matthew Ballance" % datetime.datetime.now().year
author = "Matthew Ballance"
version = __version__
release = __version__
html_title = project

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinxemoji.sphinxemoji",
    "diagnostics_table",
]

templates_path = ["_templates"]

# design/ holds the design record -- working documents, not user documentation.
# They stay in the repository but out of the built site.
exclude_patterns = ["_build", "design", "Thumbs.db", ".DS_Store", "README.md"]

html_theme = "sphinx_book_theme"
html_theme_options = {
    "path_to_docs": "docs",
    "use_download_button": False,
    "use_repository_button": False,
    "use_issues_button": False,
}
html_static_path = []

autodoc_member_order = "bysource"
autodoc_typehints = "description"

highlight_language = "systemrdl"

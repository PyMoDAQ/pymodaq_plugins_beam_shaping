# -*- coding: utf-8 -*-
import os
import sys
import datetime
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('.../src'))

# -- Project information -----------------------------------------------------
project = u'PyMoDAQ-BeamShaping'
year = datetime.datetime.now().year
copyright = u'%d, CEMES-CNRS, Valentin Rollo, Arnaud Arbouet, Sébastien Weber' % year
author = u'Valentin Rollo, Arnaud Arbouet, Sébastien Weber'

releases_issue_uri = "https://github.com/PyMoDAQ/pymodaq_plugins_beam_shaping/issues/%s"
releases_release_uri = "https://github.com/PyMoDAQ/pymodaq_plugins_beam_shaping/tree/%s"

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), '..')))
from pymodaq_utils.utils import get_version

version = get_version()
release = get_version()

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx_design",
    "sphinx_favicon",
    "sphinxext.rediraffe",
    "sphinxcontrib.images",
    "sphinx_autodoc_typehints",
    'sphinx.ext.doctest',
    'sphinx.ext.coverage',
    'sphinx.ext.mathjax',  # equations rendered in the browser, no LaTeX needed on the build machine (Read the Docs)
    'sphinx.ext.githubpages',
    'sphinx.ext.autosummary',
    'releases',
    'crate.sphinx.csv',
    'numpydoc',
    "sphinxcontrib.jquery",
    "sphinx_datatables",
    "sphinxcontrib.bibtex",
]

# Configuration pour numfig (références numérotées)
numfig = True
numfig_format = {
    'figure': 'Figure %s',
    'table': 'Table %s',
    'code-block': 'Listing %s',
    'section': 'Section %s',
}

html_css_files = [
    'https://fonts.googleapis.com/icon?family=Material+Icons',
    'css/custom.css',  # Pour styliser les icônes
]

bibtex_bibfiles = ['bibtex.bib']  # Chemin relatif à docs/
bibtex_reference_style = 'author_year'  # Style de citation (ex: "Weber 2021")

# -- Options for autodocumentation ---------------------------------------------
autodoc_member_order = "groupwise"
autoclass_content = "class"
autosummary_generate = []
autodoc_inherit_docstrings = False
numpydoc_show_inherited_class_members = False
numpydoc_class_members_toctree = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
primary_domain = 'py'

templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'
language = 'en'
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

pygments_style = 'sphinx'

autodoc_inherit_docstrings = False
autodoc_mock_imports = [
    "scipy",
    "h5py",
    "matplotlib",
    "qtpy",
    "qtpy.QtCore",
    "qtpy.QtGui",
    "qtpy.QtWidgets",
    "pyqtgraph",  # NOUVEAU
    "pymodaq_data",  # NOUVEAU
    "pymodaq_gui",  # NOUVEAU
    "pymodaq_utils",  # NOUVEAU
    "pymodaq_plugins_beam_shaping",  # NOUVEAU
    "numpy",
    "pytorch",  # NOUVEAU
]

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'

# NOUVEAU: Options pour le thème
html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'includehidden': True,
    'titles_only': False,
    'logo_only': False,
    'style_external_links': True,
    'vcs_pageview_mode': 'blob',
    'style_nav_header_background': '#2980B9',
}

html_css_files = [
    'css/overflow.css',
]

html_static_path = ["_static", "_images"]  # NOUVEAU: Ajout de "_images"
html_logo = '_static/logo.png'  # Assurez-vous que logo.png existe

# Configuration pour datatables
datatables_options = {
    'pageLength': 10,
    'lengthChange': True,
    'searching': True,
    'paging': True,
}

# -- Options for rediraffe -----------------------------------------------------
# Redirections of the pages that are renamed or removed, one "old_page new_page" per line (without the extension)
rediraffe_redirects = 'redirects.txt'

# -- Options for intersphinx ---------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
}

# -- Options for LaTeX output ------------------------------------------------
latex_engine = 'pdflatex'
latex_elements = {
    'papersize': 'letterpaper',
    'pointsize': '10pt',
    'preamble': '',
    'figure_align': 'htbp',
}
latex_documents = [
    (master_doc, 'PyMoDAQ-BeamShaping.tex', 'PyMoDAQ-BeamShaping Documentation',
     author, 'manual'),
]

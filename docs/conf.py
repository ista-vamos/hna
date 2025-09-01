# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
mod_path = os.path.abspath('..')
sys.path.insert(0, mod_path)

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'RVHyno'
copyright = '2025, Marek Chalupa'
author = 'Marek Chalupa'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc', 
    'sphinx.ext.autosummary',
    'sphinx.ext.apidoc'
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

autosummary_generate = True

apidoc_modules = [
    {'path': f'{mod_path}/rvhyno', 'destination': 'apidoc/',
     #'automodule_options': {#'members',
     #                       'show-inheritance', 'undoc-members'   }
     },
   #{
   #    'path': 'path/to/another_module',
   #    'destination': 'source/',
   #    'exclude_patterns': ['**/test*'],
   #    'max_depth': 4,
   #    'follow_links': False,
   #    'separate_modules': False,
   #    'include_private': False,
   #    'no_headings': False,
   #    'module_first': False,
   #    'implicit_namespaces': False,
   #    'automodule_options': {
   #        'members', 'show-inheritance', 'undoc-members'
   #    },
   #},
]



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']

# docs/conf.py
"""Configuración de Sphinx para la documentación del motor lógico de IPC.

Generación:
    sphinx-build -b html docs/ docs/_build/html
"""

import os
import sys

# Agregar la raíz del proyecto al path para que autodoc pueda importar `motor`
sys.path.insert(0, os.path.abspath('..'))

# ---------------------------------------------------------------------------
# Información del proyecto
# ---------------------------------------------------------------------------

project   = 'PropLogPlat'
copyright = '2025–2026, ETEC-UBA / CBC-UBA'
author    = 'Sebastián Goyburu'
release   = '0.3.0'

# ---------------------------------------------------------------------------
# Extensiones
# ---------------------------------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',          # genera API docs desde docstrings
    'sphinx.ext.napoleon',         # soporte para Google-style docstrings
    'sphinx.ext.viewcode',         # enlaza al código fuente desde la doc
    'sphinx_autodoc_typehints',    # muestra type hints en la doc
    # intersphinx deshabilitado: requiere acceso externo a docs.python.org y
    # docs.sympy.org, que no está disponible en el entorno de build.
    # Reactivar en CI/CD con acceso a internet:
    # 'sphinx.ext.intersphinx',
]

# ---------------------------------------------------------------------------
# Configuración de autodoc
# ---------------------------------------------------------------------------

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',    # mantiene el orden del archivo fuente
    'special-members': '__init__',
    'undoc-members': False,        # no documentar funciones sin docstring
    'show-inheritance': True,
    'private-members': False,      # no exponer _tokenize, _Parser, etc.
}

# Mostrar tipo de retorno en la firma, no en la sección Returns
autodoc_typehints = 'description'
autodoc_typehints_format = 'short'

# ---------------------------------------------------------------------------
# Configuración de Napoleon (Google-style docstrings)
# ---------------------------------------------------------------------------

napoleon_google_docstring         = True
napoleon_numpy_docstring          = False
napoleon_include_init_with_doc    = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples  = False
napoleon_use_admonition_for_notes     = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar                 = False
napoleon_use_param                = True
napoleon_use_rtype                = True

# ---------------------------------------------------------------------------
# Intersphinx (cross-references externos)
# ---------------------------------------------------------------------------

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'sympy':  ('https://docs.sympy.org/latest', None),
}

# ---------------------------------------------------------------------------
# Opciones de build HTML
# ---------------------------------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    'navigation_depth': 3,
    'titles_only': False,
    'collapse_navigation': False,
    'sticky_navigation': True,
}

html_static_path = ['_static']

# Logo y favicon opcionales (se pueden agregar más adelante)
# html_logo   = '_static/logo.png'
# html_favicon = '_static/favicon.ico'

# ---------------------------------------------------------------------------
# Opciones generales
# ---------------------------------------------------------------------------

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# El idioma del contenido es español; los strings de UI de Sphinx quedan
# en inglés (no requiere sphinx-intl, suficiente para uso interno)
language = 'es'

# Evitar warnings por referencias forward en type hints
# (relevante si se agregan más módulos con referencias circulares)
nitpicky = False

"""Etiqueta semántica sobre los catálogos gettext estándar de Django.

Cada clave ``ui.*`` vive íntegramente en los archivos ``django.po`` y sus
``django.mo`` compilados. No hay traducciones paralelas en código Python.
"""

from django import template
from django.utils.translation import gettext


register = template.Library()


@register.simple_tag
def ui(key):
    """Traduce ``key`` desde el catálogo ``django.mo`` activo."""
    return gettext(f'ui.{key}')

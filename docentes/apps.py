"""Configuración de la app docentes."""

from django.apps import AppConfig


class DocentesConfig(AppConfig):
    """Config de la app del panel docente."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'docentes'

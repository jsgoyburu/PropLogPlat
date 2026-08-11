"""Context processors de la app accounts."""

from accounts.models import ConfigSitio


def config_sitio(request):
    """Inyecta la configuración del sitio en todos los templates."""
    return {
        'config_sitio': ConfigSitio.get(),
        'idioma_actual': getattr(request, 'LANGUAGE_CODE', 'es'),
    }

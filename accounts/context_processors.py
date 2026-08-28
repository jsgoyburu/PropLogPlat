"""Context processors de la app accounts."""

from django.conf import settings

from accounts.models import ConfigSitio


def config_sitio(request):
    """Inyecta la configuración del sitio en todos los templates."""
    return {
        'config_sitio': ConfigSitio.get(),
        'idioma_actual': getattr(request, 'LANGUAGE_CODE', 'es'),
        # No anunciar recuperación en instalaciones cuyo backend solo imprime
        # el correo en consola. El endpoint se conserva para pruebas locales.
        'recuperacion_password_habilitada': bool(
            settings.BREVO_API_KEY or settings.EMAIL_HOST
        ),
    }

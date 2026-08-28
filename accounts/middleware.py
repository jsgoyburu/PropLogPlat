from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation


class IdiomaSitioMiddleware:
    """Activa el idioma elegido o el predeterminado configurado en el admin.

    El selector público usa la cookie estándar de Django. Sin cookie, se usa
    ``ConfigSitio.idioma_predeterminado``; así el cambio del admin solo afecta
    a quienes todavía no expresaron una preferencia propia.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from accounts.models import ConfigSitio

        idiomas = {codigo for codigo, _nombre in settings.LANGUAGES}
        idioma = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if idioma not in idiomas:
            idioma = ConfigSitio.get().idioma_predeterminado

        translation.activate(idioma)
        request.LANGUAGE_CODE = idioma
        try:
            response = self.get_response(request)
            response.setdefault('Content-Language', idioma)
            return response
        finally:
            translation.deactivate()


class PrimeraEntradaInstalacionMiddleware:
    """En una base realmente vacía, la primera visita a ``/`` abre el wizard.

    Se limita a la portada y a cero usuarios para no secuestrar tests, APIs ni
    una instancia parcialmente administrada. El URL del instalador sigue
    disponible explícitamente hasta que exista un superusuario.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == '/':
            from django.contrib.auth import get_user_model

            from accounts.models import ConfigSitio

            config = ConfigSitio.get()
            if not config.instalacion_completada and not get_user_model().objects.exists():
                return redirect('accounts:instalacion_inicial')
        return self.get_response(request)


class ForzarCambioPasswordMiddleware:
    """Redirige al cambio de contraseña en el primer login del estudiante.

    Detecta el primer login usando last_login=None: Django actualiza este
    campo justo después de autenticar, pero antes de llamar al middleware.
    Sin embargo, update_last_login() se dispara en la señal user_logged_in,
    que ocurre en LoginView.form_valid() — después de que el middleware ya
    procesó la request de login.

    Por eso la detección se hace en la *siguiente* request post-login:
    si last_login está seteado (ya logueó) pero la sesión tiene la marca
    'primer_login', se redirige.

    Flujo:
        1. LoginView autentica → dispara user_logged_in → update_last_login
        2. LoginView redirige al destino (next o home)
        3. En esa request, este middleware detecta el primer login y redirige

    Adicionalmente:
        - Usuarios que ya cambiaron su contraseña pero aún no respondieron
          los consentimientos son redirigidos a la vista de consentimientos.
        - Estudiantes con consentimiento pedagógico=True pero encuesta
          sin completar son redirigidos a la encuesta de onboarding.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            url_logout = reverse('accounts:logout')

            # Primer caso: debe cambiar contraseña (incluye consentimientos)
            if getattr(user, 'debe_cambiar_password', False):
                url_cambio = reverse('accounts:cambiar_password')
                if request.path not in (url_cambio, url_logout):
                    if request.path.startswith('/api/'):
                        return JsonResponse({'detail': 'Autenticación requerida.'}, status=401)
                    return redirect(url_cambio)

            # Segundo caso: ya cambió contraseña pero no respondió consentimientos
            elif (
                getattr(user, 'consentimiento_pedagogico', None) is None
                or getattr(user, 'consentimiento_investigacion', None) is None
            ):
                url_consent = reverse('accounts:consentimientos')
                if request.path not in (url_consent, url_logout):
                    if request.path.startswith('/api/'):
                        return JsonResponse({'detail': 'Autenticación requerida.'}, status=401)
                    return redirect(url_consent)

            # Tercer caso: estudiante con pedagogico=True pero encuesta pendiente
            elif (
                not user.es_docente and not user.is_staff
                and getattr(user, 'consentimiento_pedagogico', None) is True
                and not getattr(user, 'encuesta_completada', False)
            ):
                url_encuesta = reverse('accounts:encuesta')
                if request.path not in (url_encuesta, url_logout):
                    if request.path.startswith('/api/'):
                        return JsonResponse({'detail': 'Configuración de cuenta incompleta.'}, status=403)
                    return redirect(url_encuesta)

        return self.get_response(request)

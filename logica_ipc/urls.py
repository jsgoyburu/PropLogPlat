"""URLs raíz del proyecto logica_ipc.

Estructura:
    /                    → ejercicios (home del estudiante o redirect a dashboard)
    accounts/            → django.contrib.auth.urls (login, logout)
    api/                 → ejercicios API REST (intentos)
    analiticas/          → dashboard docentes/admins
    admin/               → Django admin
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

from accounts.views import favicon_view, healthz

urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path("mario.png",serve, {"path": "mario.png", "document_root": settings.BASE_DIR,}),
    path('favicon.ico', favicon_view, name='favicon'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('api/', include('ejercicios.api.urls', namespace='ejercicios_api')),
    path('analiticas/', include('analiticas.urls', namespace='analiticas')),
    path('docentes/', include('docentes.urls', namespace='docentes')),
    path('', include('ejercicios.urls', namespace='ejercicios')),
    path("ckeditor5/", include('django_ckeditor_5.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

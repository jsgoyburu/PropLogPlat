"""URLs de la API de ejercicios."""

from django.urls import path

from ejercicios.api.views import (
    IntentoComentarioUpdateView,
    IntentoCreateView,
    PreviewArgumentoView,
    PreviewDeterminacionView,
    PreviewVerificacionView,
)

app_name = 'ejercicios_api'

urlpatterns = [
    path('intentos/', IntentoCreateView.as_view(), name='intento-create'),
    path('intentos/<int:intento_id>/comentario/', IntentoComentarioUpdateView.as_view(), name='intento-comentario-update'),
    path('preview-verificacion/', PreviewVerificacionView.as_view(), name='preview-verificacion'),
    path('preview-argumento/', PreviewArgumentoView.as_view(), name='preview-argumento'),
    path('preview-determinacion/', PreviewDeterminacionView.as_view(), name='preview-determinacion'),
]

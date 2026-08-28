from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views

from . import views

app_name = 'accounts'

urlpatterns = [
    path('instalar/', views.instalacion_inicial, name='instalacion_inicial'),
    path('comision/<int:comision_id>/', views.acceso_comision, name='acceso_comision'),
    path('login/', views.LoginConPrimerAccesoView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('cambiar-password/', views.cambiar_password_forzado, name='cambiar_password'),
    path('consentimientos/', views.dar_consentimiento, name='consentimientos'),
    path('encuesta/', views.encuesta_onboarding, name='encuesta'),
    path('encuesta/editar/', views.editar_encuesta, name='editar_encuesta'),
    path('perfil/', views.mi_perfil, name='mi_perfil'),

    # Recuperación de contraseña. `success_url` va explícito porque las vistas
    # de Django lo resuelven sin namespace (reverse_lazy("password_reset_done"))
    # y esta app declara app_name = 'accounts'.
    path(
        'password_reset/',
        views.PasswordResetSitioView.as_view(
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password_reset/enviado/',
        auth_views.PasswordResetDoneView.as_view(),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        views.PasswordResetConfirmLimpiaFlagView.as_view(
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/completo/',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
]

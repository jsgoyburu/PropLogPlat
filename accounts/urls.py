from django.urls import path
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
]

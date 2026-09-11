"""URLs HTML de la app ejercicios.

Patterns:
    /                               → home (lista de comisiones/prácticas del estudiante)
    practica/<pc_id>/               → practica_detail (ejercicios con estado de desbloqueo)
    practica/<pc_id>/ejercicio/<ep_id>/  → ejercicio_detail (ejercicio interactivo)
"""

from django.urls import path

from . import views
from .experimentacion import experimentacion

app_name = 'ejercicios'

urlpatterns = [
    path('experimentacion/', experimentacion, name='experimentacion'),
    path('', views.home, name='home'),
    path('mi-historial/', views.mi_historial, name='mi_historial'),
    path('practica/<int:pc_id>/', views.practica_detail, name='practica'),
    path(
        'practica/<int:pc_id>/ejercicio/<int:ep_id>/',
        views.ejercicio_detail,
        name='ejercicio',
    ),
]

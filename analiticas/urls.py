"""URLs de analíticas.

Patterns:
    dashboard/              → dashboard operativo (docentes y admins)
    investigacion/          → métricas de investigación (solo con consentimiento)
    exportar/<dataset>/     → descarga CSV / XLSX / ODS
"""

from django.urls import path

from . import views

app_name = 'analiticas'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('investigacion/', views.investigacion, name='investigacion'),
    path('encuesta/', views.encuesta_resumen, name='encuesta_resumen'),
    path('exportar/<str:dataset>/', views.exportar, name='exportar'),
    path('descargar/', views.descargar_investigacion, name='descargar_investigacion'),
    path('detalle-ejercicio/', views.detalle_ejercicio, name='detalle_ejercicio'),
    path('red-errores/', views.red_errores_json, name='red_errores'),
]

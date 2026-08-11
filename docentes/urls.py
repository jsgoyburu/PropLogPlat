"""URLs del panel docente."""

from django.urls import path

from . import views

app_name = 'docentes'

urlpatterns = [
    path('comisiones/', views.comisiones_list, name='comisiones_list'),
    path('correcciones/pendientes/', views.correccion_pendiente, name='correccion_pendiente'),
    path('comisiones/nueva/', views.comision_create, name='comision_create'),
    path('cohortes/nueva/', views.cohorte_create, name='cohorte_create'),
    path('comisiones/<int:comision_id>/', views.comision_detail, name='comision_detail'),
    path('comisiones/<int:comision_id>/eliminar/', views.comision_delete, name='comision_delete'),
    path('comisiones/<int:comision_id>/docentes/agregar/', views.docente_add, name='docente_add'),
    path('comisiones/<int:comision_id>/docentes/<int:docente_id>/quitar/', views.docente_remove, name='docente_remove'),
    path('comisiones/<int:comision_id>/estudiantes/nuevo/', views.estudiante_create, name='estudiante_create'),
    path('comisiones/<int:comision_id>/estudiantes/importar/', views.estudiantes_importar, name='estudiantes_importar'),
    path('comisiones/<int:comision_id>/estudiantes/reinscribir-recursante/', views.estudiante_reinscribir_recursante, name='estudiante_reinscribir_recursante'),
    path('comisiones/<int:comision_id>/estudiantes/reinscribir-pase/', views.estudiante_reinscribir_pase, name='estudiante_reinscribir_pase'),
    path('comisiones/<int:comision_id>/estudiantes/exportar/', views.estudiantes_exportar, name='estudiantes_exportar'),
    path('estudiantes/<int:estudiante_id>/', views.estudiante_detail, name='estudiante_detail'),
    path('comisiones/<int:comision_id>/estudiantes/<int:estudiante_id>/editar/', views.estudiante_edit, name='estudiante_edit'),
    path('comisiones/<int:comision_id>/estudiantes/<int:estudiante_id>/eliminar/', views.estudiante_remove, name='estudiante_remove'),
    path('intentos/bulk-aprobar/', views.intentos_bulk_aprobar, name='intentos_bulk_aprobar'),
    path('intentos/<int:intento_id>/comentario/', views.intento_comentario_update, name='intento_comentario_update'),
    path('intentos/<int:intento_id>/aprobacion/', views.intento_aprobacion_update, name='intento_aprobacion_update'),
    path('practicas/nueva/', views.practica_create, name='practica_create'),
    path('paquetes/instalar/', views.paquete_instalar, name='paquete_instalar'),
    path('practicas/<int:practica_id>/descargar.zip', views.practica_descargar, name='practica_descargar'),
    path('comisiones/<int:comision_id>/practicas/importar/', views.practica_import, name='practica_import'),
    path('practicas/<int:practica_id>/', views.practica_detail, name='practica_detail'),
    path('practicas/<int:pc_id>/editar/', views.practica_edit, name='practica_edit'),
    path('practicas/<int:pc_id>/eliminar/', views.practica_delete, name='practica_delete'),
    path('practicas/<int:practica_id>/agregar-ejercicio/', views.ejercicio_practica_add, name='ejercicio_practica_add'),
    path('ejercicio-practica/<int:ep_id>/quitar/', views.ejercicio_practica_remove, name='ejercicio_practica_remove'),
    path('ejercicio-practica/<int:ep_id>/reordenar/', views.ejercicio_practica_reorder, name='ejercicio_practica_reorder'),
    path('comisiones/<int:comision_id>/parciales/nuevo/', views.parcial_create, name='parcial_create'),
    path('parciales/<int:parcial_id>/editar/', views.parcial_edit, name='parcial_edit'),
    path('parciales/<int:parcial_id>/eliminar/', views.parcial_delete, name='parcial_delete'),
    path('parciales/<int:parcial_id>/notas/', views.parcial_notas, name='parcial_notas'),
    path('parciales/<int:parcial_id>/notas/exportar/', views.parcial_notas_exportar, name='parcial_notas_exportar'),
    path('ejercicios/nuevo/', views.ejercicio_create, name='ejercicio_create'),
    path('ejercicios/<int:ejercicio_id>/editar/', views.ejercicio_edit, name='ejercicio_edit'),
    path('ejercicios/<int:ejercicio_id>/descargar.zip', views.ejercicio_descargar, name='ejercicio_descargar'),
    path('ejercicios/<int:ejercicio_id>/eliminar/', views.ejercicio_delete, name='ejercicio_delete'),
]

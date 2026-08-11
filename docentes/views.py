"""Vistas HTML del panel docente.

Todas las vistas requieren autenticación y rol docente/admin.
Los docentes solo pueden gestionar objetos propios o de sus comisiones.
"""

import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Prefetch, Q, Subquery, OuterRef
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.urls import reverse
from urllib.parse import urlencode

from cursos.models import Cohorte, Comision, Inscripcion, NotaParcial, Parcial
from ejercicios.correctitud import Q_CORRECTO
from ejercicios.progreso import avanzar_progreso
from ejercicios.historial import build_historial_context
from ejercicios.models import Ejercicio, EjercicioPractica, Intento, Practica, PracticaComision, Progreso
from ejercicios.paquetes import (
    PaqueteInvalido,
    comprimir_paquete,
    instalar_paquete,
    leer_paquete,
    paquete_ejercicio,
    paquete_practica,
)

from analiticas.views import (
    _concentracion_practica,
    _distribucion_intentos,
    _ejercicios_mas_dificiles,
    _errores_sistematicos,
    _estudiantes_en_riesgo,
    _evolucion_temporal,
    _silencio_resumen,
    _silencio_temprano,
    _velocidad_arranque,
)

from .forms import (
    CohorteForm,
    ComisionForm,
    DocenteComisionForm,
    EjercicioForm,
    EjercicioPracticaForm,
    EstudianteCreateForm,
    EstudianteEditForm,
    get_nota_parcial_formset,
    ImportarEstudiantesForm,
    InstalarPaqueteForm,
    ParcialForm,
    PracticaComisionForm,
    PracticaForm,
)


Usuario = get_user_model()


def _respuesta_paquete(payload, nombre_base):
    """Construye una descarga ZIP sin exponer rutas ni identificadores internos."""
    nombre = slugify(nombre_base)[:80] or 'contenido-proplogplat'
    response = HttpResponse(
        comprimir_paquete(payload),
        content_type='application/zip',
    )
    response['Content-Disposition'] = f'attachment; filename="{nombre}.zip"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _require_docente(user):
    if not (user.is_staff or user.es_docente):
        raise PermissionDenied


def _require_cohorte_activa(cohorte):
    """Impide modificar la composición de una camada cerrada.

    Una cohorte no activa no crece ni suma instancias de evaluación. Sí se le
    siguen corrigiendo intentos y cargando notas de parciales existentes, así
    que esta guarda va solo en las altas.
    """
    if cohorte is None or not cohorte.activa:
        raise PermissionDenied


def _puede_editar_practica(user, practica):
    """Indica si el usuario puede modificar el contenido de una práctica.

    Pueden escribir el staff y cualquier docente de una comisión donde la
    práctica esté asignada. La ``Practica`` es canónica: ``practica_import``
    la vincula a la comisión destino sin duplicarla, así que sus ejercicios se
    editan de forma compartida entre las comisiones que la usan.

    El autor escribe sólo mientras la práctica no esté asignada a ninguna
    comisión. Apenas la usa una comisión ajena, la autoría deja de alcanzar:
    quitar un ejercicio borra en cascada los ``Intento`` de los estudiantes de
    esa comisión, y reordenar o agregar altera una práctica en curso. Para
    modificarla hay que ser docente de alguna de esas comisiones.

    Ser pública tampoco habilita escritura: es un permiso de lectura.
    """
    if user.is_staff:
        return True
    pcs = PracticaComision.objects.filter(practica=practica)
    if pcs.filter(comision__docentes=user).exists():
        return True
    return practica.creada_por_id == user.id and not pcs.exists()


def _puede_ver_practica(user, practica):
    """Indica si el docente puede ver el detalle de una práctica.

    Además de quienes pueden editarla, leen su autor —aunque haya perdido la
    escritura por estar la práctica en comisiones ajenas— y cualquier docente
    si la práctica es pública: ya puede importarla con ``practica_import``, así
    que su contenido no es información reservada.
    """
    return (
        practica.es_publica
        or practica.creada_por_id == user.id
        or _puede_editar_practica(user, practica)
    )


def _practicas_editables(user):
    """Queryset de prácticas sobre las que el usuario puede escribir.

    Mismo criterio que :func:`_puede_editar_practica`.
    """
    if user.is_staff:
        return Practica.objects.all()
    return Practica.objects.filter(
        Q(practicas_comisiones__comision__docentes=user)
        | Q(creada_por=user, practicas_comisiones__isnull=True)
    ).distinct()


def _resolver_url_retorno(request):
    """Obtiene una URL segura para volver al origen desde formularios docentes.

    Args:
        request: request HTTP actual.

    Returns:
        str: URL de retorno validada o cadena vacía si no hay una válida.
    """
    candidata = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if not candidata:
        return ''

    if url_has_allowed_host_and_scheme(
        url=candidata,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidata

    return ''


def _desanclar_si_derivada(practica_id):
    """Si la práctica es una derivada (importada), la desancla de su origen.

    Se llama cada vez que el docente modifica el contenido de la práctica:
    al editar sus metadatos o al agregar, quitar o reordenar ejercicios.
    Una práctica desanclada vuelve a ser visible en el banco de prácticas.
    """
    Practica.objects.filter(pk=practica_id, practica_origen__isnull=False).update(practica_origen=None)


def _insertar_ejercicio_en_practica(practica, ejercicio, orden_destino):
    """Inserta una asignación y desplaza órdenes existentes si hay colisión.

    Args:
        practica: práctica destino.
        ejercicio: ejercicio a asignar.
        orden_destino: orden solicitado por el docente.

    Returns:
        tuple[EjercicioPractica, int]: asignación creada y orden final usado.

    Raises:
        IntegrityError: si el ejercicio ya estaba asignado a la práctica.
    """
    with transaction.atomic():
        asignaciones = EjercicioPractica.objects.select_for_update().filter(practica=practica)
        total = asignaciones.count()
        orden_final = max(1, min(int(orden_destino), total + 1))

        for asignacion in asignaciones.filter(orden__gte=orden_final).order_by('-orden'):
            asignacion.orden = asignacion.orden + 1
            asignacion.save(update_fields=['orden'])

        nueva_asignacion = EjercicioPractica.objects.create(
            practica=practica,
            ejercicio=ejercicio,
            orden=orden_final,
        )

    return nueva_asignacion, orden_final






def _reordenar_despues_de_eliminar(practica, orden_eliminado):
    """Compacta la secuencia de órdenes tras eliminar una asignación.

    Args:
        practica: práctica afectada por la eliminación.
        orden_eliminado: orden que tenía la asignación eliminada.
    """
    with transaction.atomic():
        asignaciones = (
            EjercicioPractica.objects
            .select_for_update()
            .filter(practica=practica, orden__gt=orden_eliminado)
            .order_by('orden')
        )
        for asignacion in asignaciones:
            asignacion.orden = asignacion.orden - 1
            asignacion.save(update_fields=['orden'])


def _solo_error_unique_together_practica_orden(form):
    """Indica si el único error del form es colisión de (práctica, orden)."""
    errores = form.errors.as_data()
    if not errores:
        return False

    if any(campo != '__all__' for campo in errores.keys()):
        return False

    codigos = {error.code for error in errores.get('__all__', [])}
    return codigos == {'unique_together'}


def _aprobados_por_estudiante_ep(comision_ids, estudiantes_ids, cohorte_id=None):
    """Devuelve el conjunto de ternas (estudiante_id, comision_id, ep_id) aprobadas.

    Una terna se considera aprobada si existe al menos un Intento con
    ``aprobado_docente=True`` para ese estudiante y ese ejercicio_practica,
    realizado en esa comisión.

    La comisión forma parte de la clave porque una misma :class:`Practica`
    canónica puede estar asignada a varias comisiones (es lo que hace importar
    una práctica), compartiendo sus ``EjercicioPractica``. Sin la comisión, lo
    que un estudiante resolvió en una comisión inflaría el avance de la otra.

    Args:
        comision_ids: IDs de comisiones a considerar.
        estudiantes_ids: IDs de estudiantes a considerar.
        cohorte_id: si se da, acota los intentos a esa cohorte. Necesario para
            no contar como "aprobado" en la camada actual algo que un
            recursante resolvió en una camada anterior: ``estudiantes_ids``
            identifica personas, no camadas, así que sin este filtro un
            recursante con intentos solo en su cohorte vieja aparece con
            avance en la cohorte que se está mirando ahora.

    Returns:
        set[tuple[int, int, int]]: conjunto de
        (estudiante_id, comision_id, ejercicio_practica_id).
    """
    if not comision_ids or not estudiantes_ids:
        return set()
    filtros = dict(
        aprobado_docente=True,
        estudiante_id__in=estudiantes_ids,
        practica_comision__comision_id__in=comision_ids,
    )
    if cohorte_id is not None:
        filtros['cohorte_id'] = cohorte_id
    rows = (
        Intento.objects
        .filter(**filtros)
        .values('estudiante_id', 'practica_comision__comision_id', 'ejercicio_practica_id')
        .distinct()
    )
    return {
        (r['estudiante_id'], r['practica_comision__comision_id'], r['ejercicio_practica_id'])
        for r in rows
    }


def _resueltos_por_estudiante_ep(comision_ids, estudiantes_ids, cohorte_id=None):
    """Devuelve el conjunto de ternas (estudiante_id, comision_id, ep_id) resueltas.

    Una terna se considera resuelta si existe al menos un Intento con correctitud
    efectiva (ver :mod:`ejercicios.correctitud`) en esa comisión: aprobado por el
    docente, o correcto según el motor y todavía sin revisar.

    A diferencia de :func:`_aprobados_por_estudiante_ep`, no depende de que el
    docente haya corregido a mano, así que sigue siendo informativa en comisiones
    masivas donde revisar todos los intentos no es viable. La clave incluye la
    comisión por el mismo motivo explicado en esa función.

    Args:
        comision_ids: IDs de comisiones a considerar.
        estudiantes_ids: IDs de estudiantes a considerar.
        cohorte_id: si se da, acota los intentos a esa cohorte (ver
            :func:`_aprobados_por_estudiante_ep`).

    Returns:
        set[tuple[int, int, int]]: conjunto de
        (estudiante_id, comision_id, ejercicio_practica_id).
    """
    if not comision_ids or not estudiantes_ids:
        return set()
    filtros = dict(
        estudiante_id__in=estudiantes_ids,
        practica_comision__comision_id__in=comision_ids,
    )
    if cohorte_id is not None:
        filtros['cohorte_id'] = cohorte_id
    rows = (
        Intento.objects
        .filter(Q_CORRECTO, **filtros)
        .values('estudiante_id', 'practica_comision__comision_id', 'ejercicio_practica_id')
        .distinct()
    )
    return {
        (r['estudiante_id'], r['practica_comision__comision_id'], r['ejercicio_practica_id'])
        for r in rows
    }


def _calcular_avance_promedio(comision, estudiantes_ids, pares):
    """Calcula el avance promedio de una comisión para la vista operativa docente.

    La métrica se define como el promedio de avance por par
    ``(estudiante, práctica)`` donde:

    ``avance = ejercicios_contados / total_ejercicios_practica``.

    Qué se cuenta depende del índice que se pase en ``pares``: con
    ``_aprobados_por_estudiante_ep`` la métrica es "revisado" (cuánto corrigió el
    docente a mano) y con ``_resueltos_por_estudiante_ep`` es "resuelto" (cuánto
    le salió al estudiante, sin depender de la corrección manual).

    Args:
        comision: instancia de ``Comision`` con prefetched de prácticas.
        estudiantes_ids: IDs de estudiantes de la comisión.
        pares: set de (estudiante_id, ejercicio_practica_id) que cuentan como
            avance.

    Returns:
        float | None: porcentaje promedio [0, 100], o ``None`` si no hay
        suficientes datos para computar (sin estudiantes o sin ejercicios).
    """
    practicas = [pc.practica for pc in comision.practicas_comisiones.select_related('practica').all()]
    if not estudiantes_ids or not practicas:
        return None

    total_ratio = 0
    total_pares = 0

    for practica in practicas:
        eps = [ep.id for ep in practica.ejercicio_practicas.all()]
        total_ejercicios = len(eps)
        if total_ejercicios == 0:
            continue

        for estudiante_id in estudiantes_ids:
            pares_count = sum(
                1 for ep_id in eps
                if (estudiante_id, comision.id, ep_id) in pares
            )
            total_ratio += pares_count / total_ejercicios
            total_pares += 1

    if total_pares == 0:
        return None

    return round((total_ratio / total_pares) * 100, 1)


def _build_progreso_estudiantes(comision, aprobados, resueltos):
    """Construye el resumen de progreso por estudiante para una comisión.

    Calcula dos métricas por par (estudiante, práctica), sobre el mismo total de
    ejercicios:

    - **revisado**: ``aprobados_docente / total_ejercicios``. Cuánto miró el
      docente. Alimenta ``porcentaje_global``, ``completada`` y
      ``practicas_completadas``.
    - **resuelto**: ``resueltos / total_ejercicios``, con correctitud efectiva
      (ver :mod:`ejercicios.correctitud`). Cuánto le salió al estudiante. No
      depende de la corrección manual, así que sigue siendo informativa en
      comisiones masivas.

    Args:
        comision: Comisión con inscripciones, practicas_comisiones y sus
            progresos prefetchados.
        aprobados: set de (estudiante_id, ejercicio_practica_id) aprobados,
            generado por ``_aprobados_por_estudiante_ep``.
        resueltos: set de (estudiante_id, ejercicio_practica_id) resueltos,
            generado por ``_resueltos_por_estudiante_ep``.

    Returns:
        list[dict]: lista con métricas por estudiante para render de tabla.
    """
    pcs = list(comision.practicas_comisiones.all())
    practicas = [pc.practica for pc in pcs]
    practicas_por_id = {practica.id: practica for practica in practicas}

    # PracticaComision no tiene cohorte propia (pertenece a la Comision, que
    # persiste entre camadas): un recursante de la misma comisión tiene una
    # fila de Progreso por cohorte para el mismo practica_comision. Resolvemos
    # la cohorte "actual" de cada estudiante en esta comisión (la de su
    # inscripción más reciente, mismo criterio que cohorte_de) a partir de las
    # inscripciones ya traídas en una sola query, sin repetir por estudiante.
    cohorte_actual_por_estudiante = {}
    for inscripcion in sorted(
        comision.inscripciones.all(), key=lambda i: (i.fecha_inscripcion, i.id)
    ):
        cohorte_actual_por_estudiante[inscripcion.estudiante_id] = inscripcion.cohorte_id

    # Índice de progresos por PracticaComision y (estudiante, cohorte): el
    # progreso es por cursado, así que dos comisiones que comparten una
    # práctica canónica tienen filas distintas y no se pisan, y dos camadas de
    # la misma comisión tampoco.
    progresos_index = {
        pc.id: {
            (progreso.estudiante_id, progreso.cohorte_id): progreso
            for progreso in pc.progresos.all()
        }
        for pc in pcs
    }

    filas = []
    for inscripcion in comision.inscripciones.all():
        estudiante = inscripcion.estudiante
        practicas_detalle = []
        practicas_completadas = 0
        total_ratio = 0
        total_ratio_resuelto = 0
        total_practicas_computables = 0

        for pc in pcs:
            practica = pc.practica
            ejercicio_practicas = list(practica.ejercicio_practicas.all())
            total_ejercicios = len(ejercicio_practicas)
            cohorte_id = cohorte_actual_por_estudiante.get(estudiante.id)
            progreso = progresos_index[pc.id].get((estudiante.id, cohorte_id))

            if total_ejercicios == 0:
                practicas_detalle.append({
                    'practica': practica,
                    'ejercicio_actual': None,
                    'completada': False,
                    'resueltos_count': 0,
                    'total_ejercicios': 0,
                    'desbloqueo_secuencial': pc.desbloqueo_secuencial,
                })
                continue

            # Ejercicio actual según Progreso (para mostrar en la UI)
            if progreso is None:
                ejercicio_actual = ejercicio_practicas[0]
            elif progreso.ejercicio_practica_actual is None:
                ejercicio_actual = None
            else:
                ejercicio_actual = progreso.ejercicio_practica_actual

            # Avance basado en aprobados por docente
            aprobados_count = sum(
                1 for ep in ejercicio_practicas
                if (estudiante.id, comision.id, ep.id) in aprobados
            )
            completada = aprobados_count == total_ejercicios

            # Avance basado en correctitud efectiva (no requiere corrección manual)
            resueltos_count = sum(
                1 for ep in ejercicio_practicas
                if (estudiante.id, comision.id, ep.id) in resueltos
            )

            if completada:
                practicas_completadas += 1

            total_ratio += aprobados_count / total_ejercicios
            total_ratio_resuelto += resueltos_count / total_ejercicios
            total_practicas_computables += 1

            practicas_detalle.append({
                'practica': practica,
                'ejercicio_actual': ejercicio_actual,
                'completada': completada,
                'resueltos_count': resueltos_count,
                'total_ejercicios': total_ejercicios,
                'desbloqueo_secuencial': pc.desbloqueo_secuencial,
            })

        porcentaje_global = None
        porcentaje_resuelto = None
        if total_practicas_computables > 0:
            porcentaje_global = round((total_ratio / total_practicas_computables) * 100, 1)
            porcentaje_resuelto = round((total_ratio_resuelto / total_practicas_computables) * 100, 1)

        filas.append({
            'estudiante': estudiante,
            'practicas_completadas': practicas_completadas,
            'practicas_totales': len(practicas_por_id),
            'practicas_detalle': practicas_detalle,
            'porcentaje_global': porcentaje_global,
            'porcentaje_resuelto': porcentaje_resuelto,
        })

    filas.sort(key=lambda f: (
        f['estudiante'].last_name.lower(),
        f['estudiante'].first_name.lower(),
        f['estudiante'].username,
    ))
    return filas


@login_required
def comisiones_list(request):
    """Pantalla de entrada del panel docente: una fila por comisión.

    Muestra la camada seleccionada por el docente (default: la activa), no el
    acumulado histórico de todas las camadas. Dos razones:

    - Un recursante tiene una :class:`Inscripcion` por camada en la misma
      comisión; sumar todas las inscripciones lo cuenta dos veces en
      ``cantidad_estudiantes`` y pesa doble (y cruza camadas) en
      ``avance_promedio``/``avance_resuelto``.
    - Es la misma noción de "la comisión ahora mismo" que respeta el resto
      del panel a través de la cohorte de sesión (mismo mecanismo que
      :func:`comision_detail`, vía :func:`_resolver_cohorte_actual`): esta
      pantalla es donde arranca (o continúa) esa selección, así que debe
      contar lo mismo que las demás pantallas van a mostrar.

    Esta también es la puerta de entrada del selector de cohorte y del botón
    "Nueva cohorte" (antes vivían en ``comision_detail``): elegir cohorte es
    una acción global de "modo de vista" de todo el panel, no de una
    comisión puntual, así que corresponde acá y no en el detalle de una
    comisión (ver :func:`_cohortes_del_docente`, :func:`_resolver_cohorte_home`).

    Sin cohorte resuelta (caso raro, ver ``unica_cohorte_activa``), no hay
    "camada en curso" que mostrar: las comisiones aparecen con 0 estudiantes
    en vez de mezclar camadas pasadas para rellenar el número.
    """
    _require_docente(request.user)

    cohorte_actual, cohortes_disponibles = _resolver_cohorte_home(request)

    comisiones = (
        Comision.objects.filter(docentes=request.user)
        .prefetch_related(
            'docentes',
            Prefetch(
                'inscripciones',
                queryset=Inscripcion.objects.filter(cohorte=cohorte_actual).select_related('estudiante'),
            ),
            'practicas_comisiones__practica__ejercicio_practicas',
            'practicas_comisiones__progresos__ejercicio_practica_actual',
        )
        .order_by('nombre')
    )

    # Precalcular aprobados y resueltos para todas las comisiones de una vez
    todos_los_estudiantes_ids = list(
        {i.estudiante_id for c in comisiones for i in c.inscripciones.all()}
    )
    todas_las_comisiones_ids = [c.id for c in comisiones]
    _cohorte_id = cohorte_actual.id if cohorte_actual else None
    aprobados = _aprobados_por_estudiante_ep(
        todas_las_comisiones_ids, todos_los_estudiantes_ids, cohorte_id=_cohorte_id,
    )
    resueltos = _resueltos_por_estudiante_ep(
        todas_las_comisiones_ids, todos_los_estudiantes_ids, cohorte_id=_cohorte_id,
    )

    comisiones_data = []
    for comision in comisiones:
        estudiantes_ids = [i.estudiante_id for i in comision.inscripciones.all()]
        comisiones_data.append({
            'comision': comision,
            'cantidad_estudiantes': len(estudiantes_ids),
            'cantidad_practicas': len(comision.practicas_comisiones.all()),
            'avance_promedio': _calcular_avance_promedio(comision, estudiantes_ids, aprobados),
            'avance_resuelto': _calcular_avance_promedio(comision, estudiantes_ids, resueltos),
            'docentes_display': ', '.join(d.nombre_display for d in comision.docentes.all()),
        })

    # Banco de prácticas: las propias más las marcadas como públicas (banco común),
    # mismo criterio que el selector de importación (_get_practicas_disponibles).
    # Sin excepción para is_staff: el alcance del banco se define por autoría y por
    # es_publica, no por rol, igual que se hizo con las comisiones en 7040945. El
    # admin conserva su permiso de editar/eliminar cualquier práctica; lo que no
    # tiene es un listado global en el panel.
    #
    # Solo originales (practica_origen=None): las prácticas derivadas (importadas con
    # practica_import) son copias de trabajo de una comisión y no deben aparecer aquí;
    # si el docente las modifica, se desanclan automáticamente con
    # _desanclar_si_derivada() y vuelven a aparecer.
    mis_practicas = list(
        Practica.objects
        .filter(Q(creada_por=request.user) | Q(es_publica=True))
        .filter(practica_origen__isnull=True)
        .distinct()
        .select_related('creada_por')
        .prefetch_related('ejercicio_practicas')
        .order_by('titulo')
    )

    # Sobre una práctica pública ajena hay lectura pero no escritura, así que la
    # plantilla esconde "+ Ejercicio": ejercicio_create descarta la preselección con
    # _puede_editar_practica y el ejercicio terminaría creado sin asignar. Se resuelve
    # con una consulta para toda la lista en vez de llamar a _puede_editar_practica
    # por fila.
    ids_editables = set(
        _practicas_editables(request.user)
        .filter(pk__in=[practica.pk for practica in mis_practicas])
        .values_list('pk', flat=True)
    )
    for practica in mis_practicas:
        practica.puede_editar = practica.pk in ids_editables

    # Banco de ejercicios: los propios más los del banco común (es_publico), mismo
    # criterio que el banco de prácticas y que el selector de ejercicios
    # (EjercicioPracticaForm en docentes/forms.py). Tampoco hay rama is_staff.
    # Los ejercicios ajenos son de solo lectura: la plantilla oculta Editar/Eliminar
    # porque ejercicio_edit/ejercicio_delete exigen ser el autor (o admin).
    mis_ejercicios = (
        Ejercicio.objects
        .filter(Q(creado_por=request.user) | Q(es_publico=True))
        .distinct()
        .select_related('creado_por')
        .order_by('-fecha_creacion')
    )

    # Correcciones pendientes: intentos correctos sin revisión docente
    pendientes_count = Intento.objects.filter(
        es_correcto=True,
        aprobado_docente__isnull=True,
        practica_comision__comision__docentes=request.user,
    ).count()

    return render(request, 'docentes/comisiones_list.html', {
        'comisiones_data': comisiones_data,
        'mis_practicas': mis_practicas,
        'mis_ejercicios': mis_ejercicios,
        'pendientes_count': pendientes_count,
        'cohorte_actual': cohorte_actual,
        'cohortes_disponibles': cohortes_disponibles,
        'siguiente_cohorte': _siguiente_cohorte(),
    })


def _siguiente_cohorte():
    """(anio, cuatrimestre) del cuatrimestre siguiente al activo.

    Si la activa es C1, propone C2 del mismo año; si es C2, propone C1 del
    año siguiente. Sin cohorte activa, propone el cuatrimestre en curso según
    la fecha de hoy.
    """
    from cursos.cohortes import cohorte_activa
    activa = cohorte_activa()
    if activa is None:
        hoy = timezone.localdate()
        return hoy.year, (1 if hoy.month <= 7 else 2)
    if activa.cuatrimestre == 1:
        return activa.anio, 2
    return activa.anio + 1, 1


@login_required
@require_POST
def cohorte_create(request):
    """Crea una cohorte y la marca activa. Solo superusuarios.

    Crear una cohorte es global: cambia cuál es la cohorte activa para toda la
    plataforma, no solo para la comisión desde la que se dispara. Por eso el
    gate es ``is_superuser`` y no ``is_staff`` como en el resto del panel.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    form = CohorteForm(request.POST)
    # `next` viene del cliente: validarlo contra el host propio evita convertir
    # esta vista en un open redirect. Mismo criterio que el resto del panel.
    destino = _resolver_url_retorno(request) or reverse('docentes:comisiones_list')

    if not form.is_valid():
        for error in form.errors.get('__all__', []) or ['No se pudo crear la cohorte.']:
            messages.error(request, error)
        return redirect(destino)

    with transaction.atomic():
        Cohorte.objects.filter(activa=True).update(activa=False)
        cohorte = form.save(commit=False)
        cohorte.activa = True
        cohorte.save()

    # La cohorte fijada en sesión (si había alguna) puede ser justo la que se
    # acaba de cerrar. Sin este pop, el panel seguiría mostrando esa camada
    # vieja en vez de la nueva activa hasta que el docente la reseleccionara a
    # mano: crear una cohorte es la acción que debería "saltar" la vista a la
    # nueva por default (ver _resolver_cohorte_actual, que cae a la activa
    # cuando no hay cohorte en sesión).
    request.session.pop('cohorte_id', None)

    messages.success(request, f'Cohorte {cohorte} creada y marcada como activa.')
    return redirect(destino)


@login_required
def comision_create(request):
    _require_docente(request.user)

    form = ComisionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        comision = form.save()
        if request.user.es_docente:
            comision.docentes.add(request.user)
        # Agregar docentes adicionales seleccionados en el form de creación
        docentes_ids = request.POST.getlist('docentes_adicionales')
        if docentes_ids:
            docentes_validos = Usuario.objects.filter(
                pk__in=docentes_ids, es_docente=True
            )
            for docente in docentes_validos:
                comision.docentes.add(docente)
        messages.success(request, 'Comisión creada correctamente.')
        return redirect('docentes:comision_detail', comision_id=comision.id)

    docentes_disponibles = Usuario.objects.filter(es_docente=True).exclude(
        pk=request.user.pk
    ).order_by('username')
    return render(request, 'docentes/comision_form.html', {
        'form': form,
        'modo': 'crear',
        'docentes_disponibles': docentes_disponibles,
    })


def _build_practicas_con_form(comision, user):
    """Prepara un EjercicioPracticaForm por cada práctica de la comisión."""
    pcs = list(comision.practicas_comisiones.select_related('practica').order_by('orden'))
    result = []
    for pc in pcs:
        practica = pc.practica
        add_form = EjercicioPracticaForm(usuario=user)
        add_form.fields['practica'].initial = practica
        add_form.fields['practica'].widget = add_form.fields['practica'].hidden_widget()
        result.append({'practica': practica, 'pc': pc, 'add_form': add_form})
    return result


def _cohortes_de_comision(comision):
    """Cohortes ofrecibles en el selector de esta comisión, más nuevas primero.

    Son las que tienen al menos una inscripción acá, **más la activa**, aunque
    todavía no tenga a nadie inscripto. Incluirla siempre resuelve dos cosas:

    - El default de :func:`_resolver_cohorte` es la activa, así que sin esto una
      comisión sin inscriptos en la camada en curso mostraría datos de una
      cohorte ausente del ``<select>``: ninguna ``<option>`` quedaría marcada y
      el desplegable diría una cosa mientras la página muestra otra.
    - Las altas actúan sobre la cohorte que se está viendo. Si al abrir un
      cuatrimestre nuevo el panel cayera en la cohorte anterior, el primer
      estudiante que se diera de alta entraría en la camada equivocada.
    """
    from cursos.cohortes import cohorte_activa

    cohortes = {
        c.pk: c
        for c in Cohorte.objects.filter(inscripciones__comision=comision).distinct()
    }
    activa = cohorte_activa()
    if activa is not None:
        cohortes.setdefault(activa.pk, activa)

    return sorted(
        cohortes.values(),
        key=lambda c: (c.anio, c.cuatrimestre),
        reverse=True,
    )


def _resolver_cohorte(param, comision):
    """Cohorte a mostrar: la del querystring si es válida, si no la activa.

    Un id inexistente o sin inscripciones en esta comisión cae a la activa en
    silencio: es navegación, no un error del que haya que avisar.

    Función pura, sin acceso a la sesión: la mantenemos así porque hay tests
    que la llaman directamente con un ``param`` explícito. Las vistas del
    panel no la llaman más a ella directamente; llaman a
    :func:`_resolver_cohorte_sesion`, que le agrega persistencia en sesión
    reusando esta misma lógica de "querystring válido o no" a través de
    :func:`_resolver_cohorte_actual`.
    """
    from cursos.cohortes import cohorte_activa

    disponibles = _cohortes_de_comision(comision)
    if param and str(param).isdigit():
        elegida = next((c for c in disponibles if c.pk == int(param)), None)
        if elegida is not None:
            return elegida, disponibles
    activa = cohorte_activa()
    if activa is not None:
        return activa, disponibles
    return (disponibles[0] if disponibles else None), disponibles


def _cohortes_del_docente(user):
    """Cohortes ofrecibles en el selector del home, más nuevas primero.

    Mismo criterio que :func:`_cohortes_de_comision`, pero para todas las
    comisiones del docente en vez de una sola: el selector de cohorte vive en
    el home del panel (:func:`comisiones_list`) desde que dejó de ser un
    parámetro por comisión y pasó a ser el "modo de vista" de todo el panel,
    así que sus opciones tienen que cubrir todo lo que ese docente puede ver.

    Son las cohortes con al menos una inscripción en alguna comisión propia,
    más la activa, aunque todavía no tenga inscriptos: mismo motivo que en
    ``_cohortes_de_comision`` — sin esto, el default (la activa) podría faltar
    del ``<select>`` mientras el resto del panel ya la está usando.
    """
    from cursos.cohortes import cohorte_activa

    cohortes = {
        c.pk: c
        for c in Cohorte.objects.filter(
            inscripciones__comision__docentes=user,
        ).distinct()
    }
    activa = cohorte_activa()
    if activa is not None:
        cohortes.setdefault(activa.pk, activa)

    return sorted(
        cohortes.values(),
        key=lambda c: (c.anio, c.cuatrimestre),
        reverse=True,
    )


def _resolver_cohorte_actual(request, disponibles):
    """Cohorte de vista del panel: querystring > sesión > activa.

    Implementa la selección global de cohorte (elegida una vez, respetada por
    todas las pantallas): la usan :func:`_resolver_cohorte_sesion` (por
    comisión) y :func:`_resolver_cohorte_home` (desde el home, sin comisión
    puntual), cada una con su propio cálculo de ``disponibles``.

    - ``?cohorte=<id>`` es el override explícito: si matchea alguna cohorte de
      ``disponibles``, se usa y además se persiste en
      ``request.session['cohorte_id']``, para que entrar a otra pantalla o
      volver atrás no pierda la selección.
    - Sin querystring (o con uno inválido: id inexistente o fuera de
      ``disponibles``), se lee la sesión. Un querystring inválido NO consulta
      la sesión: cae derecho a la activa, en silencio, igual que hacía la
      resolución por querystring antes de que existiera la persistencia.
    - Si la cohorte de la sesión ya no existe (se borró), se limpia la sesión
      y se sigue como si no hubiera sesión, sin romper.
    - Sin sesión (o recién limpiada), cae a la activa; sin activa, a la
      primera de ``disponibles``.

    Args:
        request: request HTTP actual (se lee y eventualmente se escribe su
            sesión).
        disponibles: cohortes ofrecibles en el contexto que llama.

    Returns:
        Cohorte | None: la cohorte resuelta.
    """
    from cursos.cohortes import cohorte_activa

    param = request.GET.get('cohorte')
    if param and str(param).isdigit():
        elegida = next((c for c in disponibles if c.pk == int(param)), None)
        if elegida is not None:
            request.session['cohorte_id'] = elegida.pk
            return elegida
    else:
        sesion_id = request.session.get('cohorte_id')
        if sesion_id is not None:
            de_sesion = Cohorte.objects.filter(pk=sesion_id).first()
            if de_sesion is not None:
                return de_sesion
            # La cohorte de la sesión ya no existe (se borró): no dejar una
            # referencia colgada para el próximo request.
            del request.session['cohorte_id']

    activa = cohorte_activa()
    if activa is not None:
        return activa
    return disponibles[0] if disponibles else None


def _resolver_cohorte_sesion(request, comision):
    """Envoltorio de :func:`_resolver_cohorte_actual` para una comisión puntual.

    Misma forma de retorno que :func:`_resolver_cohorte` (tupla cohorte +
    disponibles), pero con persistencia en sesión. La usan las vistas del
    panel que antes resolvían con
    ``_resolver_cohorte(request.GET.get('cohorte'), comision)`` directamente;
    esa función pura sigue sin cambios (la siguen usando los tests que
    resuelven por parámetro explícito, sin request).
    """
    disponibles = _cohortes_de_comision(comision)
    return _resolver_cohorte_actual(request, disponibles), disponibles


def _resolver_cohorte_home(request):
    """Cohorte de vista del panel, resuelta desde el home (sin comisión).

    Es donde arranca (o continúa) la selección global: mismo mecanismo que
    :func:`_resolver_cohorte_sesion`, con :func:`_cohortes_del_docente` en vez
    de :func:`_cohortes_de_comision` porque acá no hay una sola comisión de la
    que sacar las opciones ofrecibles — son las de todas las del docente.
    """
    disponibles = _cohortes_del_docente(request.user)
    return _resolver_cohorte_actual(request, disponibles), disponibles


def _recursantes_disponibles(comision, cohorte):
    """Estudiantes con historial en otra camada de esta comisión, sin
    inscripción en la cohorte que se está viendo.

    Son las cuentas ofrecibles en el camino 1 de reinscripción (el ``<select>``
    de recursantes en :func:`estudiante_reinscribir_recursante`): ya son
    visibles para este docente en el panel -aparecen en el historial de esta
    misma comisión-, así que ofrecerlas acá no expone nada que el docente no
    pudiera ver antes.

    Args:
        comision: comisión sobre la que se busca historial.
        cohorte: cohorte que se está viendo (se excluyen quienes ya están
            inscriptos en ella). ``None`` (sin cohorte activa ni disponible)
            devuelve un queryset vacío.

    Returns:
        QuerySet[Usuario]: estudiantes reinscribibles, ordenados por nombre.
    """
    if cohorte is None:
        return Usuario.objects.none()
    return (
        Usuario.objects.filter(
            inscripciones__comision=comision, es_docente=False, is_staff=False,
        )
        .exclude(inscripciones__cohorte=cohorte)
        .distinct()
        .order_by('last_name', 'first_name', 'username')
    )


def _get_practicas_disponibles(user):
    """Devuelve prácticas propias del docente + las del banco común, para importar.

    Solo incluye prácticas "originales" (practica_origen=None). Las prácticas
    derivadas (importadas de otra) no aparecen en el banco: se consideran copias
    de trabajo de una comisión específica. Si el docente modifica una derivada,
    ésta se desancla y vuelve a aparecer aquí como práctica independiente.
    """
    if user.is_staff:
        return (
            Practica.objects
            .filter(practica_origen__isnull=True)
            .select_related('creada_por')
            .prefetch_related('ejercicio_practicas')
            .order_by('titulo')
        )
    return (
        Practica.objects
        .filter(Q(creada_por=user) | Q(es_publica=True))
        .filter(practica_origen__isnull=True)
        .distinct()
        .select_related('creada_por')
        .prefetch_related('ejercicio_practicas')
        .order_by('titulo')
    )


@login_required
def comision_detail(request, comision_id):
    _require_docente(request.user)

    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, cohortes_disponibles = _resolver_cohorte_sesion(request, comision)

    comision = get_object_or_404(
        Comision.objects.prefetch_related(
            'docentes',
            Prefetch(
                'inscripciones',
                queryset=Inscripcion.objects
                    .filter(cohorte=cohorte)
                    .select_related('estudiante', 'estudiante__encuesta')
                    .order_by('estudiante__last_name', 'estudiante__first_name', 'estudiante__username'),
            ),
            Prefetch(
                'practicas_comisiones',
                queryset=PracticaComision.objects.order_by('orden').select_related('practica').prefetch_related(
                    Prefetch(
                        'practica__ejercicio_practicas',
                        queryset=EjercicioPractica.objects.order_by('orden'),
                    ),
                    Prefetch(
                        'progresos',
                        queryset=Progreso.objects.filter(cohorte=cohorte).select_related('ejercicio_practica_actual'),
                    ),
                ),
            ),
        ),
        pk=comision_id,
    )

    estudiantes_ids = [i.estudiante_id for i in comision.inscripciones.all()]
    _cohorte_id = cohorte.id if cohorte else None
    aprobados = _aprobados_por_estudiante_ep([comision.id], estudiantes_ids, cohorte_id=_cohorte_id)
    resueltos = _resueltos_por_estudiante_ep([comision.id], estudiantes_ids, cohorte_id=_cohorte_id)
    progreso_estudiantes = _build_progreso_estudiantes(comision, aprobados, resueltos)
    practicas_con_form = _build_practicas_con_form(comision, request.user)
    practicas_disponibles = _get_practicas_disponibles(request.user)

    # Docentes ya asignados y formulario para agregar nuevos
    docentes_actuales = list(comision.docentes.all())
    docente_form = DocenteComisionForm()
    # Excluir del select a los docentes ya asignados
    ids_actuales = [d.pk for d in docentes_actuales]
    docente_form.fields['docente'].queryset = Usuario.objects.filter(
        es_docente=True
    ).exclude(pk__in=ids_actuales).order_by('username')

    from accounts.models import ConfigSitio
    _ids = [comision.id]
    cfg = ConfigSitio.get()

    # Analíticas con cache de 5 minutos (cómputo intensivo sobre tabla Intento).
    # La clave incluye la cohorte: sin eso, ver primero la camada anterior y
    # después la activa (o viceversa) serviría desde caché los números de una
    # camada dentro de otra durante el TTL completo, en silencio.
    _ANALITICAS_TTL = 300
    _cache_key = f'analiticas_{comision_id}_{cohorte.pk if cohorte else 0}'
    analiticas = cache.get(_cache_key)
    if analiticas is None:
        # Esta vista es por cohorte (a diferencia del dashboard de analiticas,
        # que agrega varias comisiones): se pasa _cohorte_id para que las
        # ocho funciones no mezclen, en un recursante, los intentos de su
        # camada anterior con los de la que se está mirando.
        _silencio_cd = _silencio_temprano(_ids, estudiantes_ids, cohorte_id=_cohorte_id)
        analiticas = {
            'ejercicios_dificiles':  _ejercicios_mas_dificiles(
                _ids, estudiantes_ids, min_intentos=cfg.umbral_min_intentos, cohorte_id=_cohorte_id,
            ),
            'en_riesgo':             _estudiantes_en_riesgo(
                _ids, estudiantes_ids, umbral_riesgo=cfg.umbral_riesgo, cohorte_id=_cohorte_id,
            ),
            'distribucion_intentos': _distribucion_intentos(_ids, estudiantes_ids, cohorte_id=_cohorte_id),
            'evolucion_temporal':    _evolucion_temporal(_ids, estudiantes_ids, cohorte_id=_cohorte_id),
            'errores_sistematicos':  _errores_sistematicos(
                _ids, estudiantes_ids, min_estudiantes=cfg.error_consenso_min, cohorte_id=_cohorte_id,
            ),
            'silencio':              _silencio_cd,
            'silencio_resumen':      _silencio_resumen(
                _silencio_cd, umbral_silencio_dias=cfg.umbral_silencio_dias,
            ),
            'concentracion':         _concentracion_practica(
                _ids, estudiantes_ids, umbral_maraton=cfg.umbral_maraton, cohorte_id=_cohorte_id,
            ),
            'velocidad':             _velocidad_arranque(
                _ids, estudiantes_ids, umbral_arranque_dias=cfg.umbral_arranque_dias, cohorte_id=_cohorte_id,
            ),
        }
        cache.set(_cache_key, analiticas, _ANALITICAS_TTL)

    _todos_estudiantes = [i.estudiante for i in comision.inscripciones.all()]
    estudiantes_adaptaciones = [
        e for e in _todos_estudiantes
        if bool(getattr(getattr(e, 'encuesta', None), 'necesita_adecuacion', False))
        or bool(getattr(getattr(e, 'encuesta', None), 'tiene_cud', False))
    ]

    parciales = (
        Parcial.objects
        .filter(comision=comision, cohorte=cohorte)
        .order_by('fecha', 'nombre')
        .annotate(
            total_notas=Count('notas'),
            notas_cargadas=Count('notas', filter=Q(notas__puntaje__isnull=False)),
        )
    )

    return render(request, 'docentes/comision_detail.html', {
        'comision': comision,
        'practicas_con_form': practicas_con_form,
        'practicas_disponibles': practicas_disponibles,
        'estudiantes': _todos_estudiantes,
        'estudiantes_adaptaciones': estudiantes_adaptaciones,
        'progreso_estudiantes': progreso_estudiantes,
        'estudiante_form': EstudianteCreateForm(),
        'importar_form': ImportarEstudiantesForm(),
        'recursantes_disponibles': _recursantes_disponibles(comision, cohorte),
        'docentes_actuales': docentes_actuales,
        'docente_form': docente_form,
        'docentes_display': ', '.join(d.nombre_display for d in docentes_actuales),
        'parciales': parciales,
        'cohorte_actual': cohorte,
        'cohortes_disponibles': cohortes_disponibles,
        'es_cohorte_activa': bool(cohorte and cohorte.activa),
        # Analíticas (cacheadas 5 min por comisión)
        **analiticas,
        # Umbrales visibles en template para documentar criterios al docente
        'cfg_umbral_riesgo':        cfg.umbral_riesgo,
        'cfg_umbral_silencio_dias': cfg.umbral_silencio_dias,
        'cfg_umbral_maraton':       cfg.umbral_maraton,
        'cfg_umbral_arranque_dias': cfg.umbral_arranque_dias,
        'cfg_umbral_min_intentos':  cfg.umbral_min_intentos,
        'cfg_error_consenso_min':   cfg.error_consenso_min,
    })


@login_required
@require_POST
def docente_add(request, comision_id):
    """Agrega un docente a la comisión."""
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    form = DocenteComisionForm(request.POST)
    if form.is_valid():
        docente = form.cleaned_data['docente']
        comision.docentes.add(docente)
        messages.success(request, f'Docente "{docente}" agregado a la comisión.')
    else:
        messages.error(request, 'No se pudo agregar el docente. Verificá la selección.')
    return redirect('docentes:comision_detail', comision_id=comision.id)


@login_required
@require_POST
def docente_remove(request, comision_id, docente_id):
    """Quita un docente de la comisión."""
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    docente = get_object_or_404(Usuario, pk=docente_id, es_docente=True)
    # No permitir que un docente se quite a sí mismo si es el único
    if docente == request.user and comision.docentes.count() <= 1:
        messages.error(request, 'No podés quitarte si sos el único docente de la comisión.')
        return redirect('docentes:comision_detail', comision_id=comision.id)

    comision.docentes.remove(docente)
    messages.success(request, f'Docente "{docente}" quitado de la comisión.')
    return redirect('docentes:comision_detail', comision_id=comision.id)


@login_required
def estudiante_create(request, comision_id):
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, _ = _resolver_cohorte_sesion(request, comision)
    if request.method == 'POST':
        _require_cohorte_activa(cohorte)

    form = EstudianteCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            estudiante = form.save()
            Inscripcion.objects.create(
                estudiante=estudiante, comision=comision, cohorte=cohorte,
            )
        messages.success(request, f'Estudiante {estudiante.username} creado e inscripto.')
        return redirect('docentes:comision_detail', comision_id=comision.id)
    elif request.method == 'POST':
        messages.error(request, 'No se pudo crear el estudiante. Revisá los errores del formulario.')

    _estudiantes_ids = list(
        Usuario.objects.filter(
            inscripciones__comision=comision, inscripciones__cohorte=cohorte,
        ).values_list('id', flat=True)
    )
    _cohorte_id = cohorte.id if cohorte else None
    _aprobados = _aprobados_por_estudiante_ep([comision.id], _estudiantes_ids, cohorte_id=_cohorte_id)
    _resueltos = _resueltos_por_estudiante_ep([comision.id], _estudiantes_ids, cohorte_id=_cohorte_id)
    return render(request, 'docentes/comision_detail.html', {
        'comision': comision,
        'practicas_con_form': _build_practicas_con_form(comision, request.user),
        'practicas_disponibles': _get_practicas_disponibles(request.user),
        'estudiantes': Usuario.objects.filter(
            inscripciones__comision=comision, inscripciones__cohorte=cohorte,
        ).order_by('last_name', 'first_name', 'username'),
        'progreso_estudiantes': _build_progreso_estudiantes(comision, _aprobados, _resueltos),
        'estudiante_form': form,
        'importar_form': ImportarEstudiantesForm(),
        'recursantes_disponibles': _recursantes_disponibles(comision, cohorte),
        'cohorte_actual': cohorte,
        'es_cohorte_activa': bool(cohorte and cohorte.activa),
    })


@login_required
def estudiantes_importar(request, comision_id):
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, _ = _resolver_cohorte_sesion(request, comision)
    if request.method == 'POST':
        _require_cohorte_activa(cohorte)

    form = ImportarEstudiantesForm(request.POST or None, request.FILES or None)
    reporte = None
    if request.method == 'POST' and form.is_valid():
        try:
            reporte = _procesar_importacion_estudiantes(form.cleaned_data['archivo'], comision, cohorte)
            messages.info(
                request,
                f"Importación finalizada: {reporte['importadas']} importadas, "
                f"{reporte['fallidas']} fallidas.",
            )
        except RuntimeError as error:
            messages.error(request, str(error))
    elif request.method == 'POST':
        messages.error(request, 'No se pudo procesar el archivo de importación.')

    _estudiantes_ids = list(
        Usuario.objects.filter(
            inscripciones__comision=comision, inscripciones__cohorte=cohorte,
        ).values_list('id', flat=True)
    )
    _cohorte_id = cohorte.id if cohorte else None
    _aprobados = _aprobados_por_estudiante_ep([comision.id], _estudiantes_ids, cohorte_id=_cohorte_id)
    _resueltos = _resueltos_por_estudiante_ep([comision.id], _estudiantes_ids, cohorte_id=_cohorte_id)
    return render(request, 'docentes/comision_detail.html', {
        'comision': comision,
        'practicas_con_form': _build_practicas_con_form(comision, request.user),
        'practicas_disponibles': _get_practicas_disponibles(request.user),
        'estudiantes': Usuario.objects.filter(
            inscripciones__comision=comision, inscripciones__cohorte=cohorte,
        ).order_by('last_name', 'first_name', 'username'),
        'progreso_estudiantes': _build_progreso_estudiantes(comision, _aprobados, _resueltos),
        'estudiante_form': EstudianteCreateForm(),
        'importar_form': form,
        'reporte_importacion': reporte,
        'recursantes_disponibles': _recursantes_disponibles(comision, cohorte),
        'cohorte_actual': cohorte,
        'es_cohorte_activa': bool(cohorte and cohorte.activa),
    })


def _render_pase_pendiente(request, comision, cohorte, candidato):
    """Re-renderiza el panel con la pantalla de confirmación del camino 2 de
    reinscripción (búsqueda por usuario/email).

    Se llama cuando la búsqueda encontró una cuenta válida pero todavía no se
    confirmó la inscripción: ``pase_pendiente`` en el contexto le muestra al
    docente el nombre resuelto antes de que la acción sea definitiva. Mismo
    patrón de reconstrucción parcial de contexto que usan ``estudiante_create``
    y ``estudiantes_importar`` al re-renderizar tras un POST.
    """
    _estudiantes_ids = list(
        Usuario.objects.filter(
            inscripciones__comision=comision, inscripciones__cohorte=cohorte,
        ).values_list('id', flat=True)
    )
    _cohorte_id = cohorte.id if cohorte else None
    _aprobados = _aprobados_por_estudiante_ep([comision.id], _estudiantes_ids, cohorte_id=_cohorte_id)
    _resueltos = _resueltos_por_estudiante_ep([comision.id], _estudiantes_ids, cohorte_id=_cohorte_id)
    return render(request, 'docentes/comision_detail.html', {
        'comision': comision,
        'practicas_con_form': _build_practicas_con_form(comision, request.user),
        'practicas_disponibles': _get_practicas_disponibles(request.user),
        'estudiantes': Usuario.objects.filter(
            inscripciones__comision=comision, inscripciones__cohorte=cohorte,
        ).order_by('last_name', 'first_name', 'username'),
        'progreso_estudiantes': _build_progreso_estudiantes(comision, _aprobados, _resueltos),
        'estudiante_form': EstudianteCreateForm(),
        'importar_form': ImportarEstudiantesForm(),
        'recursantes_disponibles': _recursantes_disponibles(comision, cohorte),
        'pase_pendiente': candidato,
        'cohorte_actual': cohorte,
        'es_cohorte_activa': bool(cohorte and cohorte.activa),
    })


@login_required
@require_POST
def estudiante_reinscribir_recursante(request, comision_id):
    """Re-inscribe como recursante a una cuenta con historial en otra camada
    de esta misma comisión (camino 1 de reinscripción).

    El nombre y username del candidato ya están a la vista en el ``<select>``
    que alimenta este POST (ver :func:`_recursantes_disponibles`), así que un
    ``confirm()`` de JS en el template alcanza como confirmación: a diferencia
    del camino 2 (:func:`estudiante_reinscribir_pase`), acá no hace falta un
    paso de servidor extra para mostrar de quién se trata.

    Mismo permiso que el resto de las altas de esta comisión (docente de la
    comisión o staff) y misma guarda de cohorte activa: una camada cerrada no
    crece.
    """
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, _ = _resolver_cohorte_sesion(request, comision)
    _require_cohorte_activa(cohorte)

    destino = _resolver_url_retorno(request) or reverse(
        'docentes:comision_detail', kwargs={'comision_id': comision.id},
    )

    estudiante_id = (request.POST.get('estudiante_id') or '').strip()
    estudiante = (
        _recursantes_disponibles(comision, cohorte).filter(pk=estudiante_id).first()
        if estudiante_id.isdigit() else None
    )
    if estudiante is None:
        messages.error(request, 'Seleccioná un recursante válido de la lista.')
        return redirect(destino)

    Inscripcion.objects.create(estudiante=estudiante, comision=comision, cohorte=cohorte)
    messages.success(
        request,
        f'{estudiante.nombre_display} ({estudiante.username}) re-inscripto en {cohorte}.',
    )
    return redirect(destino)


@login_required
@require_POST
def estudiante_reinscribir_pase(request, comision_id):
    """Busca por usuario o email EXACTO una cuenta existente (de otra
    comisión) para re-inscribirla como recursante en la cohorte actual de
    esta comisión (camino 2 de reinscripción; ver
    :func:`estudiante_reinscribir_recursante` para el camino 1).

    Deliberadamente sin ``icontains`` ni listado de candidatos: con búsqueda
    parcial un docente podría tantear el padrón de cuentas ajenas escribiendo
    prefijos. El docente tiene que saber el dato de antemano.

    A diferencia del camino 1 -donde el nombre ya está a la vista en el
    ``<select>``-, acá el docente escribe un identificador a ciegas y no sabe
    a quién corresponde hasta que el servidor lo resuelve. Por eso el flujo es
    de dos pasos:

    1. POST inicial (sin ``confirmar``): busca por ``identificador``. Si
       encuentra una cuenta válida, NO inscribe todavía: re-renderiza el panel
       con una pantalla de confirmación que muestra el nombre resuelto
       (``pase_pendiente`` en el contexto, vía :func:`_render_pase_pendiente`).
    2. POST de confirmación (``confirmar=1`` + ``estudiante_id`` ya resuelto):
       recién ahí crea la ``Inscripcion``.

    Así el docente ve de quién se trata antes de que la acción sea definitiva,
    en vez de confiar a ciegas en lo que tipeó. Es deliberadamente más pesado
    que el ``confirm()`` de JS del camino 1: ahí alcanza porque el nombre ya
    está en pantalla; acá el nombre es justamente lo que hay que revelar antes
    de confirmar.
    """
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, _ = _resolver_cohorte_sesion(request, comision)
    _require_cohorte_activa(cohorte)

    destino = _resolver_url_retorno(request) or reverse(
        'docentes:comision_detail', kwargs={'comision_id': comision.id},
    )

    if request.POST.get('confirmar'):
        estudiante_id = (request.POST.get('estudiante_id') or '').strip()
        candidato = (
            Usuario.objects.filter(pk=estudiante_id, es_docente=False, is_staff=False).first()
            if estudiante_id.isdigit() else None
        )
        if candidato is None:
            messages.error(request, 'No se pudo confirmar la inscripción: la cuenta ya no está disponible.')
            return redirect(destino)
        if Inscripcion.objects.filter(estudiante=candidato, comision=comision, cohorte=cohorte).exists():
            messages.info(
                request,
                f'{candidato.nombre_display} ({candidato.username}) ya está inscripto '
                'en esta comisión en la cohorte actual.',
            )
            return redirect(destino)
        Inscripcion.objects.create(estudiante=candidato, comision=comision, cohorte=cohorte)
        messages.success(
            request,
            f'{candidato.nombre_display} ({candidato.username}) re-inscripto en {cohorte}.',
        )
        return redirect(destino)

    identificador = (request.POST.get('identificador') or '').strip()
    if not identificador:
        messages.error(request, 'Ingresá un usuario o email para buscar.')
        return redirect(destino)

    candidato = Usuario.objects.filter(
        Q(username=identificador) | Q(email__iexact=identificador)
    ).first()

    if candidato is None:
        messages.error(request, f'No existe ninguna cuenta con usuario o email "{identificador}".')
        return redirect(destino)
    if candidato.es_docente or candidato.is_staff:
        messages.error(
            request,
            f'La cuenta "{identificador}" pertenece a un docente o a personal del staff, no a un estudiante.',
        )
        return redirect(destino)
    if Inscripcion.objects.filter(estudiante=candidato, comision=comision, cohorte=cohorte).exists():
        messages.info(
            request,
            f'{candidato.nombre_display} ({candidato.username}) ya está inscripto '
            'en esta comisión en la cohorte actual.',
        )
        return redirect(destino)

    return _render_pase_pendiente(request, comision, cohorte, candidato)


@login_required
def estudiantes_exportar(request, comision_id):
    """Exporta estudiantes de una comisión en formato XLSX.

    Acota a la cohorte que se está viendo (``?cohorte=`` o, sin ese
    parámetro, la activa), con el mismo criterio que el resto del panel
    (:func:`_resolver_cohorte`). Sin este filtro, un recursante con dos
    ``Inscripcion`` en la comisión aparecía dos veces y el XLSX mezclaba
    camadas — el ``exportar_cohorte`` management command ya se corrigió para
    esto; este botón del panel no lo tenía.
    """
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, _ = _resolver_cohorte_sesion(request, comision)

    try:
        from openpyxl import Workbook
    except ModuleNotFoundError as error:
        raise RuntimeError('openpyxl no está instalado en el entorno actual.') from error

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Estudiantes'
    worksheet.append(['DNI', 'Apellido', 'Nombre', 'Correo electrónico'])

    estudiantes = (
        Usuario.objects.filter(
            inscripciones__comision=comision, inscripciones__cohorte=cohorte,
            es_docente=False, is_staff=False,
        )
        .select_related('encuesta')
        .order_by('last_name', 'first_name', 'username')
    )
    for estudiante in estudiantes:
        encuesta = getattr(estudiante, 'encuesta', None)
        worksheet.append([
            (encuesta.dni if encuesta else '') or '',
            estudiante.last_name or '',
            estudiante.first_name or '',
            estudiante.email or '',
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename=\"comision_{comision.id}_estudiantes.xlsx\"'
    )
    workbook.save(response)
    return response


@login_required
def estudiante_edit(request, comision_id, estudiante_id):
    """Edita los datos básicos de un estudiante inscripto en la comisión.

    Un recursante tiene dos filas de :class:`Inscripcion` en esta comisión
    (una por cohorte). El estudiante se busca aparte de la verificación de
    pertenencia para no hacer un join que devuelva dos filas: los datos que
    se editan acá son del ``Usuario`` (no de la inscripción puntual), así que
    alcanza con que pertenezca a la comisión en cualquier cohorte.
    """
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    estudiante = get_object_or_404(
        Usuario.objects.filter(es_docente=False, is_staff=False),
        pk=estudiante_id,
    )
    if not Inscripcion.objects.filter(estudiante=estudiante, comision=comision).exists():
        raise Http404('El estudiante no está inscripto en esta comisión.')

    form = EstudianteEditForm(request.POST or None, instance=estudiante)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Datos de {estudiante.username} actualizados.')
        return redirect('docentes:comision_detail', comision_id=comision.id)

    return render(request, 'docentes/estudiante_edit.html', {
        'comision': comision,
        'estudiante': estudiante,
        'form': form,
    })


@login_required
@require_POST
def estudiante_remove(request, comision_id, estudiante_id):
    """Desinscribe a un estudiante de la comisión (no elimina la cuenta).

    Actúa sobre la cohorte que el docente está viendo (``?cohorte=`` en el
    querystring, resuelta igual que en el resto del panel): un recursante
    tiene una :class:`Inscripcion` por camada, y borrar sin filtrar por
    cohorte le arruinaría el historial de la camada que no se está dando de
    baja. ``Progreso`` e ``Intento`` no cuelgan de ``Inscripcion`` (tienen su
    propio FK a ``cohorte``), así que no se ven afectados por este borrado:
    el historial de intentos de esa cohorte queda intacto aunque la
    inscripción se borre.
    """
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    estudiante = get_object_or_404(
        Usuario.objects.filter(es_docente=False, is_staff=False),
        pk=estudiante_id,
    )
    cohorte, _ = _resolver_cohorte_sesion(request, comision)
    eliminadas, _ = Inscripcion.objects.filter(
        estudiante=estudiante, comision=comision, cohorte=cohorte,
    ).delete()
    if not eliminadas:
        raise Http404('El estudiante no está inscripto en esa cohorte de esta comisión.')

    messages.success(request, f'Estudiante {estudiante.username} eliminado de la comisión.')
    return redirect('docentes:comision_detail', comision_id=comision.id)


def _procesar_importacion_estudiantes(archivo, comision, cohorte):
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as error:
        raise RuntimeError('openpyxl no está instalado en el entorno actual.') from error

    reporte = {'procesadas': 0, 'importadas': 0, 'fallidas': 0, 'errores': []}
    workbook = load_workbook(filename=archivo, read_only=True, data_only=True)
    worksheet = workbook.active

    for indice_fila, fila in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
        if not any(fila):
            continue

        reporte['procesadas'] += 1
        username   = (str(fila[0] or '').strip()) if len(fila) > 0 else ''
        email      = (str(fila[1] or '').strip()) if len(fila) > 1 else ''
        password   = (str(fila[2] or '').strip()) if len(fila) > 2 else ''
        first_name = (str(fila[3] or '').strip()) if len(fila) > 3 else ''
        last_name  = (str(fila[4] or '').strip()) if len(fila) > 4 else ''

        form = EstudianteCreateForm(data={
            'username': username,
            'email': email,
            'password': password,
            'first_name': first_name,
            'last_name': last_name,
        })

        if not form.is_valid():
            reporte['fallidas'] += 1
            reporte['errores'].append({
                'fila': indice_fila,
                'motivo': '; '.join(
                    error for errores in form.errors.values() for error in errores
                ),
            })
            continue

        try:
            with transaction.atomic():
                estudiante = form.save()
                Inscripcion.objects.create(
                    estudiante=estudiante, comision=comision, cohorte=cohorte,
                )
        except IntegrityError as error:
            reporte['fallidas'] += 1
            reporte['errores'].append({'fila': indice_fila, 'motivo': str(error)})
            continue

        reporte['importadas'] += 1

    workbook.close()
    return reporte






@login_required
def estudiante_detail(request, estudiante_id):
    """Muestra detalle de intentos de un estudiante para el panel docente."""
    _require_docente(request.user)

    if request.user.is_staff:
        comisiones = Comision.objects.filter(inscripciones__estudiante_id=estudiante_id).distinct().order_by('nombre')
    else:
        comisiones = Comision.objects.filter(
            docentes=request.user,
            inscripciones__estudiante_id=estudiante_id,
        ).distinct().order_by('nombre')

    if not comisiones.exists():
        raise PermissionDenied

    estudiante = get_object_or_404(
        Usuario.objects.filter(pk=estudiante_id, es_docente=False, is_staff=False),
    )

    comision_id = request.GET.get('comision')
    pc_id = request.GET.get('pc')
    context = build_historial_context(
        estudiante=estudiante,
        comisiones=comisiones,
        comision_id=int(comision_id) if comision_id and comision_id.isdigit() else None,
        pc_id=int(pc_id) if pc_id and pc_id.isdigit() else None,
    )

    return render(request, 'docentes/estudiante_detail.html', {'estudiante': estudiante, **context})


@login_required
def correccion_pendiente(request):
    """Lista intentos según el filtro y la comisión seleccionados por el docente.

    Filtros disponibles:
    - auto_correctas (default): es_correcto=True y aprobado_docente=None.
    - mas_fallidos: último intento incorrecto por (estudiante, ejercicio),
      ordenado por cantidad de intentos fallidos descendente.
    - ultimos: todos los intentos incorrectos, más recientes primero.

    Se puede filtrar adicionalmente por comisión (GET param comision_id) y por
    cohorte (GET param cohorte_id, default la activa; "todas las camadas" es
    una opción explícita del desplegable — ver el docstring de la sección de
    filtro de cohorte más abajo, no depende de la cohorte de sesión del resto
    del panel). Solo se muestran intentos de comisiones donde el docente
    autenticado está asignado.
    """
    _require_docente(request.user)

    FILTROS_VALIDOS = {'auto_correctas', 'auto_correctas_revisar', 'mas_fallidos', 'ultimos', 'aprobadas'}
    filtro = request.GET.get('filtro', 'auto_correctas')
    if filtro not in FILTROS_VALIDOS:
        filtro = 'auto_correctas'

    # Todas las comisiones propias del docente (para el desplegable de filtro).
    mis_comisiones = list(
        Comision.objects.filter(docentes=request.user).order_by('nombre')
    )

    # Filtro opcional por comisión.
    comision_filtro = None
    comision_id_raw = request.GET.get('comision_id', '').strip()
    if comision_id_raw and comision_id_raw.isdigit():
        comision_filtro = next(
            (c for c in mis_comisiones if c.id == int(comision_id_raw)), None
        )

    # Prácticas disponibles para filtrar.
    if comision_filtro:
        practicas_filtro_options = list(
            Practica.objects
            .filter(practicas_comisiones__comision=comision_filtro)
            .distinct()
            .order_by('titulo')
        )
    else:
        practicas_filtro_options = list(
            Practica.objects
            .filter(practicas_comisiones__comision__docentes=request.user)
            .distinct()
            .order_by('titulo')
        )

    practica_filtro = None
    practica_id_raw = request.GET.get('practica_id', '').strip()
    if practica_id_raw and practica_id_raw.isdigit():
        practica_filtro = next(
            (p for p in practicas_filtro_options if p.id == int(practica_id_raw)), None
        )

    # EjercicioPracticas para filtrar (solo cuando hay práctica seleccionada).
    ejercicio_practicas_filtro_options = []
    if practica_filtro:
        ejercicio_practicas_filtro_options = list(
            EjercicioPractica.objects
            .filter(practica=practica_filtro)
            .select_related('ejercicio')
            .order_by('orden')
        )

    ejercicio_practica_filtro = None
    ep_id_raw = request.GET.get('ejercicio_practica_id', '').strip()
    if ep_id_raw and ep_id_raw.isdigit():
        ejercicio_practica_filtro = next(
            (ep for ep in ejercicio_practicas_filtro_options if ep.id == int(ep_id_raw)), None
        )

    # Cohortes disponibles para filtrar (narrowed por comisión si hay una
    # elegida, mismo patrón que practicas_filtro_options).
    if comision_filtro:
        cohortes_filtro_options = _cohortes_de_comision(comision_filtro)
    else:
        cohortes_filtro_options = _cohortes_del_docente(request.user)

    # Filtro opcional por cohorte, con default a la activa. Esta pantalla
    # cruzaba TODAS las cohortes a propósito (cada fila trae su badge de
    # cohorte): es lo que permite corregirle a quien rinde un final de una
    # camada anterior. El default reduce ruido en el caso de uso más común
    # -corregir la camada en curso- sin perder esa capacidad: "Todas las
    # camadas" queda como opción explícita del <select>, a un clic.
    #
    # Deliberadamente INDEPENDIENTE de la cohorte de sesión que usa el resto
    # del panel (comision_detail/comisiones_list, ver
    # _resolver_cohorte_sesion): esta pantalla ya cruzaba camadas por diseño,
    # y atarla a esa selección global acoplaría dos cosas separadas. Si un
    # docente dejó el panel mirando una camada vieja (por ejemplo, revisando
    # estadísticas históricas de comision_detail) y entra acá, no debería
    # encontrarse sin correcciones del día a día -el caso de uso más común
    # de esta pantalla- por una selección hecha en otro contexto. El default
    # fijo a la activa es predecible sin importar por dónde se navegó antes.
    #
    # `cohorte_id_presente` distingue "no vino el parámetro" (default: la
    # activa) de "vino vacío / 'todas'" (sin filtro, explícito): con solo
    # `.get(..., '')` no se podría distinguir un primer ingreso de un click
    # en "Todas las camadas".
    cohorte_id_presente = 'cohorte_id' in request.GET
    cohorte_id_raw = request.GET.get('cohorte_id', '').strip()
    if cohorte_id_presente:
        cohorte_filtro = (
            Cohorte.objects.filter(pk=cohorte_id_raw).first()
            if cohorte_id_raw.isdigit() else None
        )
    else:
        from cursos.cohortes import cohorte_activa
        cohorte_filtro = cohorte_activa()

    # Base: solo las comisiones donde el docente está asignado.
    base_qs = Intento.objects.filter(
        practica_comision__comision__docentes=request.user,
    )
    if comision_filtro:
        base_qs = base_qs.filter(practica_comision__comision=comision_filtro)
    if practica_filtro:
        base_qs = base_qs.filter(ejercicio_practica__practica=practica_filtro)
    if ejercicio_practica_filtro:
        base_qs = base_qs.filter(ejercicio_practica=ejercicio_practica_filtro)
    if cohorte_filtro:
        base_qs = base_qs.filter(cohorte=cohorte_filtro)

    estudiante_q = request.GET.get('estudiante_q', '').strip()
    if estudiante_q:
        for token in estudiante_q.split():
            base_qs = base_qs.filter(
                Q(estudiante__first_name__icontains=token)
                | Q(estudiante__last_name__icontains=token)
                | Q(estudiante__username__icontains=token)
            )

    if filtro == 'mas_fallidos':
        # Para cada (estudiante, ejercicio_practica), mostrar únicamente el
        # intento más reciente de aquellos que todavía no lo resolvieron
        # correctamente, ordenado por cantidad de intentos fallidos desc.

        # Subquery: ID del intento más reciente para este combo.
        latest_id_subq = (
            base_qs
            .filter(
                estudiante=OuterRef('estudiante'),
                ejercicio_practica=OuterRef('ejercicio_practica'),
            )
            .order_by('-timestamp')
            .values('id')[:1]
        )

        # Subquery: cantidad de intentos fallidos para este combo.
        failed_count_subq = (
            Intento.objects
            .filter(
                estudiante=OuterRef('estudiante'),
                ejercicio_practica=OuterRef('ejercicio_practica'),
                es_correcto=False,
            )
            .values('estudiante', 'ejercicio_practica')
            .annotate(c=Count('id'))
            .values('c')
        )

        intentos_qs = (
            base_qs
            .filter(es_correcto=False)
            .annotate(
                cant_fallidos=Subquery(failed_count_subq),
                latest_id=Subquery(latest_id_subq),
            )
            .filter(id=F('latest_id'), cant_fallidos__gt=0)
            .order_by('-cant_fallidos', '-timestamp')
        )

    elif filtro == 'ultimos':
        # Todos los intentos incorrectos, más recientes primero.
        intentos_qs = base_qs.filter(es_correcto=False).order_by('-timestamp')

    elif filtro == 'aprobadas':
        # Intentos ya aprobados por el docente, para poder corregir errores.
        intentos_qs = base_qs.filter(aprobado_docente=True).order_by('-timestamp')

    elif filtro == 'auto_correctas_revisar':
        # Correctos automáticamente pero con diccionario que Groq marcó para revisar.
        # Esta sección NO se ve afectada por la aprobación en bloque.
        intentos_qs = (
            base_qs
            .filter(es_correcto=True, aprobado_docente__isnull=True, revision_diccionario='revisar')
            .order_by('timestamp')
        )

    else:  # auto_correctas (default)
        # Excluir los que Groq marcó para revisión del diccionario (van a su propia sección).
        intentos_qs = (
            base_qs
            .filter(es_correcto=True, aprobado_docente__isnull=True)
            .exclude(revision_diccionario='revisar')
            .order_by('timestamp')
        )

    intentos_qs_paginados = intentos_qs.select_related(
        'estudiante',
        'ejercicio_practica__ejercicio',
        'ejercicio_practica__practica',
        'practica_comision__comision',
        # Esta vista cruza todas las cohortes a propósito: hay que poder
        # corregirle a quien rinde un final de una camada anterior. El badge
        # de cohorte en cada fila es lo que dice de qué camada es cada quien.
        'cohorte',
    )

    # Paginación: 25 correcciones por página para evitar páginas muy pesadas.
    paginator = Paginator(intentos_qs_paginados, 25)
    try:
        page_obj = paginator.page(request.GET.get('pagina', 1))
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    # Enriquecer solo los intentos de la página actual.
    for intento in page_obj:
        tipo = intento.ejercicio_practica.ejercicio.tipo
        if tipo == 'tabla_verdad':
            try:
                intento.enunciados_parsed = json.loads(intento.respuesta_raw)
            except (ValueError, TypeError):
                intento.enunciados_parsed = None
        else:
            intento.enunciados_parsed = None
        if tipo == 'determinacion_verdad':
            dic = intento.diccionario or {}
            vv = intento.valores_verdad or {}
            intento.diccionario_con_valores = [
                {'letra': letra, 'frase': frase, 'valor': vv.get(letra)}
                for letra, frase in dic.items()
            ]
        else:
            intento.diccionario_con_valores = None

    total = intentos_qs.count()

    # Comisiones con auto_correctas pendientes (para el bulk approval).
    comisiones_con_pendientes = []
    if filtro == 'auto_correctas':
        comisiones_con_pendientes = list(
            Comision.objects
            .filter(
                docentes=request.user,
                practicas_comisiones__intentos__es_correcto=True,
                practicas_comisiones__intentos__aprobado_docente__isnull=True,
            )
            .distinct()
            .order_by('nombre')
        )

    _filtros_query_params = {'filtro': filtro}
    if comision_filtro:
        _filtros_query_params['comision_id'] = comision_filtro.id
    if practica_filtro:
        _filtros_query_params['practica_id'] = practica_filtro.id
    if ejercicio_practica_filtro:
        _filtros_query_params['ejercicio_practica_id'] = ejercicio_practica_filtro.id
    if estudiante_q:
        _filtros_query_params['estudiante_q'] = estudiante_q
    # El default (la activa) también se fija explícitamente en la query de
    # paginación/navegación: sin esto, "Todas las camadas" (cohorte_id=todas)
    # se perdería al pasar de página, porque la ausencia del parámetro cae de
    # nuevo al default en vez de mantenerse en "todas".
    if cohorte_id_presente:
        _filtros_query_params['cohorte_id'] = cohorte_id_raw or 'todas'
    elif cohorte_filtro:
        _filtros_query_params['cohorte_id'] = cohorte_filtro.id
    filtros_query = urlencode(_filtros_query_params)

    return render(request, 'docentes/correccion_pendiente.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'total': total,
        'filtro': filtro,
        'mis_comisiones': mis_comisiones,
        'comision_filtro': comision_filtro,
        'practica_filtro': practica_filtro,
        'practicas_filtro_options': practicas_filtro_options,
        'ejercicio_practica_filtro': ejercicio_practica_filtro,
        'ejercicio_practicas_filtro_options': ejercicio_practicas_filtro_options,
        'cohorte_filtro': cohorte_filtro,
        'cohortes_filtro_options': cohortes_filtro_options,
        'estudiante_q': estudiante_q,
        'comisiones_con_pendientes': comisiones_con_pendientes,
        'filtros_query': filtros_query,
    })


@login_required
def ejercicio_descargar(request, ejercicio_id):
    """Descarga un ejercicio visible como paquete portable."""
    _require_docente(request.user)
    ejercicio = get_object_or_404(Ejercicio, pk=ejercicio_id)
    if not (
        request.user.is_staff
        or ejercicio.creado_por_id == request.user.id
        or ejercicio.es_publico
    ):
        raise PermissionDenied
    return _respuesta_paquete(
        paquete_ejercicio(ejercicio),
        f'ejercicio-{ejercicio.id}',
    )


@login_required
def practica_descargar(request, practica_id):
    """Descarga una práctica visible con todos sus ejercicios."""
    _require_docente(request.user)
    practica = get_object_or_404(Practica, pk=practica_id)
    if not _puede_ver_practica(request.user, practica):
        raise PermissionDenied
    return _respuesta_paquete(
        paquete_practica(practica),
        practica.titulo,
    )


@login_required
@require_POST
def paquete_instalar(request):
    """Instala un ZIP como copia privada en el banco del docente."""
    _require_docente(request.user)
    form = InstalarPaqueteForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(
            request,
            'No se pudo instalar el paquete: '
            + '; '.join(
                mensaje
                for errores in form.errors.values()
                for mensaje in errores
            ),
        )
        return redirect('docentes:comisiones_list')

    try:
        payload = leer_paquete(form.cleaned_data['archivo'])
        tipo, objeto = instalar_paquete(payload, request.user)
    except PaqueteInvalido as error:
        messages.error(request, f'No se pudo instalar el paquete: {error}')
        return redirect('docentes:comisiones_list')

    if tipo == 'practice':
        messages.success(
            request,
            f'Práctica “{objeto.titulo}” instalada como copia privada. Revisala antes de publicarla.',
        )
        return redirect('docentes:practica_detail', practica_id=objeto.id)

    messages.success(
        request,
        'Ejercicio instalado como copia privada. Revisalo antes de publicarlo.',
    )
    return redirect('docentes:ejercicio_edit', ejercicio_id=objeto.id)


@login_required
def practica_create(request):
    _require_docente(request.user)

    # comision_id opcional en GET para pre-seleccionar la comisión
    comision_id_inicial = request.GET.get('comision')
    initial_pc = {}
    if comision_id_inicial and comision_id_inicial.isdigit():
        initial_pc['comision'] = comision_id_inicial
        ultimo_orden = PracticaComision.objects.filter(comision_id=comision_id_inicial).aggregate(
            max_orden=Max('orden')
        )['max_orden'] or 0
        initial_pc['orden'] = ultimo_orden + 1

    form = PracticaForm(request.POST or None)
    pc_form = PracticaComisionForm(
        request.POST or None, usuario=request.user, initial=initial_pc
    )

    if request.method == 'POST' and form.is_valid() and pc_form.is_valid():
        with transaction.atomic():
            practica = form.save(commit=False)
            practica.creada_por = request.user
            practica.save()
            pc = pc_form.save(commit=False)
            pc.practica = practica
            pc.save()
        messages.success(request, 'Práctica creada correctamente.')
        next_url = _resolver_url_retorno(request)
        if next_url:
            return redirect(next_url)
        return redirect('docentes:practica_detail', practica_id=practica.id)

    return render(request, 'docentes/practica_form.html', {
        'form': form,
        'pc_form': pc_form,
        'modo': 'crear',
        'next': request.GET.get('next', ''),
    })


@login_required
def practica_edit(request, pc_id):
    _require_docente(request.user)

    pc = get_object_or_404(
        PracticaComision.objects.select_related('practica', 'comision'),
        pk=pc_id,
    )
    practica = pc.practica
    if not request.user.is_staff and not pc.comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    form = PracticaForm(request.POST or None, instance=practica)
    pc_form = PracticaComisionForm(request.POST or None, instance=pc, usuario=request.user)

    if request.method == 'POST' and form.is_valid() and pc_form.is_valid():
        form.save()
        pc_form.save()
        _desanclar_si_derivada(practica.pk)
        messages.success(request, 'Práctica actualizada.')
        return redirect('docentes:practica_detail', practica_id=practica.id)

    return render(request, 'docentes/practica_form.html', {
        'form': form,
        'pc_form': pc_form,
        'modo': 'editar',
        'practica': practica,
        'pc': pc,
    })


@login_required
@require_POST
def practica_delete(request, pc_id):
    """Elimina una PracticaComision (y la Practica si queda huérfana)."""
    _require_docente(request.user)

    pc = get_object_or_404(
        PracticaComision.objects.select_related('practica', 'comision'),
        pk=pc_id,
    )
    if not request.user.is_staff and not pc.comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    comision_id = pc.comision_id
    titulo = pc.practica.titulo
    practica = pc.practica
    pc.delete()
    # Si la práctica ya no está en ninguna comisión, eliminarla también
    if not PracticaComision.objects.filter(practica=practica).exists():
        practica.delete()
    messages.success(request, f'Práctica "{titulo}" eliminada de la comisión.')
    next_url = _resolver_url_retorno(request)
    if next_url:
        return redirect(next_url)
    return redirect('docentes:comision_detail', comision_id=comision_id)


@login_required
@require_POST
def ejercicio_delete(request, ejercicio_id):
    """Elimina un ejercicio del banco (solo si lo creó el docente autenticado)."""
    _require_docente(request.user)

    ejercicio = get_object_or_404(Ejercicio, pk=ejercicio_id)
    if not request.user.is_staff and ejercicio.creado_por_id != request.user.id:
        raise PermissionDenied

    enunciado = ejercicio.enunciado[:60]
    ejercicio.delete()
    messages.success(request, f'Ejercicio eliminado.')
    next_url = _resolver_url_retorno(request)
    if next_url:
        return redirect(next_url)
    return redirect('docentes:comisiones_list')


@login_required
@require_POST
def practica_import(request, comision_id):
    """Importa una práctica existente a una comisión creando una PracticaComision.

    No duplica la Practica; solo crea el vínculo PracticaComision entre la
    Practica canónica y la Comision destino.
    """
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    practica_origen_id = request.POST.get('practica_origen')
    orden_destino = request.POST.get('orden_destino')

    if not practica_origen_id or not orden_destino:
        messages.error(request, 'Faltan datos: elegí una práctica y un orden.')
        return redirect('docentes:comision_detail', comision_id=comision.id)

    if request.user.is_staff:
        qs_origen = Practica.objects.all()
    else:
        qs_origen = Practica.objects.filter(
            Q(creada_por=request.user) | Q(es_publica=True)
        )

    practica_origen = get_object_or_404(qs_origen, pk=practica_origen_id)

    try:
        orden_int = int(orden_destino)
    except (ValueError, TypeError):
        messages.error(request, 'El orden debe ser un número entero.')
        return redirect('docentes:comision_detail', comision_id=comision.id)

    try:
        with transaction.atomic():
            PracticaComision.objects.create(
                practica=practica_origen,
                comision=comision,
                orden=orden_int,
            )
        eps_count = practica_origen.ejercicio_practicas.count()
        messages.success(
            request,
            f'Práctica "{practica_origen.titulo}" importada con {eps_count} ejercicio(s).'
        )
    except Exception:
        messages.error(request, 'No se pudo importar: verificá que el orden no esté repetido en esta comisión.')

    return redirect('docentes:comision_detail', comision_id=comision.id)


@login_required
def parcial_create(request, comision_id):
    """Crea un nuevo parcial para la comisión y pre-crea notas null para inscriptos."""
    _require_docente(request.user)
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, _ = _resolver_cohorte_sesion(request, comision)

    # El GET también corta, pero redirigiendo: `parcial_form.html` es una
    # plantilla aparte que no sabe de cohortes, así que sin esto la URL directa
    # muestra un formulario completo que solo va a fallar al enviarse. El POST
    # sigue rechazando con 403 más abajo, que es lo que corresponde a un envío
    # directo al endpoint.
    if request.method != 'POST' and (cohorte is None or not cohorte.activa):
        messages.error(
            request,
            'Esa cohorte está cerrada: no se pueden crear parciales nuevos. '
            'Sí podés cargar notas de los parciales que ya tiene.',
        )
        return redirect('docentes:comision_detail', comision_id=comision.id)

    if request.method == 'POST':
        _require_cohorte_activa(cohorte)
        form = ParcialForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                parcial = form.save(commit=False)
                parcial.comision = comision
                parcial.cohorte = cohorte
                parcial.save()
                # Solo la camada del parcial: sin el filtro, un parcial de la
                # cohorte nueva nacía con una nota por cada estudiante de todas
                # las camadas anteriores de esta comisión.
                inscripciones = list(
                    comision.inscripciones
                    .filter(cohorte=cohorte)
                    .select_related('estudiante')
                )
                NotaParcial.objects.bulk_create([
                    NotaParcial(parcial=parcial, estudiante=i.estudiante)
                    for i in inscripciones
                ])
            messages.success(request, f'Parcial "{parcial.nombre}" creado con {len(inscripciones)} notas pre-cargadas.')
            return redirect('docentes:parcial_notas', parcial_id=parcial.id)
    else:
        form = ParcialForm()

    return render(request, 'docentes/parcial_form.html', {
        'form': form,
        'comision': comision,
        'modo': 'crear',
    })


@login_required
def parcial_edit(request, parcial_id):
    """Edita metadatos del parcial (nombre, fecha, puntaje_total). No toca las notas."""
    _require_docente(request.user)
    parcial = get_object_or_404(Parcial, pk=parcial_id)
    comision = parcial.comision
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    if request.method == 'POST':
        form = ParcialForm(request.POST, instance=parcial)
        if form.is_valid():
            form.save()
            messages.success(request, f'Parcial "{parcial.nombre}" actualizado.')
            return redirect('docentes:comision_detail', comision_id=comision.id)
    else:
        form = ParcialForm(instance=parcial)

    return render(request, 'docentes/parcial_form.html', {
        'form': form,
        'comision': comision,
        'modo': 'editar',
        'parcial': parcial,
    })


@login_required
@require_POST
def parcial_delete(request, parcial_id):
    """Elimina el parcial y todas sus notas (CASCADE)."""
    _require_docente(request.user)
    parcial = get_object_or_404(Parcial, pk=parcial_id)
    comision = parcial.comision
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    nombre = parcial.nombre
    parcial.delete()
    messages.success(request, f'Parcial "{nombre}" eliminado.')
    return redirect('docentes:comision_detail', comision_id=comision.id)


@login_required
def parcial_notas(request, parcial_id):
    """Tabla editable para cargar progresivamente las notas de lógica."""
    _require_docente(request.user)
    parcial = get_object_or_404(Parcial, pk=parcial_id)
    comision = parcial.comision
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    qs = (
        NotaParcial.objects
        .filter(parcial=parcial)
        .select_related('estudiante')
        .order_by('estudiante__last_name', 'estudiante__first_name', 'estudiante__username')
    )
    NotaParcialFormSet = get_nota_parcial_formset()

    if request.method == 'POST':
        formset = NotaParcialFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            messages.success(request, 'Notas guardadas.')
            return redirect('docentes:parcial_notas', parcial_id=parcial_id)
    else:
        formset = NotaParcialFormSet(queryset=qs)

    total = qs.count()
    cargadas = qs.filter(Q(puntaje__isnull=False) | Q(ausente=True)).count()

    return render(request, 'docentes/parcial_notas.html', {
        'parcial': parcial,
        'comision': comision,
        'formset': formset,
        'total': total,
        'cargadas': cargadas,
    })


@login_required
def parcial_notas_exportar(request, parcial_id):
    """Exporta las notas de un parcial en formato XLSX."""
    _require_docente(request.user)
    parcial = get_object_or_404(Parcial, pk=parcial_id)
    comision = parcial.comision
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    try:
        from openpyxl import Workbook
    except ModuleNotFoundError as error:
        raise RuntimeError('openpyxl no está instalado en el entorno actual.') from error

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Notas'
    worksheet.append(['DNI', 'Apellido/s', 'Nombre/s', 'Carrera', 'Nota global', 'Nota lógica'])

    notas = (
        NotaParcial.objects
        .filter(parcial=parcial)
        .select_related('estudiante', 'estudiante__encuesta')
        .order_by('estudiante__last_name', 'estudiante__first_name', 'estudiante__username')
    )
    for nota in notas:
        encuesta = getattr(nota.estudiante, 'encuesta', None)
        worksheet.append([
            (encuesta.dni if encuesta else '') or '',
            nota.estudiante.last_name or '',
            nota.estudiante.first_name or '',
            encuesta.get_carrera_display() if encuesta and encuesta.carrera else '',
            'Ausente' if nota.ausente else nota.puntaje,
            'Ausente' if nota.ausente else nota.nota_logica_parcial,
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename=\"parcial_{parcial.id}_notas.xlsx\"'
    )
    workbook.save(response)
    return response


@login_required
def ejercicio_create(request):
    _require_docente(request.user)

    form = EjercicioForm(request.POST or None)
    ep_form = EjercicioPracticaForm(request.POST or None, usuario=request.user)
    # Marcamos los campos de asignación como opcionales para esta vista
    ep_form.fields['practica'].required = False
    ep_form.fields['ejercicio'].required = False
    ep_form.fields['orden'].required = False

    next_url = _resolver_url_retorno(request)

    if request.method == 'POST' and form.is_valid():
        ejercicio = form.save(commit=False)
        ejercicio.creado_por = request.user
        # Guardar el diccionario de variables enviado por Alpine
        dic_raw = request.POST.get('diccionario_solucion', '{}')
        try:
            ejercicio.diccionario_solucion = json.loads(dic_raw) if dic_raw else {}
        except (json.JSONDecodeError, TypeError):
            ejercicio.diccionario_solucion = {}
        # Guardar valores de verdad del diccionario (solo para determinacion_verdad)
        if ejercicio.tipo == 'determinacion_verdad':
            vv_raw = request.POST.get('valores_verdad_solucion', '{}')
            try:
                ejercicio.valores_verdad_solucion = json.loads(vv_raw) if vv_raw else {}
            except (json.JSONDecodeError, TypeError):
                ejercicio.valores_verdad_solucion = {}
        else:
            ejercicio.valores_verdad_solucion = None
        ejercicio.save()

        practica_id = request.POST.get('ep_practica')
        orden_ep = request.POST.get('ep_orden')
        if practica_id and orden_ep:
            practica = Practica.objects.filter(pk=practica_id).first()
            if practica and _puede_editar_practica(request.user, practica):
                try:
                    _, orden_final = _insertar_ejercicio_en_practica(practica, ejercicio, int(orden_ep))
                    _desanclar_si_derivada(practica.pk)
                    messages.success(request, f'Ejercicio asignado a "{practica.titulo}" en orden {orden_final}.')
                except (IntegrityError, ValueError):
                    messages.warning(
                        request,
                        'El ejercicio se creó pero no se pudo asignar a la práctica (quizás ya estaba agregado).',
                    )

        messages.success(request, 'Ejercicio creado correctamente.')
        url = reverse('docentes:ejercicio_edit', kwargs={'ejercicio_id': ejercicio.id})
        if next_url:
            url = f"{url}?{urlencode({'next': next_url})}"
        return redirect(url)

    practicas_disponibles = _practicas_editables(request.user).order_by('titulo')

    # Pre-selección de práctica si viene ?practica=ID desde practica_detail
    practica_preseleccionada = None
    orden_siguiente = None
    practica_id_get = request.GET.get('practica')
    if practica_id_get and practica_id_get.isdigit():
        practica_preseleccionada = Practica.objects.filter(pk=practica_id_get).first()
        if practica_preseleccionada and not _puede_editar_practica(request.user, practica_preseleccionada):
            practica_preseleccionada = None
        if practica_preseleccionada:
            ultimo = practica_preseleccionada.ejercicio_practicas.aggregate(
                max_orden=Max('orden')
            )['max_orden'] or 0
            orden_siguiente = ultimo + 1

    return render(request, 'docentes/ejercicio_form.html', {
        'form': form,
        'modo': 'crear',
        'practicas_disponibles': practicas_disponibles,
        'practica_preseleccionada': practica_preseleccionada,
        'orden_siguiente': orden_siguiente,
        'diccionario_solucion_json': '',
        'next': next_url,
    })


@login_required
def ejercicio_edit(request, ejercicio_id):
    _require_docente(request.user)

    ejercicio = get_object_or_404(Ejercicio, pk=ejercicio_id)
    if not request.user.is_staff and ejercicio.creado_por_id != request.user.id:
        raise PermissionDenied

    next_url = _resolver_url_retorno(request)

    form = EjercicioForm(request.POST or None, instance=ejercicio)
    if request.method == 'POST' and form.is_valid():
        ejercicio_guardado = form.save(commit=False)
        # Guardar el diccionario de variables enviado por Alpine
        dic_raw = request.POST.get('diccionario_solucion', '{}')
        try:
            ejercicio_guardado.diccionario_solucion = json.loads(dic_raw) if dic_raw else {}
        except (json.JSONDecodeError, TypeError):
            ejercicio_guardado.diccionario_solucion = {}
        # Guardar valores de verdad del diccionario (solo para determinacion_verdad)
        if ejercicio_guardado.tipo == 'determinacion_verdad':
            vv_raw = request.POST.get('valores_verdad_solucion', '{}')
            try:
                ejercicio_guardado.valores_verdad_solucion = json.loads(vv_raw) if vv_raw else {}
            except (json.JSONDecodeError, TypeError):
                ejercicio_guardado.valores_verdad_solucion = {}
        else:
            ejercicio_guardado.valores_verdad_solucion = None
        ejercicio_guardado.save()

        practica_id = request.POST.get('ep_practica')
        orden_ep = request.POST.get('ep_orden')
        if practica_id and orden_ep:
            practica = Practica.objects.filter(pk=practica_id).first()
            if practica and _puede_editar_practica(request.user, practica):
                try:
                    _, orden_final = _insertar_ejercicio_en_practica(practica, ejercicio_guardado, int(orden_ep))
                    _desanclar_si_derivada(practica.pk)
                    messages.success(request, f'Ejercicio asignado a "{practica.titulo}" en orden {orden_final}.')
                except (IntegrityError, ValueError):
                    messages.warning(request, 'No se pudo asignar a la práctica (quizás ya estaba agregado).')

        messages.success(request, 'Ejercicio actualizado.')
        url = reverse('docentes:ejercicio_edit', kwargs={'ejercicio_id': ejercicio_guardado.id})
        if next_url:
            url = f"{url}?{urlencode({'next': next_url})}"
        return redirect(url)

    asignaciones = (
        EjercicioPractica.objects
        .filter(ejercicio=ejercicio)
        .select_related('practica')
        .order_by('practica__titulo', 'orden')
    )
    practicas_disponibles = _practicas_editables(request.user).order_by('titulo')

    return render(request, 'docentes/ejercicio_form.html', {
        'form': form,
        'modo': 'editar',
        'ejercicio': ejercicio,
        'asignaciones': asignaciones,
        'practicas_disponibles': practicas_disponibles,
        'diccionario_solucion_json': json.dumps(ejercicio.diccionario_solucion, ensure_ascii=False),
        'valores_verdad_solucion_json': json.dumps(ejercicio.valores_verdad_solucion or {}, ensure_ascii=False),
        'next': next_url,
    })


@login_required
def practica_detail(request, practica_id):
    """Muestra los ejercicios de una práctica y permite agregar/quitar/reordenar."""
    _require_docente(request.user)

    practica = get_object_or_404(
        Practica.objects.prefetch_related(
            Prefetch(
                'ejercicio_practicas',
                queryset=EjercicioPractica.objects.select_related('ejercicio').order_by('orden'),
            )
        ),
        pk=practica_id,
    )
    if not _puede_ver_practica(request.user, practica):
        raise PermissionDenied
    puede_editar = _puede_editar_practica(request.user, practica)

    add_form = EjercicioPracticaForm(usuario=request.user)
    # Fijamos la práctica en el form de agregar para que no sea seleccionable
    add_form.fields['practica'].initial = practica
    add_form.fields['practica'].widget = add_form.fields['practica'].hidden_widget()

    if request.user.is_staff:
        pcs = list(
            PracticaComision.objects.filter(practica=practica)
            .select_related('comision')
            .order_by('comision__nombre', 'orden')
        )
    else:
        pcs = list(
            PracticaComision.objects.filter(practica=practica, comision__docentes=request.user)
            .select_related('comision')
            .order_by('comision__nombre', 'orden')
        )
    comision_ids = [pc.comision.id for pc in pcs]
    return render(request, 'docentes/practica_detail.html', {
        'practica': practica,
        'ejercicio_practicas': practica.ejercicio_practicas.all(),
        'add_form': add_form,
        'puede_editar': puede_editar,
        'pcs': pcs,
        'comision_ids': comision_ids,
        'comision_default_id': comision_ids[0] if comision_ids else None,
    })


@login_required
@require_POST
def ejercicio_practica_add(request, practica_id):
    """Agrega un ejercicio a una práctica."""
    _require_docente(request.user)

    practica = get_object_or_404(Practica.objects, pk=practica_id)
    if not _puede_editar_practica(request.user, practica):
        raise PermissionDenied

    data = request.POST.copy()
    data['practica'] = practica.id
    # Si no se indicó orden, usar el próximo número disponible
    if not data.get('orden', '').strip():
        data['orden'] = EjercicioPractica.objects.filter(practica=practica).count() + 1
    form = EjercicioPracticaForm(data, usuario=request.user)
    es_valido = form.is_valid()
    if es_valido or _solo_error_unique_together_practica_orden(form):
        try:
            _, orden_final = _insertar_ejercicio_en_practica(
                practica=practica,
                ejercicio=form.cleaned_data['ejercicio'],
                orden_destino=form.cleaned_data['orden'],
            )
            _desanclar_si_derivada(practica.pk)
            messages.success(request, f'Ejercicio agregado a la práctica en orden {orden_final}.')
        except (IntegrityError, ValueError):
            messages.error(request, 'No se pudo agregar: verificá si el ejercicio ya estaba en la práctica.')
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)

    return redirect('docentes:practica_detail', practica_id=practica.id)


@login_required
@require_POST
def ejercicio_practica_remove(request, ep_id):
    """Quita un ejercicio de una práctica."""
    _require_docente(request.user)

    ep = get_object_or_404(
        EjercicioPractica.objects.select_related('practica'),
        pk=ep_id,
    )
    if not _puede_editar_practica(request.user, ep.practica):
        raise PermissionDenied

    practica_id = ep.practica_id
    practica = ep.practica
    orden_eliminado = ep.orden
    ep.delete()
    _reordenar_despues_de_eliminar(practica, orden_eliminado)
    _desanclar_si_derivada(practica_id)
    messages.success(request, 'Ejercicio quitado de la práctica.')
    return redirect('docentes:practica_detail', practica_id=practica_id)


@login_required
@require_POST
def comision_delete(request, comision_id):
    """Elimina una comisión junto con todos sus datos relacionados."""
    _require_docente(request.user)

    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    nombre = comision.nombre
    comision.delete()
    messages.success(request, f'Comisión "{nombre}" eliminada.')
    return redirect('docentes:comisiones_list')


@login_required
@require_POST
def ejercicio_practica_reorder(request, ep_id):
    """Intercambia el orden de un EjercicioPractica con el adyacente (arriba o abajo)."""
    _require_docente(request.user)

    ep = get_object_or_404(
        EjercicioPractica.objects.select_related('practica'),
        pk=ep_id,
    )
    if not _puede_editar_practica(request.user, ep.practica):
        raise PermissionDenied

    direccion = request.POST.get('direccion')  # 'subir' o 'bajar'
    ejercicios = list(EjercicioPractica.objects.filter(practica=ep.practica).order_by('orden'))
    indices = {e.id: i for i, e in enumerate(ejercicios)}
    idx = indices[ep.id]

    if direccion == 'subir' and idx > 0:
        vecino = ejercicios[idx - 1]
    elif direccion == 'bajar' and idx < len(ejercicios) - 1:
        vecino = ejercicios[idx + 1]
    else:
        return redirect('docentes:practica_detail', practica_id=ep.practica_id)

    # Swap de órdenes usando un valor temporal para evitar conflicto de unique_together
    orden_original = ep.orden
    orden_vecino = vecino.orden
    temp_orden = 0
    ep.orden = temp_orden
    ep.save(update_fields=['orden'])
    vecino.orden = orden_original
    vecino.save(update_fields=['orden'])
    ep.orden = orden_vecino
    ep.save(update_fields=['orden'])
    _desanclar_si_derivada(ep.practica_id)

    return redirect('docentes:practica_detail', practica_id=ep.practica_id)


@login_required
@require_POST
def intento_comentario_update(request, intento_id):
    """Actualiza comentario docente de un intento y redirige a la página previa."""
    _require_docente(request.user)

    intento = get_object_or_404(
        Intento.objects.select_related('practica_comision__comision'),
        pk=intento_id,
    )

    if not request.user.is_staff:
        es_docente_de_comision = intento.practica_comision.comision.docentes.filter(
            pk=request.user.pk
        ).exists()
        if not es_docente_de_comision:
            raise PermissionDenied

    intento.comentario_docente = request.POST.get('comentario_docente', '')
    intento.save(update_fields=['comentario_docente'])
    messages.success(request, 'Comentario guardado correctamente.')

    destino = _resolver_url_retorno(request)
    if destino:
        return redirect(destino)

    return redirect('docentes:estudiante_detail', estudiante_id=intento.estudiante_id)


def _avanzar_progreso_por_aprobacion_docente(intento):
    """Avanza el progreso cuando el docente aprueba a mano un intento incorrecto.

    Delega en :func:`ejercicios.progreso.avanzar_progreso`. La comisión, el modo
    de desbloqueo y la cohorte salen del propio intento.
    """
    avanzar_progreso(
        intento.estudiante, intento.ejercicio_practica, intento.practica_comision,
        intento.cohorte,
    )


@login_required
@require_POST
def intento_aprobacion_update(request, intento_id):
    """Aprueba o rechaza un intento y guarda la devolución docente.

    Al rechazar, el comentario es obligatorio: la devolución argumentada
    es parte de la función pedagógica del rechazo (AGENTS.md Objetivo 4).
    """
    _require_docente(request.user)

    intento = get_object_or_404(
        Intento.objects.select_related(
            'practica_comision__comision',
            'ejercicio_practica__practica',
        ),
        pk=intento_id,
    )

    if not request.user.is_staff:
        es_docente_de_comision = intento.practica_comision.comision.docentes.filter(
            pk=request.user.pk
        ).exists()
        if not es_docente_de_comision:
            raise PermissionDenied

    accion = request.POST.get('accion')  # 'aprobar' | 'rechazar' | 'pendiente'
    comentario = request.POST.get('comentario_docente', '').strip()

    if accion == 'rechazar' and not comentario:
        messages.error(
            request,
            'Para rechazar un intento es necesario escribir una devolución. '
            'La devolución argumentada es parte del acompañamiento pedagógico.',
        )
        destino = _resolver_url_retorno(request)
        if destino:
            return redirect(destino)
        return redirect('docentes:estudiante_detail', estudiante_id=intento.estudiante_id)

    if accion == 'aprobar':
        intento.aprobado_docente = True
        msg = 'Intento aprobado.'
    elif accion == 'rechazar':
        intento.aprobado_docente = False
        msg = 'Intento rechazado.'
    else:
        intento.aprobado_docente = None
        msg = 'Revisión restablecida a pendiente.'

    campos = ['aprobado_docente']
    if comentario:
        intento.comentario_docente = comentario
        campos.append('comentario_docente')

    intento.save(update_fields=campos)
    cache.delete(f'analiticas_{intento.practica_comision.comision_id}_{intento.cohorte_id}')

    if accion == 'aprobar' and not intento.es_correcto:
        _avanzar_progreso_por_aprobacion_docente(intento)

    messages.success(request, msg)

    destino = _resolver_url_retorno(request)
    if destino:
        return redirect(destino)
    return redirect('docentes:estudiante_detail', estudiante_id=intento.estudiante_id)


@login_required
@require_POST
def intentos_bulk_aprobar(request):
    """Aprueba en bloque intentos con corrección automática correcta y sin revisar.

    Acepta un parámetro opcional `comision_id` para limitar la acción a una
    comisión específica. Siempre restringido a comisiones propias del docente.
    Invalida la caché de analíticas de cada comisión afectada.
    """
    _require_docente(request.user)

    qs = Intento.objects.filter(
        es_correcto=True,
        aprobado_docente__isnull=True,
        practica_comision__comision__docentes=request.user,
    ).exclude(revision_diccionario='revisar')

    comision_id_raw = request.POST.get('comision_id', '').strip()
    if comision_id_raw:
        if not comision_id_raw.isdigit():
            raise PermissionDenied
        qs = qs.filter(practica_comision__comision_id=comision_id_raw)

    # Pares (comisión, cohorte) afectados: la clave de caché de analíticas es
    # por cohorte, así que hace falta invalidar cada combinación por separado
    # y no solo la comisión (un bulk puede tocar intentos de varias camadas).
    comision_cohorte_pares = set(
        qs.values_list('practica_comision__comision_id', 'cohorte_id').distinct()
    )

    cantidad = qs.update(aprobado_docente=True)

    for comision_id, cohorte_id in comision_cohorte_pares:
        if comision_id:
            cache.delete(f'analiticas_{comision_id}_{cohorte_id}')

    messages.success(
        request,
        f'Se aprobaron {cantidad} intento{"s" if cantidad != 1 else ""} correctos pendientes.',
    )
    return redirect('docentes:correccion_pendiente')

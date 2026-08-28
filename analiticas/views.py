"""Vistas de analíticas para docentes y administradores.

Expone un dashboard por comisión con:
    - Total de estudiantes inscriptos.
    - Por práctica: cuántos completaron, total de intentos, tasa de acierto global.
    - Ejercicios más difíciles (mayor tasa de error, mín. 3 intentos).
    - Estudiantes en riesgo (racha ≥ 5 fallos consecutivos en algún ejercicio).
    - Distribución de intentos por ejercicio (cuántos intentos hasta resolver).
    - Evolución temporal (intentos por semana ISO, últimas 8 semanas).

Los estudiantes son redirigidos a :func:`ejercicios.views.home`.
"""

import io
import re
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Max, Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import ConfigSitio
from analiticas.calculos import _matriz_juicio_computo, _patron_adivinacion
from cursos.models import Comision
from ejercicios.models import EjercicioPractica, Intento, PracticaComision, Progreso

# Ventana temporal fija (no tiene sentido pedagógico dejarla editable por comisión)
_SEMANAS = 8

# Correctitud efectiva: ver ejercicios/correctitud.py. Los alias con guión bajo
# se mantienen porque el resto del módulo ya los usa con ese nombre.
from ejercicios.correctitud import Q_CORRECTO as _Q_CORRECTO  # noqa: E402
from ejercicios.correctitud import Q_INCORRECTO as _Q_INCORRECTO  # noqa: E402


def _correcto_efectivo(es_correcto, aprobado_docente):
    """Devuelve True/False según la correctitud efectiva del intento."""
    if aprobado_docente is not None:
        return aprobado_docente
    return es_correcto


# ──────────────────────────────────────────────
#  Helpers analíticos (reutilizables desde docentes/views.py)
# ──────────────────────────────────────────────

def _strip_html(text):
    """Elimina etiquetas HTML básicas de un string."""
    return re.sub(r'<[^>]+>', '', text or '')


def _url_ejercicio(pc_id, ep_id):
    """Ruta al ejercicio dentro de su práctica, o ``None`` si no hay práctica.

    Este es el único lugar del proyecto que conoce el nombre de la ruta para
    los gráficos. La alternativa —reconstruirla en JavaScript— se rompe en
    silencio si ``ejercicios/urls.py`` cambia: el link sigue ahí y no lleva
    a ninguna parte.

    Args:
        pc_id: ID de PracticaComision, o None si el ejercicio no tiene una
            práctica visible para el usuario.
        ep_id: ID de EjercicioPractica.

    Returns:
        La ruta, o ``None``. Una fila con ``None`` deja su barra inerte en el
        gráfico, que es preferible a un link roto o al de otra comisión.
    """
    if pc_id is None:
        return None
    return reverse('ejercicios:ejercicio', args=[pc_id, ep_id])


def _urls_ejercicios(ep_ids, comision_ids):
    """Resuelve en bulk la URL de cada EjercicioPractica dado.

    Los paneles del dashboard agregan varias comisiones, así que una misma
    práctica puede estar asignada a más de una y el ``PracticaComision`` no es
    único. Se elige el de menor ``id``: es determinístico —dos cargas dan el
    mismo link— y el ejercicio que se abre es el mismo en cualquier caso; lo
    único que cambia es la práctica que lo enmarca.

    Args:
        ep_ids: iterable de IDs de EjercicioPractica.
        comision_ids: comisiones visibles para el usuario.

    Returns:
        Dict ``{ep_id: url | None}``, con una entrada por cada ep pedido.
    """
    ep_ids = list(ep_ids)
    if not ep_ids or not comision_ids:
        return {ep_id: None for ep_id in ep_ids}

    # Una sola query: (ep, pc) para todos los ep pedidos. Resolver de a uno
    # sería N+1 sobre gráficos de ~40 barras.
    filas = (
        EjercicioPractica.objects
        .filter(id__in=ep_ids, practica__practicas_comisiones__comision_id__in=comision_ids)
        .values_list('id', 'practica__practicas_comisiones__id')
    )

    mejor_pc = {}
    for ep_id, pc_id in filas:
        if pc_id is None:
            continue
        actual = mejor_pc.get(ep_id)
        if actual is None or pc_id < actual:
            mejor_pc[ep_id] = pc_id

    return {ep_id: _url_ejercicio(mejor_pc.get(ep_id), ep_id) for ep_id in ep_ids}


def _ejercicios_mas_dificiles(comision_ids, estudiante_ids, top_n=5, min_intentos=3, cohorte_ids=None):
    """Devuelve los EjercicioPractica más difíciles por tasa de error.

    Solo considera EP con ≥ ``min_intentos`` intentos totales (evita ruido).
    Ordena por tasa de error descendente y devuelve los primeros ``top_n``.

    Args:
        comision_ids: iterable de IDs de Comision a considerar.
        estudiante_ids: IDs de estudiantes a considerar (define la población:
            quiénes cuentan y con qué permisos). No alcanza por sí solo para
            acotar por camada: un recursante tiene el mismo estudiante_id en
            todas sus cohortes de una comisión.
        top_n: cuántos resultados devolver.
        min_intentos: mínimo de intentos totales para incluir el EP.
        cohorte_ids: si se da, acota los intentos a esas cohortes. Necesario
            para no mezclar, en un recursante, los intentos de su camada
            anterior con los de la que se está mirando.

    Returns:
        Lista de dicts con claves:
        ``enunciado_corto``, ``practica_titulo``, ``tipo``,
        ``total``, ``errores``, ``error_rate``.
    """
    if not comision_ids or not estudiante_ids:
        return []

    _filtro_estudiantes = Q(intentos__estudiante_id__in=estudiante_ids)
    if cohorte_ids is not None:
        _filtro_estudiantes &= Q(intentos__cohorte_id__in=cohorte_ids)

    eps = (
        EjercicioPractica.objects
        .filter(practica__practicas_comisiones__comision_id__in=comision_ids)
        .distinct()
        .select_related('ejercicio', 'practica')
        .annotate(
            total=Count('intentos', filter=_filtro_estudiantes),
            errores=Count('intentos', filter=(
                _filtro_estudiantes
                & (
                    Q(intentos__aprobado_docente=False)
                    | Q(intentos__es_correcto=False, intentos__aprobado_docente__isnull=True)
                )
            )),
        )
        .filter(total__gte=min_intentos)
    )
    resultado = []
    for ep in eps:
        error_rate = ep.errores / ep.total * 100
        enunciado_corto = _strip_html(ep.ejercicio.enunciado[:120]).strip()[:70]
        resultado.append({
            'ejercicio_id': ep.ejercicio.id,
            'ep_id': ep.id,
            'enunciado_corto': enunciado_corto,
            'practica_titulo': ep.practica.titulo,
            'tipo': ep.ejercicio.tipo,
            'total': ep.total,
            'errores': ep.errores,
            'error_rate': round(error_rate, 1),
        })
    resultado.sort(key=lambda x: x['error_rate'], reverse=True)
    resultado = resultado[:top_n]
    # Se resuelve DESPUÉS del corte: no tiene sentido pedir URLs de filas
    # que el panel no va a mostrar.
    _urls = _urls_ejercicios([r['ep_id'] for r in resultado], comision_ids)
    for r in resultado:
        r['url'] = _urls.get(r['ep_id'])
    return resultado


def _estudiantes_en_riesgo(comision_ids, estudiante_ids, umbral_riesgo=5, cohorte_ids=None):
    """Retorna estudiantes con racha ≥ ``umbral_riesgo`` fallos consecutivos.

    Para cada par (estudiante, EP), toma los intentos ordenados por timestamp
    y cuenta la racha final de ``es_correcto=False``. Si la racha activa
    (todavía no interrumpida por un acierto) supera el umbral, el estudiante
    aparece en el panel de alertas de acompañamiento.

    Args:
        comision_ids: iterable de IDs de Comision.
        estudiante_ids: IDs de estudiantes a considerar (define la
            población). No alcanza para acotar por camada: ver
            :func:`_ejercicios_mas_dificiles`.
        umbral_riesgo: cantidad de fallos consecutivos para activar la alerta.
        cohorte_ids: si se da, acota los intentos a esas cohortes.

    Returns:
        Lista de dicts con claves:
        ``username``, ``nombre``, ``enunciado_corto``,
        ``practica_titulo``, ``racha``.
        Ordenada por ``racha`` descendente.
    """
    if not comision_ids or not estudiante_ids:
        return []

    _filtros = dict(
        practica_comision__comision_id__in=comision_ids,
        estudiante_id__in=estudiante_ids,
    )
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids

    intentos = (
        Intento.objects
        .filter(**_filtros)
        .order_by('estudiante_id', 'ejercicio_practica_id', 'timestamp')
        .values(
            'estudiante_id', 'ejercicio_practica_id', 'es_correcto', 'aprobado_docente',
            'estudiante__username', 'estudiante__first_name', 'estudiante__last_name',
            'ejercicio_practica__ejercicio__enunciado',
            'ejercicio_practica__practica__titulo',
        )
    )

    grupos = defaultdict(list)
    meta = {}
    for intento in intentos:
        key = (intento['estudiante_id'], intento['ejercicio_practica_id'])
        grupos[key].append(_correcto_efectivo(intento['es_correcto'], intento['aprobado_docente']))
        if key not in meta:
            meta[key] = intento

    en_riesgo = []
    for key, correcciones in grupos.items():
        racha = 0
        for c in reversed(correcciones):
            if not c:
                racha += 1
            else:
                break
        if racha >= umbral_riesgo:
            m = meta[key]
            enunciado_corto = _strip_html(
                m['ejercicio_practica__ejercicio__enunciado'][:120]
            ).strip()[:70]
            nombre = (
                f"{m['estudiante__first_name']} {m['estudiante__last_name']}".strip()
                or m['estudiante__username']
            )
            en_riesgo.append({
                'username': m['estudiante__username'],
                'nombre': nombre,
                'enunciado_corto': enunciado_corto,
                'practica_titulo': m['ejercicio_practica__practica__titulo'],
                'racha': racha,
            })

    en_riesgo.sort(key=lambda x: x['racha'], reverse=True)
    return en_riesgo


def _distribucion_intentos(comision_ids, estudiante_ids, cohorte_ids=None):
    """Calcula la distribución de intentos hasta resolver, agrupada por ejercicio.

    El mismo ejercicio puede aparecer en varias prácticas/comisiones (vía
    distintos EjercicioPractica). En lugar de mostrar una fila por EP, esta
    función agrupa por ``ejercicio_id`` y devuelve estadísticas consolidadas
    más un listado de detalle por comisión/práctica para el desplegable.

    Incluye a **todos** los estudiantes que intentaron el EP: los que
    resolvieron (contados hasta el primer correcto) y los que nunca
    resolvieron (contados como censurados). Esto corrige el sesgo de
    excluir a quienes no llegaron a resolver, que distorsiona la dificultad
    real cuando muchos estudiantes abandonan.

    Args:
        comision_ids: iterable de IDs de Comision.
        estudiante_ids: IDs de estudiantes a considerar (define la
            población). No alcanza para acotar por camada: ver
            :func:`_ejercicios_mas_dificiles`.
        cohorte_ids: si se da, acota los intentos a esas cohortes.

    Returns:
        Lista de dicts con claves:
        ``enunciado_corto``, ``practica_titulo``, ``tipo``,
        ``resolvieron``, ``no_resolvieron``, ``pct_no_resolvio``,
        ``promedio``, ``mediana``,
        ``bucket_1``, ``bucket_2_3``, ``bucket_4_6``, ``bucket_7plus``.
        Ordenada por ``promedio`` descendente (None al final).
    """
    import statistics as _statistics

    if not comision_ids or not estudiante_ids:
        return []

    _filtros = dict(
        practica_comision__comision_id__in=comision_ids,
        estudiante_id__in=estudiante_ids,
    )
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids

    intentos = (
        Intento.objects
        .filter(**_filtros)
        .order_by('estudiante_id', 'ejercicio_practica_id', 'timestamp')
        .values(
            'estudiante_id', 'ejercicio_practica_id', 'es_correcto', 'aprobado_docente',
            'ejercicio_practica__ejercicio_id',
            'ejercicio_practica__ejercicio__enunciado',
            'ejercicio_practica__practica__titulo',
            'practica_comision__comision__nombre',
            'ejercicio_practica__ejercicio__tipo',
        )
    )

    grupos = defaultdict(list)
    meta = {}
    for intento in intentos:
        key = (intento['estudiante_id'], intento['ejercicio_practica_id'])
        grupos[key].append(_correcto_efectivo(intento['es_correcto'], intento['aprobado_docente']))
        if key not in meta:
            meta[key] = intento

    # Para cada EP: coleccionar intentos hasta primer correcto (quienes resolvieron)
    # y conteo total (quienes no resolvieron, datos censurados).
    ep_resolvieron = defaultdict(list)   # ep_id → [n_intentos_hasta_correcto]
    ep_no_resolvieron = defaultdict(int)  # ep_id → count de quienes nunca resolvieron
    ep_meta = {}

    for key, correcciones in grupos.items():
        ep_id = key[1]
        if ep_id not in ep_meta:
            ep_meta[ep_id] = meta[key]
        try:
            primer_correcto = next(i + 1 for i, c in enumerate(correcciones) if c)
            ep_resolvieron[ep_id].append(primer_correcto)
        except StopIteration:
            ep_no_resolvieron[ep_id] += 1

    # Unir todos los EP que tuvieron al menos un intento
    todos_ep_ids = set(ep_resolvieron.keys()) | set(ep_no_resolvieron.keys())

    # Índice ep_id → primer intento (para metadatos)
    ep_meta_map = {}
    for (_, ep_id), m in meta.items():
        if ep_id not in ep_meta_map:
            ep_meta_map[ep_id] = m

    # Agrupar EPs por ejercicio_id (el mismo ejercicio puede estar en varias prácticas).
    ejercicio_grupos = defaultdict(list)   # ejercicio_id → [ep_id, ...]
    for ep_id in todos_ep_ids:
        m = ep_meta_map[ep_id]
        ejercicio_id = m['ejercicio_practica__ejercicio_id']
        ejercicio_grupos[ejercicio_id].append(ep_id)

    resultado = []
    for ejercicio_id, eps_del_ejercicio in ejercicio_grupos.items():
        # Representante determinístico: el mismo ejercicio puede estar en
        # varias prácticas y esta fila las agrega todas. Cualquiera de sus EP
        # abre el mismo ejercicio; se fija el menor para que el link no cambie
        # entre cargas.
        ep_representante = min(eps_del_ejercicio)
        # La metadata mostrada (práctica, enunciado) tiene que salir del MISMO
        # EP que va a recibir el link más abajo. Si se tomara de otro EP del
        # grupo, la fila podría mostrar "Práctica 3" mientras la barra abre
        # la Práctica 1.
        first_m = ep_meta_map[ep_representante]
        enunciado_corto = _strip_html(
            first_m['ejercicio_practica__ejercicio__enunciado'][:120]
        ).strip()[:70]

        # Agregar stats de todos los EPs del ejercicio y construir detalle
        all_counts = []
        all_no_res = 0
        detalle = []
        for ep_id in eps_del_ejercicio:
            counts = ep_resolvieron.get(ep_id, [])
            no_res = ep_no_resolvieron.get(ep_id, 0)
            all_counts.extend(counts)
            all_no_res += no_res
            ep_m = ep_meta_map[ep_id]
            ep_promedio = round(sum(counts) / len(counts), 1) if counts else None
            detalle.append({
                'comision_nombre': ep_m.get('practica_comision__comision__nombre', '—'),
                'practica_titulo': ep_m['ejercicio_practica__practica__titulo'],
                'resolvieron': len(counts),
                'promedio': ep_promedio,
                'bucket_1': sum(1 for c in counts if c == 1),
                'bucket_2_3': sum(1 for c in counts if 2 <= c <= 3),
                'bucket_4_6': sum(1 for c in counts if 4 <= c <= 6),
                'bucket_7plus': sum(1 for c in counts if c >= 7),
            })

        total_intentaron = len(all_counts) + all_no_res
        promedio = round(sum(all_counts) / len(all_counts), 1) if all_counts else None
        mediana = round(_statistics.median(all_counts), 1) if all_counts else None
        resultado.append({
            'ep_id': ep_representante,
            'enunciado_corto': enunciado_corto,
            'practica_titulo': first_m['ejercicio_practica__practica__titulo'],
            'tipo': first_m['ejercicio_practica__ejercicio__tipo'],
            'resolvieron': len(all_counts),
            'no_resolvieron': all_no_res,
            'pct_no_resolvio': round(all_no_res / total_intentaron * 100, 1) if total_intentaron else None,
            'promedio': promedio,
            'mediana': mediana,
            'bucket_1': sum(1 for c in all_counts if c == 1),
            'bucket_2_3': sum(1 for c in all_counts if 2 <= c <= 3),
            'bucket_4_6': sum(1 for c in all_counts if 4 <= c <= 6),
            'bucket_7plus': sum(1 for c in all_counts if c >= 7),
            'detalle': detalle,
        })
    resultado.sort(key=lambda x: (x['promedio'] is None, x['promedio'] or 0), reverse=True)
    _urls = _urls_ejercicios([r['ep_id'] for r in resultado], comision_ids)
    for r in resultado:
        r['url'] = _urls.get(r['ep_id'])
    return resultado


def _evolucion_temporal(comision_ids, estudiante_ids, semanas=_SEMANAS, cohorte_ids=None):
    """Intentos por semana ISO en las últimas ``semanas`` semanas.

    Args:
        comision_ids: iterable de IDs de Comision.
        estudiante_ids: IDs de estudiantes a considerar (define la
            población). No alcanza para acotar por camada: ver
            :func:`_ejercicios_mas_dificiles`.
        semanas: cuántas semanas hacia atrás considerar.
        cohorte_ids: si se da, acota los intentos a esas cohortes.

    Returns:
        Lista de dicts con claves:
        ``semana_label`` (e.g. ``"2026-S07"``), ``total``,
        ``correctos``, ``estudiantes_unicos``.
        Ordenada ascendentemente por semana.
    """
    if not comision_ids or not estudiante_ids:
        return []

    cutoff = timezone.now() - timedelta(weeks=semanas)
    _filtros = dict(
        practica_comision__comision_id__in=comision_ids,
        estudiante_id__in=estudiante_ids,
        timestamp__gte=cutoff,
    )
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids
    intentos = (
        Intento.objects
        .filter(**_filtros)
        .values('timestamp', 'es_correcto', 'aprobado_docente', 'estudiante_id')
        .order_by('timestamp')
    )

    semanas_data = defaultdict(lambda: {'total': 0, 'correctos': 0, 'estudiantes': set()})
    for intento in intentos:
        iso = intento['timestamp'].isocalendar()
        label = f"{iso[0]}-S{iso[1]:02d}"
        semanas_data[label]['total'] += 1
        if _correcto_efectivo(intento['es_correcto'], intento['aprobado_docente']):
            semanas_data[label]['correctos'] += 1
        semanas_data[label]['estudiantes'].add(intento['estudiante_id'])

    resultado = []
    for label in sorted(semanas_data.keys()):
        d = semanas_data[label]
        resultado.append({
            'semana_label': label,
            'total': d['total'],
            'correctos': d['correctos'],
            'estudiantes_unicos': len(d['estudiantes']),
        })
    return resultado


def _silencio_temprano(comision_ids, estudiante_ids, cohorte_ids=None):
    """Para cada estudiante inscripto, días desde su último intento.

    Incluye a todos los inscriptos aunque no hayan intentado nada
    (``nunca=True``). Ordenado: primero quienes nunca intentaron,
    luego por días de silencio descendente.

    Args:
        comision_ids: iterable de IDs de Comision.
        estudiante_ids: IDs de estudiantes a considerar; define la población
            que se reporta (incluye a quien nunca intentó nada). No alcanza
            para acotar por camada: ver :func:`_ejercicios_mas_dificiles`.
        cohorte_ids: si se da, acota los intentos a esas cohortes. Un
            recursante con intentos solo en su camada vieja debe verse como
            "nunca intentó" al mirar la camada actual, no arrastrar el
            último intento de la otra.

    Returns:
        Lista de dicts con claves:
        ``username``, ``nombre``, ``ultimo_intento``,
        ``dias_silencio``, ``total_intentos``, ``nunca``.
    """
    from accounts.models import Usuario

    if not comision_ids or not estudiante_ids:
        return []

    inscriptos = (
        Usuario.objects
        .filter(pk__in=estudiante_ids)
        .values(
            estudiante_id=F('pk'),
            estudiante__username=F('username'),
            estudiante__first_name=F('first_name'),
            estudiante__last_name=F('last_name'),
        )
    )

    _filtros = dict(
        practica_comision__comision_id__in=comision_ids,
        estudiante_id__in=estudiante_ids,
    )
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids
    ultimos = (
        Intento.objects
        .filter(**_filtros)
        .values('estudiante_id')
        .annotate(ultimo=Max('timestamp'), total=Count('id'))
    )
    por_estudiante = {r['estudiante_id']: r for r in ultimos}

    ahora = timezone.now()
    resultado = []
    for ins in inscriptos:
        eid = ins['estudiante_id']
        datos = por_estudiante.get(eid)
        if datos is None:
            dias, nunca, total, ultimo = None, True, 0, None
        else:
            dias = (ahora - datos['ultimo']).days
            nunca, total, ultimo = False, datos['total'], datos['ultimo']
        nombre = (
            f"{ins['estudiante__first_name']} {ins['estudiante__last_name']}".strip()
            or ins['estudiante__username']
        )
        resultado.append({
            'username': ins['estudiante__username'],
            'nombre': nombre,
            'ultimo_intento': ultimo,
            'dias_silencio': dias,
            'total_intentos': total,
            'nunca': nunca,
        })

    resultado.sort(key=lambda x: (not x['nunca'], -(x['dias_silencio'] or 9999)))
    return resultado


def _silencio_resumen(silencio_lista, umbral_silencio_dias=7):
    """Computa conteos de resumen para el panel de silencio temprano.

    Args:
        silencio_lista: lista devuelta por ``_silencio_temprano``.
        umbral_silencio_dias: días sin actividad para considerar alerta.

    Returns:
        Dict con claves ``total``, ``nunca``, ``alertas``, ``activos``.
    """
    nunca   = sum(1 for s in silencio_lista if s['nunca'])
    alertas = sum(1 for s in silencio_lista
                  if not s['nunca'] and (s['dias_silencio'] or 0) >= umbral_silencio_dias)
    return {
        'total':   len(silencio_lista),
        'nunca':   nunca,
        'alertas': alertas,
        'activos': len(silencio_lista) - nunca - alertas,
    }


def _concentracion_practica(comision_ids, estudiante_ids, umbral_maraton=6, cohorte_ids=None):
    """Detecta pares (estudiante, práctica) con práctica muy concentrada.

    Calcula el ratio intentos / días únicos con actividad. Un ratio alto
    (≥ ``umbral_maraton``) sugiere que el estudiante estudió de golpe,
    posiblemente de última hora.

    Solo incluye pares con ≥ 3 intentos totales y ratio ≥ ``umbral_maraton``.

    Args:
        comision_ids: iterable de IDs de Comision.
        estudiante_ids: IDs de estudiantes a considerar (define la
            población). No alcanza para acotar por camada: ver
            :func:`_ejercicios_mas_dificiles`.
        cohorte_ids: si se da, acota los intentos a esas cohortes.

    Returns:
        Lista de dicts con claves:
        ``username``, ``nombre``, ``practica_titulo``,
        ``total``, ``dias_unicos``, ``ratio``.
        Ordenada por ratio descendente.
    """
    if not comision_ids or not estudiante_ids:
        return []

    _filtros = dict(
        practica_comision__comision_id__in=comision_ids,
        estudiante_id__in=estudiante_ids,
    )
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids
    intentos = (
        Intento.objects
        .filter(**_filtros)
        .order_by('estudiante_id', 'ejercicio_practica__practica_id', 'timestamp')
        .values(
            'estudiante_id', 'estudiante__username',
            'estudiante__first_name', 'estudiante__last_name',
            'ejercicio_practica__practica_id',
            'ejercicio_practica__practica__titulo',
            'timestamp',
        )
    )

    grupos = defaultdict(lambda: {'timestamps': [], 'meta': None})
    for i in intentos:
        key = (i['estudiante_id'], i['ejercicio_practica__practica_id'])
        grupos[key]['timestamps'].append(i['timestamp'])
        if grupos[key]['meta'] is None:
            grupos[key]['meta'] = i

    resultado = []
    for key, data in grupos.items():
        ts = data['timestamps']
        if len(ts) < 3:
            continue
        dias_unicos = len(set(t.date() for t in ts))
        if dias_unicos == 0:
            continue
        ratio = round(len(ts) / dias_unicos, 1)
        if ratio < umbral_maraton:
            continue
        m = data['meta']
        nombre = (
            f"{m['estudiante__first_name']} {m['estudiante__last_name']}".strip()
            or m['estudiante__username']
        )
        resultado.append({
            'username': m['estudiante__username'],
            'nombre': nombre,
            'practica_titulo': m['ejercicio_practica__practica__titulo'],
            'total': len(ts),
            'dias_unicos': dias_unicos,
            'ratio': ratio,
        })

    resultado.sort(key=lambda x: x['ratio'], reverse=True)
    return resultado


def _velocidad_arranque(comision_ids, estudiante_ids, umbral_arranque_dias=14, cohorte_ids=None):
    """Detecta estudiantes con arranque tardío en alguna práctica.

    Un arranque tardío ocurre cuando el estudiante no realizó ningún
    intento en los primeros ``umbral_arranque_dias`` días desde la apertura
    de la práctica (definida como el primer intento de cualquier
    estudiante en esa práctica), pero sí tiene intentos posteriores.

    Args:
        comision_ids: iterable de IDs de Comision.
        estudiante_ids: IDs de estudiantes a considerar (define la
            población). No alcanza para acotar por camada: ver
            :func:`_ejercicios_mas_dificiles`.
        cohorte_ids: si se da, acota los intentos a esas cohortes.

    Returns:
        Lista de dicts con claves:
        ``username``, ``nombre``, ``practica_titulo``, ``intentos_total``.
        Ordenada por intentos_total descendente.
    """
    if not comision_ids or not estudiante_ids:
        return []

    _filtros = dict(
        practica_comision__comision_id__in=comision_ids,
        estudiante_id__in=estudiante_ids,
    )
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids
    intentos = (
        Intento.objects
        .filter(**_filtros)
        .order_by('ejercicio_practica__practica_id', 'timestamp')
        .values(
            'estudiante_id', 'estudiante__username',
            'estudiante__first_name', 'estudiante__last_name',
            'ejercicio_practica__practica_id',
            'ejercicio_practica__practica__titulo',
            'timestamp',
        )
    )

    apertura_practica = {}  # pid → timestamp del primer intento global
    grupos = defaultdict(list)
    for i in intentos:
        pid = i['ejercicio_practica__practica_id']
        if pid not in apertura_practica:
            apertura_practica[pid] = i['timestamp']
        grupos[(i['estudiante_id'], pid)].append(i)

    resultado = []
    for (eid, pid), items in grupos.items():
        if pid not in apertura_practica:
            continue
        limite = apertura_practica[pid] + timedelta(days=umbral_arranque_dias)
        tempranos = sum(1 for i in items if i['timestamp'] <= limite)
        if tempranos > 0 or len(items) == 0:
            continue  # solo mostrar los que arrancaron tarde con intentos posteriores
        m = items[0]
        nombre = (
            f"{m['estudiante__first_name']} {m['estudiante__last_name']}".strip()
            or m['estudiante__username']
        )
        resultado.append({
            'username': m['estudiante__username'],
            'nombre': nombre,
            'practica_titulo': m['ejercicio_practica__practica__titulo'],
            'intentos_total': len(items),
        })

    resultado.sort(key=lambda x: x['intentos_total'], reverse=True)
    return resultado


def _fmt_respuesta_error(respuesta_raw, tipo):
    """Convierte respuesta_raw a un string legible para mostrar en el dashboard.

    Para ``formalizacion`` devuelve la fórmula tal cual.
    Para ``tabla_verdad`` (JSON de enunciados) produce algo como
    ``P1: p·q  /  P2: ~r  /  C: p``.
    """
    import json as _json
    if tipo != 'tabla_verdad':
        return respuesta_raw or '(vacío)'
    try:
        enunciados = _json.loads(respuesta_raw)
        partes = []
        n_p = 0
        for e in enunciados:
            t = e.get('tipo', '')
            f = e.get('formula') or '(vacío)'
            if t == 'premisa':
                n_p += 1
                partes.append(f'P{n_p}: {f}')
            elif t == 'conclusion':
                partes.append(f'C: {f}')
        return '  /  '.join(partes) if partes else (respuesta_raw or '(vacío)')
    except Exception:
        return respuesta_raw or '(vacío)'


def _errores_sistematicos(comision_ids, estudiante_ids, min_estudiantes=2, cohorte_ids=None):
    """Detecta respuestas incorrectas compartidas por ≥ ``min_estudiantes`` estudiantes.

    Agrupa los intentos incorrectos por (ejercicio, práctica, respuesta_raw) y
    devuelve los grupos donde la misma fórmula equivocada fue escrita por al
    menos ``min_estudiantes`` estudiantes distintos.  Esto revela concepciones
    erróneas compartidas (no ruido individual).

    Args:
        comision_ids: iterable de IDs de Comision a considerar.
        estudiante_ids: IDs de estudiantes a considerar (define la
            población). No alcanza para acotar por camada: ver
            :func:`_ejercicios_mas_dificiles`.
        min_estudiantes: umbral mínimo de estudiantes coincidentes.
            Por defecto usa ``_ERROR_CONSENSO_MIN``; las vistas lo sobreescriben
            con el valor de ``ConfigSitio.error_consenso_min``.
        cohorte_ids: si se da, acota los intentos a esas cohortes. Sin
            acotar, un mismo error de un recursante en dos camadas cuenta
            dos veces hacia ``n_estudiantes`` cuando en realidad es la
            misma persona.

    Returns:
        Lista de dicts con claves:
        ``enunciado``, ``practica_titulo``, ``tipo``,
        ``respuesta_display``, ``n_estudiantes``.
        Ordenada por ``n_estudiantes`` desc.
    """
    if not comision_ids or not estudiante_ids:
        return []

    _filtros = dict(
        practica_comision__comision_id__in=comision_ids,
        estudiante_id__in=estudiante_ids,
    )
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids

    filas = (
        Intento.objects
        .filter(**_filtros)
        .filter(_Q_INCORRECTO)
        .values(
            'ejercicio_practica__ejercicio__enunciado',
            'ejercicio_practica__ejercicio__tipo',
            'ejercicio_practica__practica__titulo',
            'respuesta_raw',
        )
        .annotate(n_estudiantes=Count('estudiante_id', distinct=True))
        .filter(n_estudiantes__gte=min_estudiantes)
        .order_by('-n_estudiantes')
    )

    resultado = []
    for f in filas:
        tipo = f['ejercicio_practica__ejercicio__tipo']
        resultado.append({
            'enunciado':      f['ejercicio_practica__ejercicio__enunciado'],
            'practica_titulo': f['ejercicio_practica__practica__titulo'],
            'tipo':           tipo,
            'respuesta_display': _fmt_respuesta_error(f['respuesta_raw'], tipo),
            'n_estudiantes':  f['n_estudiantes'],
        })
    return resultado


# ──────────────────────────────────────────────
#  Vista principal
# ──────────────────────────────────────────────

@login_required
def dashboard(request):
    """Dashboard de analíticas por comisión para docentes y admins.

    Para cada comisión del usuario (o todas, si es admin), muestra:
        - Cantidad de estudiantes inscriptos.
        - Por práctica: completaron/total, total de intentos y tasa de acierto.
        - Ejercicios más difíciles (top 5 por tasa de error).
        - Estudiantes en riesgo (racha ≥ 5 fallos consecutivos).
        - Distribución de intentos hasta resolver por ejercicio.
        - Evolución temporal (intentos por semana, últimas 8 semanas).

    Estudiantes son redirigidos a ``ejercicios:home``.
    """
    usuario = request.user

    if not (usuario.is_staff or usuario.es_docente):
        return redirect('ejercicios:home')

    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids
    comisiones = (
        filtros.comisiones
        .filter(id__in=comision_ids)
        .prefetch_related('practicas_comisiones__practica')
    )

    # Pre-calcular estadísticas en bulk para evitar N+1 por (comisión × práctica).
    all_pcs = list(
        PracticaComision.objects
        .filter(comision_id__in=comision_ids)
        .values('id', 'practica_id', 'comision_id')
    )
    all_pc_ids = [pc['id'] for pc in all_pcs]

    _qs_intentos = Intento.objects.filter(practica_comision_id__in=all_pc_ids)
    if cohorte_ids is not None:
        _qs_intentos = _qs_intentos.filter(cohorte_id__in=cohorte_ids)

    total_intentos_map = {
        row['practica_comision_id']: row['n']
        for row in _qs_intentos.values('practica_comision_id').annotate(n=Count('id'))
    }
    intentos_correctos_map = {
        row['practica_comision_id']: row['n']
        for row in (
            _qs_intentos.filter(_Q_CORRECTO)
            .values('practica_comision_id').annotate(n=Count('id'))
        )
    }
    _qs_progreso = Progreso.objects.filter(
        practica_comision_id__in=all_pc_ids,
        ejercicio_practica_actual__isnull=True,
        estudiante__inscripciones__comision=F('practica_comision__comision'),
    )
    if cohorte_ids is not None:
        _qs_progreso = _qs_progreso.filter(cohorte_id__in=cohorte_ids)

    completaron_map = {
        row['practica_comision_id']: row['n']
        for row in (
            # Numerador de "completaron X de N": cuenta personas, para que
            # la unidad matche al denominador (_estudiantes_por_comision,
            # más abajo). Un recursante que completó la práctica en dos
            # camadas de la misma comisión tiene dos filas de Progreso (una
            # por cohorte, ver unique_together en el modelo); contar filas
            # de Progreso lo contaría dos veces frente a una sola persona
            # en el denominador. Además, el join contra
            # estudiante__inscripciones duplica cada fila de Progreso por
            # cada Inscripcion que matchea, así que distinct=True es
            # necesario incluso para contar personas correctamente.
            _qs_progreso.values('practica_comision_id').annotate(n=Count('estudiante_id', distinct=True))
        )
    }

    from cursos.models import Inscripcion

    _insc_qs = Inscripcion.objects.filter(comision_id__in=comision_ids)
    if cohorte_ids is not None:
        _insc_qs = _insc_qs.filter(cohorte_id__in=cohorte_ids)

    # Denominador de "completaron X de N". Cuenta estudiantes distintos: un
    # recursante con dos inscripciones en la misma comisión es una persona.
    _estudiantes_por_comision = {
        row['comision_id']: row['n']
        for row in _insc_qs.values('comision_id').annotate(
            n=Count('estudiante_id', distinct=True),
        )
    }

    comisiones_data = []
    for comision in comisiones:
        total_estudiantes = _estudiantes_por_comision.get(comision.id, 0)
        practicas_data = []
        for pc in comision.practicas_comisiones.all():
            practica = pc.practica
            completaron = completaron_map.get(pc.id, 0)
            total_intentos = total_intentos_map.get(pc.id, 0)
            intentos_correctos = intentos_correctos_map.get(pc.id, 0)
            tasa = (intentos_correctos / total_intentos * 100) if total_intentos else None
            practicas_data.append({
                'practica': practica,
                'pc': pc,
                'completaron': completaron,
                'total_estudiantes': total_estudiantes,
                'total_intentos': total_intentos,
                'tasa_acierto': round(tasa, 1) if tasa is not None else None,
            })
        comisiones_data.append({
            'comision': comision,
            'total_estudiantes': total_estudiantes,
            'practicas': practicas_data,
        })

    cfg = ConfigSitio.get()

    # Población del panel: los estudiantes inscriptos en las comisiones y
    # cohortes filtradas. Sin filtro de cohorte agrega todas las camadas,
    # que es lo que este panel viene reportando.
    _estudiantes_dashboard = list(
        _insc_qs.values_list('estudiante_id', flat=True).distinct()
    )

    _silencio = _silencio_temprano(comision_ids, _estudiantes_dashboard, cohorte_ids=cohorte_ids)
    return render(request, 'analiticas/dashboard.html', {
        'filtros':              filtros,
        'comisiones_data':      comisiones_data,
        'ejercicios_dificiles': _ejercicios_mas_dificiles(
            comision_ids, _estudiantes_dashboard, min_intentos=cfg.umbral_min_intentos,
            cohorte_ids=cohorte_ids,
        ),
        'en_riesgo':            _estudiantes_en_riesgo(
            comision_ids, _estudiantes_dashboard, umbral_riesgo=cfg.umbral_riesgo,
            cohorte_ids=cohorte_ids,
        ),
        'distribucion_intentos': _distribucion_intentos(
            comision_ids, _estudiantes_dashboard, cohorte_ids=cohorte_ids,
        ),
        'evolucion_temporal':    _evolucion_temporal(
            comision_ids, _estudiantes_dashboard, cohorte_ids=cohorte_ids,
        ),
        'errores_sistematicos':  _errores_sistematicos(
            comision_ids, _estudiantes_dashboard, min_estudiantes=cfg.error_consenso_min,
            cohorte_ids=cohorte_ids,
        ),
        'silencio':              _silencio,
        'silencio_resumen':      _silencio_resumen(
            _silencio, umbral_silencio_dias=cfg.umbral_silencio_dias,
        ),
        'concentracion':         _concentracion_practica(
            comision_ids, _estudiantes_dashboard, umbral_maraton=cfg.umbral_maraton,
            cohorte_ids=cohorte_ids,
        ),
        'velocidad':             _velocidad_arranque(
            comision_ids, _estudiantes_dashboard, umbral_arranque_dias=cfg.umbral_arranque_dias,
            cohorte_ids=cohorte_ids,
        ),
        # M2: matriz juicio×cómputo. Desde el refactor a multi-comisión ya no
        # depende de que el usuario tenga exactamente una comisión.
        'matriz_juicio':         _matriz_juicio_computo(comision_ids, cohorte_ids=cohorte_ids),
        # M6: señal de práctica con baja variación entre intentos
        'patron_baja_variacion': _patron_adivinacion(
            comision_ids,
            min_intentos=cfg.umbral_adivinacion_intentos,
            max_intervalo_seg=cfg.umbral_adivinacion_segundos,
            modo_pedagogico=True,
            cohorte_ids=cohorte_ids,
        ),
        # Umbrales visibles en template para documentar criterios al docente
        'cfg_umbral_riesgo':                cfg.umbral_riesgo,
        'cfg_umbral_silencio_dias':         cfg.umbral_silencio_dias,
        'cfg_umbral_maraton':               cfg.umbral_maraton,
        'cfg_umbral_arranque_dias':         cfg.umbral_arranque_dias,
        'cfg_umbral_min_intentos':          cfg.umbral_min_intentos,
        'cfg_error_consenso_min':           cfg.error_consenso_min,
        'cfg_umbral_adivinacion_intentos':  cfg.umbral_adivinacion_intentos,
        'cfg_umbral_adivinacion_segundos':  cfg.umbral_adivinacion_segundos,
        'comision_ids_csv':                 ','.join(str(c) for c in comision_ids),
    })


# ──────────────────────────────────────────────
#  Analíticas de investigación
# ──────────────────────────────────────────────

@login_required
def investigacion(request):
    """Vista de métricas de investigación pedagógica.

    Muestra las métricas del módulo ``analiticas.research`` restringidas
    únicamente a estudiantes con ``consentimiento_investigacion=True``.

    Solo accesible para docentes y administradores.
    """
    from django.contrib.auth import get_user_model
    from cursos.models import Inscripcion
    from analiticas.research import (
        cohortes_nse_onboarding,
        cohortes_onboarding,
        cohortes_pandemia_onboarding,
        correlaciones_encuesta,
        desacople_docente_maquina,
        desempeno_por_nse_onboarding,
        desempeno_por_pandemia_onboarding,
        desempeno_por_puntaje_logicas,
        distribucion_carrera_onboarding,
        distribucion_facultad_onboarding,
        distribucion_nse_onboarding,
        distribucion_pandemia_onboarding,
        distribucion_puntaje_logicas,
        intentos_hasta_correcto_sin_sesgo,
        nube_ciencia,
        perfiles_encuesta_onboarding,
        persistencia_relativa,
        tasa_abandono_local,
        tasa_entrada_efectiva,
        trabajo_vs_nota_logica,
    )

    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return redirect('ejercicios:home')

    User = get_user_model()

    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    comisiones = filtros.comisiones
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids

    # Estadísticas de consentimiento
    _insc_qs = Inscripcion.objects.filter(comision_id__in=comision_ids)
    if cohorte_ids is not None:
        _insc_qs = _insc_qs.filter(cohorte_id__in=cohorte_ids)
    estudiantes_ids = list(_insc_qs.values_list('estudiante_id', flat=True).distinct())
    total_est = len(estudiantes_ids)
    con_consent = User.objects.filter(
        id__in=estudiantes_ids, consentimiento_investigacion=True
    ).count()
    sin_consent = User.objects.filter(
        id__in=estudiantes_ids, consentimiento_investigacion=False
    ).count()
    pendiente = total_est - con_consent - sin_consent

    # Métricas filtradas por consentimiento
    entrada = tasa_entrada_efectiva(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    intentos = intentos_hasta_correcto_sin_sesgo(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    persistencia = persistencia_relativa(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    abandono = tasa_abandono_local(
        comision_ids=comision_ids, solo_consentimiento=True, solo_practicas_cerradas=False,
        cohorte_ids=cohorte_ids,
    )

    # Enriquecer filas de EP con pc_id (para links) y enunciado_corto (para tooltip).
    _all_ep_ids = {r['ep_id'] for r in intentos + persistencia + abandono}
    if _all_ep_ids:
        _ep_rows = list(
            EjercicioPractica.objects.filter(id__in=_all_ep_ids)
            .values('id', 'practica_id', 'ejercicio__enunciado')
        )
        _ep_practica = {r['id']: r['practica_id'] for r in _ep_rows}
        _ep_enunciado = {
            r['id']: _strip_html((r['ejercicio__enunciado'] or '')[:120]).strip()[:70]
            for r in _ep_rows
        }
        _pc_lookup = {
            (pc['practica_id'], pc['comision_id']): pc['id']
            for pc in PracticaComision.objects.filter(comision_id__in=comision_ids)
            .values('id', 'practica_id', 'comision_id')
        }

        def _enrich(row):
            ep_id = row['ep_id']
            practica_id = _ep_practica.get(ep_id)
            pc_id = _pc_lookup.get((practica_id, row['comision_id'])) if practica_id else None
            return {
                **row,
                'pc_id': pc_id,
                'enunciado_corto': _ep_enunciado.get(ep_id, ''),
                # Los gráficos consumen esto vía json_script; la tabla de la
                # misma sección arma su link con {% url %} y pc_id/ep_id.
                'url': _url_ejercicio(pc_id, ep_id),
            }

        intentos = [_enrich(r) for r in intentos]
        persistencia = [_enrich(r) for r in persistencia]
        abandono = [_enrich(r) for r in abandono]

    desacople = desacople_docente_maquina(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    encuesta_perfiles = perfiles_encuesta_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    nse = distribucion_nse_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    logicas = distribucion_puntaje_logicas(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    pandemia = distribucion_pandemia_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    cohortes = cohortes_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    cohortes_nse = cohortes_nse_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    cohortes_pandemia = cohortes_pandemia_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    facultades = distribucion_facultad_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    carreras = distribucion_carrera_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    desempeno_nse = desempeno_por_nse_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    desempeno_pandemia = desempeno_por_pandemia_onboarding(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    desempeno_logicas = desempeno_por_puntaje_logicas(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    correlaciones = correlaciones_encuesta(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    nube_palabras_ciencia = nube_ciencia(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    trabajo_nota = trabajo_vs_nota_logica(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)

    return render(request, 'analiticas/investigacion.html', {
        'filtros': filtros,
        'comisiones': comisiones,
        'total_est': total_est,
        'con_consent': con_consent,
        'sin_consent': sin_consent,
        'pendiente': pendiente,
        'entrada': entrada,
        'intentos': intentos,
        'persistencia': persistencia,
        'abandono': abandono,
        'desacople': desacople,
        'encuesta_total': len(encuesta_perfiles),
        'nse': nse,
        'logicas': logicas,
        'pandemia': pandemia,
        'cohortes': cohortes,
        'cohortes_nse': cohortes_nse,
        'cohortes_pandemia': cohortes_pandemia,
        'facultades': facultades,
        'carreras': carreras,
        'desempeno_nse': desempeno_nse,
        'desempeno_pandemia': desempeno_pandemia,
        'desempeno_logicas': desempeno_logicas,
        'correlaciones': correlaciones,
        'nube_palabras_ciencia': nube_palabras_ciencia,
        'trabajo_nota': trabajo_nota,
        'nota_final_disponible': False,
    })


# ──────────────────────────────────────────────
#  Red de co-ocurrencia de errores (JSON)
# ──────────────────────────────────────────────

@login_required
def red_errores_json(request):
    """Endpoint JSON para la red de co-ocurrencia de errores.

    Query params:
        comision_ids: IDs separados por coma (default: todas las permitidas).
        cohorte_ids: IDs separados por coma (default: todas).
        comision_id: alias singular heredado.
    """
    from django.http import JsonResponse
    from analiticas.research import red_errores
    from analiticas.filtros import resolver_filtros

    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return JsonResponse({'error': 'no autorizado'}, status=403)

    filtros = resolver_filtros(request)
    if filtros.seleccion_vacia:
        return JsonResponse({'error': 'no autorizado'}, status=403)

    data = red_errores(
        comision_ids=filtros.comision_ids,
        solo_consentimiento=True,
        cohorte_ids=filtros.cohorte_ids,
    )
    return JsonResponse(data)


# ──────────────────────────────────────────────
#  Resumen de encuesta inicial
# ──────────────────────────────────────────────

@login_required
def encuesta_resumen(request):
    """Vista de resumen descriptivo de la encuesta inicial de onboarding.

    Muestra distribuciones por pregunta para todos los estudiantes que
    completaron la encuesta (consentimiento pedagógico). No requiere
    consentimiento de investigación.

    Solo accesible para docentes y administradores.
    """
    from django.contrib.auth import get_user_model
    from cursos.models import Inscripcion
    from analiticas.research import (
        cohortes_onboarding,
        distribucion_carrera_onboarding,
        distribucion_facultad_onboarding,
        distribucion_nse_onboarding,
        distribucion_pandemia_onboarding,
        distribucion_puntaje_logicas,
        distribuciones_encuesta_detalle,
    )

    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return redirect('ejercicios:home')

    User = get_user_model()

    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    comisiones = filtros.comisiones
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids

    # Totales de participación
    _insc_qs = Inscripcion.objects.filter(comision_id__in=comision_ids)
    if cohorte_ids is not None:
        _insc_qs = _insc_qs.filter(cohorte_id__in=cohorte_ids)
    estudiantes_ids = list(_insc_qs.values_list('estudiante_id', flat=True).distinct())
    total_est = len(estudiantes_ids)
    con_encuesta = User.objects.filter(
        id__in=estudiantes_ids, encuesta__isnull=False,
    ).count()

    nse = distribucion_nse_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    logicas = distribucion_puntaje_logicas(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    pandemia = distribucion_pandemia_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    facultades = distribucion_facultad_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    carreras = distribucion_carrera_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    cohortes = cohortes_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    detalle = distribuciones_encuesta_detalle(comision_ids, cohorte_ids=cohorte_ids)

    return render(request, 'analiticas/encuesta_resumen.html', {
        'filtros': filtros,
        'comisiones': comisiones,
        'comision_ids_csv': ','.join(str(cid) for cid in comision_ids),
        'total_est': total_est,
        'con_encuesta': con_encuesta,
        'sin_encuesta': total_est - con_encuesta,
        'nse': nse,
        'logicas': logicas,
        'pandemia': pandemia,
        'facultades': facultades,
        'carreras': carreras,
        'cohortes': cohortes,
        'detalle': detalle,
    })


# ──────────────────────────────────────────────
#  Drill-down por ejercicio (M3 / M4 / M5)
# ──────────────────────────────────────────────

@login_required
def detalle_ejercicio(request):
    """Devuelve JSON con métricas M3/M4/M5 para un ejercicio y un recorte dado.

    GET params:
        ejercicio_id: int — ID del Ejercicio (obligatorio)
        comision_ids: IDs separados por coma (default: todas las permitidas)
        cohorte_ids: IDs separados por coma (default: todas)

    Solo accesible para docentes y admins. ``resolver_filtros`` descarta las
    comisiones ajenas; si la selección explícita queda vacía, devuelve 403.
    """
    from django.http import JsonResponse
    from analiticas.calculos import (
        _convergencia_por_ejercicio,
        _indice_atomizacion,
        _perfil_error_tabla,
    )
    from analiticas.filtros import resolver_filtros

    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return JsonResponse({'error': 'Acceso denegado'}, status=403)

    try:
        ejercicio_id = int(request.GET['ejercicio_id'])
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Parámetros inválidos'}, status=400)

    filtros = resolver_filtros(request)
    if filtros.seleccion_vacia or not filtros.comision_ids:
        return JsonResponse({'error': 'Acceso denegado'}, status=403)

    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids

    return JsonResponse({
        'convergencia': _convergencia_por_ejercicio(comision_ids, ejercicio_id, cohorte_ids=cohorte_ids),
        'perfil_tabla': _perfil_error_tabla(comision_ids, ejercicio_id, cohorte_ids=cohorte_ids),
        'atomizacion': _indice_atomizacion(comision_ids, ejercicio_id, cohorte_ids=cohorte_ids),
    })


# ──────────────────────────────────────────────
#  Exportación CSV / XLSX / ODS
# ──────────────────────────────────────────────

_DATASET_INFO = {
    'errores_sistematicos': 'Errores compartidos',
    'entrada': 'Tasa de entrada efectiva',
    'intentos': 'Intentos hasta correcto (sin sesgo)',
    'persistencia': 'Persistencia relativa',
    'abandono': 'Tasa de abandono local',
    'desacople': 'Desacople docente-máquina',
    'encuesta_perfiles': 'Perfiles de onboarding y desempeño',
    'encuesta_nse': 'Distribución NSE de onboarding',
    'encuesta_logicas': 'Distribución puntaje lógicas',
    'encuesta_pandemia': 'Distribución pandemia',
    'encuesta_cohortes': 'Cohortes de onboarding',
    'encuesta_cohortes_nse': 'Cohortes por NSE',
    'encuesta_cohortes_pandemia': 'Cohortes por pandemia',
    'encuesta_facultades': 'Distribución de facultades',
    'encuesta_carreras': 'Distribución de carreras',
    'desempeno_nse': 'Desempeño por NSE',
    'desempeno_pandemia': 'Desempeño por pandemia',
    'desempeno_logicas': 'Desempeño por puntaje de lógicas',
}


def _datos_exportacion(dataset, comision_ids, cohorte_ids=None):
    """Devuelve (headers, rows) para el dataset indicado.

    Los datos están filtrados por consentimiento_investigacion=True.
    Retorna (None, None) si el dataset es desconocido.
    """
    from analiticas.research import (
        cohortes_nse_onboarding,
        cohortes_onboarding,
        cohortes_pandemia_onboarding,
        desacople_docente_maquina,
        desempeno_por_nse_onboarding,
        desempeno_por_pandemia_onboarding,
        desempeno_por_puntaje_logicas,
        distribucion_carrera_onboarding,
        distribucion_facultad_onboarding,
        distribucion_nse_onboarding,
        distribucion_pandemia_onboarding,
        distribucion_puntaje_logicas,
        intentos_hasta_correcto_sin_sesgo,
        perfiles_encuesta_onboarding,
        persistencia_relativa,
        tasa_abandono_local,
        tasa_entrada_efectiva,
    )

    kw = dict(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)

    if dataset == 'entrada':
        rows = tasa_entrada_efectiva(**kw)
        headers = ['comision_id', 'practica_id', 'practica_titulo',
                   'total_estudiantes', 'con_intento', 'sin_intento', 'tasa_entrada']

    elif dataset == 'intentos':
        rows = intentos_hasta_correcto_sin_sesgo(**kw)
        headers = ['ep_id', 'comision_id', 'resolvieron', 'no_resolvieron',
                   'pct_no_resolvio', 'mediana_hasta_correcto', 'promedio_hasta_correcto']

    elif dataset == 'persistencia':
        rows = persistencia_relativa(**kw)
        headers = ['ep_id', 'comision_id', 'intentaron_con_fallo',
                   'persistieron', 'abandonaron', 'tasa_persistencia']

    elif dataset == 'abandono':
        rows = tasa_abandono_local(solo_practicas_cerradas=False, **kw)
        headers = ['ep_id', 'comision_id', 'intentaron', 'no_resolvieron',
                   'tasa_abandono', 'practica_cerrada']

    elif dataset == 'desacople':
        data = desacople_docente_maquina(**kw)
        rows = [data]
        headers = ['total_revisados', 'maquina_ok_docente_no', 'maquina_no_docente_ok',
                   'acuerdo', 'tasa_desacople', 'tasa_maquina_liberal', 'tasa_maquina_estricta']

    elif dataset == 'encuesta_perfiles':
        rows = perfiles_encuesta_onboarding(**kw)
        headers = ['pseudonimo', 'comision_id', 'comision_nombre', 'anio', 'cuatri', 'facultad', 'carrera', 'puntaje_nse', 'categoria_nse', 'puntaje_logicas', 'pandemia', 'intentos_total', 'intentos_correctos', 'ejercicios_intentados', 'ejercicios_resueltos', 'practicas_completadas', 'tasa_acierto_intentos', 'tasa_resolucion_ejercicios', 'hizo_algun_intento', 'resolvio_alguno']

    elif dataset == 'encuesta_nse':
        rows = distribucion_nse_onboarding(**kw)
        headers = ['categoria_nse', 'count', 'porcentaje', 'puntaje_promedio']

    elif dataset == 'encuesta_logicas':
        rows = distribucion_puntaje_logicas(**kw)
        headers = ['puntaje_logicas', 'count', 'porcentaje']

    elif dataset == 'encuesta_pandemia':
        rows = distribucion_pandemia_onboarding(**kw)
        headers = ['pandemia', 'count', 'porcentaje']

    elif dataset == 'encuesta_cohortes':
        rows = cohortes_onboarding(**kw)
        headers = ['anio', 'cuatri', 'count']

    elif dataset == 'encuesta_cohortes_nse':
        rows = cohortes_nse_onboarding(**kw)
        headers = ['anio', 'cuatri', 'categoria_nse', 'count']

    elif dataset == 'encuesta_cohortes_pandemia':
        rows = cohortes_pandemia_onboarding(**kw)
        headers = ['anio', 'cuatri', 'pandemia', 'count', 'porcentaje']

    elif dataset == 'encuesta_facultades':
        rows = distribucion_facultad_onboarding(**kw)
        headers = ['facultad', 'count', 'porcentaje']

    elif dataset == 'encuesta_carreras':
        rows = distribucion_carrera_onboarding(**kw)
        headers = ['carrera', 'count', 'porcentaje']

    elif dataset == 'desempeno_nse':
        rows = desempeno_por_nse_onboarding(**kw)
        headers = ['categoria_nse', 'count', 'con_intento', 'resolvio_alguno', 'promedio_intentos', 'promedio_resueltos', 'promedio_tasa_resolucion', 'promedio_practicas_completadas', 'pct_con_intento', 'pct_resolvio_alguno']

    elif dataset == 'desempeno_pandemia':
        rows = desempeno_por_pandemia_onboarding(**kw)
        headers = ['pandemia', 'count', 'con_intento', 'resolvio_alguno', 'promedio_intentos', 'promedio_resueltos', 'promedio_tasa_resolucion', 'promedio_practicas_completadas', 'pct_con_intento', 'pct_resolvio_alguno']

    elif dataset == 'desempeno_logicas':
        rows = desempeno_por_puntaje_logicas(**kw)
        headers = ['puntaje_logicas', 'count', 'con_intento', 'resolvio_alguno', 'promedio_intentos', 'promedio_resueltos', 'promedio_tasa_resolucion', 'promedio_practicas_completadas', 'pct_con_intento', 'pct_resolvio_alguno']

    elif dataset == 'errores_sistematicos':
        from accounts.models import ConfigSitio as _ConfigSitio
        from cursos.models import Inscripcion as _Inscripcion
        cfg = _ConfigSitio.get()
        # Misma población y filtro de cohorte que dashboard() (views.py,
        # _estudiantes_dashboard): _insc_qs se acota por cohorte_ids antes
        # de listar estudiantes, y _errores_sistematicos recibe cohorte_ids
        # para filtrar los intentos directamente por Intento.cohorte (evita
        # contar dos veces al mismo recursante en distintas camadas).
        _insc_qs_export = _Inscripcion.objects.filter(comision_id__in=comision_ids)
        if cohorte_ids is not None:
            _insc_qs_export = _insc_qs_export.filter(cohorte_id__in=cohorte_ids)
        _estudiantes_export = list(
            _insc_qs_export.values_list('estudiante_id', flat=True).distinct()
        )
        data = _errores_sistematicos(
            comision_ids, _estudiantes_export, min_estudiantes=cfg.error_consenso_min,
            cohorte_ids=cohorte_ids,
        )
        rows = [
            {
                'ejercicio': _strip_html(e['enunciado']),
                'practica': e['practica_titulo'],
                'tipo': e['tipo'],
                'respuesta': e['respuesta_display'],
                'n_estudiantes': e['n_estudiantes'],
            }
            for e in data
        ]
        headers = ['ejercicio', 'practica', 'tipo', 'respuesta', 'n_estudiantes']

    else:
        return None, None

    return headers, rows


def _bytes_csv(headers, rows):
    """Genera bytes UTF-8 con BOM de un CSV."""
    import csv
    import json as _j

    def _normalizar(row):
        return {
            k: (_j.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
            for k, v in row.items()
        }

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers, extrasaction='ignore', lineterminator='\r\n')
    w.writeheader()
    w.writerows(_normalizar(r) for r in rows)
    return b'\xef\xbb\xbf' + buf.getvalue().encode('utf-8')


def _bytes_xlsx(headers, rows, titulo='Datos'):
    """Genera bytes XLSX usando openpyxl."""
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titulo[:31]

    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    def _celda(v):
        if isinstance(v, (list, dict)):
            import json as _j
            return _j.dumps(v, ensure_ascii=False)
        return v

    for row in rows:
        ws.append([_celda(row.get(h)) for h in headers])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _bytes_ods(headers, rows, titulo='Datos'):
    """Genera bytes ODS mínimo usando stdlib (zipfile + xml.etree)."""
    import zipfile
    import xml.etree.ElementTree as ET

    NS = {
        'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
        'table':  'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
        'text':   'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
        'meta':   'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    }
    for prefix, uri in NS.items():
        ET.register_namespace(prefix, uri)

    def cell(value):
        tc = ET.Element('{%s}table-cell' % NS['table'])
        p = ET.SubElement(tc, '{%s}p' % NS['text'])
        p.text = '' if value is None else str(value)
        return tc

    def make_row(values):
        tr = ET.Element('{%s}table-row' % NS['table'])
        for v in values:
            tr.append(cell(v))
        return tr

    root = ET.Element('{%s}document-content' % NS['office'])
    body = ET.SubElement(root, '{%s}body' % NS['office'])
    ss = ET.SubElement(body, '{%s}spreadsheet' % NS['office'])
    tbl = ET.SubElement(ss, '{%s}table' % NS['table'])
    tbl.set('{%s}name' % NS['table'], titulo[:31])

    tbl.append(make_row(headers))
    for row in rows:
        tbl.append(make_row([row.get(h) for h in headers]))

    content_xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode').encode('utf-8')

    manifest_xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        b'<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>'
        b'<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
        b'</manifest:manifest>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo('mimetype'), 'application/vnd.oasis.opendocument.spreadsheet')
        zf.writestr('META-INF/manifest.xml', manifest_xml)
        zf.writestr('content.xml', content_xml)
    return buf.getvalue()


@login_required
def exportar(request, dataset):
    """Exporta un dataset de investigación en CSV, XLSX u ODS.

    Solo datos de estudiantes con consentimiento_investigacion=True.

    Query params:
        formato: 'csv' (default) | 'xlsx' | 'ods'
        comision_ids: IDs separados por coma (default: todas las del usuario)
        cohorte_ids: IDs separados por coma (default: todas)
    """
    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return redirect('ejercicios:home')

    formato = request.GET.get('formato', 'csv')
    if formato not in ('csv', 'xlsx', 'ods'):
        formato = 'csv'

    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    if filtros.seleccion_vacia:
        return HttpResponse('Sin datos para exportar con ese filtro.', status=403)
    headers, rows = _datos_exportacion(dataset, filtros.comision_ids, filtros.cohorte_ids)
    if headers is None:
        from django.http import Http404
        raise Http404

    titulo = _DATASET_INFO.get(dataset, dataset)
    filename = f'ipc-investigacion-{dataset}'

    if formato == 'xlsx':
        content = _bytes_xlsx(headers, rows, titulo)
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ext = 'xlsx'
    elif formato == 'ods':
        content = _bytes_ods(headers, rows, titulo)
        mime = 'application/vnd.oasis.opendocument.spreadsheet'
        ext = 'ods'
    else:
        content = _bytes_csv(headers, rows)
        mime = 'text/csv; charset=utf-8'
        ext = 'csv'

    response = HttpResponse(content, content_type=mime)
    response['Content-Disposition'] = f'attachment; filename="{filename}.{ext}"'
    return response


# ──────────────────────────────────────────────
#  Descarga de datasets anonimizados (encuesta e intentos)
# ──────────────────────────────────────────────

_HEADERS_EJERCICIOS = (
    "ejercicio_practica_id",
    "practica_id", "practica_titulo", "orden_en_practica",
    "ejercicio_id", "tipo", "enunciado",
    "formula_solucion", "diccionario_solucion", "valores_verdad_solucion",
)

_HEADERS_PRACTICAS = (
    "practica_comision_id",
    "practica_id", "practica_titulo",
    "comision_id", "orden_en_comision",
    "fecha_apertura_unix", "fecha_cierre_unix",
)


def _dataset_ejercicios(comision_ids):
    """Catálogo de ejercicios (EjercicioPractica) para las comisiones dadas. Sin PII."""
    from ejercicios.models import EjercicioPractica
    qs = (
        EjercicioPractica.objects
        .filter(practica__practicas_comisiones__comision_id__in=comision_ids)
        .select_related('practica', 'ejercicio')
        .order_by('practica_id', 'orden')
        .distinct()
    )
    filas = []
    for ep in qs:
        ej = ep.ejercicio
        filas.append({
            "ejercicio_practica_id": ep.id,
            "practica_id": ep.practica_id,
            "practica_titulo": ep.practica.titulo,
            "orden_en_practica": ep.orden,
            "ejercicio_id": ej.id,
            "tipo": ej.tipo,
            "enunciado": ej.enunciado,
            "formula_solucion": ej.formula_solucion,
            "diccionario_solucion": ej.diccionario_solucion or None,
            "valores_verdad_solucion": ej.valores_verdad_solucion,
        })
    return filas


def _dataset_practicas(comision_ids):
    """Catálogo de prácticas (PracticaComision) para las comisiones dadas. Sin PII."""
    from ejercicios.models import PracticaComision
    qs = (
        PracticaComision.objects
        .filter(comision_id__in=comision_ids)
        .select_related('practica')
        .order_by('comision_id', 'orden')
    )
    filas = []
    for pc in qs:
        filas.append({
            "practica_comision_id": pc.id,
            "practica_id": pc.practica_id,
            "practica_titulo": pc.practica.titulo,
            "comision_id": pc.comision_id,
            "orden_en_comision": pc.orden,
            "fecha_apertura_unix": int(pc.fecha_apertura.timestamp()) if pc.fecha_apertura else None,
            "fecha_cierre_unix": int(pc.fecha_cierre.timestamp()) if pc.fecha_cierre else None,
        })
    return filas


@login_required
def descargar_investigacion(request):
    """Descarga un dataset anonimizado (encuesta o intentos) con filtros opcionales.

    Query params:
        dataset   : 'encuesta' | 'intentos' | 'ejercicios' | 'practicas' | 'trabajo_nota'
        formato   : 'csv' | 'xlsx'  (encuesta)  /  'csv' | 'json'  (intentos)
        comision_ids : IDs separados por coma (default: todas las permitidas)
        cohorte_ids  : IDs separados por coma (default: todas)
        cohorte      : 'YYYY-C' ej. '2026-1' — alias heredado
    """
    import json as _json
    from analiticas.anonimizador import (
        HEADERS_ENCUESTA, HEADERS_INTENTOS,
        dataset_encuesta, dataset_intentos,
    )
    from analiticas.filtros import resolver_filtros

    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return redirect('ejercicios:home')

    dataset = request.GET.get('dataset', 'encuesta')
    if dataset not in ('encuesta', 'intentos', 'ejercicios', 'practicas', 'trabajo_nota'):
        dataset = 'encuesta'

    formato = request.GET.get('formato', 'csv')

    filtros = resolver_filtros(request)
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids

    if not comision_ids:
        return HttpResponse('Sin comisiones disponibles.', status=403)

    from django.utils.timezone import now as _now
    fecha_str = _now().strftime('%Y%m%d')

    if dataset == 'encuesta':
        rows = dataset_encuesta(comision_ids, cohorte_ids=cohorte_ids)
        headers = list(HEADERS_ENCUESTA)
        nombre_base = f'ipc-encuesta-{fecha_str}'

        if formato == 'xlsx':
            content = _bytes_xlsx(headers, rows, 'Encuesta inicial IPC')
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ext = 'xlsx'
        else:
            content = _bytes_csv(headers, rows)
            mime = 'text/csv; charset=utf-8'
            ext = 'csv'

    elif dataset == 'ejercicios':
        rows = _dataset_ejercicios(comision_ids)
        headers = list(_HEADERS_EJERCICIOS)
        nombre_base = f'ipc-ejercicios-{fecha_str}'

        if formato == 'json':
            content = _json.dumps(rows, ensure_ascii=False, indent=2).encode('utf-8')
            mime = 'application/json; charset=utf-8'
            ext = 'json'
        elif formato == 'xlsx':
            content = _bytes_xlsx(headers, rows, 'Ejercicios IPC')
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ext = 'xlsx'
        else:
            content = _bytes_csv(headers, rows)
            mime = 'text/csv; charset=utf-8'
            ext = 'csv'

    elif dataset == 'practicas':
        rows = _dataset_practicas(comision_ids)
        headers = list(_HEADERS_PRACTICAS)
        nombre_base = f'ipc-practicas-{fecha_str}'

        if formato == 'xlsx':
            content = _bytes_xlsx(headers, rows, 'Prácticas IPC')
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ext = 'xlsx'
        else:
            content = _bytes_csv(headers, rows)
            mime = 'text/csv; charset=utf-8'
            ext = 'csv'

    elif dataset == 'trabajo_nota':
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=comision_ids, solo_consentimiento=True,
                                     cohorte_ids=cohorte_ids)
        headers = ['intentos_totales', 'dias_activos', 'ejercicios_distintos',
                   'practicas_abiertas', 'indice_trabajo', 'nota_logica', 'desenlace']
        rows = [[p[h] for h in headers] for p in res['puntos']]
        nombre_base = f'ipc-trabajo-nota-{fecha_str}'

        if formato == 'xlsx':
            content = _bytes_xlsx(headers, rows, 'Trabajo vs nota lógica')
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ext = 'xlsx'
        else:
            content = _bytes_csv(headers, rows)
            mime = 'text/csv; charset=utf-8'
            ext = 'csv'

    else:  # intentos
        rows = dataset_intentos(comision_ids, cohorte_ids=cohorte_ids)
        headers = list(HEADERS_INTENTOS)
        nombre_base = f'ipc-intentos-{fecha_str}'

        if formato == 'json':
            content = _json.dumps(rows, ensure_ascii=False, indent=2).encode('utf-8')
            mime = 'application/json; charset=utf-8'
            ext = 'json'
        else:
            content = _bytes_csv(headers, rows)
            mime = 'text/csv; charset=utf-8'
            ext = 'csv'

    response = HttpResponse(content, content_type=mime)
    response['Content-Disposition'] = f'attachment; filename="{nombre_base}.{ext}"'
    return response

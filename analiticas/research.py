"""Métricas de investigación pedagógica para la parte lógica de IPC-Lógica.

Funciones puras sobre QuerySets de Intento/Progreso, separadas del dashboard
operativo (analiticas/views.py). Devuelven listas de dicts con tipos documentados.

## API uniforme

Todas las funciones principales aceptan ``comision_ids=None``:
  - ``None``           → agrega datos de TODAS las comisiones del sistema
  - ``[1, 3, 5]``     → filtra a esas comisiones

Las funciones de nivel EP aceptan además ``ep_ids=None``:
  - ``None``           → deriva los EPs de comision_ids
  - ``[10, 20, 30]``  → usa exactamente esos EPs (ignora comision_ids)

Para desagregar resultados por comisión usar la utilidad:
  ``desagregar_por_comision(fn, comision_ids=None, **kwargs)``
  → devuelve ``{comision_id: resultado, ...}``

## Principios (AGENTS.md)
  - Sin rankings ni score global de riesgo.
  - Variables continuas > umbrales fijos binarios.
  - Transparencia: cada función documenta su nivel de análisis y sesgos.
  - Los datos de investigación deben filtrar por consentimiento_investigacion=True
    antes de publicarlos externamente. Ver ``_filtrar_por_consentimiento()``.
"""

import math as _math
import statistics as _statistics
from collections import Counter, defaultdict

from django.db.models import Count, Min, Q
from django.utils import timezone

from cursos.models import Inscripcion
from ejercicios.models import EjercicioPractica, Intento, PracticaComision, Progreso


# ─── Utilidades ───────────────────────────────────────────────────────────────

def _resolver_comision_ids(comision_ids):
    """Si comision_ids es None, devuelve todos los IDs del sistema."""
    from cursos.models import Comision
    if comision_ids is None:
        return list(Comision.objects.values_list('id', flat=True))
    return list(comision_ids)


def _ep_ids_de_comisiones(comision_ids):
    """Devuelve los IDs de EjercicioPractica de las comisiones dadas.

    Traversal: EP → Practica → PracticaComision → Comision.
    Usa distinct() porque una Practica puede estar en varias comisiones
    (múltiples filas en PracticaComision).
    """
    return list(
        EjercicioPractica.objects
        .filter(practica__practicas_comisiones__comision_id__in=comision_ids)
        .distinct()
        .values_list('id', flat=True)
    )


def _filtrar_por_consentimiento(qs):
    """Filtra un queryset de Intento a estudiantes con consentimiento de investigación.

    Usar cuando los datos se vayan a publicar en investigación formal.
    No necesario para el dashboard operativo (cubierto por consentimiento pedagógico).
    """
    return qs.filter(estudiante__consentimiento_investigacion=True)


def _filtrar_por_cohorte(qs, cohorte_ids):
    """Acota un queryset de Intento (o de otro modelo con campo ``cohorte``) por cohorte.

    ``cohorte_ids=None`` incluye todas las camadas. Acotar por cohorte permite
    comparar camadas entre sí en vez de mezclarlas en un solo agregado.
    """
    if cohorte_ids is None:
        return qs
    return qs.filter(cohorte_id__in=cohorte_ids)


def desagregar_por_comision(fn, comision_ids=None, **kwargs):
    """Ejecuta una función de research.py una vez por comisión.

    Útil para comparar resultados entre comisiones o cuatrimestres.

    Args:
        fn: función de research.py que acepta ``comision_ids`` como kwarg.
        comision_ids: iterable de IDs, o None para todas las comisiones.
        **kwargs: argumentos adicionales pasados a fn (p.ej. solo_consentimiento=True).

    Returns:
        Dict ``{comision_id: resultado}`` donde resultado es lo que
        devuelve ``fn(comision_ids=[cid], **kwargs)``.

    Ejemplo:
        >>> por_comision = desagregar_por_comision(desacople_docente_maquina)
        >>> por_comision[3]['tasa_desacople']
        0.12
    """
    ids = _resolver_comision_ids(comision_ids)
    return {cid: fn(comision_ids=[cid], **kwargs) for cid in ids}


# ─── A. ENTRADA AL TRABAJO ────────────────────────────────────────────────────

def tasa_entrada_efectiva(comision_ids=None, practica_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Proporción de estudiantes que realizó ≥1 intento en cada práctica.

    Pregunta: ¿Qué fracción del aula llega a trabajar en cada práctica?
    Nivel: práctica × comisión.

    Args:
        comision_ids: iterable de IDs de Comision, o None para todas.
        practica_ids: iterable de IDs de Practica para filtrar adicionalmente.
            Si None, usa todas las prácticas de las comisiones.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Lista de dicts con:
          - comision_id (int)
          - practica_id (int)
          - practica_titulo (str)
          - total_estudiantes (int): inscriptos en esa comisión
          - con_intento (int): quienes realizaron ≥1 intento en esa práctica
          - sin_intento (int)
          - tasa_entrada (float | None): con_intento / total

    Sesgo: no controla si la práctica estaba abierta durante todo el período.
    Para prácticas cerradas antes de que el estudiante se inscribiera,
    tasa_entrada será 0 de forma correcta pero no informativa.
    """
    from cursos.models import Inscripcion

    cids = _resolver_comision_ids(comision_ids)

    # Prácticas en estas comisiones via PracticaComision (tabla intermedia).
    pcs_qs = PracticaComision.objects.filter(comision_id__in=cids)
    if practica_ids is not None:
        pcs_qs = pcs_qs.filter(practica_id__in=practica_ids)
    pcs_list = list(pcs_qs.values('id', 'practica_id', 'practica__titulo', 'comision_id'))

    # Inscriptos por comisión.
    # Si solo_consentimiento=True, el denominador también se restringe a
    # estudiantes con consentimiento_investigacion=True para que numerador
    # y denominador sean poblaciones comparables.
    qs_inscriptos = Inscripcion.objects.filter(comision_id__in=cids)
    qs_inscriptos = _filtrar_por_cohorte(qs_inscriptos, cohorte_ids)
    if solo_consentimiento:
        qs_inscriptos = qs_inscriptos.filter(
            estudiante__consentimiento_investigacion=True
        )
    inscriptos_por_comision = {
        r['comision_id']: r['n']
        for r in qs_inscriptos
        .values('comision_id').annotate(n=Count('estudiante_id', distinct=True))
    }

    # Estudiantes con ≥1 intento por PracticaComision.
    # Nota: solo captura intentos con practica_comision seteado (post-PR#37).
    pc_ids = [pc['id'] for pc in pcs_list]
    qs_intentos = Intento.objects.filter(practica_comision_id__in=pc_ids)
    qs_intentos = _filtrar_por_cohorte(qs_intentos, cohorte_ids)
    if solo_consentimiento:
        qs_intentos = _filtrar_por_consentimiento(qs_intentos)
    intentos_por_pc = {
        r['practica_comision_id']: r['n']
        for r in qs_intentos
        .values('practica_comision_id')
        .annotate(n=Count('estudiante_id', distinct=True))
    }

    resultados = []
    for pc in pcs_list:
        total = inscriptos_por_comision.get(pc['comision_id'], 0)
        con = intentos_por_pc.get(pc['id'], 0)
        resultados.append({
            'comision_id': pc['comision_id'],
            'practica_id': pc['practica_id'],
            'practica_titulo': pc['practica__titulo'],
            'total_estudiantes': total,
            'con_intento': con,
            'sin_intento': total - con,
            'tasa_entrada': round(con / total, 4) if total else None,
        })
    return resultados


def demora_primer_intento(practica_id, comision_ids=None, *, cohorte_ids=None):
    """Días entre la apertura de la práctica y el primer intento de cada estudiante.

    Pregunta: ¿Cuándo empieza el trabajo lógico?
    Nivel: estudiante × práctica.

    Solo calcula si la práctica tiene fecha_apertura definida.

    Args:
        practica_id: ID de la Practica.
        comision_ids: iterable de IDs de Comision, o None para todas.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Lista de dicts con:
          - comision_id (int)
          - estudiante_id (int)
          - dias_demora (int | None): días desde apertura hasta primer intento;
            None si el estudiante nunca intentó.

    Sesgo: dias_demora < 0 posible en prácticas migradas con fecha_apertura
    retroactiva. Filtrar dias_demora >= 0 para análisis limpio.

    PRIVACIDAD: devuelve estudiante_id individualmente (dato identificable).
    Filtrar por consentimiento antes de exponer externamente:
        qs = Intento.objects.filter(...)
        qs = _filtrar_por_consentimiento(qs)
    Esta función no tiene parámetro solo_consentimiento porque agrega a nivel
    individual; quien la consuma en contexto de investigación debe aplicar el
    filtro manualmente o agregar antes de publicar.
    """
    from cursos.models import Inscripcion

    cids = _resolver_comision_ids(comision_ids)

    # fecha_apertura ahora vive en PracticaComision, no en Practica.
    # Puede ser distinta por comisión para la misma práctica.
    pcs = list(
        PracticaComision.objects
        .filter(practica_id=practica_id, comision_id__in=cids)
        .values('comision_id', 'fecha_apertura')
    )
    # apertura_por_comision = {comision_id: fecha_apertura}
    apertura_por_comision = {pc['comision_id']: pc['fecha_apertura'] for pc in pcs}
    # Sólo procesar comisiones con fecha_apertura definida
    cids_con_apertura = [cid for cid, fa in apertura_por_comision.items() if fa is not None]
    if not cids_con_apertura:
        return []

    # Primer intento por estudiante en esta práctica (dentro de las comisiones relevantes)
    qs_intentos = Intento.objects.filter(
        ejercicio_practica__practica_id=practica_id,
        practica_comision__comision_id__in=cids_con_apertura,
    )
    qs_intentos = _filtrar_por_cohorte(qs_intentos, cohorte_ids)
    primeros = {
        r['estudiante']: r['primer']
        for r in qs_intentos.values('estudiante').annotate(primer=Min('timestamp'))
    }

    # Inscriptos en las comisiones con apertura definida.
    # Un recursante tiene una fila de Inscripcion por cohorte en la misma
    # comisión; esta función agrega a nivel estudiante × práctica (no por
    # cohorte), así que se deduplica por (estudiante_id, comision_id) para
    # no emitir dos filas idénticas para la misma persona.
    qs_inscriptos = Inscripcion.objects.filter(comision_id__in=cids_con_apertura)
    qs_inscriptos = _filtrar_por_cohorte(qs_inscriptos, cohorte_ids)
    inscriptos = list(
        qs_inscriptos.values('estudiante_id', 'comision_id').distinct()
    )

    resultados = []
    for ins in inscriptos:
        apertura = apertura_por_comision.get(ins['comision_id'])
        primer = primeros.get(ins['estudiante_id'])
        dias = (primer - apertura).days if primer and apertura else None
        resultados.append({
            'comision_id': ins['comision_id'],
            'estudiante_id': ins['estudiante_id'],
            'dias_demora': dias,
        })
    return resultados


# ─── B. SOSTENIMIENTO / RITMO ─────────────────────────────────────────────────

def persistencia_relativa(ep_ids=None, comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Proporción de estudiantes que re-intentaron un EP tras un primer fallo.

    Pregunta: ¿Los estudiantes que fallan persisten o abandonan?
    Nivel: EP.

    Args:
        ep_ids: iterable de IDs de EjercicioPractica, o None para derivar
            de comision_ids.
        comision_ids: iterable de IDs de Comision, o None para todas.
            Ignorado si ep_ids está especificado.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Lista de dicts con:
          - ep_id (int)
          - comision_id (int)
          - intentaron_con_fallo (int): estudiantes con ≥1 fallo
          - persistieron (int): de esos, cuántos volvieron a intentar
          - abandonaron (int)
          - tasa_persistencia (float | None)

    Sesgo: no distingue abandono local (deja ese EP, sigue con otro) de
    abandono global. Combinar con tasa_entrada_efectiva para ese análisis.
    """
    cids = _resolver_comision_ids(comision_ids)
    ids = ep_ids if ep_ids is not None else _ep_ids_de_comisiones(cids)

    # Mapeo ep_id → comision_id via PracticaComision.
    # Si un EP está en varias comisiones de cids, queda la última (inusual).
    ep_comision = dict(
        EjercicioPractica.objects
        .filter(id__in=ids, practica__practicas_comisiones__comision_id__in=cids)
        .distinct()
        .values_list('id', 'practica__practicas_comisiones__comision_id')
    )

    qs_raw = Intento.objects.filter(ejercicio_practica_id__in=ids)
    qs_raw = _filtrar_por_cohorte(qs_raw, cohorte_ids)
    if solo_consentimiento:
        qs_raw = _filtrar_por_consentimiento(qs_raw)
    intentos_raw = (
        qs_raw
        .order_by('estudiante_id', 'ejercicio_practica_id', 'timestamp')
        .values('estudiante_id', 'ejercicio_practica_id', 'es_correcto')
    )

    grupos = defaultdict(list)
    for i in intentos_raw:
        grupos[(i['ejercicio_practica_id'], i['estudiante_id'])].append(i['es_correcto'])

    ep_stats = defaultdict(lambda: {'intentaron_con_fallo': 0, 'persistieron': 0})
    for (ep_id, _est_id), correcciones in grupos.items():
        if not any(not c for c in correcciones):
            continue
        ep_stats[ep_id]['intentaron_con_fallo'] += 1
        primer_fallo = next(i for i, c in enumerate(correcciones) if not c)
        if len(correcciones) > primer_fallo + 1:
            ep_stats[ep_id]['persistieron'] += 1

    resultados = []
    for ep_id in ids:
        stats = ep_stats.get(ep_id, {'intentaron_con_fallo': 0, 'persistieron': 0})
        icf = stats['intentaron_con_fallo']
        per = stats['persistieron']
        resultados.append({
            'ep_id': ep_id,
            'comision_id': ep_comision.get(ep_id),
            'intentaron_con_fallo': icf,
            'persistieron': per,
            'abandonaron': icf - per,
            'tasa_persistencia': round(per / icf, 4) if icf else None,
        })
    return resultados


# ─── C. ERROR Y RECUPERACIÓN ──────────────────────────────────────────────────

def intentos_hasta_correcto_sin_sesgo(ep_ids=None, comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de intentos hasta resolver, incluyendo quienes no resolvieron.

    Pregunta: ¿Cuánto cuesta resolver cada ejercicio contando a todos?
    Nivel: EP.

    Corrige el sesgo de ``_distribucion_intentos`` en views.py: incluye a
    quienes nunca resolvieron como datos censurados.

    Args:
        ep_ids: iterable de IDs de EjercicioPractica, o None para derivar
            de comision_ids.
        comision_ids: iterable de IDs de Comision, o None para todas.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Lista de dicts con:
          - ep_id (int)
          - comision_id (int)
          - resolvieron (int)
          - no_resolvieron (int): intentaron pero nunca llegaron al correcto
          - pct_no_resolvio (float | None): no_resolvieron / total × 100
          - mediana_hasta_correcto (float | None): solo sobre quienes resolvieron
          - promedio_hasta_correcto (float | None): solo sobre quienes resolvieron

    Sesgo: usar mediana + pct_no_resolvio como par, no el promedio solo.
    El promedio ignora los censurados y subestima la dificultad real.
    """
    cids = _resolver_comision_ids(comision_ids)
    ids = ep_ids if ep_ids is not None else _ep_ids_de_comisiones(cids)

    # Mapeo ep_id → comision_id via PracticaComision.
    ep_comision = dict(
        EjercicioPractica.objects
        .filter(id__in=ids, practica__practicas_comisiones__comision_id__in=cids)
        .distinct()
        .values_list('id', 'practica__practicas_comisiones__comision_id')
    )

    qs_base = Intento.objects.filter(ejercicio_practica_id__in=ids)
    qs_base = _filtrar_por_cohorte(qs_base, cohorte_ids)
    if solo_consentimiento:
        qs_base = _filtrar_por_consentimiento(qs_base)
    intentos_raw = (
        qs_base
        .order_by('estudiante_id', 'ejercicio_practica_id', 'timestamp')
        .values('estudiante_id', 'ejercicio_practica_id', 'es_correcto')
    )

    grupos = defaultdict(list)
    for i in intentos_raw:
        grupos[(i['ejercicio_practica_id'], i['estudiante_id'])].append(i['es_correcto'])

    ep_resolvieron = defaultdict(list)
    ep_no_resolvieron = defaultdict(int)

    for (ep_id, _est_id), correcciones in grupos.items():
        try:
            primer_correcto = next(idx + 1 for idx, c in enumerate(correcciones) if c)
            ep_resolvieron[ep_id].append(primer_correcto)
        except StopIteration:
            ep_no_resolvieron[ep_id] += 1

    resultados = []
    for ep_id in ids:
        counts = ep_resolvieron.get(ep_id, [])
        no_res = ep_no_resolvieron.get(ep_id, 0)
        total = len(counts) + no_res
        resultados.append({
            'ep_id': ep_id,
            'comision_id': ep_comision.get(ep_id),
            'resolvieron': len(counts),
            'no_resolvieron': no_res,
            'pct_no_resolvio': round(no_res / total * 100, 1) if total else None,
            'mediana_hasta_correcto': round(_statistics.median(counts), 1) if counts else None,
            'promedio_hasta_correcto': round(sum(counts) / len(counts), 1) if counts else None,
        })
    return resultados


def desacople_docente_maquina(comision_ids=None, tipo_ejercicio=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Tasa de desacople entre corrección automática y juicio docente.

    Pregunta: ¿En qué proporción difiere el juicio docente del motor?
    ¿El motor es más liberal o más estricto que el docente?
    Nivel: agregado (comisión o global).

    Puede usarse con ``desagregar_por_comision()`` para comparar entre comisiones.
    Puede filtrarse por ``tipo_ejercicio`` ('formalizacion' | 'tabla_verdad').

    ADVERTENCIA: el denominador es solo los intentos revisados por el docente
    (aprobado_docente != None). Esta muestra es sesgada hacia los casos dudosos.

    Args:
        comision_ids: iterable de IDs de Comision, o None para todas.
        tipo_ejercicio: 'formalizacion', 'tabla_verdad', o None para ambos.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Dict con:
          - total_revisados (int)
          - maquina_ok_docente_no (int): motor aprueba, docente rechaza
          - maquina_no_docente_ok (int): motor rechaza, docente aprueba
          - acuerdo (int)
          - tasa_desacople (float | None)
          - tasa_maquina_liberal (float | None): maquina_ok_docente_no / total
          - tasa_maquina_estricta (float | None): maquina_no_docente_ok / total
    """
    es_global = comision_ids is None
    cids = _resolver_comision_ids(comision_ids)
    filtro_comision = Q(practica_comision__comision_id__in=cids)
    if es_global:
        filtro_comision |= Q(practica_comision__isnull=True)
    qs = Intento.objects.filter(filtro_comision, aprobado_docente__isnull=False)
    qs = _filtrar_por_cohorte(qs, cohorte_ids)
    if tipo_ejercicio is not None:
        qs = qs.filter(ejercicio_practica__ejercicio__tipo=tipo_ejercicio)
    if solo_consentimiento:
        qs = _filtrar_por_consentimiento(qs)

    maquina_ok_docente_no = qs.filter(es_correcto=True, aprobado_docente=False).count()
    maquina_no_docente_ok = qs.filter(es_correcto=False, aprobado_docente=True).count()
    total = qs.count()
    acuerdo = total - maquina_ok_docente_no - maquina_no_docente_ok
    return {
        'total_revisados': total,
        'maquina_ok_docente_no': maquina_ok_docente_no,
        'maquina_no_docente_ok': maquina_no_docente_ok,
        'acuerdo': acuerdo,
        'tasa_desacople': round((maquina_ok_docente_no + maquina_no_docente_ok) / total, 4) if total else None,
        'tasa_maquina_liberal': round(maquina_ok_docente_no / total, 4) if total else None,
        'tasa_maquina_estricta': round(maquina_no_docente_ok / total, 4) if total else None,
    }


def desacople_por_tipo(comision_ids=None, *, cohorte_ids=None):
    """Desacople docente-máquina desagregado por tipo de ejercicio.

    Atajo sobre desacople_docente_maquina() para comparar formalización vs
    tabla de verdad en una sola llamada.

    Args:
        comision_ids: iterable de IDs de Comision, o None para todas.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Dict ``{'formalizacion': {...}, 'tabla_verdad': {...}}``.
    """
    return {
        tipo: desacople_docente_maquina(
            comision_ids=comision_ids, tipo_ejercicio=tipo, cohorte_ids=cohorte_ids,
        )
        for tipo in ('formalizacion', 'tabla_verdad')
    }


# ─── D. DIFICULTAD / PARED / CONSENSO ────────────────────────────────────────

def tasa_abandono_local(ep_ids=None, comision_ids=None, solo_practicas_cerradas=True, solo_consentimiento=True, *, cohorte_ids=None):
    """Porcentaje de estudiantes que intentaron un EP pero nunca lo resolvieron.

    Pregunta: ¿Qué ejercicios son muros? ¿Cuántos llegan y no pasan?
    Nivel: EP.

    Args:
        ep_ids: iterable de IDs de EjercicioPractica, o None para derivar
            de comision_ids.
        comision_ids: iterable de IDs de Comision, o None para todas.
        solo_practicas_cerradas: si True (default), omite EPs de prácticas
            sin fecha_cierre o con fecha_cierre en el futuro (evita sesgo de
            "aún pueden resolver").
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Lista de dicts con:
          - ep_id (int)
          - comision_id (int)
          - intentaron (int): estudiantes con ≥1 intento
          - no_resolvieron (int): de esos, sin ningún correcto
          - tasa_abandono (float | None)
          - practica_cerrada (bool)

    Sesgo: no cuenta estudiantes que no intentaron por bloqueo de progreso.
    """
    ahora = timezone.now()
    cids = _resolver_comision_ids(comision_ids)
    ids = ep_ids if ep_ids is not None else _ep_ids_de_comisiones(cids)

    # fecha_cierre y comision_id viven en PracticaComision, no en Practica.
    # Para cada EP, buscamos la(s) PracticaComision en cids.
    # Si una Practica está en varias comisiones de cids, usamos la primera encontrada.
    ep_practica_ids = list(
        EjercicioPractica.objects.filter(id__in=ids).values_list('id', 'practica_id')
    )
    practica_ids_unicos = list({p_id for _, p_id in ep_practica_ids})

    pcs_info = {
        pc['practica_id']: pc
        for pc in PracticaComision.objects
        .filter(practica_id__in=practica_ids_unicos, comision_id__in=cids)
        .values('practica_id', 'comision_id', 'fecha_cierre')
    }

    ep_practica_map = {ep_id: p_id for ep_id, p_id in ep_practica_ids}

    resultados = []
    for ep_id in ids:
        p_id = ep_practica_map.get(ep_id)
        pc = pcs_info.get(p_id)
        if pc is None:
            continue
        cerrada = pc['fecha_cierre'] is not None and pc['fecha_cierre'] <= ahora
        if solo_practicas_cerradas and not cerrada:
            continue

        qs_agg = Intento.objects.filter(ejercicio_practica_id=ep_id)
        qs_agg = _filtrar_por_cohorte(qs_agg, cohorte_ids)
        if solo_consentimiento:
            qs_agg = _filtrar_por_consentimiento(qs_agg)
        intentos_agg = (
            qs_agg
            .values('estudiante')
            .annotate(algun_correcto=Count('id', filter=Q(es_correcto=True)))
        )
        intentaron = intentos_agg.count()
        no_resolvieron = intentos_agg.filter(algun_correcto=0).count()
        resultados.append({
            'ep_id': ep_id,
            'comision_id': pc['comision_id'],
            'intentaron': intentaron,
            'no_resolvieron': no_resolvieron,
            'tasa_abandono': round(no_resolvieron / intentaron, 4) if intentaron else None,
            'practica_cerrada': cerrada,
        })
    return resultados


def indice_pared(practica_id, comision_ids=None, *, cohorte_ids=None):
    """Identifica qué EP dentro de una práctica actúa estructuralmente como pared.

    Calcula z-score de (intentos promedio + tasa abandono) para cada EP
    respecto al resto de la práctica.

    Pregunta: ¿Hay un ejercicio que concentra la dificultad de toda la práctica?
    Nivel: EP comparativo dentro de una práctica.

    Args:
        practica_id: ID de la Practica.
        comision_ids: iterable de IDs de Comision, o None para todas.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Lista de dicts con:
          - ep_id (int)
          - orden (int)
          - intentos_promedio (float | None)
          - tasa_abandono (float | None)
          - z_intentos (float | None)
          - z_abandono (float | None)
          - indice_pared (float | None): promedio de ambos z-scores
        Ordenada por indice_pared descendente (None al final).

    Sesgo: z-score no interpretable con ≤3 EP. El consumidor debe validar.

    PRIVACIDAD: agrega internamente ``intentos_hasta_correcto_sin_sesgo`` y
    ``tasa_abandono_local`` sin pasar ``solo_consentimiento``. Para uso en
    investigación formal, pasar ``solo_consentimiento=True`` directamente a
    esas funciones o agregar el filtro en quien llame a ``indice_pared``.
    """
    eps = list(
        EjercicioPractica.objects
        .filter(practica_id=practica_id)
        .order_by('orden')
        .values('id', 'orden')
    )
    ids = [ep['id'] for ep in eps]
    cids = _resolver_comision_ids(comision_ids)

    sin_sesgo = {
        r['ep_id']: r
        for r in intentos_hasta_correcto_sin_sesgo(ep_ids=ids, comision_ids=cids, cohorte_ids=cohorte_ids)
    }
    abandono = {
        r['ep_id']: r
        for r in tasa_abandono_local(
            ep_ids=ids, comision_ids=cids, solo_practicas_cerradas=False, cohorte_ids=cohorte_ids,
        )
    }

    datos = []
    for ep in eps:
        ep_id = ep['id']
        prom = sin_sesgo.get(ep_id, {}).get('promedio_hasta_correcto')
        abn = abandono.get(ep_id, {}).get('tasa_abandono')
        datos.append({'ep_id': ep_id, 'orden': ep['orden'],
                      'intentos_promedio': prom, 'tasa_abandono': abn})

    proms = [d['intentos_promedio'] for d in datos if d['intentos_promedio'] is not None]
    abns = [d['tasa_abandono'] for d in datos if d['tasa_abandono'] is not None]

    def _zscore(val, vals):
        if val is None or len(vals) < 2:
            return None
        mu = sum(vals) / len(vals)
        sigma = _statistics.pstdev(vals)
        return round((val - mu) / sigma, 3) if sigma else 0.0

    resultados = []
    for d in datos:
        z_i = _zscore(d['intentos_promedio'], proms)
        z_a = _zscore(d['tasa_abandono'], abns)
        ip = (
            round((z_i + z_a) / 2, 3) if z_i is not None and z_a is not None
            else z_i if z_i is not None
            else z_a
        )
        resultados.append({**d, 'z_intentos': z_i, 'z_abandono': z_a, 'indice_pared': ip})

    resultados.sort(key=lambda x: (x['indice_pared'] is None, -(x['indice_pared'] or 0)))
    return resultados


def errores_compartidos_semanticos(ep_id, comision_ids=None, *, cohorte_ids=None):
    """Agrupa respuestas incorrectas de un EP por equivalencia semántica.

    Para formalización: dos respuestas son la misma concepción errónea si
    producen la misma tabla de verdad, aunque difieran en sintaxis.
    Para tabla_verdad: agrupa por patrón de columnas con diferencias.

    Pregunta: ¿Qué concepciones erróneas son compartidas y sistemáticas?
    Nivel: EP.

    Args:
        ep_id: ID de EjercicioPractica.
        comision_ids: iterable de IDs de Comision para filtrar estudiantes,
            o None para incluir a todos.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        Lista de dicts ordenada por n_estudiantes desc. Ver _errores_semanticos_*.

    Sesgo: respuestas con error de parse se omiten (no agregan al análisis).

    PRIVACIDAD: usa ``estudiante_id`` internamente para deduplicar grupos pero
    no lo expone en el output. Sin embargo, los ``ejemplos`` son respuestas raw
    que en grupos pequeños pueden ser identificables. No exponer externamente
    sin filtro de consentimiento previo. Agregar parámetro solo_consentimiento
    si se incorpora a las vistas de investigación.
    """
    ep = EjercicioPractica.objects.select_related('ejercicio').get(id=ep_id)
    tipo = ep.ejercicio.tipo

    qs = Intento.objects.filter(ejercicio_practica_id=ep_id, es_correcto=False)
    qs = _filtrar_por_cohorte(qs, cohorte_ids)
    if comision_ids is not None:
        cids = _resolver_comision_ids(comision_ids)
        qs = qs.filter(practica_comision__comision_id__in=cids)

    intentos = list(qs.values('estudiante_id', 'respuesta_raw', 'tabla_json'))

    if tipo == 'formalizacion':
        return _errores_semanticos_formalizacion(intentos, ep.ejercicio.formula_solucion)
    elif tipo == 'tabla_verdad':
        return _errores_semanticos_tabla(intentos, ep.ejercicio)
    return []


# ─── Helpers internos de errores ─────────────────────────────────────────────

def _errores_semanticos_formalizacion(intentos, formula_solucion):
    from motor import generar_tabla
    from motor.tabla import columna_resultado
    try:
        col_sol = tuple(columna_resultado(generar_tabla(formula_solucion)))
    except Exception:
        return []

    grupos = defaultdict(lambda: {'estudiantes': set(), 'ejemplos': []})
    for intento in intentos:
        try:
            col_r = tuple(columna_resultado(generar_tabla(intento['respuesta_raw'])))
            if col_r == col_sol:
                continue
            grupos[col_r]['estudiantes'].add(intento['estudiante_id'])
            if len(grupos[col_r]['ejemplos']) < 3:
                grupos[col_r]['ejemplos'].append(intento['respuesta_raw'])
        except Exception:
            pass

    return sorted(
        [{'fingerprint': str(k), 'n_estudiantes': len(v['estudiantes']),
          'ejemplos': v['ejemplos']} for k, v in grupos.items()],
        key=lambda x: x['n_estudiantes'], reverse=True,
    )


def _errores_semanticos_tabla(intentos, ejercicio):
    import json as _json
    from motor import verificar_argumento
    try:
        enunciados_solucion = _json.loads(ejercicio.formula_solucion)
        if not isinstance(enunciados_solucion, list):
            return []
    except Exception:
        return []

    grupos = defaultdict(lambda: {'estudiantes': set(), 'ejemplos': []})
    for intento in intentos:
        if not intento['tabla_json']:
            continue
        try:
            enunciados_est = _json.loads(intento['respuesta_raw'])
            if not isinstance(enunciados_est, list):
                enunciados_est = enunciados_solucion
        except Exception:
            enunciados_est = enunciados_solucion
        try:
            resultado = verificar_argumento(
                enunciados_est, enunciados_solucion, None, intento['tabla_json'],
            )
            canonica = resultado.get('tabla_canonica', [])
            if not canonica:
                continue
            cols_error = tuple(sorted(_patron_columnas_error(intento['tabla_json'], canonica)))
            if not cols_error:
                continue
            grupos[cols_error]['estudiantes'].add(intento['estudiante_id'])
            if len(grupos[cols_error]['ejemplos']) < 3:
                grupos[cols_error]['ejemplos'].append(str(intento['tabla_json'])[:80])
        except Exception:
            pass

    return sorted(
        [{'patron_error': str(list(k)), 'n_estudiantes': len(v['estudiantes']),
          'ejemplos': v['ejemplos']} for k, v in grupos.items()],
        key=lambda x: x['n_estudiantes'], reverse=True,
    )


def _patron_columnas_error(tabla_estudiante, tabla_canonica):
    if not tabla_estudiante or not tabla_canonica:
        return []
    cols = set(tabla_canonica[0].keys()) & set(tabla_estudiante[0].keys())
    errores = {
        col
        for fila_e, fila_c in zip(tabla_estudiante, tabla_canonica)
        for col in cols
        if fila_e.get(col) != fila_c.get(col)
    }
    return sorted(errores)

_NSE_ORDEN = ['Muy bajo', 'Bajo', 'Medio bajo', 'Medio alto', 'Alto', 'Sin datos']
_PANDEMIA_ORDEN = ['PREVIO', 'SÍ', 'NO', 'Sin datos']


def _ordenar_rows(rows, campo, orden):
    posicion = {valor: idx for idx, valor in enumerate(orden)}
    return sorted(rows, key=lambda row: (posicion.get(row.get(campo), len(posicion)), str(row.get(campo) or '')))


def _registros_encuesta(comision_ids=None, solo_consentimiento=True, cohorte_ids=None):
    """Devuelve un registro único por estudiante con encuesta en las comisiones dadas.

    ``cohorte_ids=None`` incluye todas las camadas. Acotar por cohorte permite
    comparar camadas entre sí en vez de mezclarlas en un solo agregado.

    El campo ``'pseudonimo'`` contiene el hex del ``research_id``; es ``None``
    para estudiantes sin consentimiento de investigación.
    El campo privado ``'_eid'`` (PK interna) se usa solo como clave de join
    con ``_metricas_desempeno_por_estudiante`` y nunca se incluye en outputs.
    La cohorte (``anio``/``cuatri``) sale de ``Inscripcion.cohorte``, no de una
    derivación por fecha.

    Deduplicación: se conserva la primera ``Inscripcion`` (por
    ``fecha_inscripcion``) de cada estudiante. Al filtrar por ``cohorte_ids``
    esa deduplicación ocurre DESPUÉS de acotar el queryset a esas cohortes, así
    que un recursante deduplica dentro de la cohorte pedida: pedir C2 devuelve
    su fila de C2 aunque también tenga una inscripción en C1.
    """
    cids = _resolver_comision_ids(comision_ids)
    qs = (
        Inscripcion.objects
        .filter(comision_id__in=cids, estudiante__encuesta__isnull=False)
        .select_related('estudiante', 'estudiante__encuesta', 'comision', 'cohorte')
        .order_by('estudiante_id', 'fecha_inscripcion', 'id')
    )
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)
    if solo_consentimiento:
        qs = qs.filter(estudiante__consentimiento_investigacion=True)

    registros = []
    vistos = set()
    for inscripcion in qs:
        if inscripcion.estudiante_id in vistos:
            continue
        vistos.add(inscripcion.estudiante_id)
        rid = inscripcion.estudiante.research_id
        cohorte = inscripcion.cohorte
        anio, cuatri = cohorte.anio, cohorte.cuatrimestre
        registros.append({
            '_eid': inscripcion.estudiante_id,         # clave interna de join — no exponer
            'pseudonimo': rid.hex if rid else None,
            'comision_id': inscripcion.comision_id,
            'comision_nombre': inscripcion.comision.nombre,
            'anio': anio,
            'cuatri': cuatri,
            'encuesta': inscripcion.estudiante.encuesta,
        })
    return registros


def _encuesta_attr(encuesta, attr, default=None):
    """Lee atributos de encuesta tolerando esquemas legacy."""
    if encuesta is None:
        return default
    return getattr(encuesta, attr, default)


def _encuesta_display(encuesta, field_name, default='Sin datos'):
    """Devuelve el label de choices tolerando encuestas con campos faltantes."""
    value = _encuesta_attr(encuesta, field_name)
    if value in (None, ''):
        return default
    display = getattr(encuesta, f'get_{field_name}_display', None)
    if callable(display):
        return display()
    return value


def puntaje_nse_encuesta(encuesta):
    """Replica el índice NSE usado en la memoria profesional sobre onboarding."""
    if encuesta is None:
        return None

    puntaje = 0.0
    con_quien_vive = _encuesta_attr(encuesta, 'con_quien_vive')

    if con_quien_vive == 'solo':
        puntaje += 1
    elif con_quien_vive == 'residencia':
        puntaje -= 1

    dispositivos = _encuesta_attr(encuesta, 'dispositivos', {}) or {}
    for key in ('pc', 'laptop', 'tablet'):
        if dispositivos.get(key) == 'individual':
            puntaje += 1
    if dispositivos.get('celular') not in (None, '', 'individual'):
        puntaje -= 1

    estudios_superiores = _encuesta_attr(encuesta, 'estudios_superiores')
    if estudios_superiores in ('si_uba', 'si_fuera_uba'):
        if _encuesta_attr(encuesta, 'se_recibio_uba') is True or _encuesta_attr(encuesta, 'se_recibio_fuera_uba') is True:
            puntaje += 1

    if _encuesta_attr(encuesta, 'hizo_uba_xxi') is True:
        puntaje += 1

    if _encuesta_attr(encuesta, 'tiempo_en_cbc') != 'primero':
        try:
            if (_encuesta_attr(encuesta, 'materias_aprobadas', 0) or 0) >= 2:
                puntaje += 1
        except TypeError:
            pass

    tiempo_viaje_puan = _encuesta_attr(encuesta, 'tiempo_viaje_puan')
    if tiempo_viaje_puan == 'menos_30':
        puntaje += 1
    elif tiempo_viaje_puan == 'mas_90':
        puntaje -= 1

    dias_trabaja = _encuesta_attr(encuesta, 'dias_trabaja')
    situacion_laboral = _encuesta_attr(encuesta, 'situacion_laboral')
    if dias_trabaja == 'no' and situacion_laboral == 'no_trabajo':
        puntaje += 1
    elif situacion_laboral == 'busco':
        puntaje -= 1
    elif dias_trabaja == 'menos_5' and situacion_laboral == 'hasta_4':
        puntaje += 0.5
    elif dias_trabaja == 'mas_5' and situacion_laboral == 'mas_6':
        puntaje -= 1

    if _encuesta_attr(encuesta, 'mudado_para_trabajar_estudiar') is True:
        puntaje -= 1

    if _encuesta_attr(encuesta, 'tiene_cud') is True:
        puntaje -= 1

    return puntaje


def categorizar_nse(puntaje):
    """Categoriza el puntaje NSE con los umbrales del notebook original."""
    try:
        valor = float(puntaje)
    except (TypeError, ValueError):
        return 'Sin datos'
    if valor < -2.5:
        return 'Muy bajo'
    if valor < -1:
        return 'Bajo'
    if valor < 1:
        return 'Medio bajo'
    if valor < 2.5:
        return 'Medio alto'
    return 'Alto'


def puntaje_logicas_encuesta(encuesta):
    """Puntaje 0-3 en los tres acertijos lógicos del onboarding."""
    if encuesta is None:
        return None

    puntaje = 0
    if _encuesta_attr(encuesta, 'acertijo_silogismo') == 'mas_bajo':
        puntaje += 1

    # Cirugía: usar evaluación de IA si está disponible; fallback a keyword matching
    cirugia_correcto = _encuesta_attr(encuesta, 'acertijo_cirugia_correcto')
    if cirugia_correcto is True:
        puntaje += 1
    elif cirugia_correcto is None:
        respuesta_cirugia = (_encuesta_attr(encuesta, 'acertijo_cirugia', '') or '').strip().lower()
        if 'madre' in respuesta_cirugia or 'mamá' in respuesta_cirugia or 'mama' in respuesta_cirugia:
            puntaje += 1

    if _encuesta_attr(encuesta, 'acertijo_hilera') == 'rodriguez':
        puntaje += 1

    return puntaje


def clasificacion_pandemia_encuesta(encuesta):
    """Clasifica si la secundaria transcurrió antes, durante o después de pandemia."""
    fecha_nacimiento = _encuesta_attr(encuesta, 'fecha_nacimiento')
    if encuesta is None or fecha_nacimiento is None:
        return 'Sin datos'

    anio_nacimiento = fecha_nacimiento.year
    inicio_secundaria = anio_nacimiento + 15
    fin_secundaria = anio_nacimiento + 18
    if fin_secundaria < 2020:
        return 'PREVIO'
    if inicio_secundaria <= 2021 <= fin_secundaria:
        return 'SÍ'
    return 'NO'


def _metricas_desempeno_por_estudiante(comision_ids=None, solo_consentimiento=True, cohorte_ids=None):
    """Resume desempeño en ejercicios por estudiante dentro de las comisiones dadas.

    Retorna un dict keyed por ``research_id.hex`` (pseudónimo). Estudiantes
    sin ``research_id`` se omiten para que el resultado sea siempre anónimo.

    Args:
        cohorte_ids: cohortes a incluir; None = todas. Importante para
            recursantes: un mismo estudiante pertenece a varias cohortes con
            el mismo pseudónimo, así que sin este filtro sus intentos de
            otras cohortes se mezclarían al pedir una sola.
    """
    es_global = comision_ids is None
    cids = _resolver_comision_ids(comision_ids)
    filtro_comision = Q(practica_comision__comision_id__in=cids)
    if es_global:
        filtro_comision |= Q(practica_comision__isnull=True)
    qs = Intento.objects.filter(filtro_comision, estudiante__research_id__isnull=False)
    qs = _filtrar_por_cohorte(qs, cohorte_ids)
    if solo_consentimiento:
        qs = _filtrar_por_consentimiento(qs)

    intentos = list(qs.values(
        'estudiante__research_id',
        'ejercicio_practica_id',
        'es_correcto',
        'aprobado_docente',
        'practica_comision__orden',
        'ejercicio_practica__orden',
    ))
    grupos = defaultdict(lambda: {
        'intentos': 0,
        'correctos': 0,
        'eps_intentados': set(),
        'eps_resueltos': set(),
        'eps_indice': {},
        'eps_estado': {},
    })
    for intento in intentos:
        pid = intento['estudiante__research_id']
        fila = grupos[pid.hex]
        fila['intentos'] += 1
        ep_id = intento['ejercicio_practica_id']
        fila['eps_intentados'].add(ep_id)

        practica_orden = intento.get('practica_comision__orden') or 0
        ejercicio_orden = intento.get('ejercicio_practica__orden') or 0
        indice_orden = (practica_orden, ejercicio_orden)
        previo = fila['eps_indice'].get(ep_id)
        if previo is None or indice_orden > previo:
            fila['eps_indice'][ep_id] = indice_orden

        if intento['es_correcto']:
            fila['correctos'] += 1
            fila['eps_resueltos'].add(ep_id)

        estado = 1  # error/rechazo docente
        if intento['es_correcto']:
            estado = 2  # aprobación automática (verificación formal)
        if intento['aprobado_docente'] is True:
            estado = 3  # aprobación docente
        fila['eps_estado'][ep_id] = max(fila['eps_estado'].get(ep_id, 0), estado)

    qs_progreso = Progreso.objects.filter(
        practica_comision__comision_id__in=cids,
        ejercicio_practica_actual__isnull=True,
        estudiante__research_id__isnull=False,
    )
    qs_progreso = _filtrar_por_cohorte(qs_progreso, cohorte_ids)
    if solo_consentimiento:
        qs_progreso = qs_progreso.filter(estudiante__consentimiento_investigacion=True)

    # Cuenta prácticas DISTINTAS, no filas de Progreso: Progreso es único por
    # (estudiante, practica_comision, cohorte) (ver ejercicios/models.py), así
    # que un recursante que completó la misma práctica en dos cohortes de la
    # misma comisión aporta dos filas para una sola práctica. Deduplicar por
    # ``practica_comision__practica_id`` (no por ``practica_comision_id``)
    # también cubre el caso de un estudiante en dos comisiones distintas que
    # comparten la misma Practica canónica: sigue siendo la misma práctica
    # hecha dos veces, no dos prácticas.
    practicas_completadas = {
        row['estudiante__research_id'].hex: row['n']
        for row in qs_progreso.values('estudiante__research_id').annotate(
            n=Count('practica_comision__practica_id', distinct=True),
        )
        if row['estudiante__research_id'] is not None
    }

    resultado = {}
    for pid_hex, fila in grupos.items():
        ejercicios_intentados = len(fila['eps_intentados'])
        ejercicios_resueltos = len(fila['eps_resueltos'])

        rendimiento_con_ausentismo = None
        if fila['eps_indice']:
            ultimo_idx = max(fila['eps_indice'].values())
            ejercicios_hasta_tope = [ep for ep, idx in fila['eps_indice'].items() if idx <= ultimo_idx]
            if ejercicios_hasta_tope:
                suma = 0
                for ep in ejercicios_hasta_tope:
                    suma += fila['eps_estado'].get(ep, 0)
                rendimiento_con_ausentismo = round(suma / (len(ejercicios_hasta_tope) * 3), 4)

        resultado[pid_hex] = {
            'intentos_total': fila['intentos'],
            'intentos_correctos': fila['correctos'],
            'ejercicios_intentados': ejercicios_intentados,
            'ejercicios_resueltos': ejercicios_resueltos,
            'practicas_completadas': practicas_completadas.get(pid_hex, 0),
            'tasa_acierto_intentos': round(fila['correctos'] / fila['intentos'], 4) if fila['intentos'] else None,
            'tasa_resolucion_ejercicios': round(ejercicios_resueltos / ejercicios_intentados, 4) if ejercicios_intentados else None,
            'rendimiento_con_ausentismo': rendimiento_con_ausentismo,
            'hizo_algun_intento': fila['intentos'] > 0,
            'resolvio_alguno': ejercicios_resueltos > 0,
        }
    return resultado


def perfiles_encuesta_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Dataset base anonimizado con índices de onboarding y desempeño en ejercicios.

    Args:
        comision_ids: iterable de IDs de Comision, o None para todas.
        solo_consentimiento: si True, filtra a consentimiento_investigacion=True.
        cohorte_ids: cohortes a incluir; None = todas.
    """
    desempeno = _metricas_desempeno_por_estudiante(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    filas = []
    for registro in _registros_encuesta(comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids):
        # Excluir estudiantes sin research_id (sin consentimiento de investigación).
        # No basta con enmascarar el pseudonimo: la fila podría re-identificarse
        # por combinación de atributos demográficos.
        if registro['pseudonimo'] is None:
            continue
        encuesta = registro['encuesta']
        puntaje_nse = puntaje_nse_encuesta(encuesta)
        # Join por pseudonimo (research_id.hex); ambos dicts usan la misma clave.
        fila_desempeno = desempeno.get(registro['pseudonimo'], {})
        filas.append({
            'pseudonimo': registro['pseudonimo'],
            'comision_id': registro['comision_id'],
            'comision_nombre': registro['comision_nombre'],
            'anio': registro['anio'],
            'cuatri': registro['cuatri'],
            'facultad': _encuesta_display(encuesta, 'facultad'),
            'carrera': _encuesta_display(encuesta, 'carrera'),
            'puntaje_nse': puntaje_nse,
            'categoria_nse': categorizar_nse(puntaje_nse),
            'puntaje_logicas': puntaje_logicas_encuesta(encuesta),
            'pandemia': clasificacion_pandemia_encuesta(encuesta),
            'intentos_total': fila_desempeno.get('intentos_total', 0),
            'intentos_correctos': fila_desempeno.get('intentos_correctos', 0),
            'ejercicios_intentados': fila_desempeno.get('ejercicios_intentados', 0),
            'ejercicios_resueltos': fila_desempeno.get('ejercicios_resueltos', 0),
            'practicas_completadas': fila_desempeno.get('practicas_completadas', 0),
            'tasa_acierto_intentos': fila_desempeno.get('tasa_acierto_intentos'),
            'tasa_resolucion_ejercicios': fila_desempeno.get('tasa_resolucion_ejercicios'),
            'hizo_algun_intento': fila_desempeno.get('hizo_algun_intento', False),
            'resolvio_alguno': fila_desempeno.get('resolvio_alguno', False),
        })
    return filas


def _promedio(valores):
    valores = [v for v in valores if v is not None]
    return round(sum(valores) / len(valores), 4) if valores else None


def distribucion_nse_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de estudiantes por categoría NSE.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    total = len(filas)
    conteos = Counter(f['categoria_nse'] for f in filas)
    puntajes = defaultdict(list)
    for fila in filas:
        if fila['puntaje_nse'] is not None:
            puntajes[fila['categoria_nse']].append(fila['puntaje_nse'])

    resultado = []
    for categoria, count in conteos.items():
        valores = puntajes.get(categoria, [])
        resultado.append({
            'categoria_nse': categoria,
            'count': count,
            'porcentaje': round(count / total * 100, 2) if total else None,
            'puntaje_promedio': round(sum(valores) / len(valores), 2) if valores else None,
        })
    return _ordenar_rows(resultado, 'categoria_nse', _NSE_ORDEN)


def distribucion_puntaje_logicas(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de estudiantes por puntaje en los acertijos lógicos.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    total = len(filas)
    conteos = Counter(f['puntaje_logicas'] for f in filas if f['puntaje_logicas'] is not None)
    return [
        {
            'puntaje_logicas': puntaje,
            'count': conteos[puntaje],
            'porcentaje': round(conteos[puntaje] / total * 100, 2) if total else None,
        }
        for puntaje in sorted(conteos.keys())
    ]


def distribucion_pandemia_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de estudiantes por clasificación pandemia.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    total = len(filas)
    conteos = Counter(f['pandemia'] for f in filas)
    resultado = [
        {
            'pandemia': pandemia,
            'count': count,
            'porcentaje': round(count / total * 100, 2) if total else None,
        }
        for pandemia, count in conteos.items()
    ]
    return _ordenar_rows(resultado, 'pandemia', _PANDEMIA_ORDEN)


def cohortes_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Cantidad de estudiantes con encuesta por cohorte (año, cuatrimestre).

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    conteos = Counter((f['anio'], f['cuatri']) for f in filas if f['anio'] is not None and f['cuatri'] is not None)
    return [
        {'anio': anio, 'cuatri': cuatri, 'count': count}
        for (anio, cuatri), count in sorted(conteos.items())
    ]


def cohortes_nse_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de categoría NSE por cohorte (año, cuatrimestre).

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    conteos = Counter(
        (f['anio'], f['cuatri'], f['categoria_nse'])
        for f in filas
        if f['anio'] is not None and f['cuatri'] is not None
    )
    resultado = [
        {'anio': anio, 'cuatri': cuatri, 'categoria_nse': categoria, 'count': count}
        for (anio, cuatri, categoria), count in conteos.items()
    ]
    return sorted(
        resultado,
        key=lambda row: (
            row['anio'],
            row['cuatri'],
            _NSE_ORDEN.index(row['categoria_nse']) if row['categoria_nse'] in _NSE_ORDEN else len(_NSE_ORDEN),
        ),
    )


def cohortes_pandemia_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de clasificación pandemia por cohorte (año, cuatrimestre).

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    conteos = Counter(
        (f['anio'], f['cuatri'], f['pandemia'])
        for f in filas
        if f['anio'] is not None and f['cuatri'] is not None
    )
    totales = Counter((f['anio'], f['cuatri']) for f in filas if f['anio'] is not None and f['cuatri'] is not None)
    resultado = []
    for (anio, cuatri, pandemia), count in conteos.items():
        total = totales[(anio, cuatri)]
        resultado.append({
            'anio': anio,
            'cuatri': cuatri,
            'pandemia': pandemia,
            'count': count,
            'porcentaje': round(count / total * 100, 2) if total else None,
        })
    return sorted(
        resultado,
        key=lambda row: (
            row['anio'],
            row['cuatri'],
            _PANDEMIA_ORDEN.index(row['pandemia']) if row['pandemia'] in _PANDEMIA_ORDEN else len(_PANDEMIA_ORDEN),
        ),
    )


def distribucion_facultad_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de estudiantes por facultad.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    total = len(filas)
    conteos = Counter(f['facultad'] for f in filas)
    return [
        {'facultad': facultad, 'count': count, 'porcentaje': round(count / total * 100, 2) if total else None}
        for facultad, count in sorted(conteos.items(), key=lambda item: (-item[1], item[0]))
    ]


def distribucion_carrera_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Distribución de estudiantes por carrera.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    total = len(filas)
    conteos = Counter(f['carrera'] for f in filas)
    return [
        {'carrera': carrera, 'count': count, 'porcentaje': round(count / total * 100, 2) if total else None}
        for carrera, count in sorted(conteos.items(), key=lambda item: (-item[1], item[0]))
    ]


def desempeno_por_nse_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Cruza categoría NSE con desempeño observado en ejercicios.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    grupos = defaultdict(list)
    for fila in filas:
        grupos[fila['categoria_nse']].append(fila)

    resultado = []
    for categoria, items in grupos.items():
        total = len(items)
        resultado.append({
            'categoria_nse': categoria,
            'count': total,
            'con_intento': sum(1 for item in items if item['hizo_algun_intento']),
            'resolvio_alguno': sum(1 for item in items if item['resolvio_alguno']),
            'promedio_intentos': _promedio([item['intentos_total'] for item in items]),
            'promedio_resueltos': _promedio([item['ejercicios_resueltos'] for item in items]),
            'promedio_tasa_resolucion': _promedio([item['tasa_resolucion_ejercicios'] for item in items]),
            'promedio_practicas_completadas': _promedio([item['practicas_completadas'] for item in items]),
            'pct_con_intento': round(sum(1 for item in items if item['hizo_algun_intento']) / total * 100, 2) if total else None,
            'pct_resolvio_alguno': round(sum(1 for item in items if item['resolvio_alguno']) / total * 100, 2) if total else None,
        })
    return _ordenar_rows(resultado, 'categoria_nse', _NSE_ORDEN)


def desempeno_por_pandemia_onboarding(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Cruza clasificación pandemia con desempeño observado en ejercicios.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    grupos = defaultdict(list)
    for fila in filas:
        grupos[fila['pandemia']].append(fila)

    resultado = []
    for pandemia, items in grupos.items():
        total = len(items)
        resultado.append({
            'pandemia': pandemia,
            'count': total,
            'con_intento': sum(1 for item in items if item['hizo_algun_intento']),
            'resolvio_alguno': sum(1 for item in items if item['resolvio_alguno']),
            'promedio_intentos': _promedio([item['intentos_total'] for item in items]),
            'promedio_resueltos': _promedio([item['ejercicios_resueltos'] for item in items]),
            'promedio_tasa_resolucion': _promedio([item['tasa_resolucion_ejercicios'] for item in items]),
            'promedio_practicas_completadas': _promedio([item['practicas_completadas'] for item in items]),
            'pct_con_intento': round(sum(1 for item in items if item['hizo_algun_intento']) / total * 100, 2) if total else None,
            'pct_resolvio_alguno': round(sum(1 for item in items if item['resolvio_alguno']) / total * 100, 2) if total else None,
        })
    return _ordenar_rows(resultado, 'pandemia', _PANDEMIA_ORDEN)


def desempeno_por_puntaje_logicas(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Cruza puntaje de acertijos lógicos con desempeño observado en ejercicios.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.
    """
    filas = perfiles_encuesta_onboarding(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    grupos = defaultdict(list)
    for fila in filas:
        grupos[fila['puntaje_logicas']].append(fila)

    return [
        {
            'puntaje_logicas': puntaje,
            'count': len(items),
            'con_intento': sum(1 for item in items if item['hizo_algun_intento']),
            'resolvio_alguno': sum(1 for item in items if item['resolvio_alguno']),
            'promedio_intentos': _promedio([item['intentos_total'] for item in items]),
            'promedio_resueltos': _promedio([item['ejercicios_resueltos'] for item in items]),
            'promedio_tasa_resolucion': _promedio([item['tasa_resolucion_ejercicios'] for item in items]),
            'promedio_practicas_completadas': _promedio([item['practicas_completadas'] for item in items]),
            'pct_con_intento': round(sum(1 for item in items if item['hizo_algun_intento']) / len(items) * 100, 2) if items else None,
            'pct_resolvio_alguno': round(sum(1 for item in items if item['resolvio_alguno']) / len(items) * 100, 2) if items else None,
        }
        for puntaje, items in sorted(grupos.items(), key=lambda item: (item[0] is None, item[0]))
    ]


# ─── Distribuciones detalladas de encuesta (para resumen tipo Forms) ──────────

def distribuciones_encuesta_detalle(comision_ids=None, *, cohorte_ids=None):
    """Distribuciones por pregunta de la encuesta inicial.

    Usa únicamente consentimiento pedagógico (no requiere consentimiento de
    investigación), por lo que incluye a todos los estudiantes que completaron
    la encuesta. Devuelve un dict con una clave por campo de EncuestaEstudiante.

    Campos de selección única → lista de dicts ``{label, value, count, porcentaje}``.
    Campos booleanos          → lista de dicts ``{label, count, porcentaje}``.
    ``materias_aprobadas``    → lista de dicts ``{valor, count, porcentaje}``.
    ``acceso_internet``       → lista de dicts ``{opcion, count, porcentaje}``
                                (porcentaje sobre n encuestas, no sobre menciones).
    ``dispositivos``          → lista de dicts ``{dispositivo, uso, count}``.

    Args:
        comision_ids: iterable de IDs de Comision, o None para todas.
        cohorte_ids: cohortes a incluir; None = todas.
    """
    registros = _registros_encuesta(comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    encuestas = [r['encuesta'] for r in registros]
    total = len(encuestas)

    K_ANONIMATO = 5  # filas con count < K se suprimen o agrupan

    def _dist_choice(field_name, orden=None):
        conteos = Counter(
            _encuesta_display(e, field_name, default=None) for e in encuestas
        )
        conteos.pop(None, None)
        otros = sum(c for c in conteos.values() if c < K_ANONIMATO)
        items = [
            {
                'label': label,
                'value': label,
                'count': count,
                'porcentaje': round(count / total * 100, 2) if total else None,
            }
            for label, count in conteos.items()
            if count >= K_ANONIMATO
        ]
        if otros:
            items.append({
                'label': 'Otra',
                'value': 'Otra',
                'count': otros,
                'porcentaje': round(otros / total * 100, 2) if total else None,
            })
        if orden:
            orden_map = {v: i for i, v in enumerate(orden)}
            items.sort(key=lambda x: orden_map.get(x['label'], len(orden)))
        else:
            items.sort(key=lambda x: -x['count'])
        return items

    def _dist_bool(field_name):
        si = sum(1 for e in encuestas if _encuesta_attr(e, field_name) is True)
        no = sum(1 for e in encuestas if _encuesta_attr(e, field_name) is False)
        sin = total - si - no
        resultado = [
            {'label': 'Sí',            'count': si,  'porcentaje': round(si  / total * 100, 2) if total else None},
            {'label': 'No',            'count': no,  'porcentaje': round(no  / total * 100, 2) if total else None},
        ]
        if sin:
            resultado.append({'label': 'Sin respuesta', 'count': sin, 'porcentaje': round(sin / total * 100, 2) if total else None})
        return resultado

    # ── Órdenes fijos por campo ──────────────────────────────────────────────
    _orden_con_quien_vive = [
        'Con mi familia (padres/hermanos)', 'Con mi pareja/hijos',
        'Con otros familiares', 'Con amigos/compañeros', 'Solo/a',
        'En residencia u hogar universitario',
    ]
    _orden_viaje = ['Menos de 30 min', 'Entre 30 y 60 min', 'Entre 60 y 90 min', 'Más de 90 min']
    _orden_situacion_laboral = [
        'No trabajo y no estoy buscando', 'Busco trabajo',
        'Trabajo hasta 4 horas por día', 'Trabajo entre 4 y 6 horas por día',
        'Trabajo 6 o más horas por día',
    ]
    _orden_dias_trabaja = [
        'No trabajo', 'Trabajo menos de 5 días a la semana',
        'Trabajo 5 días de la semana', 'Trabajo más de 5 días a la semana',
    ]
    _orden_tiempo_secundaria = ['Menos de un año', 'Entre 1 y 3 años', 'Más de 3 años']
    _orden_estudios_sup = [
        'No, esta es mi primera carrera de nivel superior',
        'Sí, estudié o estoy estudiando en la UBA',
        'Sí, en otra institución',
    ]
    _orden_tiempo_cbc = [
        'Es mi primer cuatrimestre', 'Es mi segundo cuatrimestre',
        'Entre 1 y 2 años', 'Más de 2 años',
    ]
    _orden_interrupcion = ['No, nunca interrumpí', 'Sí, un cuatrimestre', 'Sí, más de un cuatrimestre']
    _orden_silogismo = ['Más alto', 'Más bajo']
    _orden_hilera = ['Rodríguez', 'Rivera', 'Posada']

    # ── Acceso a internet (JSON lista) ───────────────────────────────────────
    _INTERNET_LABELS = {
        'wifi_hogar': 'WiFi en el hogar',
        'datos_abono': 'Datos móviles (abono)',
        'datos_prepago': 'Datos móviles (prepago)',
        'wifi_facultad': 'WiFi de la facultad',
        'wifi_trabajo': 'WiFi en el trabajo',
        'wifi_otro': 'WiFi en otro lugar',
        'sin_acceso': 'Sin acceso a internet',
    }
    internet_conteos = Counter()
    for e in encuestas:
        opciones = _encuesta_attr(e, 'acceso_internet') or []
        if isinstance(opciones, list):
            for op in opciones:
                internet_conteos[op] += 1
    acceso_internet = sorted(
        [
            {
                'opcion': _INTERNET_LABELS.get(op, op),
                'count': count,
                'porcentaje': round(count / total * 100, 2) if total else None,
            }
            for op, count in internet_conteos.items()
        ],
        key=lambda x: -x['count'],
    )

    # ── Dispositivos (JSON dict) ──────────────────────────────────────────────
    _DISP_LABELS = {
        'celular': 'Celular', 'pc': 'PC de escritorio',
        'laptop': 'Notebook/laptop', 'tablet': 'Tablet',
    }
    _USO_LABELS = {
        'individual': 'Individual', 'compartido': 'Compartido', 'no_tengo': 'No tengo',
    }
    disp_conteos = Counter()
    for e in encuestas:
        devs = _encuesta_attr(e, 'dispositivos') or {}
        if isinstance(devs, dict):
            for disp, uso in devs.items():
                disp_conteos[(disp, uso)] += 1
    dispositivos = sorted(
        [
            {
                'dispositivo': _DISP_LABELS.get(disp, disp),
                'uso': _USO_LABELS.get(uso, uso),
                'count': count,
                'porcentaje': round(count / total * 100, 2) if total else None,
            }
            for (disp, uso), count in disp_conteos.items()
        ],
        key=lambda x: (
            list(_DISP_LABELS.values()).index(x['dispositivo']) if x['dispositivo'] in _DISP_LABELS.values() else 99,
            list(_USO_LABELS.values()).index(x['uso']) if x['uso'] in _USO_LABELS.values() else 99,
        ),
    )

    # ── Materias aprobadas (numérico) ────────────────────────────────────────
    mat_conteos = Counter(
        _encuesta_attr(e, 'materias_aprobadas') for e in encuestas
        if _encuesta_attr(e, 'materias_aprobadas') is not None
    )
    materias_aprobadas = [
        {'valor': valor, 'count': count, 'porcentaje': round(count / total * 100, 2) if total else None}
        for valor, count in sorted(mat_conteos.items())
    ]

    return {
        'total': total,
        'origen_caba_gba': _dist_bool('origen_caba_gba'),
        'con_quien_vive': _dist_choice('con_quien_vive', _orden_con_quien_vive),
        'tiempo_viaje_puan': _dist_choice('tiempo_viaje_puan', _orden_viaje),
        'situacion_laboral': _dist_choice('situacion_laboral', _orden_situacion_laboral),
        'dias_trabaja': _dist_choice('dias_trabaja', _orden_dias_trabaja),
        'acceso_internet': acceso_internet,
        'dispositivos': dispositivos,
        'tipo_escuela': _dist_choice('tipo_escuela'),
        'tiempo_desde_secundaria': _dist_choice('tiempo_desde_secundaria', _orden_tiempo_secundaria),
        'estudios_superiores': _dist_choice('estudios_superiores', _orden_estudios_sup),
        'hizo_uba_xxi': _dist_bool('hizo_uba_xxi'),
        'tiempo_en_cbc': _dist_choice('tiempo_en_cbc', _orden_tiempo_cbc),
        'interrupcion_cbc': _dist_choice('interrupcion_cbc', _orden_interrupcion),
        'ya_curso_ipc': _dist_bool('ya_curso_ipc'),
        'materias_aprobadas': materias_aprobadas,
        'acertijo_silogismo': _dist_choice('acertijo_silogismo', _orden_silogismo),
        'acertijo_hilera': _dist_choice('acertijo_hilera', _orden_hilera),
        'articulo_risa': _dist_bool('articulo_risa'),
        'tiene_cud': _dist_bool('tiene_cud'),
        'necesita_adecuacion': _dist_bool('necesita_adecuacion'),
    }


# ─── Nube de palabras: ¿qué es la ciencia? ───────────────────────────────────

import re as _re
from collections import Counter as _Counter

_STOPWORDS_ES = {
    # artículos
    'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
    # preposiciones
    'a', 'al', 'ante', 'bajo', 'con', 'contra', 'de', 'del', 'desde',
    'durante', 'en', 'entre', 'hacia', 'hasta', 'mediante', 'para',
    'por', 'según', 'sin', 'sobre', 'tras',
    # conjunciones
    'e', 'ni', 'o', 'u', 'pero', 'sino', 'aunque', 'porque', 'pues',
    'que', 'si', 'y',
    # pronombres / determinantes
    'aquel', 'aquella', 'aquello', 'aquellos', 'aquellas',
    'ese', 'esa', 'eso', 'esos', 'esas',
    'este', 'esta', 'esto', 'estos', 'estas',
    'cual', 'cuales', 'quien', 'quienes',
    'le', 'les', 'lo', 'me', 'mi', 'mis', 'nos', 'se', 'su', 'sus',
    'te', 'ti', 'tu', 'tus', 'yo', 'él', 'ella', 'ellos', 'ellas',
    'nosotros', 'nosotras', 'vosotros', 'vosotras',
    # verbos auxiliares / cópulas muy frecuentes
    'es', 'son', 'era', 'eran', 'fue', 'fueron', 'ser', 'estar',
    'hay', 'tiene', 'tienen', 'tener', 'hace', 'hacen', 'hacer',
    'puede', 'pueden', 'poder', 'debe', 'deben', 'deber',
    'busca', 'buscan', 'buscar',
    # adverbios comunes
    'así', 'aquí', 'allí', 'también', 'tampoco', 'muy', 'más', 'menos',
    'no', 'sí', 'ya', 'aún', 'solo', 'sólo', 'bien', 'mal',
    'cuando', 'donde', 'como', 'cómo', 'qué', 'cuál',
    # palabra trivial por ser el tema de la pregunta
    'ciencia',
    # comodines de relleno
    'etc', 'etc.', 'tipo', 'algo', 'todo', 'toda', 'todos', 'todas',
    'cada', 'cualquier', 'mismo', 'misma', 'mismos', 'mismas',
    'otro', 'otra', 'otros', 'otras',
}


def nube_ciencia(comision_ids=None, solo_consentimiento=True, top_n=80, *, cohorte_ids=None):
    """Frecuencia de palabras en las respuestas a '¿qué es la ciencia?'.

    Devuelve hasta ``top_n`` palabras con sus frecuencias, excluyendo
    stopwords y palabras de menos de 3 caracteres.

    Args:
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        list[dict] — cada dict con ``word`` y ``count``, ordenado desc.
    """
    registros = _registros_encuesta(comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)
    textos = [
        (_encuesta_attr(r['encuesta'], 'que_es_ciencia') or '').strip()
        for r in registros
    ]
    textos = [t for t in textos if t and t not in ('.', '-', '…')]

    counts: _Counter = _Counter()
    token_re = _re.compile(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{3,}", _re.UNICODE)
    for texto in textos:
        for token in token_re.findall(texto.lower()):
            if token not in _STOPWORDS_ES:
                counts[token] += 1

    return [
        {'word': word, 'count': cnt}
        for word, cnt in counts.most_common(top_n)
    ]


# ─── Correlaciones encuesta × rendimiento ─────────────────────────────────────

_VARS_CORRELACION = [
    # (campo, label, tipo, orden_ordinal | None)
    ('puntaje_logicas',       'Puntaje en acertijos lógicos',              'numerico', None),
    ('acertijo_hilera_correcto',  'Acierto: hilera de casas (Rodríguez)',  'binario',  None),
    ('acertijo_cirugia_correcto', 'Acierto: cirugía (sesgo de género)',    'binario',  None),
    ('puntaje_nse',           'Índice NSE (recursos)',                     'numerico', None),
    ('materias_aprobadas', 'Materias aprobadas en CBC',         'numerico', None),
    ('hizo_uba_xxi',     'Cursó UBA XXI',                       'binario',  None),
    ('ya_curso_ipc',     'Ya cursó IPC antes',                  'binario',  None),
    ('origen_caba_gba',  'Es de CABA o GBA',                    'binario',  None),
    ('articulo_risa',    'Creyó artículo (sesgo cognitivo)',     'binario',  None),
    ('necesita_adecuacion', 'Necesita adecuación',              'binario',  None),
    ('tiene_cud',        'Tiene CUD',                           'binario',  None),
    ('mudado_para_trabajar_estudiar', 'Se mudó para trabajar/estudiar', 'binario', None),
    ('situacion_laboral', 'Carga horaria laboral',              'ordinal',
     ['no_trabajo', 'busco', 'hasta_4', '4_6', 'mas_6']),
    ('dias_trabaja',     'Días de trabajo por semana',          'ordinal',
     ['no', 'menos_5', '5', 'mas_5']),
    ('tiempo_viaje_puan', 'Tiempo de viaje a Puán',             'ordinal',
     ['menos_30', '30_60', '60_90', 'mas_90']),
    ('tiempo_desde_secundaria', 'Tiempo desde secundaria',      'ordinal',
     ['menos_1', '1_3', 'mas_3']),
    ('tiempo_en_cbc',    'Cuatrimestres en el CBC',             'ordinal',
     ['primero', 'segundo', '1_2_anios', 'mas_2_anios']),
    ('interrupcion_cbc', 'Interrupciones en el CBC',            'ordinal',
     ['no', 'un_cuatr', 'mas']),
    ('facultad',         'Facultad',                            'nominal',  None),
    ('carrera',          'Carrera',                             'nominal',  None),
    ('tipo_escuela',     'Tipo de escuela secundaria',          'nominal',  None),
    ('estudios_superiores', 'Estudios superiores previos',      'nominal',  None),
    ('con_quien_vive',   'Con quién vive',                      'nominal',  None),
]

_CORR_N_MIN = 5  # mínimo de casos válidos para reportar una variable


def correlaciones_encuesta(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Correlaciones entre variables del onboarding y rendimiento en ejercicios.

    Métrica de rendimiento: ``rendimiento_con_ausentismo`` (escala 0–1),
    incorporando ausentismo hasta el último ejercicio con intento y ponderando
    estados en este orden: sin intento < error/rechazo docente < verificación
    formal automática < aprobación docente.

    Métodos estadísticos:
    - Variables binarias/numéricas → r de Pearson (point-biserial para binarias).
    - Variables ordinales           → r de Spearman (Pearson sobre rangos).
    - Variables nominales           → η² convertido a r_eq = √η² para comparabilidad.

    Requiere consentimiento_investigacion=True (solo_consentimiento=True por defecto).

    Args:
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        list[dict] ordenada por |r| descendente. Cada dict:
        - campo, label, tipo, metodo
        - r        : float — Pearson r, Spearman r, o √η² según tipo
        - efecto_raw: float — mismo valor (o η² para nominales)
        - n        : int   — estudiantes con datos válidos para esta variable
        - direction: 'positiva' | 'negativa' | None (None para nominales)
        - grupos   : list[dict] con {valor, label, n, media} ordenados por grupo
    """
    desempeno = _metricas_desempeno_por_estudiante(
        comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids,
    )
    registros = _registros_encuesta(comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)

    datos = []
    for registro in registros:
        d = desempeno.get(registro['pseudonimo'])
        if d is None or d['rendimiento_con_ausentismo'] is None:
            continue
        datos.append({
            'encuesta': registro['encuesta'],
            '_logicas': puntaje_logicas_encuesta(registro['encuesta']),
            '_nse': puntaje_nse_encuesta(registro['encuesta']),
            'y': d['rendimiento_con_ausentismo'],
        })

    resultados = []
    for campo, label, tipo, orden in _VARS_CORRELACION:
        resultado = _correlacion_variable(datos, campo, label, tipo, orden)
        if resultado is not None:
            resultados.append(resultado)

    return sorted(resultados, key=lambda x: (-abs(x['r'] or 0), x['label']))


def _corr_valor_campo(dato, campo):
    if campo == 'puntaje_logicas':
        return dato['_logicas']
    if campo == 'puntaje_nse':
        return dato['_nse']
    if campo == 'acertijo_hilera_correcto':
        val = _encuesta_attr(dato['encuesta'], 'acertijo_hilera')
        if val in (None, ''):
            return None
        return val == 'rodriguez'
    return _encuesta_attr(dato['encuesta'], campo)


def _correlacion_variable(datos, campo, label, tipo, orden):
    if tipo == 'nominal':
        return _corr_nominal(datos, campo, label)

    pares_raw = []  # (x_raw_str, y) para grupos de display
    pares_num = []  # (x_numeric, y) para el cálculo
    for d in datos:
        y = d['y']
        x = _corr_valor_campo(d, campo)
        if tipo == 'binario':
            if x is None:
                continue
            x_num = 1 if x else 0
            x_raw = 'Sí' if x else 'No'
        elif tipo == 'numerico':
            if x is None:
                continue
            try:
                x_num = float(x)
            except (TypeError, ValueError):
                continue
            x_raw = str(x)
        else:  # ordinal
            if x in (None, '') or orden is None or x not in orden:
                continue
            x_num = orden.index(x)
            x_raw = x
        pares_raw.append((x_raw, y))
        pares_num.append((x_num, y))

    if len(pares_num) < _CORR_N_MIN:
        return None

    xs = [p[0] for p in pares_num]
    ys = [p[1] for p in pares_num]

    if tipo == 'ordinal':
        r = _corr_pearson(_corr_rankdata(xs), _corr_rankdata(ys))
        metodo = 'spearman'
    else:
        r = _corr_pearson(xs, ys)
        metodo = 'pearson'

    if r is None:
        return None

    # Grupos para el desglose visual
    grupos_dict: dict = defaultdict(list)
    for x_raw, y in pares_raw:
        grupos_dict[x_raw].append(y)

    if tipo == 'ordinal' and orden is not None:
        sort_key = lambda k: orden.index(k) if k in orden else len(orden)
    elif tipo == 'binario':
        sort_key = lambda k: (k != 'Sí')
    else:
        sort_key = lambda k: k

    grupos = [
        {
            'valor': k,
            'label': k,
            'n': len(vs),
            'media': round(_statistics.mean(vs), 3),
        }
        for k, vs in sorted(grupos_dict.items(), key=lambda item: sort_key(item[0]))
    ]

    return {
        'campo': campo,
        'label': label,
        'tipo': tipo,
        'metodo': metodo,
        'r': round(r, 3),
        'efecto_raw': round(r, 3),
        'n': len(pares_num),
        'direction': 'positiva' if r > 0.005 else ('negativa' if r < -0.005 else None),
        'grupos': grupos,
    }


def _corr_nominal(datos, campo, label):
    grupos_dict: dict = defaultdict(list)
    for d in datos:
        x = _corr_valor_campo(d, campo)
        if x in (None, ''):
            continue
        grupos_dict[x].append(d['y'])

    valid = {k: vs for k, vs in grupos_dict.items() if len(vs) >= 2}
    if len(valid) < 2:
        return None

    eta2 = _corr_eta_squared(list(valid.values()))
    if eta2 is None:
        return None

    n = sum(len(vs) for vs in valid.values())
    if n < _CORR_N_MIN:
        return None

    r_eq = _math.sqrt(eta2)
    grupos = sorted(
        [
            {
                'valor': k,
                'label': k,
                'n': len(grupos_dict[k]),
                'media': round(_statistics.mean(grupos_dict[k]), 3),
            }
            for k in grupos_dict
        ],
        key=lambda g: -g['n'],
    )
    return {
        'campo': campo,
        'label': label,
        'tipo': 'nominal',
        'metodo': 'eta2',
        'r': round(r_eq, 3),
        'efecto_raw': round(eta2, 3),
        'n': n,
        'direction': None,
        'grupos': grupos,
    }


def _corr_pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = _statistics.mean(xs)
    my = _statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    ss_x = sum((x - mx) ** 2 for x in xs)
    ss_y = sum((y - my) ** 2 for y in ys)
    denom = _math.sqrt(ss_x * ss_y)
    if denom == 0:
        return None
    return cov / denom


def _corr_rankdata(xs):
    n = len(xs)
    sorted_pairs = sorted(enumerate(xs), key=lambda t: t[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and sorted_pairs[j][1] == sorted_pairs[i][1]:
            j += 1
        avg_rank = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[sorted_pairs[k][0]] = avg_rank
        i = j
    return ranks


# ─── Red de co-ocurrencia de errores ──────────────────────────────────────────

_ERRORES_LABELS = {
    'tautologia':      'Tautología',
    'contradiccion':   'Contradicción',
    'polaridad':       'Polaridad invertida',
    'mas_fuerte':      'Más fuerte',
    'mas_debil':       'Más débil',
    'equivalente_alt': 'Equivalente alt.',
    'error_parcial_1': 'Error parcial (leve)',
    'error_parcial_2': 'Error parcial (grave)',
    'error_sistemico': 'Error sistemático',
    'variables_extra': 'Variables extra',
    'variables_menos': 'Variables de menos',
    'sin_clasificar':  'Sin clasificar',
}

# Grupo semántico: determina el color del nodo en la red
_ERRORES_GRUPO = {
    'tautologia':      0,  # extremos lógicos
    'contradiccion':   0,
    'polaridad':       1,  # equivalencia/dirección
    'equivalente_alt': 1,
    'mas_fuerte':      2,  # fuerza lógica
    'mas_debil':       2,
    'error_parcial_1': 3,  # errores parciales
    'error_parcial_2': 3,
    'error_sistemico': 4,  # sistemático
    'variables_extra': 5,  # variables
    'variables_menos': 5,
    'sin_clasificar':  6,
}


def red_errores(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Grafo de co-ocurrencia de tipos de error a nivel de ejercicio-estudiante.

    Unidad de análisis: par ``(estudiante, ejercicio_practica)``.
    Dos tipos de error co-ocurren si el mismo estudiante acumuló ambos en sus
    intentos sobre el mismo ejercicio — sin rankear ejercicios ni estudiantes.

    Args:
        comision_ids: lista de IDs de comisión, o None para todas.
        solo_consentimiento: si True, filtra a consentimiento_investigacion=True.
        cohorte_ids: cohortes a incluir; None = todas.

    Returns:
        dict con:
        - nodes: list[{id, label, count, grupo}] — count = pares (est, ej) con ese error
        - links: list[{source, target, weight}]  — weight = pares donde co-ocurren
        - n_pares: total de pares (estudiante, ejercicio) con al menos un error clasificado
    """
    cids = _resolver_comision_ids(comision_ids)

    qs = (
        Intento.objects
        .filter(
            practica_comision__comision_id__in=cids,
            error_categoria__isnull=False,
        )
        .exclude(error_categoria='')
        .values('estudiante_id', 'ejercicio_practica_id', 'error_categoria')
    )
    qs = _filtrar_por_cohorte(qs, cohorte_ids)
    if solo_consentimiento:
        qs = qs.filter(estudiante__consentimiento_investigacion=True)

    # Por par (estudiante, ejercicio): set de tipos de error distintos
    pares: dict = defaultdict(set)
    for intento in qs:
        key = (intento['estudiante_id'], intento['ejercicio_practica_id'])
        pares[key].add(intento['error_categoria'])

    node_counts: Counter = Counter()
    edge_counts: Counter = Counter()

    for errores in pares.values():
        for err in errores:
            node_counts[err] += 1
        errores_list = sorted(errores)
        for i in range(len(errores_list)):
            for j in range(i + 1, len(errores_list)):
                edge_counts[(errores_list[i], errores_list[j])] += 1

    nodes = [
        {
            'id': err,
            'label': _ERRORES_LABELS.get(err, err),
            'count': count,
            'grupo': _ERRORES_GRUPO.get(err, 6),
        }
        for err, count in node_counts.items()
    ]

    links = [
        {'source': src, 'target': tgt, 'weight': w}
        for (src, tgt), w in edge_counts.items()
    ]

    return {
        'nodes': nodes,
        'links': links,
        'n_pares': len(pares),
    }


def _corr_eta_squared(groups_y):
    all_y = [y for g in groups_y for y in g]
    n = len(all_y)
    if n < 2:
        return None
    grand_mean = _statistics.mean(all_y)
    ss_total = sum((y - grand_mean) ** 2 for y in all_y)
    if ss_total == 0:
        return None
    ss_between = sum(
        len(g) * (_statistics.mean(g) - grand_mean) ** 2
        for g in groups_y if len(g) > 0
    )
    return ss_between / ss_total


# ─── Trabajo en plataforma vs. nota de lógica del parcial ─────────────────────

_TRABAJO_INDICADORES = (
    'intentos_totales', 'dias_activos',
    'ejercicios_distintos', 'practicas_abiertas',
)


def trabajo_vs_nota_logica(comision_ids=None, solo_consentimiento=True, *, cohorte_ids=None):
    """Relaciona el esfuerzo en la plataforma con la nota de lógica del 1er parcial.

    Un punto por estudiante (consentido y con nota de lógica graduada). El eje X
    son indicadores de esfuerzo (no rendimiento) acumulados antes de la fecha del
    primer parcial de cada comisión; el eje Y es ``nota_logica_parcial``.

    Args:
        comision_ids: iterable de IDs de Comision, o None para todas.
        solo_consentimiento: si True, filtra a consentimiento_investigacion=True.
        cohorte_ids: cohortes a incluir; None = todas. A diferencia del resto
            de la familia "intentos", acá no hay un queryset de ``Intento``
            propio que filtrar: se acota a través de ``Parcial.cohorte``
            (``NotaParcial`` no tiene campo ``cohorte`` propio). El "primer
            parcial" se elige POR (comisión, cohorte): si se piden varias
            cohortes, cada una aporta su propio primer parcial en vez de
            competir por un único primer parcial de la comisión entera.

    Returns:
        dict con ``puntos`` (lista de dicts), ``correlaciones`` (por indicador,
        con ``r_pearson``/``r_spearman``/``n``) y ``n``.
        ``desenlace`` en cada punto se basa en el ``puntaje`` TOTAL del parcial
        (no en ``nota_logica_parcial``) y puede ser ``None`` si el puntaje no
        fue cargado.
    """
    from cursos.models import Parcial, NotaParcial
    from analiticas.calculos import (
        calcular_uso_plataforma_antes_parcial,
        calcular_desenlace_parcial,
    )

    comision_ids = _resolver_comision_ids(comision_ids)

    # Primer parcial (menor fecha) de cada comisión, ya acotado a las
    # cohortes pedidas: si se filtra primero por fecha sin mirar la cohorte,
    # el "primer parcial" elegido puede pertenecer a otra camada y dejar
    # `notas` vacío más abajo (ver hallazgo 1 del review de PR #189). Cuando
    # se piden varias cohortes, hace falta un primer parcial POR cohorte, no
    # uno solo por comisión, así que la clave del dict incluye la cohorte.
    parciales_qs = Parcial.objects.filter(comision_id__in=comision_ids)
    if cohorte_ids is not None:
        parciales_qs = parciales_qs.filter(cohorte_id__in=cohorte_ids)

    primer_parcial = {}
    for parcial in parciales_qs.order_by('fecha'):
        primer_parcial.setdefault((parcial.comision_id, parcial.cohorte_id), parcial)

    crudos = []  # (uso_dict, nota_logica, desenlace)
    for parcial in primer_parcial.values():
        notas = NotaParcial.objects.filter(
            parcial=parcial, ausente=False, nota_logica_parcial__isnull=False,
        ).select_related('estudiante', 'parcial')
        if solo_consentimiento:
            notas = notas.filter(estudiante__consentimiento_investigacion=True)
        for nota in notas:
            uso = calcular_uso_plataforma_antes_parcial(nota.estudiante, parcial)
            crudos.append((uso, float(nota.nota_logica_parcial),
                           calcular_desenlace_parcial(nota)))

    if not crudos:
        correlaciones = {
            ind: {'r_pearson': None, 'r_spearman': None, 'n': 0}
            for ind in [*_TRABAJO_INDICADORES, 'indice_trabajo']
        }
        return {'puntos': [], 'correlaciones': correlaciones, 'n': 0}

    # Normalización min-max por indicador sobre la cohorte mostrada.
    mins = {ind: min((u[ind] for u, _, _ in crudos), default=0) for ind in _TRABAJO_INDICADORES}
    maxs = {ind: max((u[ind] for u, _, _ in crudos), default=0) for ind in _TRABAJO_INDICADORES}

    def _norm(ind, val):
        rng = maxs[ind] - mins[ind]
        return 0.0 if rng == 0 else (val - mins[ind]) / rng

    puntos = []
    for uso, nota_logica, desenlace in crudos:
        norms = [_norm(ind, uso[ind]) for ind in _TRABAJO_INDICADORES]
        punto = {ind: uso[ind] for ind in _TRABAJO_INDICADORES}
        punto['indice_trabajo'] = round(sum(norms) / len(norms) * 100, 1)
        punto['nota_logica'] = nota_logica
        punto['desenlace'] = desenlace
        puntos.append(punto)

    # Correlaciones de cada indicador (y del índice) contra la nota de lógica.
    ys = [p['nota_logica'] for p in puntos]
    correlaciones = {}
    # n >= 3 evita computar rangos innecesariamente (_corr_pearson ya devuelve None si n<3)
    for ind in [*_TRABAJO_INDICADORES, 'indice_trabajo']:
        xs = [p[ind] for p in puntos]
        n = len(xs)
        r_p = _corr_pearson(xs, ys) if n >= 3 else None
        r_s = _corr_pearson(_corr_rankdata(xs), _corr_rankdata(ys)) if n >= 3 else None
        correlaciones[ind] = {
            'r_pearson': round(r_p, 3) if r_p is not None else None,
            'r_spearman': round(r_s, 3) if r_s is not None else None,
            'n': n,
        }

    return {'puntos': puntos, 'correlaciones': correlaciones, 'n': len(puntos)}

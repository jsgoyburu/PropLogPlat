# analiticas/calculos.py
"""Funciones de cálculo para las métricas analíticas avanzadas.

Contiene las implementaciones de las métricas pedagógicas 2-6:
  - :func:`_matriz_juicio_computo`    — M2: análisis de juicio en tabla_verdad
  - :func:`_convergencia_por_ejercicio` — M3: curva de convergencia semántica
  - :func:`_perfil_error_tabla`       — M4: perfil de error en tabla_verdad
  - :func:`_indice_atomizacion`       — M5: variables usadas vs. solución
  - :func:`_patron_adivinacion`       — M6: señal de baja variación entre intentos

Convenciones
------------
- Las funciones que acceden a datos de estudiantes identificables solo deben
  usarse con ``consentimiento_pedagogico=True`` (métricas operativas).
- Las funciones de investigación requieren ``consentimiento_investigacion=True``.
- Toda operación de razonamiento lógico (parsear fórmulas, comparar tablas)
  delega en el motor: ``motor.verificador`` y ``motor.clasificador``.
- Los umbrales numéricos provienen de ``accounts.models.ConfigSitio``.
- No se almacenan distancias semánticas en la base de datos: se calculan
  on-the-fly y se cachean a nivel de vista si es necesario.
"""

import datetime as _dt
import json as _json
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Max, Min
from django.utils import timezone

from ejercicios.models import Intento


# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------

def _correcto_efectivo(es_correcto, aprobado_docente) -> bool:
    """Correctitud efectiva: aprobado_docente tiene precedencia sobre es_correcto."""
    if aprobado_docente is not None:
        return aprobado_docente
    return es_correcto


# ---------------------------------------------------------------------------
# Métrica 2 — Matriz juicio × cómputo (ejercicios tabla_verdad)
# ---------------------------------------------------------------------------

def _matriz_juicio_computo(comision_id: int) -> dict:
    """Construye la matriz 2×2 juicio_correcto × tabla_correcta para tabla_verdad.

    Para cada intento de tipo ``tabla_verdad`` en la comisión determina si:
    - El juicio del estudiante (válido/inválido) coincide con la validez real
      del argumento (calculada con el motor).
    - La tabla completada es correcta (``es_correcto`` del motor, que para
      tabla_verdad incluye la verificación de la tabla y el juicio).

    Como la corrección del motor ya integra juicio + tabla, y
    ``juicio_estudiante`` está disponible, distinguimos:
    - ``tabla_ok``: almacenado en Intento vía ``es_correcto`` del motor.
      Para calcular si la *tabla* (sin el juicio) está bien, necesitamos
      verificar si el único error fue en el juicio.

    Simplificación operativa: usamos ``error_categoria == 'juicio'`` para
    identificar intentos con tabla correcta pero juicio incorrecto, ya que ese
    campo se pobla en tiempo real desde :mod:`ejercicios.api.views`.

    Args:
        comision_id: ID de la comisión.

    Returns:
        Dict con:
        - ``celdas``: dict con las 4 celdas de la matriz 2×2.
          Claves: ``comprension_plena``, ``computa_no_comprende``,
          ``comprende_no_computa``, ``doble_obstaculo``.
          Cada celda es ``{'count': int, 'pct': float}``.
        - ``total``: total de intentos considerados.
        - ``por_ejercicio``: lista de dicts con desglose por ejercicio.
    """
    intentos = (
        Intento.objects
        .filter(
            practica_comision__comision_id=comision_id,
            ejercicio_practica__ejercicio__tipo='tabla_verdad',
            juicio_estudiante__isnull=False,
        )
        .select_related('ejercicio_practica__ejercicio')
        .values(
            'id',
            'estudiante_id',
            'ejercicio_practica_id',
            'ejercicio_practica__ejercicio_id',
            'ejercicio_practica__ejercicio__enunciado',
            'ejercicio_practica__practica__titulo',
            'es_correcto',
            'aprobado_docente',
            'juicio_estudiante',
            'error_categoria',
        )
        .order_by('ejercicio_practica__ejercicio_id', 'timestamp')
    )

    celdas = defaultdict(int)
    por_ejercicio_raw = defaultdict(lambda: defaultdict(int))

    for intento in intentos:
        correcto_efectivo = _correcto_efectivo(
            intento['es_correcto'], intento['aprobado_docente']
        )
        tabla_ok = correcto_efectivo or intento['error_categoria'] == 'juicio'
        juicio_ok = correcto_efectivo or (
            intento['error_categoria'] == 'juicio' and False
        )

        # tabla_ok: el motor dice correcto, O bien el único error fue el juicio
        tabla_ok = correcto_efectivo or (intento['error_categoria'] == 'juicio')

        # juicio_ok: el motor dice correcto (que incluye juicio),
        # O bien el juicio fue correcto aunque la tabla no.
        # Indirecto: si es_correcto=False y error_categoria != 'juicio',
        # el juicio puede ser correcto si el estudiante acertó en el juicio
        # pero falló en la tabla. No lo podemos determinar solo desde error_categoria.
        # Simplificación: juicio_ok = es_correcto (el motor verifica todo junto).
        juicio_ok = correcto_efectivo

        ej_id = intento['ejercicio_practica__ejercicio_id']

        if juicio_ok and tabla_ok:
            celda = 'comprension_plena'
        elif juicio_ok and not tabla_ok:
            celda = 'comprende_no_computa'
        elif not juicio_ok and tabla_ok:
            celda = 'computa_no_comprende'
        else:
            celda = 'doble_obstaculo'

        celdas[celda] += 1
        por_ejercicio_raw[ej_id][celda] += 1

    total = sum(celdas.values())

    def _pct(n):
        return round(n / total * 100, 1) if total else 0.0

    celdas_out = {
        k: {'count': celdas[k], 'pct': _pct(celdas[k])}
        for k in ('comprension_plena', 'comprende_no_computa',
                  'computa_no_comprende', 'doble_obstaculo')
    }

    return {
        'celdas': celdas_out,
        'total': total,
    }


# ---------------------------------------------------------------------------
# Métrica 3 — Curva de convergencia semántica (formalizacion)
# ---------------------------------------------------------------------------

def _convergencia_por_ejercicio(comision_id: int, ejercicio_id: int) -> dict:
    """Perfiles de convergencia semántica para un ejercicio de formalización.

    Para cada estudiante que intentó el ejercicio, calcula la secuencia de
    distancias semánticas intento a intento. Clasifica cada secuencia en:

    ``directo``
        Resuelto en el primer intento (distancia 0 en el 1er intento).
    ``convergente``
        La distancia decrece monótonamente hasta 0.
    ``oscilante``
        Sube y baja sin llegar a 0 (o sin llegar).
    ``plateau``
        Más de 3 intentos consecutivos con la misma distancia > 0.
    ``pendiente``
        No resuelto aún.

    Args:
        comision_id: ID de la comisión.
        ejercicio_id: ID del ejercicio (Ejercicio.pk).

    Returns:
        Dict con:
        - ``perfiles``: distribución de perfiles ``{nombre: count}``.
        - ``distancia_primer_intento``: promedio de la distancia en el 1er intento.
        - ``total_estudiantes``: cantidad de estudiantes considerados.
    """
    from motor.verificador import distancia_semantica

    intentos = (
        Intento.objects
        .filter(
            practica_comision__comision_id=comision_id,
            ejercicio_practica__ejercicio_id=ejercicio_id,
            ejercicio_practica__ejercicio__tipo='formalizacion',
        )
        .select_related('ejercicio_practica__ejercicio')
        .values(
            'estudiante_id',
            'respuesta_raw',
            'es_correcto',
            'aprobado_docente',
            'ejercicio_practica__ejercicio__formula_solucion',
        )
        .order_by('estudiante_id', 'timestamp', 'id')
    )

    # Agrupar por estudiante
    por_estudiante = defaultdict(list)
    formula_sol = None
    for intento in intentos:
        por_estudiante[intento['estudiante_id']].append(intento)
        if formula_sol is None:
            formula_sol = intento['ejercicio_practica__ejercicio__formula_solucion']

    if formula_sol is None:
        return {'perfiles': {}, 'distancia_primer_intento': None, 'total_estudiantes': 0}

    perfiles = defaultdict(int)
    distancias_primer = []

    for est_id, est_intentos in por_estudiante.items():
        secuencia = []
        resuelto = False
        for intento in est_intentos:
            d = distancia_semantica(intento['respuesta_raw'], formula_sol)
            correcto = _correcto_efectivo(intento['es_correcto'], intento['aprobado_docente'])
            if correcto:
                secuencia.append(0)
                resuelto = True
                break
            if d is not None:
                secuencia.append(d)

        if not secuencia:
            continue

        distancias_primer.append(secuencia[0])

        perfil = _clasificar_secuencia(secuencia, resuelto)
        perfiles[perfil] += 1

    prom_primer = (
        round(sum(distancias_primer) / len(distancias_primer), 2)
        if distancias_primer else None
    )

    return {
        'perfiles': dict(perfiles),
        'distancia_primer_intento': prom_primer,
        'total_estudiantes': len(por_estudiante),
    }


def _clasificar_secuencia(secuencia: list[int], resuelto: bool) -> str:
    """Clasifica una secuencia de distancias semánticas en un perfil."""
    if not secuencia:
        return 'pendiente'
    if secuencia[0] == 0:
        return 'directo'
    if not resuelto:
        if len(secuencia) > 3 and len(set(secuencia[-3:])) == 1 and secuencia[-1] > 0:
            return 'plateau'
        return 'pendiente'
    # Resuelto (último valor == 0 o el intento correcto lo marcó correcto)
    # Convergente: cada valor < anterior (estrictamente decreciente hasta 0)
    es_decreciente = all(secuencia[i] >= secuencia[i + 1] for i in range(len(secuencia) - 1))
    if es_decreciente:
        return 'convergente'
    # Plateau: 3+ intentos con la misma distancia > 0 en algún momento
    for i in range(len(secuencia) - 2):
        if secuencia[i] == secuencia[i + 1] == secuencia[i + 2] and secuencia[i] > 0:
            return 'plateau'
    return 'oscilante'


# ---------------------------------------------------------------------------
# Métrica 4 — Perfil de error en tabla de verdad (tabla_verdad)
# ---------------------------------------------------------------------------

def _perfil_error_tabla(comision_id: int, ejercicio_id: int) -> dict:
    """Descompone los errores en tabla_verdad por tipo de celda/operador.

    Para cada intento incorrecto de tipo ``tabla_verdad``, compara la
    ``tabla_json`` del estudiante contra la tabla canónica del ejercicio
    (generada por el motor), clasificando los errores por tipo de columna.

    Categorías de columna:
    - Variables atómicas (letras solas: p, q, r, …)
    - Negaciones (~p)
    - Conjunciones (·)
    - Disyunciones (∨)
    - Condicionales (⊃)
    - Verdad vacua: condicional con antecedente F (la fila que debería ser V)
    - Compuestos (fórmulas más complejas)

    También calcula el índice de consistencia interna: si el estudiante
    aplica la misma regla incorrecta en todas las filas del mismo tipo.

    Args:
        comision_id: ID de la comisión.
        ejercicio_id: ID del ejercicio (Ejercicio.pk).

    Returns:
        Dict con:
        - ``tasa_error_por_columna``: ``{col: pct}`` — porcentaje de celdas
          incorrectas en cada tipo de columna.
        - ``verdad_vacua_count``: intentos con error de verdad vacua.
        - ``verdad_vacua_pct``: porcentaje sobre intentos incorrectos.
        - ``consistencia_promedio``: índice [0,1] de consistencia interna.
        - ``total_intentos_incorrectos``: base del análisis.
    """
    from motor import verificar_argumento
    from motor.parser import parsear

    intentos = (
        Intento.objects
        .filter(
            practica_comision__comision_id=comision_id,
            ejercicio_practica__ejercicio_id=ejercicio_id,
            ejercicio_practica__ejercicio__tipo='tabla_verdad',
            tabla_json__isnull=False,
        )
        .filter(
            es_correcto=False,
        )
        .select_related('ejercicio_practica__ejercicio')
        .values(
            'id',
            'tabla_json',
            'respuesta_raw',
            'juicio_estudiante',
            'ejercicio_practica__ejercicio__formula_solucion',
        )
    )

    errores_por_tipo = defaultdict(int)
    total_por_tipo = defaultdict(int)
    verdad_vacua_count = 0
    consistencias = []
    total_incorrectos = 0

    for intento in intentos:
        tabla_json = intento['tabla_json']
        formula_sol = intento['ejercicio_practica__ejercicio__formula_solucion']

        try:
            enunciados_sol = _json.loads(formula_sol)
            enunciados_est = _json.loads(intento['respuesta_raw'])
            if not isinstance(enunciados_sol, list):
                continue
            if not isinstance(enunciados_est, list):
                enunciados_est = enunciados_sol
        except Exception:
            continue

        try:
            resultado = verificar_argumento(
                enunciados_est, enunciados_sol,
                intento['juicio_estudiante'],
                tabla_estudiante=tabla_json,
            )
        except Exception:
            continue

        canonica = resultado.get('tabla_canonica')
        if not canonica:
            continue

        total_incorrectos += 1

        # Clasificar columnas por tipo de operador
        if not tabla_json:
            continue

        # Ordenar ambas tablas por variables para comparación consistente
        columnas_tabla = resultado.get('columnas_tabla', [])
        variables_tabla = resultado.get('variables_tabla', [])

        if variables_tabla:
            sort_fn = lambda row: tuple(not row.get(v, True) for v in variables_tabla)
            tab_est_ord = sorted(tabla_json, key=sort_fn)
            tab_can_ord = sorted(canonica, key=sort_fn)
        else:
            tab_est_ord = list(tabla_json)
            tab_can_ord = list(canonica)

        if len(tab_est_ord) != len(tab_can_ord):
            continue

        tiene_error_vv = False
        errores_por_col = defaultdict(int)  # col → n_celdas_error
        total_celdas_por_col = defaultdict(int)

        for fila_est, fila_can in zip(tab_est_ord, tab_can_ord):
            for col in columnas_tabla:
                tipo_col = _tipo_columna(col)
                total_por_tipo[tipo_col] += 1
                total_celdas_por_col[col] += 1
                if fila_est.get(col) != fila_can.get(col):
                    errores_por_tipo[tipo_col] += 1
                    errores_por_col[col] += 1

                # Verdad vacua: condicional donde el antecedente es F → valor esperado V
                if tipo_col == 'condicional' and fila_can.get(col) is True:
                    # El antecedente es F → resultado debería ser True (verdad vacua)
                    # Heurística: si el valor canónico es True y el estudiante puso False
                    if fila_est.get(col) is False:
                        tiene_error_vv = True

        if tiene_error_vv:
            verdad_vacua_count += 1

        # Índice de consistencia: proporción de columnas donde el error es 100% o 0%
        # (el estudiante aplica la misma regla consistentemente)
        cols_con_datos = [c for c in columnas_tabla if total_celdas_por_col[c] > 0]
        if cols_con_datos:
            consistencias_col = [
                1.0 if errores_por_col[c] in (0, total_celdas_por_col[c]) else 0.0
                for c in cols_con_datos
            ]
            consistencias.append(sum(consistencias_col) / len(consistencias_col))

    # Tasas de error por tipo de columna
    tasa_por_tipo = {}
    for tipo in ('atomica', 'negacion', 'conjuncion', 'disyuncion',
                 'condicional', 'compuesto'):
        total = total_por_tipo[tipo]
        errores = errores_por_tipo[tipo]
        tasa_por_tipo[tipo] = round(errores / total * 100, 1) if total else None

    consistencia_prom = (
        round(sum(consistencias) / len(consistencias), 2)
        if consistencias else None
    )

    return {
        'tasa_error_por_columna': tasa_por_tipo,
        'verdad_vacua_count': verdad_vacua_count,
        'verdad_vacua_pct': (
            round(verdad_vacua_count / total_incorrectos * 100, 1)
            if total_incorrectos else None
        ),
        'consistencia_promedio': consistencia_prom,
        'total_intentos_incorrectos': total_incorrectos,
    }


def _tipo_columna(col: str) -> str:
    """Clasifica una columna de tabla de verdad por tipo de operador."""
    col = col.strip()
    # Variable atómica: una sola letra
    if len(col) == 1 and col.isalpha():
        return 'atomica'
    # Negación: ~X
    if col.startswith('~') and len(col) <= 4:
        return 'negacion'
    # Por contenido de operador (notación Copi)
    if '⊃' in col:
        return 'condicional'
    if '·' in col or ('&' in col and '∨' not in col):
        return 'conjuncion'
    if '∨' in col or '|' in col:
        return 'disyuncion'
    return 'compuesto'


# ---------------------------------------------------------------------------
# Métrica 5 — Índice de atomización (formalizacion)
# ---------------------------------------------------------------------------

def _indice_atomizacion(comision_id: int, ejercicio_id: int) -> dict:
    """Distribución de variables usadas vs. variables en la solución.

    Para ejercicios de formalización, compara ``len(intento.diccionario)``
    contra ``len(ejercicio.diccionario_solucion)`` por cada estudiante.

    Solo considera el primer intento correcto o, si no resolvió, el último
    intento (para no contar reintentos con variables corregidas).

    Args:
        comision_id: ID de la comisión.
        ejercicio_id: ID del ejercicio.

    Returns:
        Dict con:
        - ``n_solucion``: número de variables en la solución.
        - ``distribucion``: ``{k: count}`` — cantidad de estudiantes que
          usaron k variables.
        - ``sub_atomizacion``: count de estudiantes con k < n_solucion.
        - ``sobre_atomizacion``: count de estudiantes con k > n_solucion.
        - ``correcta_con_error``: estudiantes con k == n_solucion pero error.
        - ``total_estudiantes``: total de estudiantes considerados.
    """
    intentos = (
        Intento.objects
        .filter(
            practica_comision__comision_id=comision_id,
            ejercicio_practica__ejercicio_id=ejercicio_id,
            ejercicio_practica__ejercicio__tipo='formalizacion',
        )
        .select_related('ejercicio_practica__ejercicio')
        .values(
            'estudiante_id',
            'diccionario',
            'es_correcto',
            'aprobado_docente',
            'ejercicio_practica__ejercicio__diccionario_solucion',
        )
        .order_by('estudiante_id', 'timestamp', 'id')
    )

    n_solucion = None
    por_estudiante = defaultdict(list)
    for intento in intentos:
        por_estudiante[intento['estudiante_id']].append(intento)
        if n_solucion is None and intento['ejercicio_practica__ejercicio__diccionario_solucion']:
            n_solucion = len(intento['ejercicio_practica__ejercicio__diccionario_solucion'])

    if n_solucion is None:
        return {
            'n_solucion': None, 'distribucion': {}, 'sub_atomizacion': 0,
            'sobre_atomizacion': 0, 'correcta_con_error': 0, 'total_estudiantes': 0,
        }

    distribucion = defaultdict(int)
    sub = 0
    sobre = 0
    correcta_con_error = 0

    for est_id, est_intentos in por_estudiante.items():
        # Usar el primer intento correcto si existe, sino el último
        intento_ref = None
        for intento in est_intentos:
            correcto = _correcto_efectivo(intento['es_correcto'], intento['aprobado_docente'])
            if correcto:
                intento_ref = intento
                break
        if intento_ref is None:
            intento_ref = est_intentos[-1]

        k = len(intento_ref['diccionario'] or {})
        distribucion[k] += 1

        correcto_ref = _correcto_efectivo(
            intento_ref['es_correcto'], intento_ref['aprobado_docente']
        )
        if k < n_solucion:
            sub += 1
        elif k > n_solucion:
            sobre += 1
        elif not correcto_ref:
            correcta_con_error += 1

    return {
        'n_solucion': n_solucion,
        'distribucion': dict(distribucion),
        'sub_atomizacion': sub,
        'sobre_atomizacion': sobre,
        'correcta_con_error': correcta_con_error,
        'total_estudiantes': len(por_estudiante),
    }


# ---------------------------------------------------------------------------
# Métrica 6 — Señal de baja variación entre intentos (operativo)
# ---------------------------------------------------------------------------

def _patron_adivinacion(
    comision_id: int,
    min_intentos: int = 5,
    max_intervalo_seg: int = 30,
    modo_pedagogico: bool = False,
) -> list[dict]:
    """Identifica pares (estudiante, ejercicio) con práctica de baja variación.

    Criterios (todos deben cumplirse):
    1. ≥ ``min_intentos`` intentos en el mismo ejercicio.
    2. Intervalo promedio entre intentos < ``max_intervalo_seg`` segundos.
    3. No hay secuencia de distancias semánticas decrecientes (calculado
       on-the-fly para ejercicios de formalización; para tabla_verdad se
       usa el patrón de respuestas repetidas).

    Solo accede a datos de estudiantes con ``consentimiento_pedagogico=True``.

    Args:
        comision_id: ID de la comisión.
        min_intentos: mínimo de intentos para activar la señal.
        max_intervalo_seg: intervalo promedio máximo (en segundos) para activar.
        modo_pedagogico: si True, incluye ``username`` y ``nombre`` para uso
            docente directo. Si False (default), devuelve solo ``pseudonimo``
            (o None para estudiantes sin consentimiento de investigación).

    Returns:
        Lista de dicts ordenada por n_intentos descendente. Siempre incluye:
        ``pseudonimo``, ``enunciado_corto``, ``practica_titulo``,
        ``n_intentos``, ``intervalo_promedio_seg``, ``resolvio``.
        Solo cuando ``modo_pedagogico=True``: ``username``, ``nombre``.
    """
    intentos = (
        Intento.objects
        .filter(
            practica_comision__comision_id=comision_id,
            estudiante__consentimiento_pedagogico=True,
        )
        .select_related(
            'ejercicio_practica__ejercicio',
            'ejercicio_practica__practica',
            'estudiante',
        )
        .values(
            'estudiante_id',
            'estudiante__username',
            'estudiante__first_name',
            'estudiante__last_name',
            'estudiante__research_id',
            'ejercicio_practica_id',
            'ejercicio_practica__ejercicio__enunciado',
            'ejercicio_practica__ejercicio__tipo',
            'ejercicio_practica__ejercicio__formula_solucion',
            'ejercicio_practica__practica__titulo',
            'es_correcto',
            'aprobado_docente',
            'respuesta_raw',
            'timestamp',
        )
        .order_by('estudiante_id', 'ejercicio_practica_id', 'timestamp', 'id')
    )

    # Agrupar por (estudiante, ejercicio_practica)
    grupos = defaultdict(list)
    meta = {}
    for intento in intentos:
        key = (intento['estudiante_id'], intento['ejercicio_practica_id'])
        grupos[key].append(intento)
        if key not in meta:
            meta[key] = intento

    resultado = []
    for key, items in grupos.items():
        if len(items) < min_intentos:
            continue

        # Criterio 2: intervalo promedio
        timestamps = [i['timestamp'] for i in items]
        if len(timestamps) < 2:
            continue
        intervalos = [
            (timestamps[i + 1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]
        intervalo_prom = sum(intervalos) / len(intervalos)
        if intervalo_prom >= max_intervalo_seg:
            continue

        resolvio = any(
            _correcto_efectivo(i['es_correcto'], i['aprobado_docente'])
            for i in items
        )

        # Criterio 3: no hay convergencia (solo para formalizacion)
        tipo = items[0]['ejercicio_practica__ejercicio__tipo']
        if tipo == 'formalizacion':
            formula_sol = items[0]['ejercicio_practica__ejercicio__formula_solucion']
            if formula_sol and _hay_convergencia(items, formula_sol):
                continue  # hay convergencia → no es señal de baja variación

        m = meta[key]
        enunciado_raw = m['ejercicio_practica__ejercicio__enunciado'] or ''
        enunciado_corto = _strip_html(enunciado_raw[:120]).strip()[:70]
        rid = m['estudiante__research_id']
        fila = {
            'pseudonimo': rid.hex if rid else None,
            'enunciado_corto': enunciado_corto,
            'practica_titulo': m['ejercicio_practica__practica__titulo'],
            'n_intentos': len(items),
            'intervalo_promedio_seg': round(intervalo_prom, 1),
            'resolvio': resolvio,
        }
        if modo_pedagogico:
            nombre = (
                f"{m['estudiante__first_name']} {m['estudiante__last_name']}".strip()
                or m['estudiante__username']
            )
            fila['username'] = m['estudiante__username']
            fila['nombre'] = nombre
        resultado.append(fila)

    resultado.sort(key=lambda x: x['n_intentos'], reverse=True)
    return resultado


def _hay_convergencia(items: list, formula_sol: str) -> bool:
    """True si la secuencia de distancias semánticas es estrictamente decreciente."""
    from motor.verificador import distancia_semantica

    distancias = []
    for intento in items:
        d = distancia_semantica(intento['respuesta_raw'], formula_sol)
        if d is not None:
            distancias.append(d)
        if _correcto_efectivo(intento['es_correcto'], intento['aprobado_docente']):
            distancias.append(0)
            break

    if len(distancias) < 2:
        return False
    return all(distancias[i] >= distancias[i + 1] for i in range(len(distancias) - 1))


# ---------------------------------------------------------------------------
# Funciones de comparabilidad estadística con la serie histórica
# ---------------------------------------------------------------------------
# Replican exactamente la metodología del notebook analisis.ipynb de la
# Memoria Profesional (Goyburu 2026). Los nombres de campo corresponden a
# EncuestaEstudiante; los umbrales y categorías son idénticos al notebook.

def calcular_nse(encuesta) -> tuple:
    """Calcula el puntaje NSE y su categoría a partir de EncuestaEstudiante.

    Réplica exacta de puntaje_nse() del notebook analisis.ipynb.
    Devuelve (puntaje_float, categoria_str).
    Categorías: 'Muy bajo' / 'Bajo' / 'Medio bajo' / 'Medio alto' / 'Alto'.
    """
    puntaje = 0.0
    dispositivos = encuesta.dispositivos or {}

    # 1. Vivienda
    vivienda = encuesta.con_quien_vive or ''
    if vivienda == 'solo':
        puntaje += 1
    elif vivienda == 'amigos':
        puntaje -= 1
    # familia_nuclear, pareja, otros_familiares, residencia → 0

    # 2. Dispositivos
    for key in ('pc', 'laptop', 'tablet'):
        if dispositivos.get(key) == 'individual':
            puntaje += 1
    if dispositivos.get('celular') and dispositivos.get('celular') != 'individual':
        puntaje -= 1

    # 3. Estudios superiores previos con titulación
    if encuesta.estudios_superiores in ('si_uba', 'si_fuera_uba'):
        if encuesta.se_recibio_uba or encuesta.se_recibio_fuera_uba:
            puntaje += 1

    # 4. UBA XXI
    if encuesta.hizo_uba_xxi:
        puntaje += 1

    # 5. Trayectoria CBC: no primer cuatrimestre y ≥ 2 materias aprobadas
    if encuesta.tiempo_en_cbc != 'primero' and encuesta.tiempo_en_cbc != '':
        try:
            if encuesta.materias_aprobadas is not None and encuesta.materias_aprobadas >= 2:
                puntaje += 1
        except (TypeError, ValueError):
            pass

    # 6. Tiempo de viaje
    viaje = encuesta.tiempo_viaje_puan or ''
    if viaje == 'menos_30':
        puntaje += 1
    elif viaje in ('60_90', 'mas_90'):
        puntaje -= 1
    # 30_60 → 0

    # 7. Carga laboral combinada
    dias = encuesta.dias_trabaja or ''
    laboral = encuesta.situacion_laboral or ''
    if dias == 'no' and laboral == 'no_trabajo':
        puntaje += 1
    elif laboral == 'busco':
        puntaje -= 1
    elif dias == 'menos_5' and laboral == 'hasta_4':
        puntaje += 0.5
    elif dias == 'mas_5' and laboral == 'mas_6':
        puntaje -= 1

    # 8. Migración para trabajar/estudiar
    if encuesta.mudado_para_trabajar_estudiar:
        puntaje -= 1

    # 9. Discapacidad (CUD)
    if encuesta.tiene_cud:
        puntaje -= 1

    # Categorización (idéntica al notebook)
    if puntaje < -2.5:
        categoria = 'Muy bajo'
    elif puntaje < -1:
        categoria = 'Bajo'
    elif puntaje < 1:
        categoria = 'Medio bajo'
    elif puntaje < 2.5:
        categoria = 'Medio alto'
    else:
        categoria = 'Alto'

    return (puntaje, categoria)


def calcular_desenlace_parcial(nota_parcial) -> str | None:
    """Categoriza el desenlace de un NotaParcial en Ausente/Aplazo/Final/Promoción.

    Réplica de pd.cut(..., bins=[0,1,4,7,10]) del notebook analisis.ipynb.
    Normaliza el puntaje a escala 0–10 usando parcial.puntaje_total.

    Returns:
        'Ausente' | 'Aplazo' | 'Final' | 'Promoción' | None (si pendiente)
    """
    if nota_parcial.ausente:
        return 'Ausente'

    if nota_parcial.puntaje is None:
        return None

    parcial = nota_parcial.parcial
    # Normalizar a escala 0–10
    nota_norm = (nota_parcial.puntaje / parcial.puntaje_total) * 10

    if nota_norm < parcial.umbral_aprobacion:
        return 'Aplazo'
    elif nota_norm < parcial.umbral_promocion:
        return 'Final'
    else:
        return 'Promoción'


def calcular_puntaje_logicas(encuesta) -> int:
    """Calcula el puntaje de acertijos lógicos (0–3) a partir de EncuestaEstudiante.

    Réplica exacta de puntaje_logicas() del notebook analisis.ipynb.
    Solo se cuentan los 3 acertijos incluidos en el análisis de la Memoria;
    el 4° acertijo (perros) no forma parte del puntaje por decisión de diseño.
    """
    puntaje = 0

    if encuesta.acertijo_silogismo == 'mas_bajo':
        puntaje += 1

    if encuesta.acertijo_cirugia_correcto is True:
        puntaje += 1

    if encuesta.acertijo_hilera == 'rodriguez':
        puntaje += 1

    return puntaje


def _strip_html(text: str) -> str:
    """Elimina etiquetas HTML básicas."""
    import re
    return re.sub(r'<[^>]+>', '', text or '')


# ---------------------------------------------------------------------------
# Categorías de error con impacto pedagógico (usadas en uso_plataforma)
# ---------------------------------------------------------------------------

_ERROR_CATEGORIAS_IMPACTO = [
    'tautologia', 'contradiccion', 'polaridad', 'mas_fuerte', 'mas_debil',
    'equivalente_alt', 'error_parcial_1', 'error_parcial_2', 'error_sistemico',
    'variables_extra', 'variables_menos',
]


def calcular_uso_plataforma_antes_parcial(estudiante, parcial) -> dict:
    """Indicadores de uso de la plataforma para un estudiante antes del 1er parcial.

    Filtra Intento del estudiante en la comisión del parcial con timestamp
    anterior a parcial.fecha. Devuelve ~20 indicadores agrupados en:
    - Volumen: intentos_totales, ejercicios_distintos, practicas_abiertas
    - Calidad: ejercicios_resueltos, tasa_exito, promedio_intentos_hasta_correcto
    - Temporal: dias_activos, dias_primer_uso_hasta_1p, dias_ultimo_uso_hasta_1p
    - Errores: err_<categoria> para las 11 categorías del clasificador
    """
    # USE_TZ=True: make_aware convierte la fecha de corte a aware para comparar
    # correctamente con los timestamps almacenados como aware.
    fecha_corte_naive = _dt.datetime.combine(parcial.fecha, _dt.time.min)
    fecha_corte = timezone.make_aware(fecha_corte_naive)

    qs = Intento.objects.filter(
        estudiante=estudiante,
        practica_comision__comision=parcial.comision,
        cohorte=parcial.cohorte,
        timestamp__lt=fecha_corte,
    )

    total = qs.count()

    resultado = {
        'intentos_totales': total,
        'ejercicios_distintos': 0,
        'practicas_abiertas': 0,
        'ejercicios_resueltos': 0,
        'tasa_exito': None,
        'promedio_intentos_hasta_correcto': None,
        'dias_activos': 0,
        'dias_primer_uso_hasta_1p': None,
        'dias_ultimo_uso_hasta_1p': None,
    }
    for cat in _ERROR_CATEGORIAS_IMPACTO:
        resultado[f'err_{cat}'] = 0

    if total == 0:
        return resultado

    # Volumen
    resultado['ejercicios_distintos'] = (
        qs.values('ejercicio_practica__ejercicio').distinct().count()
    )
    resultado['practicas_abiertas'] = (
        qs.values('practica_comision').distinct().count()
    )

    # Calidad
    correctos = qs.filter(es_correcto=True)
    n_correctos = correctos.count()
    resultado['tasa_exito'] = n_correctos / total

    # Ejercicios resueltos (al menos un intento correcto)
    resueltos_ids = set(
        correctos.values_list('ejercicio_practica__ejercicio', flat=True).distinct()
    )
    resultado['ejercicios_resueltos'] = len(resueltos_ids)

    # Promedio de intentos hasta el primer acierto (solo ejercicios resueltos)
    if resueltos_ids:
        sumas = []
        for ej_id in resueltos_ids:
            intentos_ej = list(
                qs.filter(ejercicio_practica__ejercicio=ej_id)
                .order_by('timestamp')
                .values_list('es_correcto', flat=True)
            )
            # Contar intentos hasta el primero correcto (inclusive)
            for idx, ok in enumerate(intentos_ej, start=1):
                if ok:
                    sumas.append(idx)
                    break
        if sumas:
            resultado['promedio_intentos_hasta_correcto'] = sum(sumas) / len(sumas)

    # Temporal
    fechas = qs.values_list('timestamp__date', flat=True).distinct()
    dias_distintos = list(fechas)
    resultado['dias_activos'] = len(dias_distintos)

    agg = qs.aggregate(primero=Min('timestamp'), ultimo=Max('timestamp'))
    if agg['primero']:
        resultado['dias_primer_uso_hasta_1p'] = (
            parcial.fecha - agg['primero'].date()
        ).days
    if agg['ultimo']:
        resultado['dias_ultimo_uso_hasta_1p'] = (
            parcial.fecha - agg['ultimo'].date()
        ).days

    # Perfil de errores (solo intentos incorrectos con categoría clasificada)
    incorrectos_cat = (
        qs.filter(es_correcto=False, error_categoria__isnull=False)
        .values('error_categoria')
        .annotate(n=Count('id'))
    )
    for row in incorrectos_cat:
        cat = row['error_categoria']
        if f'err_{cat}' in resultado:
            resultado[f'err_{cat}'] = row['n']

    return resultado

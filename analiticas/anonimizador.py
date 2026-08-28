"""Motor de anonimización para exportación de datos de investigación.

Pseudonimización basada en ``Usuario.research_id`` (UUID estable, generado una
sola vez, nunca expuesto en la UI). Permite cruzar datasets sin revelar PII:

    encuesta.pseudonimo == intentos.pseudonimo  →  mismo estudiante

## PII excluida siempre
- ``EncuestaEstudiante``: dni, whatsapp, estudiante_id (FK directa)
- ``fecha_nacimiento`` → transformada a rango de 5 años (ej. "20-24")
- ``Usuario``: username, first_name, last_name, **email**, password, last_login,
  date_joined — de Usuario solo se lee ``research_id`` (vía :func:`pseudonimo`);
  estos campos nunca se leen ni aparecen en ningún dict de salida

## Uso básico

    from analiticas.anonimizador import pseudonimo, encuesta_anonima, intento_anonimo

    pid = pseudonimo(usuario)                  # hex UUID sin guiones
    row = encuesta_anonima(encuesta_obj)       # dict sin PII
    rows = [intento_anonimo(i) for i in qs]   # lista de dicts

## Filtrado de consentimiento

Siempre aplicar antes de exportar:

    qs = Intento.objects.filter(estudiante__consentimiento_investigacion=True)
"""

from datetime import date


# Campos de Usuario que contienen PII directa y se excluyen de todo export.
# De Usuario solo se lee research_id (vía pseudonimo()); el resto nunca se toca.
CAMPOS_PII_USUARIO: frozenset[str] = frozenset({
    "id",
    "username",
    "first_name",
    "last_name",
    "email",
    "password",
    "last_login",
    "date_joined",
})

# Campos de EncuestaEstudiante que contienen PII directa y nunca se exportan.
# ``estudiante_id`` es la FK que apunta al usuario real; se reemplaza por pseudonimo.
CAMPOS_PII_ENCUESTA: frozenset[str] = frozenset({
    "id",
    "estudiante_id",
    "dni",
    "whatsapp",
    "fecha_nacimiento",  # sustituida por rango_edad
})

# Campos de EncuestaEstudiante que van al export (orden pedagógico).
CAMPOS_ENCUESTA_EXPORT: tuple[str, ...] = (
    "facultad",
    "carrera",
    "origen_caba_gba",
    "vive_en",
    "mudado_con_familia",
    "mudado_para_trabajar_estudiar",
    "tiempo_mudado",
    "desde_donde",
    "provincia_origen",
    "pais_origen",
    "necesita_adecuacion",
    "tiene_cud",
    "con_quien_vive",
    "tiempo_viaje_puan",
    "situacion_laboral",
    "dias_trabaja",
    "acceso_internet",
    "dispositivos",
    "tiempo_desde_secundaria",
    "tipo_escuela",
    "estudios_superiores",
    "carrera_uba_anterior",
    "termino_cbc_anterior",
    "se_recibio_uba",
    "tipo_inst_fuera_uba",
    "carrera_fuera_uba",
    "se_recibio_fuera_uba",
    "hizo_uba_xxi",
    "tiempo_en_cbc",
    "interrupcion_cbc",
    "ya_curso_ipc",
    "motivo_no_termino_ipc",
    "materias_aprobadas",
    "acertijo_silogismo",
    "acertijo_cirugia",
    "acertijo_cirugia_correcto",
    "acertijo_hilera",
    "articulo_risa",
    "que_es_ciencia",
)


# ─── Pseudonimización ─────────────────────────────────────────────────────────

class SinConsentimientoError(Exception):
    """El estudiante no prestó consentimiento de investigación (research_id es NULL)."""


def pseudonimo(usuario) -> str:
    """Devuelve el pseudónimo estable del usuario como string hex (32 chars, sin guiones).

    Args:
        usuario: instancia de ``Usuario`` o PK (int). Si es int hace la query.

    Returns:
        Hex del ``research_id``, ej. ``"a3f1c2..."`` (32 caracteres).

    Raises:
        SinConsentimientoError: si el estudiante no tiene ``research_id``
            (consentimiento_investigacion != True).
    """
    if isinstance(usuario, int):
        from accounts.models import Usuario
        usuario = Usuario.objects.get(pk=usuario)
    if usuario.research_id is None:
        raise SinConsentimientoError(
            f"El usuario pk={usuario.pk} no tiene research_id "
            "(consentimiento_investigacion no es True)."
        )
    return usuario.research_id.hex


# ─── Transformaciones ────────────────────────────────────────────────────────

def _rango_edad(fecha_nac: "date | None") -> "str | None":
    """Convierte una fecha de nacimiento en tramo de 5 años.

    Ejemplos: ``date(2003, 6, 1)`` → ``"20-24"``, ``date(1998, 1, 15)`` → ``"25-29"``.
    Devuelve None para valores nulos o edades fuera del rango 15–80 (outliers).
    """
    if fecha_nac is None:
        return None
    hoy = date.today()
    edad = (
        hoy.year - fecha_nac.year
        - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))
    )
    if not (15 <= edad <= 80):
        return None
    tramo = (edad // 5) * 5
    return f"{tramo}-{tramo + 4}"


# ─── Serialización de filas ──────────────────────────────────────────────────

def encuesta_anonima(encuesta) -> dict:
    """Serializa una ``EncuestaEstudiante`` sin PII.

    Sustituye ``estudiante`` por ``pseudonimo`` y ``fecha_nacimiento`` por
    ``rango_edad``. El resto de campos se copia tal cual.

    Returns:
        dict con clave ``"pseudonimo"`` como primera columna, luego los campos
        de :data:`CAMPOS_ENCUESTA_EXPORT` y finalmente ``"rango_edad"``.
    """
    row: dict = {"pseudonimo": pseudonimo(encuesta.estudiante)}
    for campo in CAMPOS_ENCUESTA_EXPORT:
        row[campo] = getattr(encuesta, campo, None)
    row["rango_edad"] = _rango_edad(encuesta.fecha_nacimiento)
    return row


def intento_anonimo(intento) -> dict:
    """Serializa un ``Intento`` sin PII.

    Incluye datos suficientes para análisis de aprendizaje. Los timestamps se
    exportan como enteros Unix (segundos) para facilitar cálculos de intervalo
    sin exponer hora exacta en formatos legibles.

    Returns:
        dict con campos: pseudonimo, ejercicio_id, practica_comision_id,
        n_intento_en_ejercicio, es_correcto, timestamp_unix, error_categoria.
    """
    ts = intento.timestamp
    return {
        "pseudonimo": pseudonimo(intento.estudiante),
        "ejercicio_practica_id": intento.ejercicio_practica_id,
        "practica_comision_id": intento.practica_comision_id,
        "n_intento_en_ejercicio": _numero_intento(intento),
        "respuesta_raw": intento.respuesta_raw,
        "diccionario": intento.diccionario or None,
        "tabla_json": intento.tabla_json,
        "valores_verdad": intento.valores_verdad,
        "valor_verdad_estudiante": intento.valor_verdad_estudiante,
        "juicio_estudiante": intento.juicio_estudiante,
        "es_correcto": intento.es_correcto,
        "aprobado_docente": intento.aprobado_docente,
        "timestamp_unix": int(ts.timestamp()) if ts else None,
        "error_categoria": intento.error_categoria or None,
    }


def _numero_intento(intento) -> "int | None":
    """Ordinal del intento dentro de (estudiante, ejercicio_practica).

    Cuenta cuántos intentos anteriores (inclusive el actual) existen para el
    mismo par, ordenados por timestamp. Devuelve None si el timestamp es nulo.

    Nota: hace una query extra por intento; usar solo en exports batch donde
    el QS ya está prefetcheado o el volumen es acotado.
    """
    if intento.timestamp is None:
        return None
    from ejercicios.models import Intento
    return (
        Intento.objects
        .filter(
            estudiante_id=intento.estudiante_id,
            ejercicio_practica_id=intento.ejercicio_practica_id,
            timestamp__lte=intento.timestamp,
        )
        .count()
    )


# ─── Headers de exportación ──────────────────────────────────────────────────

HEADERS_ENCUESTA: tuple[str, ...] = (
    "pseudonimo", "comision_id", "anio", "cuatri",
) + CAMPOS_ENCUESTA_EXPORT + ("rango_edad",)

HEADERS_INTENTOS: tuple[str, ...] = (
    "pseudonimo", "comision_id",
    "ejercicio_practica_id", "n_intento",
    "respuesta_raw",
    "diccionario", "tabla_json", "valores_verdad",
    "valor_verdad_estudiante", "juicio_estudiante",
    "es_correcto", "aprobado_docente",
    "timestamp_unix", "error_categoria",
)



# ─── Datasets batch ───────────────────────────────────────────────────────────

def dataset_encuesta(comision_ids, anio=None, cuatri=None, *, cohorte_ids=None) -> list[dict]:
    """Genera el dataset de encuesta anonimizado para los filtros dados.

    Una fila por estudiante (primera inscripción en las comisiones incluidas).
    Solo estudiantes con ``consentimiento_investigacion=True`` y ``research_id``
    no nulo.

    Args:
        comision_ids: lista de IDs de comisión permitidos para el usuario.
        anio: filtrar por año de la cohorte (None = todos).
        cuatri: filtrar por cuatrimestre (1 o 2, None = ambos). Requiere anio.
        cohorte_ids: PKs de cohorte a incluir (None = todas). Alternativa
            moderna a anio/cuatri; si se pasan ambos, se aplican los dos.

    Returns:
        Lista de dicts con columnas :data:`HEADERS_ENCUESTA`.
    """
    from cursos.models import Inscripcion
    from accounts.models import EncuestaEstudiante

    qs_insc = (
        Inscripcion.objects
        .filter(
            comision_id__in=comision_ids,
            estudiante__consentimiento_investigacion=True,
            estudiante__research_id__isnull=False,
            estudiante__encuesta__isnull=False,
        )
        .select_related('estudiante', 'estudiante__encuesta', 'comision', 'cohorte')
        .order_by('estudiante_id', 'fecha_inscripcion', 'id')
    )
    if anio is not None:
        qs_insc = qs_insc.filter(cohorte__anio=anio)
        if cuatri is not None:
            qs_insc = qs_insc.filter(cohorte__cuatrimestre=cuatri)
    if cohorte_ids is not None:
        qs_insc = qs_insc.filter(cohorte_id__in=cohorte_ids)

    filas = []
    vistos = set()
    for insc in qs_insc:
        if insc.estudiante_id in vistos:
            continue
        vistos.add(insc.estudiante_id)
        anio_insc, cuatri_insc = insc.cohorte.anio, insc.cohorte.cuatrimestre
        enc = insc.estudiante.encuesta
        row = {
            "pseudonimo": insc.estudiante.research_id.hex,
            "comision_id": insc.comision_id,
            "anio": anio_insc,
            "cuatri": cuatri_insc,
        }
        for campo in CAMPOS_ENCUESTA_EXPORT:
            row[campo] = getattr(enc, campo, None)
        row["rango_edad"] = _rango_edad(enc.fecha_nacimiento)
        filas.append(row)
    return filas


def dataset_intentos(comision_ids, anio=None, cuatri=None, *, cohorte_ids=None) -> list[dict]:
    """Genera el dataset de intentos anonimizado para los filtros dados.

    Una fila por intento. Solo intentos de estudiantes con
    ``research_id`` no nulo.  ``n_intento`` se calcula en memoria (sin N+1).

    El join a comisión va por ``Inscripcion`` (no por ``practica_comision``) para
    incluir también intentos donde ``practica_comision`` es NULL (datos históricos).
    ``comision_id`` en la fila refleja ``practica_comision.comision_id`` si está
    disponible, o la comisión de inscripción del estudiante como fallback.

    Args:
        comision_ids: lista de IDs de comisión permitidos para el usuario.
        anio: filtrar por año de la cohorte de inscripción (None = todos).
        cuatri: filtrar por cuatrimestre (1 o 2, None = ambos). Requiere anio.
        cohorte_ids: PKs de cohorte a incluir (None = todas). Alternativa
            moderna a anio/cuatri; si se pasan ambos, se aplican los dos.

    Returns:
        Lista de dicts con columnas :data:`HEADERS_INTENTOS`.
    """
    from collections import defaultdict
    from ejercicios.models import Intento
    from cursos.models import Inscripcion

    cids = list(comision_ids)

    # Obtener estudiantes consentidos inscritos en las comisiones pedidas.
    insc_qs = (
        Inscripcion.objects
        .filter(
            comision_id__in=cids,
            estudiante__research_id__isnull=False,
            estudiante__consentimiento_investigacion=True,
        )
    )
    if anio is not None:
        insc_qs = insc_qs.filter(cohorte__anio=anio)
        if cuatri is not None:
            insc_qs = insc_qs.filter(cohorte__cuatrimestre=cuatri)
    if cohorte_ids is not None:
        insc_qs = insc_qs.filter(cohorte_id__in=cohorte_ids)

    # est_comision: estudiante_id → comision_id de su primera inscripción en cids
    # (fallback cuando practica_comision es NULL)
    est_comision: dict = {}
    for insc in insc_qs.order_by('fecha_inscripcion', 'id').values('estudiante_id', 'comision_id'):
        est_comision.setdefault(insc['estudiante_id'], insc['comision_id'])

    if not est_comision:
        return []

    from django.db.models import Q
    qs = (
        Intento.objects
        .filter(
            estudiante_id__in=est_comision,
            # Limitar a las comisiones pedidas: incluir intentos cuya
            # practica_comision pertenece a cids, O intentos sin practica_comision
            # (datos históricos; la comisión se infiere por inscripción).
        )
        .filter(
            Q(practica_comision__comision_id__in=cids)
            | Q(practica_comision__isnull=True)
        )
        .select_related('estudiante', 'practica_comision')
        .order_by('estudiante__research_id', 'ejercicio_practica_id', 'timestamp')
    )
    # Intento tiene FK directa a cohorte (NOT NULL): filtrar acá también, no
    # solo en Inscripcion, para no arrastrar intentos de otra camada de un
    # mismo estudiante recursante (misma comisión, distinto anio/cuatri).
    if anio is not None:
        qs = qs.filter(cohorte__anio=anio)
        if cuatri is not None:
            qs = qs.filter(cohorte__cuatrimestre=cuatri)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)

    contadores: dict = defaultdict(int)
    filas = []
    for i in qs.iterator():
        rid = i.estudiante.research_id
        key = (rid, i.ejercicio_practica_id)
        contadores[key] += 1
        ts = i.timestamp
        comision_id = (
            i.practica_comision.comision_id
            if i.practica_comision_id
            else est_comision.get(i.estudiante_id)
        )
        filas.append({
            "pseudonimo": rid.hex,
            "comision_id": comision_id,
            "ejercicio_practica_id": i.ejercicio_practica_id,
            "n_intento": contadores[key],
            "respuesta_raw": i.respuesta_raw,
            "diccionario": i.diccionario or None,
            "tabla_json": i.tabla_json,
            "valores_verdad": i.valores_verdad,
            "valor_verdad_estudiante": i.valor_verdad_estudiante,
            "juicio_estudiante": i.juicio_estudiante,
            "es_correcto": i.es_correcto,
            "aprobado_docente": i.aprobado_docente,
            "timestamp_unix": int(ts.timestamp()) if ts else None,
            "error_categoria": i.error_categoria or None,
        })
    return filas


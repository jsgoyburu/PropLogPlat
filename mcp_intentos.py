"""Servidor MCP de solo lectura para acceso de Claude a la base de datos de intentos.

Expone herramientas de consulta sobre los modelos Intento, Ejercicio, Practica
y Comision de IPC-Lógica. No realiza ninguna escritura.

Herramientas disponibles
------------------------
Navegación:
  listar_comisiones, listar_cohortes, listar_practicas, listar_ejercicios,
  obtener_ejercicio, obtener_intento

Intentos:
  listar_intentos, intentos_por_estudiante, buscar_respuesta

Análisis existentes:
  analizar_errores_ejercicio, errores_compartidos,
  estadisticas_comision, categorias_error_resumen

Métricas avanzadas (M1–M6):
  clasificar_error_formula       — M1: clasifica semánticamente el error de una fórmula
  matriz_juicio_computo          — M2: matriz 2×2 juicio×cómputo (tabla_verdad)
  convergencia_por_ejercicio     — M3: perfiles de convergencia semántica (formalización)
  perfil_error_tabla             — M4: errores por tipo de columna (tabla_verdad)
  indice_atomizacion             — M5: variables usadas vs. solución (formalización)
  patron_baja_variacion          — M6: señal de baja variación entre intentos

Métricas de investigación (encuesta):
  correlaciones_encuesta         — correlaciones Pearson/Spearman/η² entre onboarding y rendimiento
  red_errores                    — grafo de co-ocurrencia de categorías de error
  trabajo_vs_nota_logica         — esfuerzo en plataforma vs. nota de lógica del 1er parcial
  nube_ciencia                   — frecuencia de palabras en "¿qué es la ciencia?"
  distribuciones_encuesta_detalle — distribuciones por pregunta de la encuesta inicial
  perfiles_encuesta_onboarding   — dataset base anonimizado onboarding + desempeño

Métricas pedagógicas (research):
  tasa_entrada_efectiva          — proporción de estudiantes que realizó ≥1 intento por práctica
  demora_primer_intento          — días entre apertura y primer intento por estudiante
  persistencia_relativa          — re-intentos tras primer fallo por ejercicio
  intentos_hasta_correcto_sin_sesgo — distribución de intentos hasta resolver (incl. quienes no resolvieron)
  desacople_docente_maquina      — tasa de desacople corrección automática vs. juicio docente
  desacople_por_tipo             — desacople desagregado por tipo de ejercicio
  tasa_abandono_local            — estudiantes que intentaron un ejercicio pero nunca lo resolvieron
  indice_pared                   — ejercicios que actúan estructuralmente como pared en una práctica
  errores_compartidos_semanticos — respuestas incorrectas agrupadas por equivalencia semántica

Distribuciones onboarding:
  distribucion_nse_onboarding        — distribución por nivel socioeconómico
  distribucion_puntaje_logicas       — distribución por puntaje en acertijos lógicos
  distribucion_pandemia_onboarding   — distribución por clasificación pandemia
  distribucion_facultad_onboarding   — distribución por facultad
  distribucion_carrera_onboarding    — distribución por carrera
  cohortes_onboarding                — distribución por cohorte (año + cuatrimestre)
  cohortes_nse_onboarding            — cohorte × NSE
  cohortes_pandemia_onboarding       — cohorte × pandemia
  desempeno_por_nse_onboarding       — NSE × desempeño en ejercicios
  desempeno_por_pandemia_onboarding  — pandemia × desempeño
  desempeno_por_puntaje_logicas      — puntaje acertijos × desempeño

Todas las herramientas tienen un wrapper ``*_compat`` con firma (args, kwargs)
para compatibilidad con conectores que envuelven parámetros.

Todas las herramientas analíticas aceptan ``comision_ids`` y ``cohorte_ids``
(listas de PK; None = todas). ``comision_id`` singular sigue funcionando como
alias. Los IDs salen de ``listar_comisiones`` y ``listar_cohortes``.

Configurar en .claude/settings.json bajo la clave mcpServers.
Para uso local con SQLite no se requiere DATABASE_URL; alcanza con SECRET_KEY.
"""

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "logica_ipc.settings")
# Clave mínima para que Django inicie en modo MCP/desarrollo.
# En producción, apuntar la variable de entorno SECRET_KEY al valor real.
os.environ.setdefault("SECRET_KEY", "mcp-readonly-dev-key-not-for-production")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()

from typing import Optional, Any
from functools import wraps
from asgiref.sync import sync_to_async
from mcp.server.fastmcp import FastMCP

_http_mode = os.environ.get("MCP_TRANSPORT") == "http"
_issuer_url = os.environ.get("MCP_ISSUER_URL", "")
_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
_railway_env = os.environ.get("RAILWAY_ENVIRONMENT", "").strip()

if _http_mode and _issuer_url:
    from mcp_auth import IPCOAuthProvider as _OAuthProvider
    from mcp.server.auth.settings import (
        AuthSettings as _AuthSettings,
        ClientRegistrationOptions as _ClientRegOptions,
    )
    mcp = FastMCP(
        "IPC-Lógica — Intentos",
        auth_server_provider=_OAuthProvider(),
        auth=_AuthSettings(
            issuer_url=_issuer_url,
            resource_server_url=_issuer_url,
            client_registration_options=_ClientRegOptions(
                enabled=False,
            ),
        ),
    )
else:
    mcp = FastMCP("IPC-Lógica — Intentos")


if _http_mode:
    # Railway expone el servicio bajo un dominio público y FastMCP habilita
    # protección anti DNS rebinding por defecto (solo localhost). Agregamos
    # el dominio desplegado para aceptar Host/Origin válidos en producción.
    if _railway_domain:
        mcp.settings.transport_security.allowed_hosts.append(f"{_railway_domain}:*")
        mcp.settings.transport_security.allowed_origins.extend(
            [
                f"https://{_railway_domain}",
                f"http://{_railway_domain}",
                f"https://{_railway_domain}:*",
                f"http://{_railway_domain}:*",
            ]
        )
    # En Railway puede haber reescrituras/proxies intermedios que cambian Host/Origin
    # y disparan 421 aun con allowlist. En ese entorno desactivamos esta protección
    # específica y delegamos validación al borde de Railway.
    if _railway_env:
        mcp.settings.transport_security.enable_dns_rebinding_protection = False




def db_tool():
    """Registra una herramienta MCP ejecutando su cuerpo sync en un thread seguro para Django ORM."""

    def _decorator(func):
        @wraps(func)
        async def _wrapper(*args, **kwargs):
            return await sync_to_async(func, thread_sensitive=True)(*args, **kwargs)
        return mcp.tool()(_wrapper)

    return _decorator

# ──────────────────────────────────────────────
#  Helpers internos
# ──────────────────────────────────────────────

def _correcto_efectivo(es_correcto: bool, aprobado_docente) -> bool:
    if aprobado_docente is not None:
        return bool(aprobado_docente)
    return bool(es_correcto)


def _normalizar_comisiones(comision_id, comision_ids):
    """Unifica el alias singular ``comision_id`` con el plural ``comision_ids``.

    El plural es la forma canónica; el singular sobrevive porque hay prompts y
    clientes MCP guardados que lo usan. Devuelve ``None`` cuando no se pidió
    ninguna comisión, que en todo el servidor significa "todas".
    """
    if comision_ids:
        return list(comision_ids)
    if comision_id is not None:
        return [comision_id]
    return None


def _comisiones_o_todas(comision_id, comision_ids):
    """Como ``_normalizar_comisiones``, pero materializa "todas" en una lista.

    Las funciones de ``analiticas.calculos`` filtran con ``__in`` y no
    interpretan ``None``, a diferencia de las de ``analiticas.research``.
    """
    ids = _normalizar_comisiones(comision_id, comision_ids)
    if ids is not None:
        return ids
    from cursos.models import Comision
    return list(Comision.objects.values_list('id', flat=True))


def _pid(usuario) -> str:
    """Pseudónimo del usuario para el MCP. Nunca expone username, email ni ninguna PII.

    Devuelve el hex del research_id si el estudiante consintió investigación,
    o la cadena literal '[sin-consentimiento]' como señal defensiva.
    """
    rid = usuario.research_id
    return rid.hex if rid is not None else "[sin-consentimiento]"


# ──────────────────────────────────────────────
#  Herramientas de listado / navegación
# ──────────────────────────────────────────────

def _listar_comisiones_impl() -> list[dict]:
    """Lista todas las comisiones disponibles con su ID y nombre.

    Usar los IDs devueltos para filtrar otras herramientas.
    """
    from cursos.models import Comision
    return [
        {"id": str(r["id"]), "nombre": r["nombre"]}
        for r in Comision.objects.values("id", "nombre").order_by("nombre")
    ]


@mcp.tool()
async def listar_comisiones() -> list[dict]:
    """Lista todas las comisiones disponibles con su ID y nombre.

    Usar los IDs devueltos para filtrar otras herramientas.
    """
    return await sync_to_async(_listar_comisiones_impl, thread_sensitive=True)()


@db_tool()
def listar_cohortes() -> list[dict]:
    """Lista las cohortes (camadas) con su ID, año, cuatrimestre y si está en curso.

    Usar los IDs devueltos en el parámetro ``cohorte_ids`` de las demás
    herramientas para comparar camadas entre sí en vez de mezclarlas.

    Una cohorte es la camada de pertenencia de un estudiante, no un rango de
    fechas: quien cursó en 2026-C1 y siguió practicando en septiembre para
    rendir el final sigue perteneciendo a 2026-C1.
    """
    from cursos.models import Cohorte
    return [
        {
            "id": c.pk,
            "anio": c.anio,
            "cuatrimestre": c.cuatrimestre,
            "label": f"{c.anio} – C{c.cuatrimestre}",
            "activa": c.activa,
        }
        for c in Cohorte.objects.order_by("-anio", "-cuatrimestre")
    ]


@db_tool()
def listar_practicas(comision_id: Optional[int] = None) -> list[dict]:
    """Lista las prácticas. Si se pasa comision_id, devuelve solo las de esa comisión."""
    from ejercicios.models import Practica, PracticaComision
    if comision_id is not None:
        pcs = PracticaComision.objects.filter(comision_id=comision_id).select_related("practica").order_by("orden")
        return [
            {"practica_id": pc.practica_id, "titulo": pc.practica.titulo, "orden": pc.orden}
            for pc in pcs
        ]
    return [
            {"id": str(r["id"]), "titulo": r["titulo"]}
            for r in Practica.objects.values("id", "titulo").order_by("titulo")
        ]


@db_tool()
def listar_ejercicios(practica_id: Optional[int] = None) -> list[dict]:
    """Lista ejercicios. Si se pasa practica_id, devuelve los de esa práctica en orden."""
    from ejercicios.models import Ejercicio, EjercicioPractica
    if practica_id is not None:
        eps = (
            EjercicioPractica.objects
            .filter(practica_id=practica_id)
            .select_related("ejercicio")
            .order_by("orden")
        )
        return [
            {
                "ejercicio_id": ep.ejercicio_id,
                "orden": ep.orden,
                "tipo": ep.ejercicio.tipo,
                "enunciado": ep.ejercicio.enunciado[:150],
                "formula_solucion": ep.ejercicio.formula_solucion,
            }
            for ep in eps
        ]
    return [
        {"id": str(r["id"]), "tipo": r["tipo"], "formula_solucion": r["formula_solucion"]}
        for r in Ejercicio.objects.values("id", "tipo", "formula_solucion").order_by("id")[:100]
    ]


def _obtener_ejercicio_impl(ejercicio_id: int) -> dict:
    """Devuelve la definición completa de un ejercicio: enunciado, fórmula solución,
    tipo, diccionario de variables de la solución, y en qué prácticas aparece.

    Indispensable para interpretar los intentos de los estudiantes: sin conocer la
    fórmula solución y el diccionario de variables no se puede evaluar la calidad
    de una respuesta incorrecta.
    """
    from ejercicios.models import Ejercicio, EjercicioPractica

    try:
        ej = Ejercicio.objects.get(id=ejercicio_id)
    except Ejercicio.DoesNotExist:
        raise ValueError(f"No existe el ejercicio {ejercicio_id}")

    apariciones = list(
        EjercicioPractica.objects
        .filter(ejercicio_id=ejercicio_id)
        .select_related("practica")
        .values("practica__titulo", "orden")
        .order_by("practica__titulo", "orden")
    )

    return {
        "id": str(ej.id),
        "tipo": ej.tipo,
        "enunciado": ej.enunciado,
        "formula_solucion": ej.formula_solucion,
        "diccionario_solucion": ej.diccionario_solucion,
        "valores_verdad_solucion": ej.valores_verdad_solucion,
        "es_publico": ej.es_publico,
        "fecha_creacion": ej.fecha_creacion.isoformat(),
        "aparece_en_practicas": [
            {"practica": a["practica__titulo"], "orden": a["orden"]}
            for a in apariciones
        ],
    }


@mcp.tool()
async def obtener_ejercicio(ejercicio_id: int) -> dict:
    """Devuelve la definición completa de un ejercicio: enunciado, fórmula solución,
    tipo, diccionario de variables de la solución, y en qué prácticas aparece.

    Indispensable para interpretar los intentos de los estudiantes: sin conocer la
    fórmula solución y el diccionario de variables no se puede evaluar la calidad
    de una respuesta incorrecta.
    """
    return await sync_to_async(_obtener_ejercicio_impl, thread_sensitive=True)(
        ejercicio_id=ejercicio_id
    )


# ──────────────────────────────────────────────
#  Herramientas de intentos
# ──────────────────────────────────────────────

def _listar_intentos_impl(
    comision_id: Optional[int] = None,
    ejercicio_id: Optional[int] = None,
    solo_incorrectos: bool = False,
    limit: int = 50,
    offset: int = 0,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Lista intentos recientes con filtros opcionales.

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        ejercicio_id: filtra por ejercicio (opcional).
        solo_incorrectos: si True, excluye los intentos correctos.
        limit: máximo de resultados (default 50, máximo 500).
        offset: desplazamiento para paginación (default 0).
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con id, estudiante, ejercicio, práctica, comisión,
        respuesta_raw, es_correcto, aprobado_docente, error_categoria, timestamp,
        diccionario.
    """
    from ejercicios.models import Intento
    from ejercicios.correctitud import Q_INCORRECTO

    if limit <= 0:
        raise ValueError("limit debe ser > 0")
    if offset < 0:
        raise ValueError("offset debe ser >= 0")
    limit = min(limit, 500)
    qs = (
        Intento.objects
        .select_related(
            "estudiante",
            "ejercicio_practica__ejercicio",
            "ejercicio_practica__practica",
            "practica_comision__comision",
        )
        .filter(estudiante__research_id__isnull=False)
        .order_by("-timestamp", "-id")
    )
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)
    if ejercicio_id is not None:
        qs = qs.filter(ejercicio_practica__ejercicio_id=ejercicio_id)
    if solo_incorrectos:
        qs = qs.filter(Q_INCORRECTO)

    resultado = []
    for i in qs[offset:offset + limit]:
        resultado.append({
            "id": str(i.id),
            "estudiante": _pid(i.estudiante),
            "ejercicio_id": i.ejercicio_practica.ejercicio_id,
            "ejercicio_enunciado": i.ejercicio_practica.ejercicio.enunciado[:150],
            "practica": i.ejercicio_practica.practica.titulo,
            "comision": i.practica_comision.comision.nombre if i.practica_comision else None,
            "respuesta_raw": i.respuesta_raw,
            "es_correcto": i.es_correcto,
            "aprobado_docente": i.aprobado_docente,
            "error_categoria": i.error_categoria,
            "timestamp": i.timestamp.isoformat(),
            "diccionario": i.diccionario,
        })
    return resultado


@mcp.tool()
async def listar_intentos(
    comision_id: Optional[int] = None,
    ejercicio_id: Optional[int] = None,
    solo_incorrectos: bool = False,
    limit: int = 50,
    offset: int = 0,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Lista intentos recientes con filtros opcionales y paginación por offset.

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        ejercicio_id: filtra por ejercicio (opcional).
        solo_incorrectos: si True, excluye los intentos correctos.
        limit: máximo de resultados (default 50, máximo 500).
        offset: desplazamiento para paginación (default 0).
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    return await sync_to_async(_listar_intentos_impl, thread_sensitive=True)(
        comision_id=comision_id,
        ejercicio_id=ejercicio_id,
        solo_incorrectos=solo_incorrectos,
        limit=limit,
        offset=offset,
        comision_ids=comision_ids,
        cohorte_ids=cohorte_ids,
    )


def _obtener_intento_impl(intento_id: int) -> dict:
    """Devuelve el detalle completo de un intento: fórmula solución, tabla, diccionario, etc.

    Útil para analizar en profundidad un intento específico.
    """
    from ejercicios.models import Intento
    from django.http import Http404

    try:
        i = (
            Intento.objects
            .select_related(
                "estudiante",
                "ejercicio_practica__ejercicio",
                "ejercicio_practica__practica",
                "practica_comision__comision",
            )
            .get(id=intento_id)
        )
    except Intento.DoesNotExist:
        raise ValueError(f"No existe el intento {intento_id}")

    ej = i.ejercicio_practica.ejercicio
    return {
        "id": str(i.id),
        "estudiante": _pid(i.estudiante),
        "ejercicio_id": ej.id,
        "ejercicio_tipo": ej.tipo,
        "ejercicio_enunciado": ej.enunciado,
        "formula_solucion": ej.formula_solucion,
        "diccionario_solucion": ej.diccionario_solucion,
        "practica": i.ejercicio_practica.practica.titulo,
        "comision": i.practica_comision.comision.nombre if i.practica_comision else None,
        "respuesta_raw": i.respuesta_raw,
        "es_correcto": i.es_correcto,
        "aprobado_docente": i.aprobado_docente,
        "comentario_docente": i.comentario_docente,
        "error_categoria": i.error_categoria,
        "diccionario": i.diccionario,
        "tabla_json": i.tabla_json,
        "valores_verdad": i.valores_verdad,
        "valor_verdad_estudiante": i.valor_verdad_estudiante,
        "juicio_estudiante": i.juicio_estudiante,
        "timestamp": i.timestamp.isoformat(),
    }


@mcp.tool()
async def obtener_intento(intento_id: int) -> dict:
    """Devuelve el detalle completo de un intento: fórmula solución, tabla, diccionario, etc.

    Útil para analizar en profundidad un intento específico.
    """
    return await sync_to_async(_obtener_intento_impl, thread_sensitive=True)(
        intento_id=intento_id
    )


@db_tool()
def intentos_por_estudiante(
    pseudonimo: str,
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Lista el historial completo de intentos de un estudiante, ordenado cronológicamente.

    Permite ver su evolución: cuántos intentos por ejercicio, si avanzó, qué errores cometió.

    Args:
        pseudonimo: hex del research_id del estudiante (obtenido de listar_intentos).
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    import uuid as _uuid
    from ejercicios.models import Intento

    try:
        rid = _uuid.UUID(pseudonimo)
    except (ValueError, AttributeError):
        return []

    qs = (
        Intento.objects
        .filter(estudiante__research_id=rid)
        .select_related(
            "ejercicio_practica__ejercicio",
            "ejercicio_practica__practica",
            "practica_comision__comision",
        )
        .order_by("timestamp")
    )
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)

    resultado = []
    for i in qs[:200]:
        resultado.append({
            "id": str(i.id),
            "ejercicio_id": i.ejercicio_practica.ejercicio_id,
            "ejercicio_enunciado": i.ejercicio_practica.ejercicio.enunciado[:120],
            "practica": i.ejercicio_practica.practica.titulo,
            "comision": i.practica_comision.comision.nombre if i.practica_comision else None,
            "respuesta_raw": i.respuesta_raw,
            "es_correcto": i.es_correcto,
            "aprobado_docente": i.aprobado_docente,
            "error_categoria": i.error_categoria,
            "timestamp": i.timestamp.isoformat(),
        })
    return resultado


# ──────────────────────────────────────────────
#  Herramientas de análisis
# ──────────────────────────────────────────────

@db_tool()
def analizar_errores_ejercicio(
    ejercicio_id: int,
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Analiza los errores en un ejercicio específico.

    Devuelve tasa de error, las respuestas incorrectas más frecuentes y las
    categorías de error más comunes.  Útil para detectar conceptos mal comprendidos.

    Args:
        ejercicio_id: ID del ejercicio.
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    from ejercicios.models import Intento, Ejercicio
    from django.db.models import Count

    try:
        ejercicio = Ejercicio.objects.get(id=ejercicio_id)
    except Ejercicio.DoesNotExist:
        raise ValueError(f"No existe el ejercicio {ejercicio_id}")

    qs = Intento.objects.filter(ejercicio_practica__ejercicio_id=ejercicio_id)
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)

    from ejercicios.correctitud import Q_CORRECTO as _q_correcto
    from ejercicios.correctitud import Q_INCORRECTO as _q_incorrecto

    total = qs.count()
    incorrectos = qs.filter(_q_incorrecto).count()
    correctos = qs.filter(_q_correcto).count()

    respuestas_frecuentes = list(
        qs.filter(_q_incorrecto)
        .values("respuesta_raw")
        .annotate(n_intentos=Count("id"), n_estudiantes=Count("estudiante_id", distinct=True))
        .order_by("-n_estudiantes")[:10]
    )

    categorias = list(
        qs.filter(error_categoria__isnull=False)
        .values("error_categoria")
        .annotate(n=Count("id"))
        .order_by("-n")
    )

    return {
        "ejercicio_id": ejercicio_id,
        "enunciado": ejercicio.enunciado,
        "formula_solucion": ejercicio.formula_solucion,
        "tipo": ejercicio.tipo,
        "total_intentos": total,
        "correctos": correctos,
        "incorrectos": incorrectos,
        "tasa_error_pct": round(incorrectos / total * 100, 1) if total else None,
        "respuestas_incorrectas_frecuentes": respuestas_frecuentes,
        "categorias_error": categorias,
    }


@db_tool()
def errores_compartidos(
    comision_id: Optional[int] = None,
    min_estudiantes: int = 2,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Detecta respuestas incorrectas que varios estudiantes escribieron exactamente igual.

    Revela concepciones erróneas compartidas (no errores individuales aleatorios).

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        min_estudiantes: mínimo de estudiantes distintos con la misma respuesta incorrecta.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    from ejercicios.models import Intento
    from django.db.models import Count

    from ejercicios.correctitud import Q_INCORRECTO as _q_incorrecto

    qs = Intento.objects.filter(_q_incorrecto)
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)

    filas = list(
        qs.values(
            "ejercicio_practica__ejercicio__enunciado",
            "ejercicio_practica__ejercicio__tipo",
            "ejercicio_practica__practica__titulo",
            "respuesta_raw",
        )
        .annotate(n_estudiantes=Count("estudiante_id", distinct=True))
        .filter(n_estudiantes__gte=min_estudiantes)
        .order_by("-n_estudiantes")[:30]
    )

    return [
        {
            "enunciado": f["ejercicio_practica__ejercicio__enunciado"][:150],
            "tipo": f["ejercicio_practica__ejercicio__tipo"],
            "practica": f["ejercicio_practica__practica__titulo"],
            "respuesta_incorrecta": f["respuesta_raw"],
            "n_estudiantes": f["n_estudiantes"],
        }
        for f in filas
    ]


@db_tool()
def estadisticas_comision(
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Estadísticas generales: estudiantes, intentos, tasa de acierto y desglose por práctica.

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.

    Nota: desde que ``comision_id`` es opcional, llamarla sin comisión ya no
    es un error: devuelve el agregado de todas, como el resto del servidor.

    El campo ``comision`` del resultado es el nombre de la comisión SOLO
    cuando se pidió exactamente una (por cualquiera de los dos parámetros);
    con ninguna, dos o más comisiones (incluido el caso "todas") vale
    ``None``, porque ya no hay una única comisión que nombrar.
    """
    from ejercicios.models import Intento, Progreso, PracticaComision
    from cursos.models import Comision, Inscripcion
    from ejercicios.correctitud import Q_CORRECTO as _q_correcto

    _comisiones = _normalizar_comisiones(comision_id, comision_ids)

    comision_nombre = None
    if _comisiones is not None and len(_comisiones) == 1:
        comision_nombre = (
            Comision.objects
            .filter(id=_comisiones[0])
            .values_list("nombre", flat=True)
            .first()
        )

    pcs_qs = PracticaComision.objects.all()
    if _comisiones is not None:
        pcs_qs = pcs_qs.filter(comision_id__in=_comisiones)
    pcs = list(pcs_qs.values("id", "practica__titulo").order_by("orden"))
    pc_ids = [p["id"] for p in pcs]

    qs_intentos = Intento.objects.filter(practica_comision_id__in=pc_ids)
    if cohorte_ids is not None:
        qs_intentos = qs_intentos.filter(cohorte_id__in=cohorte_ids)

    total_intentos = qs_intentos.count()
    correctos_global = qs_intentos.filter(_q_correcto).count()

    # M2M vía Inscripcion: un recursante tiene una fila por cohorte en la
    # misma comisión; sin distinct() cuenta dos veces. "completaron" (más
    # abajo) ya usa distinct por el mismo motivo, así que este contador se
    # alinea con esa convención: estudiantes distintos de todas las camadas
    # de la(s) comisión(es).
    insc_qs = Inscripcion.objects.all()
    if _comisiones is not None:
        insc_qs = insc_qs.filter(comision_id__in=_comisiones)
    if cohorte_ids is not None:
        insc_qs = insc_qs.filter(cohorte_id__in=cohorte_ids)
    total_estudiantes = insc_qs.values('estudiante_id').distinct().count()

    completaron_qs = Progreso.objects.filter(
        practica_comision_id__in=pc_ids,
        ejercicio_practica_actual__isnull=True,
    )
    if cohorte_ids is not None:
        completaron_qs = completaron_qs.filter(cohorte_id__in=cohorte_ids)
    completaron = completaron_qs.values("estudiante_id").distinct().count()

    # Agregado en dos queries (no 2×N): antes ``comision_id`` era obligatorio
    # y ``pcs`` estaba acotado a una sola comisión; ahora que es opcional
    # ("todas" por default) este loop podía iterar cada PracticaComision de
    # la base emitiendo dos COUNT por vuelta. Mismo patrón que
    # analiticas.views.dashboard() (_qs_intentos.values(...).annotate(...)).
    from django.db.models import Count

    total_por_pc = {
        row["practica_comision_id"]: row["n"]
        for row in qs_intentos.values("practica_comision_id").annotate(n=Count("id"))
    }
    correctos_por_pc = {
        row["practica_comision_id"]: row["n"]
        for row in (
            qs_intentos.filter(_q_correcto)
            .values("practica_comision_id").annotate(n=Count("id"))
        )
    }
    practicas_stats = []
    for pc in pcs:
        n = total_por_pc.get(pc["id"], 0)
        c = correctos_por_pc.get(pc["id"], 0)
        practicas_stats.append({
            "practica": pc["practica__titulo"],
            "intentos": n,
            "correctos": c,
            "tasa_acierto_pct": round(c / n * 100, 1) if n else None,
        })

    return {
        "comision": comision_nombre,
        "total_estudiantes": total_estudiantes,
        "completaron_alguna_practica": completaron,
        "total_intentos": total_intentos,
        "tasa_acierto_global_pct": round(correctos_global / total_intentos * 100, 1) if total_intentos else None,
        "practicas": practicas_stats,
    }


@db_tool()
def buscar_respuesta(
    texto: str,
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Busca intentos cuya respuesta_raw contenga el texto dado (búsqueda parcial, ignora mayúsculas).

    Útil para encontrar todos los intentos donde los estudiantes usaron una
    fórmula o patrón específico.

    Args:
        texto: texto a buscar dentro de respuesta_raw (parcial, sin distinguir mayúsculas).
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    from ejercicios.models import Intento

    qs = (
        Intento.objects
        .filter(respuesta_raw__icontains=texto, estudiante__research_id__isnull=False)
        .select_related(
            "estudiante",
            "ejercicio_practica__ejercicio",
            "ejercicio_practica__practica",
        )
        .order_by("-timestamp", "-id")
    )
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)

    resultado = []
    for i in qs[:100]:
        resultado.append({
            "id": str(i.id),
            "estudiante": _pid(i.estudiante),
            "ejercicio_enunciado": i.ejercicio_practica.ejercicio.enunciado[:100],
            "practica": i.ejercicio_practica.practica.titulo,
            "respuesta_raw": i.respuesta_raw,
            "es_correcto": i.es_correcto,
            "aprobado_docente": i.aprobado_docente,
            "timestamp": i.timestamp.isoformat(),
        })
    return resultado


@db_tool()
def categorias_error_resumen(
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Devuelve un resumen de la distribución de categorías de error en todos los intentos incorrectos.

    Muestra cuántos intentos caen en cada categoría (polaridad, tautología,
    error parcial, etc.) para identificar el patrón de error dominante.

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    from ejercicios.models import Intento
    from django.db.models import Count

    from ejercicios.correctitud import Q_INCORRECTO as _q_incorrecto

    qs = Intento.objects.filter(_q_incorrecto)
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)

    total = qs.count()
    categorias = list(
        qs.values("error_categoria")
        .annotate(n=Count("id"))
        .order_by("-n")
    )

    for c in categorias:
        c["pct"] = round(c["n"] / total * 100, 1) if total else None
        c["categoria_label"] = c["error_categoria"] or "sin_clasificar"

    return categorias


# ──────────────────────────────────────────────
#  Métricas analíticas avanzadas (M1 – M6)
# ──────────────────────────────────────────────

@mcp.tool()
async def clasificar_error_formula(
    formula_estudiante: str,
    formula_solucion: str,
) -> dict:
    """Clasifica semánticamente el error de una fórmula de formalización.

    Compara la fórmula del estudiante contra la solución usando tablas de
    verdad (no matching sintáctico) y devuelve una categoría de la taxonomía:

    - ``tautologia``: la fórmula del estudiante es siempre verdadera.
    - ``contradiccion``: la fórmula del estudiante es siempre falsa.
    - ``polaridad``: misma tabla de verdad pero negada (distancia = n filas).
    - ``mas_fuerte``: la solución implica al estudiante pero no viceversa
      (la fórmula del estudiante es más restrictiva).
    - ``mas_debil``: el estudiante implica a la solución pero no viceversa
      (la fórmula del estudiante es más permisiva).
    - ``equivalente_alt``: semánticamente equivalente con variables renombradas.
    - ``error_parcial_1``: distancia semántica exactamente 1 fila.
    - ``error_parcial_2``: distancia semántica exactamente 2 filas.
    - ``error_sistemico``: distancia > mitad de las filas (error estructural).
    - ``variables_extra``: el estudiante usó más variables que la solución.
    - ``variables_menos``: el estudiante usó menos variables que la solución.
    - ``sin_clasificar``: no encaja en ninguna categoría (distancias intermedias
      o fórmula inválida). Ver ``ok`` y ``parse_error`` para distinguir ambos casos.

    Args:
        formula_estudiante: fórmula escrita por el estudiante (notación Copi
            o ASCII: ~, ·, ∨, ⊃, ≡ o -, &, |, ->, <->).
        formula_solucion: fórmula correcta del ejercicio.

    Returns:
        Dict con claves:
        - ``categoria`` (str): categoría de error.
        - ``ok`` (bool): True solo si ambas fórmulas parsearon correctamente.
        - ``parse_error`` (str, opcional): ``'formula_estudiante'`` o
          ``'formula_solucion'`` si una de las dos no pudo parsearse.
        - ``error`` (str, opcional): mensaje de excepción cuando ``ok`` es False.
    """
    from motor.parser import parsear as _parsear
    from motor.clasificador import clasificar_error as _clasificar

    def _run(f_est: str, f_sol: str) -> dict:
        try:
            _parsear(f_est)
        except Exception as exc:
            return {
                "categoria": "sin_clasificar", "ok": False,
                "parse_error": "formula_estudiante", "error": str(exc),
            }
        try:
            _parsear(f_sol)
        except Exception as exc:
            return {
                "categoria": "sin_clasificar", "ok": False,
                "parse_error": "formula_solucion", "error": str(exc),
            }
        return {"categoria": _clasificar(f_est, f_sol), "ok": True}

    return await sync_to_async(_run, thread_sensitive=False)(
        formula_estudiante, formula_solucion
    )


@db_tool()
def matriz_juicio_computo(
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Matriz 2×2 juicio × cómputo para ejercicios de tabla_verdad.

    Para cada intento de tipo tabla_verdad con juicio_estudiante registrado,
    determina si el estudiante acertó en el juicio (correcto/incorrecto) y en
    el cómputo (llenar bien la tabla). Devuelve los cuatro cuadrantes:

    - ``comprension_plena``: juicio ✓ y tabla ✓.
    - ``comprende_no_computa``: juicio ✓ pero tabla ✗.
    - ``computa_no_comprende``: tabla ✓ pero juicio ✗.
    - ``doble_obstaculo``: juicio ✗ y tabla ✗.

    Cada celda tiene ``count`` (cantidad de intentos) y ``pct`` (porcentaje
    sobre el total de intentos con juicio registrado).

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con ``celdas`` (4 cuadrantes) y ``total`` (base del análisis).
    """
    from analiticas.calculos import _matriz_juicio_computo
    return _matriz_juicio_computo(
        _comisiones_o_todas(comision_id, comision_ids),
        cohorte_ids=cohorte_ids,
    )


@db_tool()
def convergencia_por_ejercicio(
    ejercicio_id: int,
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Perfiles de convergencia semántica para un ejercicio de formalización.

    Para cada estudiante que intentó el ejercicio, calcula la secuencia de
    distancias semánticas intento a intento (filas de tabla de verdad donde
    difiere de la solución) y clasifica el recorrido en un perfil:

    - ``directo``: resuelto en el primer intento.
    - ``convergente``: distancias estrictamente decrecientes hasta 0.
    - ``plateau``: 3+ intentos consecutivos con la misma distancia > 0.
    - ``oscilante``: sube y baja sin patrón claro.
    - ``pendiente``: aún no resuelto.

    Solo aplica a ejercicios de tipo ``formalizacion``.

    Args:
        ejercicio_id: ID del ejercicio (obtener con ``listar_ejercicios``).
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con ``perfiles`` ({nombre: count}),
        ``distancia_primer_intento`` (promedio de la distancia en el 1er intento),
        ``total_estudiantes``.
    """
    from analiticas.calculos import _convergencia_por_ejercicio
    return _convergencia_por_ejercicio(
        _comisiones_o_todas(comision_id, comision_ids),
        ejercicio_id,
        cohorte_ids=cohorte_ids,
    )


@db_tool()
def perfil_error_tabla(
    ejercicio_id: int,
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Descomposición de errores en tabla_verdad por tipo de columna.

    Para cada intento incorrecto de tipo tabla_verdad, compara celda a celda
    la respuesta del estudiante contra la tabla canónica generada por el motor.
    Clasifica los errores según el tipo de subfórmula de la columna:

    - ``atomica``: variables sueltas (p, q, r…).
    - ``negacion``: fórmulas del tipo ~p.
    - ``conjuncion``, ``disyuncion``, ``condicional``: operadores principales.
    - ``verdad_vacua``: fila de condicional con antecedente F (debería ser V).
    - ``compuesto``: fórmulas más complejas.

    Incluye también ``verdad_vacua_count`` / ``verdad_vacua_pct`` (estudiantes
    que sistemáticamente fallan la ley del condicional con antecedente falso)
    y ``consistencia_promedio`` [0,1] (qué tan consistente es el error del
    estudiante dentro del mismo tipo de columna).

    Solo aplica a ejercicios de tipo ``tabla_verdad``.

    Args:
        ejercicio_id: ID del ejercicio.
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con ``tasa_error_por_columna``, ``verdad_vacua_count``,
        ``verdad_vacua_pct``, ``consistencia_promedio``,
        ``total_intentos_incorrectos``.
    """
    from analiticas.calculos import _perfil_error_tabla
    return _perfil_error_tabla(
        _comisiones_o_todas(comision_id, comision_ids),
        ejercicio_id,
        cohorte_ids=cohorte_ids,
    )


@db_tool()
def indice_atomizacion(
    ejercicio_id: int,
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Distribución de variables usadas vs. variables en la solución (formalización).

    Para cada estudiante toma su primer intento correcto o, si no resolvió,
    su último intento. Compara cuántas variables usó frente al número de
    variables de la solución canónica.

    Detecta:
    - ``sub_atomizacion``: usó menos variables (posible colapso de variables
      o pérdida de una distinción conceptual).
    - ``sobre_atomizacion``: usó más variables (posible doble conteo o
      variables auxiliares innecesarias).
    - ``correcta_con_error``: usó el número correcto de variables pero la
      fórmula es incorrecta (el error es estructural, no de vocabulario).

    Solo aplica a ejercicios de tipo ``formalizacion``.

    Args:
        ejercicio_id: ID del ejercicio.
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con ``n_solucion``, ``distribucion`` ({k_vars: count}),
        ``sub_atomizacion``, ``sobre_atomizacion``, ``correcta_con_error``,
        ``total_estudiantes``.
    """
    from analiticas.calculos import _indice_atomizacion
    return _indice_atomizacion(
        _comisiones_o_todas(comision_id, comision_ids),
        ejercicio_id,
        cohorte_ids=cohorte_ids,
    )


@db_tool()
def patron_baja_variacion(
    comision_id: Optional[int] = None,
    min_intentos: int = 5,
    max_intervalo_seg: int = 30,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Identifica pares (estudiante, ejercicio) con señal de baja variación entre intentos.

    Activa la señal cuando se cumplen los tres criterios simultáneamente:
    1. ≥ ``min_intentos`` intentos en el mismo ejercicio.
    2. Intervalo promedio entre intentos consecutivos < ``max_intervalo_seg`` segundos.
    3. No hay secuencia de distancias semánticas decrecientes (sin convergencia).

    Útil para detectar estudiantes que reenvían respuestas rápidamente sin
    reflexionar entre intento e intento. Solo incluye estudiantes con
    ``consentimiento_pedagogico=True``.

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        min_intentos: mínimo de intentos para activar la señal (default 5).
        max_intervalo_seg: intervalo promedio máximo en segundos (default 30).
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``username``, ``nombre``, ``enunciado_corto``,
        ``practica_titulo``, ``n_intentos``, ``intervalo_promedio_seg``,
        ``resolvio``. Ordenada por ``n_intentos`` descendente.
    """
    from analiticas.calculos import _patron_adivinacion
    return _patron_adivinacion(
        _comisiones_o_todas(comision_id, comision_ids),
        min_intentos=min_intentos,
        max_intervalo_seg=max_intervalo_seg,
        cohorte_ids=cohorte_ids,
    )


# ──────────────────────────────────────────────
#  Métricas de investigación (encuesta)
# ──────────────────────────────────────────────

@db_tool()
def correlaciones_encuesta(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Correlaciones entre respuestas del onboarding y rendimiento académico.

    Calcula Pearson r para variables numéricas/binarias, Spearman r para
    ordinales, y √η² para nominales. Solo incluye estudiantes que completaron
    la encuesta de onboarding. Filtra por consentimiento de investigación cuando
    ``solo_consentimiento=True`` (default).

    Args:
        comision_ids: lista de IDs de comisiones a incluir; None = todas.
        solo_consentimiento: si True, solo estudiantes con
            ``consentimiento_investigacion=True``.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts ordenada por |r| descendente, cada uno con:
        ``campo``, ``label``, ``tipo`` ('numerico'/'binario'/'ordinal'/'nominal'),
        ``r`` (coeficiente, None si N insuficiente), ``n`` (muestra),
        ``p_aprox`` (p-value aproximado o None), ``grupos`` (para nominales).
    """
    from analiticas.research import correlaciones_encuesta as _correlaciones_encuesta
    return _correlaciones_encuesta(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def red_errores(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> dict:
    """Grafo de co-ocurrencia de categorías de error entre intentos.

    Dos categorías de error co-ocurren cuando el mismo estudiante las comete
    al resolver el mismo ejercicio (par estudiante × ejercicio_practica).
    Útil para identificar qué tipos de error suelen aparecer juntos y pueden
    tener una raíz pedagógica común.

    Args:
        comision_ids: lista de IDs de comisiones a incluir; None = todas.
        solo_consentimiento: si True, solo estudiantes con
            ``consentimiento_investigacion=True``.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con tres claves:
        ``nodes``: lista de {id, label, count, grupo}  (count = pares en que aparece),
        ``links``: lista de {source, target, weight}    (weight = co-ocurrencias),
        ``n_pares``: total de pares (estudiante, ejercicio) analizados.
    """
    from analiticas.research import red_errores as _red_errores
    return _red_errores(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def trabajo_vs_nota_logica(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> dict:
    """Relaciona el esfuerzo en la plataforma con la nota de lógica del 1er parcial.

    Un punto por estudiante (consentido, con nota de lógica graduada). El eje X
    son indicadores de esfuerzo (intentos_totales, dias_activos,
    ejercicios_distintos, practicas_abiertas e indice_trabajo compuesto 0–100)
    medidos antes de la fecha del primer parcial; el eje Y es la nota de lógica.

    Args:
        comision_ids: lista de IDs de comisión; None = todas.
        solo_consentimiento: si True, solo consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con ``puntos``, ``correlaciones`` (r_pearson/r_spearman/n por
        indicador) y ``n``.
    """
    from analiticas.research import trabajo_vs_nota_logica as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


# ──────────────────────────────────────────────
#  Métricas pedagógicas (research)
# ──────────────────────────────────────────────

@db_tool()
def tasa_entrada_efectiva(
    comision_ids: list[int] | None = None,
    practica_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Proporción de estudiantes que realizó ≥1 intento en cada práctica.

    Args:
        comision_ids: comisiones a incluir; None = todas.
        practica_ids: prácticas a incluir; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``ep_id``, ``comision_id``, ``n_intentaron``,
        ``n_total``, ``tasa``.
    """
    from analiticas.research import tasa_entrada_efectiva as _f
    return _f(comision_ids=comision_ids, practica_ids=practica_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def demora_primer_intento(
    practica_id: int,
    comision_ids: list[int] | None = None,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Días entre la apertura de la práctica y el primer intento de cada estudiante.

    Args:
        practica_id: ID de la práctica (requerido).
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``estudiante_id``, ``username``, ``dias_demora``.
    """
    from analiticas.research import demora_primer_intento as _f
    return _f(practica_id, comision_ids=comision_ids, cohorte_ids=cohorte_ids)


@db_tool()
def persistencia_relativa(
    ep_ids: list[int] | None = None,
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Proporción de estudiantes que re-intentaron un ejercicio tras un primer fallo.

    Args:
        ep_ids: IDs de EjercicioPractica a incluir; None = todos.
        comision_ids: comisiones a incluir; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``ep_id``, ``comision_id``, ``n_reintentaron``,
        ``n_fallaron_alguna_vez``, ``tasa_persistencia``.
    """
    from analiticas.research import persistencia_relativa as _f
    return _f(ep_ids=ep_ids, comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def intentos_hasta_correcto_sin_sesgo(
    ep_ids: list[int] | None = None,
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de intentos hasta resolver, incluyendo estudiantes que no resolvieron.

    Args:
        ep_ids: IDs de EjercicioPractica; None = todos.
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``ep_id``, ``comision_id``, ``n_intentos``,
        ``resolvio``, ``username``.
    """
    from analiticas.research import intentos_hasta_correcto_sin_sesgo as _f
    return _f(ep_ids=ep_ids, comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def desacople_docente_maquina(
    comision_ids: list[int] | None = None,
    tipo_ejercicio: str | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> dict:
    """Tasa de desacople entre la corrección automática del motor y el juicio docente.

    Args:
        comision_ids: comisiones; None = todas.
        tipo_ejercicio: 'formalizacion', 'tabla_verdad', etc.; None = todos.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con ``n_total``, ``n_desacople``, ``tasa_desacople``,
        ``desacople_motor_ok_docente_no``, ``desacople_motor_no_docente_ok``.
    """
    from analiticas.research import desacople_docente_maquina as _f
    return _f(comision_ids=comision_ids, tipo_ejercicio=tipo_ejercicio, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def desacople_por_tipo(
    comision_ids: list[int] | None = None,
    cohorte_ids: list[int] | None = None,
) -> dict:
    """Desacople docente-máquina desagregado por tipo de ejercicio.

    Args:
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict keyed by tipo_ejercicio, cada valor con las mismas claves
        que ``desacople_docente_maquina``.
    """
    from analiticas.research import desacople_por_tipo as _f
    return _f(comision_ids=comision_ids, cohorte_ids=cohorte_ids)


@db_tool()
def tasa_abandono_local(
    ep_ids: list[int] | None = None,
    comision_ids: list[int] | None = None,
    solo_practicas_cerradas: bool = True,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Porcentaje de estudiantes que intentaron un ejercicio pero nunca lo resolvieron.

    Args:
        ep_ids: IDs de EjercicioPractica; None = todos.
        comision_ids: comisiones; None = todas.
        solo_practicas_cerradas: considerar solo prácticas con fecha_cierre pasada.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``ep_id``, ``comision_id``, ``n_intentaron``,
        ``n_sin_resolver``, ``tasa_abandono``.
    """
    from analiticas.research import tasa_abandono_local as _f
    return _f(ep_ids=ep_ids, comision_ids=comision_ids,
              solo_practicas_cerradas=solo_practicas_cerradas,
              solo_consentimiento=solo_consentimiento,
              cohorte_ids=cohorte_ids)


@db_tool()
def indice_pared(
    practica_id: int,
    comision_ids: list[int] | None = None,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Identifica qué ejercicios dentro de una práctica actúan estructuralmente como pared.

    Un ejercicio es 'pared' si concentra un abandono desproporcionado respecto
    al resto de la práctica.

    Args:
        practica_id: ID de la práctica (requerido).
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts por ejercicio con ``ep_id``, ``orden``, ``n_intentaron``,
        ``n_sin_resolver``, ``tasa_abandono``, ``es_pared``.
    """
    from analiticas.research import indice_pared as _f
    return _f(practica_id, comision_ids=comision_ids, cohorte_ids=cohorte_ids)


@db_tool()
def errores_compartidos_semanticos(
    ep_id: int,
    comision_ids: list[int] | None = None,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Agrupa respuestas incorrectas de un ejercicio por equivalencia semántica.

    Args:
        ep_id: ID de EjercicioPractica (requerido).
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``formula_canonica``, ``n_estudiantes``,
        ``ejemplos`` (lista de respuestas originales).
    """
    from analiticas.research import errores_compartidos_semanticos as _f
    return _f(ep_id, comision_ids=comision_ids, cohorte_ids=cohorte_ids)


# ──────────────────────────────────────────────
#  Distribuciones onboarding
# ──────────────────────────────────────────────

@db_tool()
def perfiles_encuesta_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Dataset base anonimizado con índices de onboarding y desempeño en ejercicios.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts por estudiante con puntaje_nse, puntaje_logicas,
        tasa_resolucion, rendimiento_con_ausentismo, y otros campos del onboarding.
    """
    from analiticas.research import perfiles_encuesta_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def distribucion_nse_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de estudiantes por categoría de nivel socioeconómico (NSE).

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``categoria_nse``, ``n``, ``porcentaje``.
    """
    from analiticas.research import distribucion_nse_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def distribucion_puntaje_logicas_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de estudiantes por puntaje en acertijos lógicos del onboarding (0-3).

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``puntaje_logicas``, ``n``, ``porcentaje``.
    """
    from analiticas.research import distribucion_puntaje_logicas as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def distribucion_pandemia_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de estudiantes por clasificación de pandemia en secundaria.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``clasificacion_pandemia``, ``n``, ``porcentaje``.
    """
    from analiticas.research import distribucion_pandemia_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def distribucion_facultad_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de estudiantes por facultad de inscripción.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``facultad``, ``n``, ``porcentaje``.
    """
    from analiticas.research import distribucion_facultad_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def distribucion_carrera_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de estudiantes por carrera.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``carrera``, ``n``, ``porcentaje``.
    """
    from analiticas.research import distribucion_carrera_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def cohortes_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de estudiantes por cohorte (año + cuatrimestre).

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``anio``, ``cuatrimestre``, ``n``, ``porcentaje``.
    """
    from analiticas.research import cohortes_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def cohortes_nse_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución cruzada cohorte × categoría NSE.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``anio``, ``cuatrimestre``, ``categoria_nse``, ``n``.
    """
    from analiticas.research import cohortes_nse_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def cohortes_pandemia_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución cruzada cohorte × clasificación pandemia.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``anio``, ``cuatrimestre``, ``clasificacion_pandemia``, ``n``.
    """
    from analiticas.research import cohortes_pandemia_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def desempeno_por_nse_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Cruza categoría NSE con desempeño observado en ejercicios.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``categoria_nse``, ``n``, ``media_rendimiento``,
        ``media_tasa_resolucion``.
    """
    from analiticas.research import desempeno_por_nse_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def desempeno_por_pandemia_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Cruza clasificación pandemia con desempeño observado en ejercicios.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``clasificacion_pandemia``, ``n``, ``media_rendimiento``,
        ``media_tasa_resolucion``.
    """
    from analiticas.research import desempeno_por_pandemia_onboarding as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def desempeno_por_puntaje_logicas(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Cruza puntaje en acertijos lógicos (0-3) con desempeño en ejercicios.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``puntaje_logicas``, ``n``, ``media_rendimiento``,
        ``media_tasa_resolucion``.
    """
    from analiticas.research import desempeno_por_puntaje_logicas as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, cohorte_ids=cohorte_ids)


@db_tool()
def distribuciones_encuesta_detalle(
    comision_ids: list[int] | None = None,
    cohorte_ids: list[int] | None = None,
) -> dict:
    """Distribuciones completas por pregunta de la encuesta de onboarding.

    Args:
        comision_ids: comisiones; None = todas.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Dict con una clave por campo de encuesta, cada valor es
        una lista de dicts con ``valor``, ``label``, ``n``, ``porcentaje``.
    """
    from analiticas.research import distribuciones_encuesta_detalle as _f
    return _f(comision_ids=comision_ids, cohorte_ids=cohorte_ids)


@db_tool()
def nube_ciencia(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    top_n: int = 80,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Frecuencia de palabras en las respuestas a '¿qué es la ciencia?' del onboarding.

    Filtra stopwords en español y palabras de menos de 3 caracteres.

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        top_n: máximo de palabras a devolver (default 80).
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``word`` y ``count``, ordenada por frecuencia desc.
    """
    from analiticas.research import nube_ciencia as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento, top_n=top_n, cohorte_ids=cohorte_ids)


# ──────────────────────────────────────────────
#  Wrappers de compatibilidad (args/kwargs)
# ──────────────────────────────────────────────

def _compat_kwargs(args: dict | None = None, kwargs: dict | None = None) -> dict:
    """Normaliza payloads estilo wrapper externo: {"args": {}, "kwargs": {...}}."""
    if args is not None and not isinstance(args, dict):
        raise ValueError("args debe ser un dict o None")
    if kwargs is not None and not isinstance(kwargs, dict):
        raise ValueError("kwargs debe ser un dict o None")

    normalizados: dict = {}
    if args:
        normalizados.update(args)
    if kwargs:
        normalizados.update(kwargs)
    return normalizados


@mcp.tool()
async def listar_comisiones_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    params = _compat_kwargs(args=args, kwargs=kwargs)
    return await sync_to_async(_listar_comisiones_impl, thread_sensitive=True)(**params)


@mcp.tool()
async def listar_cohortes_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await listar_cohortes(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def listar_practicas_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await listar_practicas(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def listar_ejercicios_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await listar_ejercicios(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def obtener_ejercicio_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    params = _compat_kwargs(args=args, kwargs=kwargs)
    return await sync_to_async(_obtener_ejercicio_impl, thread_sensitive=True)(**params)


@mcp.tool()
async def listar_intentos_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    params: dict[str, Any] = _compat_kwargs(args=args, kwargs=kwargs)
    return await sync_to_async(_listar_intentos_impl, thread_sensitive=True)(
        comision_id=params.get("comision_id"),
        ejercicio_id=params.get("ejercicio_id"),
        solo_incorrectos=params.get("solo_incorrectos", False),
        limit=params.get("limit", 50),
        offset=params.get("offset", 0),
        comision_ids=params.get("comision_ids"),
        cohorte_ids=params.get("cohorte_ids"),
    )


@mcp.tool()
async def obtener_intento_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    params = _compat_kwargs(args=args, kwargs=kwargs)
    return await sync_to_async(_obtener_intento_impl, thread_sensitive=True)(**params)


@mcp.tool()
async def intentos_por_estudiante_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await intentos_por_estudiante(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def analizar_errores_ejercicio_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await analizar_errores_ejercicio(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def errores_compartidos_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await errores_compartidos(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def estadisticas_comision_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await estadisticas_comision(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def buscar_respuesta_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await buscar_respuesta(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def categorias_error_resumen_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await categorias_error_resumen(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def clasificar_error_formula_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await clasificar_error_formula(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def matriz_juicio_computo_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await matriz_juicio_computo(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def convergencia_por_ejercicio_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await convergencia_por_ejercicio(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def perfil_error_tabla_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await perfil_error_tabla(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def indice_atomizacion_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await indice_atomizacion(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def patron_baja_variacion_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await patron_baja_variacion(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def correlaciones_encuesta_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await correlaciones_encuesta(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def red_errores_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await red_errores(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def trabajo_vs_nota_logica_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await trabajo_vs_nota_logica(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def tasa_entrada_efectiva_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await tasa_entrada_efectiva(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def demora_primer_intento_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await demora_primer_intento(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def persistencia_relativa_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await persistencia_relativa(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def intentos_hasta_correcto_sin_sesgo_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await intentos_hasta_correcto_sin_sesgo(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def desacople_docente_maquina_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await desacople_docente_maquina(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def desacople_por_tipo_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await desacople_por_tipo(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def tasa_abandono_local_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await tasa_abandono_local(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def indice_pared_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await indice_pared(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def errores_compartidos_semanticos_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await errores_compartidos_semanticos(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def perfiles_encuesta_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await perfiles_encuesta_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def distribucion_nse_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await distribucion_nse_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def distribucion_puntaje_logicas_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await distribucion_puntaje_logicas_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def distribucion_pandemia_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await distribucion_pandemia_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def distribucion_facultad_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await distribucion_facultad_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def distribucion_carrera_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await distribucion_carrera_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def cohortes_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await cohortes_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def cohortes_nse_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await cohortes_nse_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def cohortes_pandemia_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await cohortes_pandemia_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def desempeno_por_nse_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await desempeno_por_nse_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def desempeno_por_pandemia_onboarding_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await desempeno_por_pandemia_onboarding(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def desempeno_por_puntaje_logicas_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await desempeno_por_puntaje_logicas(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def distribuciones_encuesta_detalle_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await distribuciones_encuesta_detalle(**_compat_kwargs(args=args, kwargs=kwargs))


@mcp.tool()
async def nube_ciencia_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await nube_ciencia(**_compat_kwargs(args=args, kwargs=kwargs))


if _http_mode:
    from starlette.responses import PlainTextResponse
    from mcp_auth import login_handler

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request):
        return PlainTextResponse("ok")

    @mcp.custom_route("/login", methods=["GET", "POST"])
    async def _login(request):
        return await login_handler(request)


if __name__ == "__main__":
    if _http_mode:
        _port = int(os.environ.get("PORT", 8000))
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = _port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()

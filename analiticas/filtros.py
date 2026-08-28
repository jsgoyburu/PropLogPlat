"""Filtros compartidos de comisión y cohorte para las vistas de analíticas.

Único punto de resolución de permisos y parseo de querystring, usado por las
tres páginas de analíticas, sus exportaciones y sus endpoints JSON. Antes de
este módulo, el chequeo de "qué comisiones puede ver este usuario" estaba
duplicado literalmente en ``exportar``, ``descargar_investigacion`` y
``red_errores_json``.

Este módulo es exclusivamente web: el servidor MCP se autentica con un único
usuario admin (``MCP_ADMIN_USERNAME``) y no necesita scoping por docente.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.db.models import Q

from cursos.models import Cohorte, Comision


@dataclass(frozen=True)
class FiltroAnaliticas:
    """Resultado de resolver los filtros de una request de analíticas.

    Attributes:
        comision_ids: comisiones efectivas (selección ∩ permitidas, o todas
            las permitidas si no hubo selección).
        cohorte_ids: cohortes efectivas, o ``None`` = todas. Puede ser una
            lista vacía: eso significa que se pidió explícitamente un
            recorte por cohorte y nada sobrevivió (ID inexistente, o sin
            ninguna inscripción real) -- selección explícita vacía, no
            ausencia de filtro. Distinto de ``None``, que sí es "todas".
        comisiones: queryset de comisiones permitidas, para dibujar la barra.
        cohortes: opciones de cohorte disponibles (dicts id/anio/cuatri/label).
        qs: querystring canónico para pegar en los links de exportación.
        activo: si el usuario puso algún filtro explícito.
        seleccion_vacia: se pidió explícitamente un recorte (de comisión y/o
            de cohorte) y nada sobrevivió la validación. La página muestra
            estado vacío en vez de ampliar en silencio a "todas" -- que es
            precisamente la mentira silenciosa que este módulo existe para
            evitar. Antes se llamaba ``vacio_por_permisos`` y solo cubría el
            caso de comisión; ahora cubre también cohorte.
    """

    comision_ids: list
    cohorte_ids: list | None
    comisiones: object
    cohortes: list
    qs: str
    activo: bool
    seleccion_vacia: bool


def _parse_ids(raw):
    """``'1,2,x'`` → ``[1, 2]``. Descarta lo no numérico en vez de fallar.

    Un ID basura en la URL no debe tirar un 500 en un panel de lectura.
    """
    ids = []
    for parte in (raw or '').split(','):
        parte = parte.strip()
        if not parte:
            continue
        try:
            ids.append(int(parte))
        except ValueError:
            continue
    return ids


def _ids_de_request(get, clave):
    """Lee IDs de ``?clave=1,2`` y de ``?clave=1&clave=2`` indistintamente.

    La primera forma la usan los links de exportación; la segunda la produce
    un <form> con checkboxes homónimos, que es como se dibuja la barra.
    """
    valores = get.getlist(clave)
    ids = []
    for valor in valores:
        ids.extend(_parse_ids(valor))
    return ids


def _raw_valores(get, *claves):
    """Valores crudos (sin parsear) de la primera clave que tenga algo no vacío.

    Se usa para dos cosas relacionadas: (1) decidir si el usuario "pidió"
    algo -- computado ANTES de parsear los IDs, para no confundir "pedí un ID
    basura" con "no pedí nada" -- y (2) repetir ese pedido tal cual en el
    querystring de exportación, para que un pedido que resolvió vacío siga
    siendo un pedido (no-blanco) en el próximo viaje de ida y vuelta.
    """
    for clave in claves:
        valores = get.getlist(clave)
        if any(v.strip() for v in valores):
            return valores
    return []


def _parse_cohortes_legacy(valores):
    """``['2024-1']`` → PKs de cohorte. Formato viejo del bloque de descarga."""
    pares = []
    for valor in valores:
        try:
            anio_str, cuatri_str = str(valor).split('-')
            pares.append((int(anio_str), int(cuatri_str)))
        except (ValueError, AttributeError):
            continue
    if not pares:
        return []
    filtro = Q()
    for anio, cuatri in pares:
        filtro |= Q(anio=anio, cuatrimestre=cuatri)
    return list(Cohorte.objects.filter(filtro).values_list('id', flat=True))


def comisiones_permitidas(usuario):
    """Comisiones que este usuario puede ver: todas si es staff, las suyas si no."""
    if usuario.is_staff:
        return Comision.objects.all().order_by('nombre')
    return Comision.objects.filter(docentes=usuario).order_by('nombre')


def cohortes_disponibles(comision_ids):
    """Cohortes con al menos una inscripción en esas comisiones."""
    return [
        {
            'id': c.pk,
            'anio': c.anio,
            'cuatri': c.cuatrimestre,
            'label': f'{c.anio} – C{c.cuatrimestre}',
        }
        for c in Cohorte.objects
            .filter(inscripciones__comision_id__in=comision_ids)
            .distinct()
            .order_by('anio', 'cuatrimestre')
    ]


def resolver_filtros(request):
    """Resuelve permisos y filtros de una request de analíticas.

    Reglas:
        - Sin selección de comisiones → todas las permitidas.
        - Los IDs pedidos que no estén permitidos se descartan; si la
          selección queda vacía se marca ``seleccion_vacia`` en vez de
          ampliar a "todas", que mentiría sobre lo que se está viendo. Esto
          vale igual para comisión (ID ajeno, o ni siquiera parseable) que
          para cohorte (ID inexistente, o sin ninguna inscripción real): la
          regla es "¿pidió algo?", no "¿algo sobrevivió el parseo?" -- de lo
          contrario ``?comision_ids=abc`` (irreconocible) y
          ``?comision_ids=<id ajeno>`` (reconocible pero prohibido) caerían
          en resultados opuestos, cuando ambos son el mismo tipo de pedido
          inválido.
        - El querystring de exportación (``qs``) repite el pedido crudo, no
          solo el resultado post-filtro: si una selección vacía se
          describiera con un parámetro en blanco, releerlo la convertiría
          en "no pedí nada" y la ensancharía en silencio a "todas" en el
          próximo request (el link de descarga de la propia página).
        - Las opciones de cohorte se calculan sobre **todas** las comisiones
          permitidas, no sobre las tildadas, para que la lista sea estable
          sin recargar al tildar una comisión.
    """
    comisiones = comisiones_permitidas(request.user)
    permitidas = list(comisiones.values_list('id', flat=True))
    permitidas_set = set(permitidas)

    # Alias singular heredado de los endpoints JSON (?comision_id=3).
    raw_comision = _raw_valores(request.GET, 'comision_ids', 'comision_id')
    pidio_comisiones = bool(raw_comision)
    pedidas = _ids_de_request(request.GET, 'comision_ids')
    if not pedidas:
        pedidas = _ids_de_request(request.GET, 'comision_id')
    if pidio_comisiones:
        comision_ids = [c for c in pedidas if c in permitidas_set]
    else:
        comision_ids = list(permitidas)

    cohortes = cohortes_disponibles(permitidas)
    cohortes_validas = {c['id'] for c in cohortes}

    raw_cohorte = _raw_valores(request.GET, 'cohorte_ids')
    raw_cohorte_legacy = request.GET.getlist('cohorte')
    pidio_cohortes = bool(raw_cohorte) or any(v.strip() for v in raw_cohorte_legacy)
    pedidas_cohortes = _ids_de_request(request.GET, 'cohorte_ids')
    if not pedidas_cohortes:
        pedidas_cohortes = _parse_cohortes_legacy(raw_cohorte_legacy)
    if pidio_cohortes:
        cohorte_ids = [c for c in pedidas_cohortes if c in cohortes_validas]
    else:
        cohorte_ids = None

    if comision_ids:
        comision_ids_qs = ','.join(str(c) for c in comision_ids)
    elif pidio_comisiones:
        # Selección explícita vacía: repetir el pedido crudo (basura o
        # ajeno) para que no se blanquee en el querystring.
        comision_ids_qs = ','.join(v for v in raw_comision if v.strip())
    else:
        comision_ids_qs = ''
    params = {'comision_ids': comision_ids_qs}

    if cohorte_ids:
        params['cohorte_ids'] = ','.join(str(c) for c in cohorte_ids)
    elif pidio_cohortes:
        if raw_cohorte:
            params['cohorte_ids'] = ','.join(v for v in raw_cohorte if v.strip())
        else:
            params['cohorte_ids'] = ','.join(v for v in raw_cohorte_legacy if v.strip())

    seleccion_vacia = (
        (pidio_comisiones and not comision_ids)
        or (pidio_cohortes and not cohorte_ids)
    )

    return FiltroAnaliticas(
        comision_ids=comision_ids,
        cohorte_ids=cohorte_ids,
        comisiones=comisiones,
        cohortes=cohortes,
        qs=urlencode(params),
        activo=pidio_comisiones or pidio_cohortes,
        seleccion_vacia=seleccion_vacia,
    )

# Filtros por comisión y cohorte en analíticas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las tres páginas de analíticas, sus exportaciones, sus endpoints JSON y las 12 herramientas rezagadas del MCP acepten filtros multi-selección de comisión y cohorte.

**Architecture:** Un módulo nuevo `analiticas/filtros.py` resuelve permisos y parseo de querystring una sola vez para toda la web; un partial `_filtros.html` dibuja la misma barra en las 3 páginas. La capa de cálculo (`research.py`) ya acepta ambos filtros; `calculos.py`, los helpers del dashboard y `anonimizador.py` se ponen al día. El MCP no usa `filtros.py` (se autentica con un único admin, sin scoping por docente) pero sí recibe los mismos parámetros.

**Tech Stack:** Django, Alpine.js, FastMCP.

## Global Constraints

- Python: `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe` (venv en el directorio **padre** del repo).
- Tests requieren `SECRET_KEY` en el entorno: `$env:SECRET_KEY='x'` antes de `manage.py test`.
- **Baseline verificado el 2026-08-25: `manage.py test analiticas` → 100 tests, OK, ~370 s.** La suite completa es lenta: usar tests dirigidos por paso y la suite completa solo al cerrar cada tarea.
- Comando dirigido: `$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.<Clase>.<test> -v 2`
- Sin migraciones: ningún modelo cambia.
- Todo el código y los docstrings en español, siguiendo el estilo del repo.
- Los nombres de parámetros son exactamente `comision_ids` y `cohorte_ids` (plural, listas de PK). `comision_id` y `cohorte=YYYY-C` sobreviven solo como alias de compatibilidad.
- `cohorte_ids=None` significa **todas las cohortes**, nunca "ninguna". Idem `comision_ids=None` donde aplique.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `analiticas/filtros.py` **(nuevo)** | Permisos + parseo de querystring → `FiltroAnaliticas`. Único punto de verdad para la web. |
| `templates/analiticas/_filtros.html` **(nuevo)** | Barra de filtros compartida por las 3 páginas. |
| `analiticas/calculos.py` | M2–M6 pasan a multi-comisión + cohorte. |
| `analiticas/views.py` | Helpers del dashboard a `cohorte_ids`; las 3 vistas y los 4 endpoints consumen `resolver_filtros`. |
| `analiticas/anonimizador.py` | `dataset_encuesta` / `dataset_intentos` reciben `cohorte_ids`. |
| `mcp_intentos.py` | 12 herramientas reciben `comision_ids` + `cohorte_ids`. |
| `analiticas/tests.py` | Tests de todo lo anterior. |

Orden de dependencias: Task 1 (filtros) → Tasks 2-4 (capa de cálculo, independientes entre sí) → Tasks 5-8 (wiring web) → Tasks 9-10 (MCP).

---

## Task 1: Módulo `analiticas/filtros.py`

**Files:**
- Create: `analiticas/filtros.py`
- Test: `analiticas/tests.py` (agregar al final)

**Interfaces:**
- Consumes: `cursos.models.Comision`, `cursos.models.Cohorte`.
- Produces:
  - `FiltroAnaliticas` — dataclass con `comision_ids: list[int]`, `cohorte_ids: list[int] | None`, `comisiones: QuerySet`, `cohortes: list[dict]`, `qs: str`, `activo: bool`, `vacio_por_permisos: bool`.
  - `resolver_filtros(request) -> FiltroAnaliticas`
  - `comisiones_permitidas(usuario) -> QuerySet`
  - `cohortes_disponibles(comision_ids) -> list[dict]` — dicts con claves `id`, `anio`, `cuatri`, `label`.

- [ ] **Step 1: Write the failing tests**

Agregar al final de `analiticas/tests.py`:

```python
# ─── Tests: analiticas/filtros.py ────────────────────────────────────────────

from django.test import RequestFactory

from analiticas.filtros import cohortes_disponibles, comisiones_permitidas, resolver_filtros


class ResolverFiltrosTests(TestCase):
    """resolver_filtros es el único punto que decide qué puede ver cada usuario."""

    def setUp(self):
        self.factory = RequestFactory()
        self.com_a, _, _, _, _ = _setup_comision('FA', n_estudiantes=1)
        self.com_b, _, _, _, _ = _setup_comision('FB', n_estudiantes=1)
        self.docente_a = self.com_a.docentes.first()
        self.admin = _u('admin-filtros', is_staff=True)

    def _req(self, query='', usuario=None):
        request = self.factory.get(f'/analiticas/dashboard/?{query}')
        request.user = usuario or self.docente_a
        return request

    def test_docente_solo_ve_sus_comisiones(self):
        f = resolver_filtros(self._req())
        self.assertEqual(f.comision_ids, [self.com_a.id])

    def test_staff_ve_todas(self):
        f = resolver_filtros(self._req(usuario=self.admin))
        self.assertCountEqual(f.comision_ids, [self.com_a.id, self.com_b.id])

    def test_descarta_comision_ajena(self):
        f = resolver_filtros(self._req(f'comision_ids={self.com_a.id},{self.com_b.id}'))
        self.assertEqual(f.comision_ids, [self.com_a.id])

    def test_pedir_solo_comision_ajena_marca_vacio_por_permisos(self):
        f = resolver_filtros(self._req(f'comision_ids={self.com_b.id}'))
        self.assertEqual(f.comision_ids, [])
        self.assertTrue(f.vacio_por_permisos)

    def test_sin_seleccion_no_es_vacio_por_permisos(self):
        f = resolver_filtros(self._req())
        self.assertFalse(f.vacio_por_permisos)
        self.assertFalse(f.activo)

    def test_ids_basura_se_descartan_sin_romper(self):
        f = resolver_filtros(self._req(f'comision_ids=x,,{self.com_a.id}'))
        self.assertEqual(f.comision_ids, [self.com_a.id])

    def test_cohorte_ids_se_parsea(self):
        cohorte = _cohorte()
        f = resolver_filtros(self._req(f'cohorte_ids={cohorte.id}'))
        self.assertEqual(f.cohorte_ids, [cohorte.id])
        self.assertTrue(f.activo)

    def test_cohorte_alias_legacy_se_traduce_a_pk(self):
        cohorte = _cohorte()
        f = resolver_filtros(self._req('cohorte=2026-1'))
        self.assertEqual(f.cohorte_ids, [cohorte.id])

    def test_sin_cohorte_es_none_no_lista_vacia(self):
        f = resolver_filtros(self._req())
        self.assertIsNone(f.cohorte_ids)

    def test_cohorte_inexistente_se_descarta(self):
        f = resolver_filtros(self._req('cohorte_ids=99999'))
        self.assertIsNone(f.cohorte_ids)

    def test_qs_incluye_comisiones_y_cohorte(self):
        cohorte = _cohorte()
        f = resolver_filtros(self._req(f'cohorte_ids={cohorte.id}'))
        self.assertIn(f'comision_ids={self.com_a.id}', f.qs)
        self.assertIn(f'cohorte_ids={cohorte.id}', f.qs)

    def test_cohortes_disponibles_incluye_id(self):
        opciones = cohortes_disponibles([self.com_a.id])
        self.assertEqual(opciones[0]['id'], _cohorte().id)
        self.assertEqual(opciones[0]['label'], '2026 – C1')

    def test_comisiones_permitidas_ordena_por_nombre(self):
        nombres = list(comisiones_permitidas(self.admin).values_list('nombre', flat=True))
        self.assertEqual(nombres, sorted(nombres))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.ResolverFiltrosTests -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'analiticas.filtros'`

- [ ] **Step 3: Write the implementation**

Crear `analiticas/filtros.py`:

```python
"""Filtros compartidos de comisión y cohorte para las vistas de analíticas.

Único punto de resolución de permisos y parseo de querystring, usado por las
tres páginas de analíticas, sus exportaciones y sus endpoints JSON. Antes de
este módulo, el chequeo de "qué comisiones puede ver este usuario" estaba
duplicado literalmente en ``exportar``, ``descargar_investigacion`` y
``red_errores_json``.

Este módulo es exclusivamente web: el servidor MCP se autentica con un único
usuario admin (``MCP_ADMIN_USERNAME``) y no necesita scoping por docente.
"""

from dataclasses import dataclass, field
from urllib.parse import urlencode

from django.db.models import Q

from cursos.models import Cohorte, Comision


@dataclass(frozen=True)
class FiltroAnaliticas:
    """Resultado de resolver los filtros de una request de analíticas.

    Attributes:
        comision_ids: comisiones efectivas (selección ∩ permitidas, o todas
            las permitidas si no hubo selección).
        cohorte_ids: cohortes efectivas, o ``None`` = todas. Nunca lista vacía:
            una lista vacía significaría "ninguna" y no es un estado alcanzable.
        comisiones: queryset de comisiones permitidas, para dibujar la barra.
        cohortes: opciones de cohorte disponibles (dicts id/anio/cuatri/label).
        qs: querystring canónico para pegar en los links de exportación.
        activo: si el usuario puso algún filtro explícito.
        vacio_por_permisos: pidió comisiones y ninguna era suya. La página
            muestra estado vacío en vez de ampliar en silencio a "todas".
    """

    comision_ids: list
    cohorte_ids: list | None
    comisiones: object
    cohortes: list
    qs: str
    activo: bool
    vacio_por_permisos: bool


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
        - Los IDs pedidos que no estén permitidos se descartan en silencio;
          si la selección queda vacía se marca ``vacio_por_permisos`` en vez
          de ampliar a "todas", que mentiría sobre lo que se está viendo.
        - Las opciones de cohorte se calculan sobre **todas** las comisiones
          permitidas, no sobre las tildadas, para que la lista sea estable
          sin recargar al tildar una comisión.
    """
    comisiones = comisiones_permitidas(request.user)
    permitidas = list(comisiones.values_list('id', flat=True))
    permitidas_set = set(permitidas)

    pedidas = _parse_ids(request.GET.get('comision_ids', ''))
    pidio_comisiones = bool(pedidas)
    if pidio_comisiones:
        comision_ids = [c for c in pedidas if c in permitidas_set]
    else:
        comision_ids = list(permitidas)

    cohortes = cohortes_disponibles(permitidas)
    cohortes_validas = {c['id'] for c in cohortes}

    pedidas_cohortes = _parse_ids(request.GET.get('cohorte_ids', ''))
    if not pedidas_cohortes:
        pedidas_cohortes = _parse_cohortes_legacy(request.GET.getlist('cohorte'))
    cohorte_ids = [c for c in pedidas_cohortes if c in cohortes_validas] or None

    # comision_ids va siempre en el querystring: los links de exportación
    # deben describir explícitamente el recorte que se está mirando.
    params = {'comision_ids': ','.join(str(c) for c in comision_ids)}
    if cohorte_ids:
        params['cohorte_ids'] = ','.join(str(c) for c in cohorte_ids)

    return FiltroAnaliticas(
        comision_ids=comision_ids,
        cohorte_ids=cohorte_ids,
        comisiones=comisiones,
        cohortes=cohortes,
        qs=urlencode(params),
        activo=pidio_comisiones or bool(cohorte_ids),
        vacio_por_permisos=pidio_comisiones and not comision_ids,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.ResolverFiltrosTests -v 2
```

Expected: PASS — 13 tests.

- [ ] **Step 5: Commit**

```bash
git add analiticas/filtros.py analiticas/tests.py && git commit -m "feat(analiticas): modulo compartido de filtros por comision y cohorte"
```

---

## Task 2: `calculos.py` M2–M6 a multi-comisión + cohorte

**Files:**
- Modify: `analiticas/calculos.py:49`, `:83`, `:161`, `:193`, `:281`, `:319`, `:472`, `:498`, `:570`, `:603`
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: nada de Task 1.
- Produces (firmas nuevas, usadas por Tasks 5, 8 y 9):
  - `_matriz_juicio_computo(comision_ids, *, cohorte_ids=None) -> dict`
  - `_convergencia_por_ejercicio(comision_ids, ejercicio_id, *, cohorte_ids=None) -> dict`
  - `_perfil_error_tabla(comision_ids, ejercicio_id, *, cohorte_ids=None) -> dict`
  - `_indice_atomizacion(comision_ids, ejercicio_id, *, cohorte_ids=None) -> dict`
  - `_patron_adivinacion(comision_ids, min_intentos=5, max_intervalo_seg=30, modo_pedagogico=False, *, cohorte_ids=None) -> list[dict]`

En las cinco, `comision_ids` es una **lista** y es posicional (primer argumento), reemplazando al `comision_id: int` anterior.

- [ ] **Step 1: Write the failing tests**

Agregar al final de `analiticas/tests.py`:

```python
# ─── Tests: calculos.py multi-comisión ───────────────────────────────────────

from analiticas.calculos import _indice_atomizacion, _patron_adivinacion


class CalculosMultiComisionTests(TestCase):
    """M2–M6 pasan de una comisión a una lista, sin cambiar resultados."""

    def setUp(self):
        self.com_a, _, self.pc_a, self.ep_a, self.est_a = _setup_comision('MA', n_estudiantes=1)
        self.com_b, _, self.pc_b, self.ep_b, self.est_b = _setup_comision('MB', n_estudiantes=1)
        for _ in range(6):
            _intento(self.est_a[0], self.ep_a, False, pc=self.pc_a)
        for _ in range(6):
            _intento(self.est_b[0], self.ep_b, False, pc=self.pc_b)

    def test_una_comision_en_lista_replica_el_resultado_previo(self):
        # No-regresión del refactor: acotar a una comisión debe dar exactamente
        # lo mismo que daba la firma vieja de un solo comision_id.
        solo_a = _indice_atomizacion([self.com_a.id], self.ep_a.ejercicio_id)
        ambas = _indice_atomizacion([self.com_a.id, self.com_b.id],
                                    self.ep_a.ejercicio_id)
        # El ejercicio de A no existe en B, así que agregar B no cambia nada.
        self.assertEqual(solo_a, ambas)

    def test_comision_sin_ese_ejercicio_no_aporta(self):
        solo_b = _indice_atomizacion([self.com_b.id], self.ep_a.ejercicio_id)
        solo_a = _indice_atomizacion([self.com_a.id], self.ep_a.ejercicio_id)
        self.assertNotEqual(solo_a, solo_b)

    def test_dos_comisiones_agregan_ambas(self):
        ambas = _patron_adivinacion([self.com_a.id, self.com_b.id], min_intentos=5,
                                    max_intervalo_seg=99999)
        solo_a = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                     max_intervalo_seg=99999)
        self.assertGreater(len(ambas), len(solo_a))

    def test_cohorte_inexistente_vacia_el_resultado(self):
        vacio = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                    max_intervalo_seg=99999, cohorte_ids=[99999])
        self.assertEqual(vacio, [])

    def test_cohorte_none_incluye_todo(self):
        con_none = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                       max_intervalo_seg=99999, cohorte_ids=None)
        self.assertGreater(len(con_none), 0)

    def test_cohorte_real_incluye_los_intentos(self):
        con_cohorte = _patron_adivinacion([self.com_a.id], min_intentos=5,
                                          max_intervalo_seg=99999,
                                          cohorte_ids=[_cohorte().id])
        self.assertGreater(len(con_cohorte), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.CalculosMultiComisionTests -v 2
```

Expected: FAIL — `_indice_atomizacion` recibe una lista donde espera un int, así que el filtro `comision_id=[...]` tira `TypeError`/`ValueError` de Django.

- [ ] **Step 3: Write the implementation**

En `analiticas/calculos.py`, aplicar el mismo patrón a las cinco funciones. Cada una usa `comision_id` en **un solo lugar**.

Firmas (línea 49, 161, 281, 472, 569):

```python
def _matriz_juicio_computo(comision_ids: list[int], *, cohorte_ids: list[int] | None = None) -> dict:
def _convergencia_por_ejercicio(comision_ids: list[int], ejercicio_id: int, *, cohorte_ids: list[int] | None = None) -> dict:
def _perfil_error_tabla(comision_ids: list[int], ejercicio_id: int, *, cohorte_ids: list[int] | None = None) -> dict:
def _indice_atomizacion(comision_ids: list[int], ejercicio_id: int, *, cohorte_ids: list[int] | None = None) -> dict:
def _patron_adivinacion(
    comision_ids: list[int],
    min_intentos: int = 5,
    max_intervalo_seg: int = 30,
    modo_pedagogico: bool = False,
    *,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
```

Filtros (líneas 83, 193, 319, 498, 603): reemplazar

```python
            practica_comision__comision_id=comision_id,
```

por

```python
            practica_comision__comision_id__in=comision_ids,
```

y, en cada una de las cinco, encadenar el filtro de cohorte inmediatamente después de construir el queryset base:

```python
    if cohorte_ids is not None:
        intentos = intentos.filter(cohorte_id__in=cohorte_ids)
```

> Ajustar el nombre de la variable al que use cada función (`intentos`, `qs`, etc.). `Intento.cohorte` es FK directa NOT NULL, así que el filtro no necesita join.

En los docstrings, reemplazar la línea `comision_id: ID de la comisión.` por:

```
        comision_ids: IDs de las comisiones a incluir.
        cohorte_ids: cohortes a incluir; None = todas.
```

Y agregar a los docstrings de `_convergencia_por_ejercicio`, `_perfil_error_tabla`, `_indice_atomizacion` y `_patron_adivinacion` esta nota, que documenta el cambio de comportamiento:

```
    Nota: agrupa por ``(estudiante, ejercicio)``. Con varias comisiones, un
    estudiante inscripto en más de una ve sus intentos unificados en una sola
    secuencia, en vez de una por comisión.
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.CalculosMultiComisionTests -v 2
```

Expected: PASS — 5 tests.

- [ ] **Step 5: Verificar que no se rompió ningún caller existente**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas -v 1
```

Expected: los callers viejos en `analiticas/views.py` (`dashboard` línea ~890 y `detalle_ejercicio` línea ~1240) todavía pasan un int y **fallan**. Anotar cuáles fallan; se arreglan en Tasks 5 y 8. Si falla algo más, investigarlo antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add analiticas/calculos.py analiticas/tests.py && git commit -m "refactor(analiticas): M2-M6 aceptan varias comisiones y filtro de cohorte"
```

---

## Task 3: Helpers del dashboard a `cohorte_ids`

**Files:**
- Modify: `analiticas/views.py:55`, `:119`, `:200`, `:346`, `:402`, `:502`, `:582`, `:683`
- Test: `analiticas/tests.py`

**Interfaces:**
- Produces (usadas por Task 5): los 8 helpers pasan de `cohorte_id=None` a `cohorte_ids=None`:
  `_ejercicios_mas_dificiles`, `_estudiantes_en_riesgo`, `_distribucion_intentos`, `_evolucion_temporal`, `_silencio_temprano`, `_concentracion_practica`, `_velocidad_arranque`, `_errores_sistematicos`.
  El parámetro sigue siendo el último y sigue teniendo default `None`; solo cambia nombre y tipo (int → list).

- [ ] **Step 1: Write the failing test**

Agregar al final de `analiticas/tests.py`:

```python
# ─── Tests: helpers del dashboard con cohorte_ids ────────────────────────────

class HelpersDashboardCohorteTests(TestCase):
    """Los 8 helpers del dashboard acotan por lista de cohortes."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('HC', n_estudiantes=1)
        self.est = self.ests[0]
        for _ in range(4):
            _intento(self.est, self.ep, False, pc=self.pc)

    def test_cohorte_real_incluye_intentos(self):
        filas = _ejercicios_mas_dificiles(
            [self.com.id], [self.est.id], min_intentos=1,
            cohorte_ids=[_cohorte().id],
        )
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['total'], 4)

    def test_cohorte_inexistente_excluye_todo(self):
        filas = _ejercicios_mas_dificiles(
            [self.com.id], [self.est.id], min_intentos=1, cohorte_ids=[99999],
        )
        self.assertEqual(filas, [])

    def test_cohorte_none_incluye_todo(self):
        filas = _ejercicios_mas_dificiles(
            [self.com.id], [self.est.id], min_intentos=1, cohorte_ids=None,
        )
        self.assertEqual(filas[0]['total'], 4)

    def test_distribucion_intentos_acepta_cohorte_ids(self):
        filas = _distribucion_intentos([self.com.id], [self.est.id], cohorte_ids=[99999])
        self.assertEqual(filas, [])

    def test_evolucion_temporal_acepta_cohorte_ids(self):
        datos = _evolucion_temporal([self.com.id], [self.est.id], cohorte_ids=[_cohorte().id])
        self.assertTrue(any(d['intentos'] for d in datos))

    def test_errores_sistematicos_acepta_cohorte_ids(self):
        filas = _errores_sistematicos([self.com.id], [self.est.id], min_estudiantes=1,
                                      cohorte_ids=[99999])
        self.assertEqual(filas, [])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.HelpersDashboardCohorteTests -v 2
```

Expected: FAIL — `TypeError: ... got an unexpected keyword argument 'cohorte_ids'`

- [ ] **Step 3: Write the implementation**

En `analiticas/views.py`, en los 8 helpers:

1. Firma: `cohorte_id=None` → `cohorte_ids=None`.
2. Docstring: `cohorte_id: si se da, acota los intentos a esa cohorte.` → `cohorte_ids: si se da, acota los intentos a esas cohortes.` (conservar el resto de cada explicación, que es distinta en cada helper).
3. Cuerpo — en `_ejercicios_mas_dificiles` (líneas 82-83):

```python
    if cohorte_ids is not None:
        _filtro_estudiantes &= Q(intentos__cohorte_id__in=cohorte_ids)
```

4. Cuerpo — en los otros siete, que usan el dict `_filtros`:

```python
    if cohorte_ids is not None:
        _filtros['cohorte_id__in'] = cohorte_ids
```

> Ojo: la clave del dict pasa de `'cohorte_id'` a `'cohorte_id__in'`. Dejar la clave vieja con una lista como valor no funciona.

- [ ] **Step 4: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.HelpersDashboardCohorteTests -v 2
```

Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add analiticas/views.py analiticas/tests.py && git commit -m "refactor(analiticas): helpers del dashboard aceptan cohorte_ids"
```

---

## Task 4: `anonimizador.py` acepta `cohorte_ids`

**Files:**
- Modify: `analiticas/anonimizador.py:243`, `:298`
- Test: `analiticas/tests.py`

**Interfaces:**
- Produces (usadas por Task 8):
  - `dataset_encuesta(comision_ids, anio=None, cuatri=None, *, cohorte_ids=None) -> list[dict]`
  - `dataset_intentos(comision_ids, anio=None, cuatri=None, *, cohorte_ids=None) -> list[dict]`

`anio`/`cuatri` se conservan intactos. Si vienen `cohorte_ids`, se aplica **además** de `anio`/`cuatri` (en la práctica el llamador manda uno u otro).

- [ ] **Step 1: Write the failing test**

Agregar al final de `analiticas/tests.py`:

```python
# ─── Tests: anonimizador con cohorte_ids ─────────────────────────────────────

from analiticas.anonimizador import dataset_encuesta, dataset_intentos


class AnonimizadorCohorteIdsTests(TestCase):
    """Los datasets anonimizados aceptan cohorte_ids además de anio/cuatri."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('AN', n_estudiantes=1)
        self.est = self.ests[0]
        _crear_encuesta(self.est)
        _intento(self.est, self.ep, False, pc=self.pc)

    def test_encuesta_cohorte_real_incluye_la_fila(self):
        filas = dataset_encuesta([self.com.id], cohorte_ids=[_cohorte().id])
        self.assertEqual(len(filas), 1)

    def test_encuesta_cohorte_inexistente_vacia(self):
        filas = dataset_encuesta([self.com.id], cohorte_ids=[99999])
        self.assertEqual(filas, [])

    def test_encuesta_sin_cohorte_ids_incluye_todo(self):
        filas = dataset_encuesta([self.com.id])
        self.assertEqual(len(filas), 1)

    def test_intentos_cohorte_real_incluye_la_fila(self):
        filas = dataset_intentos([self.com.id], cohorte_ids=[_cohorte().id])
        self.assertEqual(len(filas), 1)

    def test_intentos_cohorte_inexistente_vacia(self):
        filas = dataset_intentos([self.com.id], cohorte_ids=[99999])
        self.assertEqual(filas, [])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.AnonimizadorCohorteIdsTests -v 2
```

Expected: FAIL — `TypeError: dataset_encuesta() got an unexpected keyword argument 'cohorte_ids'`

- [ ] **Step 3: Write the implementation**

En `analiticas/anonimizador.py`:

Firmas:

```python
def dataset_encuesta(comision_ids, anio=None, cuatri=None, *, cohorte_ids=None) -> list[dict]:
def dataset_intentos(comision_ids, anio=None, cuatri=None, *, cohorte_ids=None) -> list[dict]:
```

Docstrings — agregar al bloque `Args:` de ambas:

```
        cohorte_ids: PKs de cohorte a incluir (None = todas). Alternativa
            moderna a anio/cuatri; si se pasan ambos, se aplican los dos.
```

En `dataset_encuesta`, después del bloque `if anio is not None:` (línea ~275):

```python
    if cohorte_ids is not None:
        qs_insc = qs_insc.filter(cohorte_id__in=cohorte_ids)
```

En `dataset_intentos` hay **dos** querysets que filtrar. Después del bloque `if anio is not None:` que acota `insc_qs` (línea ~335):

```python
    if cohorte_ids is not None:
        insc_qs = insc_qs.filter(cohorte_id__in=cohorte_ids)
```

Y después del bloque equivalente sobre `qs` (línea ~368), que es el que acota los intentos por su FK directa:

```python
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.AnonimizadorCohorteIdsTests -v 2
```

Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add analiticas/anonimizador.py analiticas/tests.py && git commit -m "feat(analiticas): datasets anonimizados aceptan cohorte_ids"
```

---

## Task 5: Partial de filtros + wiring del dashboard

**Files:**
- Create: `templates/analiticas/_filtros.html`
- Modify: `analiticas/views.py:752-908` (vista `dashboard`)
- Modify: `templates/analiticas/dashboard.html:25-35`
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `resolver_filtros` (Task 1), helpers con `cohorte_ids` (Task 3), `_matriz_juicio_computo` / `_patron_adivinacion` multi-comisión (Task 2).
- Produces: el partial `_filtros.html`, que espera en el contexto una variable `filtros` (un `FiltroAnaliticas`). Tasks 6 y 7 lo reutilizan tal cual.

- [ ] **Step 1: Write the failing test**

Agregar al final de `analiticas/tests.py`:

```python
# ─── Tests: dashboard filtrado ───────────────────────────────────────────────

class DashboardFiltradoTests(TestCase):
    """El dashboard acota todas sus secciones por comisión y cohorte."""

    def setUp(self):
        self.com_a, _, self.pc_a, self.ep_a, self.ests_a = _setup_comision('DA', n_estudiantes=1)
        self.com_b, _, self.pc_b, self.ep_b, self.ests_b = _setup_comision('DB', n_estudiantes=1)
        self.admin = _u('admin-dash', is_staff=True)
        self.c1 = _cohorte()
        self.c2 = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        for _ in range(3):
            _intento(self.ests_a[0], self.ep_a, False, pc=self.pc_a)
        # Un intento de la otra camada, que el filtro por c1 debe excluir.
        Intento.objects.create(
            estudiante=self.ests_a[0], ejercicio_practica=self.ep_a,
            respuesta_raw='q', es_correcto=False,
            practica_comision=self.pc_a, cohorte=self.c2,
        )
        self.client.force_login(self.admin)

    def test_sin_filtro_muestra_las_dos_comisiones(self):
        resp = self.client.get(reverse('analiticas:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['comisiones_data']), 2)

    def test_filtro_de_comision_acota_las_tarjetas(self):
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(len(resp.context['comisiones_data']), 1)
        self.assertEqual(resp.context['comisiones_data'][0]['comision'].id, self.com_a.id)

    def test_filtro_de_cohorte_excluye_intentos_de_otra_camada(self):
        resp = self.client.get(reverse('analiticas:dashboard'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(self.c1.id),
        })
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_intentos'], 3)

    def test_sin_filtro_de_cohorte_cuenta_las_dos_camadas(self):
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_a.id)})
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_intentos'], 4)

    def test_denominador_respeta_la_cohorte(self):
        # El estudiante está inscripto solo en c1: filtrar por c2 lo excluye.
        resp = self.client.get(reverse('analiticas:dashboard'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(self.c2.id),
        })
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_estudiantes'], 0)

    def test_recursante_no_se_cuenta_dos_veces_en_el_denominador(self):
        # Mismo estudiante inscripto en dos camadas de la MISMA comisión.
        Inscripcion.objects.create(
            estudiante=self.ests_a[0], comision=self.com_a, cohorte=self.c2,
        )
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_a.id)})
        practicas = resp.context['comisiones_data'][0]['practicas']
        # Es una persona, aunque tenga dos filas de Inscripcion.
        self.assertEqual(practicas[0]['total_estudiantes'], 1)

    def test_recursante_acotado_a_una_camada_cuenta_una_vez(self):
        Inscripcion.objects.create(
            estudiante=self.ests_a[0], comision=self.com_a, cohorte=self.c2,
        )
        resp = self.client.get(reverse('analiticas:dashboard'), {
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(self.c2.id),
        })
        practicas = resp.context['comisiones_data'][0]['practicas']
        self.assertEqual(practicas[0]['total_estudiantes'], 1)
        # Y sus intentos son solo los de esa camada: 1, no 4.
        self.assertEqual(practicas[0]['total_intentos'], 1)

    def test_matriz_juicio_se_calcula_con_varias_comisiones(self):
        # Antes solo aparecía con exactamente una comisión.
        resp = self.client.get(reverse('analiticas:dashboard'))
        self.assertIsNotNone(resp.context['matriz_juicio'])

    def test_comision_ajena_da_estado_vacio_no_todas(self):
        docente_a = self.com_a.docentes.first()
        self.client.force_login(docente_a)
        resp = self.client.get(reverse('analiticas:dashboard'),
                               {'comision_ids': str(self.com_b.id)})
        self.assertEqual(resp.context['comisiones_data'], [])
        self.assertTrue(resp.context['filtros'].vacio_por_permisos)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.DashboardFiltradoTests -v 2
```

Expected: FAIL — `KeyError: 'filtros'` y las tarjetas no se acotan.

- [ ] **Step 3: Crear el partial**

Crear `templates/analiticas/_filtros.html`:

```html
{# Barra de filtros compartida por dashboard, investigación y encuesta.
   Espera en el contexto `filtros` (analiticas.filtros.FiltroAnaliticas). #}
<form method="get" class="card"
      style="margin-bottom:1.5rem; padding:1rem 1.25rem; display:flex; gap:2rem;
             flex-wrap:wrap; align-items:flex-start;">

  <div>
    <div style="font-size:0.82rem; font-weight:600; color:#555; margin-bottom:0.4rem;">
      Comisiones <span style="font-weight:400;">(sin tildar: todas)</span>
    </div>
    {% for comision in filtros.comisiones %}
    <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.84rem;
                  cursor:pointer; margin-bottom:0.2rem;">
      <input type="checkbox" name="comision_ids" value="{{ comision.id }}"
             {% if comision.id in filtros.comision_ids %}checked{% endif %}
             style="cursor:pointer;">
      {{ comision.nombre }}
    </label>
    {% empty %}
    <span style="font-size:0.83rem; color:#888;">Sin comisiones disponibles</span>
    {% endfor %}
  </div>

  {% if filtros.cohortes %}
  <div>
    <div style="font-size:0.82rem; font-weight:600; color:#555; margin-bottom:0.4rem;">
      Cohortes <span style="font-weight:400;">(sin tildar: todas)</span>
    </div>
    {% for c in filtros.cohortes %}
    <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.84rem;
                  cursor:pointer; margin-bottom:0.2rem;">
      <input type="checkbox" name="cohorte_ids" value="{{ c.id }}"
             {% if filtros.cohorte_ids and c.id in filtros.cohorte_ids %}checked{% endif %}
             style="cursor:pointer;">
      {{ c.label }}
    </label>
    {% endfor %}
  </div>
  {% endif %}

  <div style="display:flex; gap:0.5rem; align-self:flex-end;">
    <button type="submit"
            style="padding:0.4rem 1rem; border-radius:4px; border:1px solid #1976d2;
                   background:#e3f2fd; color:#1565c0; font-size:0.84rem;
                   font-weight:600; cursor:pointer;">Aplicar</button>
    {% if filtros.activo %}
    <a href="{{ request.path }}"
       style="padding:0.4rem 1rem; border-radius:4px; border:1px solid #ccc;
              background:#fafafa; color:#555; font-size:0.84rem;
              text-decoration:none;">Limpiar</a>
    {% endif %}
  </div>
</form>

{% if filtros.vacio_por_permisos %}
<div style="background:#ffebee; border:1px solid #ef9a9a; border-radius:6px;
            padding:0.85rem 1rem; margin-bottom:1.5rem; font-size:0.88rem; color:#b71c1c;">
  Ninguna de las comisiones seleccionadas está a tu cargo. No hay datos para mostrar.
</div>
{% endif %}
```

> El `<form method="get">` con checkboxes homónimos manda `?comision_ids=1&comision_ids=2`. `_parse_ids` lee `request.GET.get()`, que devuelve **solo el último**. Por eso el paso siguiente ajusta `_parse_ids` para leer también la forma repetida.

- [ ] **Step 4: Ajustar `resolver_filtros` para checkboxes repetidos**

En `analiticas/filtros.py`, reemplazar las dos lecturas de `request.GET.get(...)` por un helper que acepte las dos formas (`?x=1,2` y `?x=1&x=2`):

```python
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
```

Y en `resolver_filtros`:

```python
    pedidas = _ids_de_request(request.GET, 'comision_ids')
```
```python
    pedidas_cohortes = _ids_de_request(request.GET, 'cohorte_ids')
```

Agregar el test correspondiente a `ResolverFiltrosTests`:

```python
    def test_acepta_checkboxes_repetidos(self):
        f = resolver_filtros(self._req(
            f'comision_ids={self.com_a.id}&comision_ids={self.com_b.id}',
            usuario=self.admin,
        ))
        self.assertCountEqual(f.comision_ids, [self.com_a.id, self.com_b.id])
```

- [ ] **Step 5: Wiring de la vista `dashboard`**

En `analiticas/views.py`, dentro de `dashboard`, reemplazar el bloque que arma `comisiones` y `comision_ids` (líneas ~767-784) por:

```python
    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids
    comisiones = (
        filtros.comisiones
        .filter(id__in=comision_ids)
        .prefetch_related('practicas_comisiones__practica')
    )
```

Acotar los tres mapas en bulk (líneas ~790-820). En `total_intentos_map` e `intentos_correctos_map`, encadenar sobre el queryset de `Intento`:

```python
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
```

En `completaron_map`, `Progreso` tiene FK propia a cohorte:

```python
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
            # El join contra estudiante__inscripciones duplica la fila de
            # Progreso por cada Inscripcion que matchea (un recursante tiene
            # una por cohorte en la misma comisión); distinct=True cuenta
            # cada Progreso una sola vez.
            _qs_progreso.values('practica_comision_id').annotate(n=Count('pk', distinct=True))
        )
    }
```

Reemplazar el conteo de estudiantes dentro del `for comision in comisiones` (línea ~828). Antes del loop, precalcular por comisión respetando la cohorte:

```python
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
```

y dentro del loop:

```python
        total_estudiantes = _estudiantes_por_comision.get(comision.id, 0)
```

Reemplazar el bloque `_estudiantes_dashboard` (líneas ~855-865) por:

```python
    # Población del panel: los estudiantes inscriptos en las comisiones y
    # cohortes filtradas. Sin filtro de cohorte agrega todas las camadas,
    # que es lo que este panel viene reportando.
    _estudiantes_dashboard = list(
        _insc_qs.values_list('estudiante_id', flat=True).distinct()
    )
```

Pasar `cohorte_ids` a los 8 helpers y a M2/M6 en el `render`. Las llamadas quedan así (reemplaza el dict del `render`, líneas ~868-905):

```python
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
```

- [ ] **Step 6: Incluir el partial en el template**

En `templates/analiticas/dashboard.html`, después del `</div>` que cierra el header con los links de navegación (línea ~35), agregar:

```html
  {% include "analiticas/_filtros.html" %}
```

En el mismo archivo, los dos paneles que hoy están envueltos en un `{% if %}` que dependía de tener una sola comisión (M2 en la línea ~472 y M6 en la línea ~666) ya no lo necesitan: `matriz_juicio` y `patron_baja_variacion` vienen siempre poblados. Dejar los `{% if matriz_juicio %}` / `{% if patron_baja_variacion %}` que chequean contenido vacío, que siguen siendo correctos.

- [ ] **Step 7: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.DashboardFiltradoTests analiticas.tests.ResolverFiltrosTests -v 2
```

Expected: PASS — 7 + 14 tests.

- [ ] **Step 8: Commit**

```bash
git add analiticas/views.py analiticas/filtros.py analiticas/tests.py templates/analiticas/_filtros.html templates/analiticas/dashboard.html && git commit -m "feat(analiticas): filtro de comision y cohorte en el dashboard"
```

---

## Task 6: Wiring de `investigacion` + unificación del bloque de descarga

**Files:**
- Modify: `analiticas/views.py:919-1060` (vista `investigacion`)
- Modify: `templates/analiticas/investigacion.html:72-130` (bloque de descarga), `:200-210` (header)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `resolver_filtros` (Task 1), `_filtros.html` (Task 5).
- Produces: contexto con `filtros`; el template deja de recibir `cohortes_disponibles` (lo reemplaza `filtros.cohortes`) y `comisiones` (lo reemplaza `filtros.comisiones`).

- [ ] **Step 1: Write the failing test**

Agregar al final de `analiticas/tests.py`:

```python
# ─── Tests: investigación filtrada ───────────────────────────────────────────

class InvestigacionFiltradaTests(TestCase):
    """La página de investigación acota sus métricas por comisión y cohorte."""

    def setUp(self):
        self.com_a, _, self.pc_a, self.ep_a, self.ests_a = _setup_comision('IA', n_estudiantes=1)
        self.com_b, _, self.pc_b, self.ep_b, self.ests_b = _setup_comision('IB', n_estudiantes=1)
        _crear_encuesta(self.ests_a[0])
        _crear_encuesta(self.ests_b[0])
        _intento(self.ests_a[0], self.ep_a, False, pc=self.pc_a)
        _intento(self.ests_b[0], self.ep_b, False, pc=self.pc_b)
        self.admin = _u('admin-inv', is_staff=True)
        self.client.force_login(self.admin)

    def test_sin_filtro_incluye_las_dos_comisiones(self):
        resp = self.client.get(reverse('analiticas:investigacion'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_est'], 2)

    def test_filtro_de_comision_acota_el_total(self):
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(resp.context['total_est'], 1)

    def test_filtro_de_cohorte_inexistente_vacia_las_metricas(self):
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'cohorte_ids': '99999'})
        # Una cohorte inválida se descarta: equivale a no filtrar.
        self.assertIsNone(resp.context['filtros'].cohorte_ids)

    def test_filtro_de_cohorte_real_se_propaga(self):
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'cohorte_ids': str(_cohorte().id)})
        self.assertEqual(resp.context['filtros'].cohorte_ids, [_cohorte().id])

    def test_qs_de_exportacion_esta_en_el_contexto(self):
        resp = self.client.get(reverse('analiticas:investigacion'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertIn(f'comision_ids={self.com_a.id}', resp.context['filtros'].qs)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.InvestigacionFiltradaTests -v 2
```

Expected: FAIL — `KeyError: 'filtros'`; `total_est` no se acota.

- [ ] **Step 3: Wiring de la vista**

En `analiticas/views.py`, dentro de `investigacion`, reemplazar el bloque que arma `comisiones` / `comision_ids` (líneas ~956-962) por:

```python
    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    comisiones = filtros.comisiones
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids
```

Acotar el conteo de consentimientos (líneas ~965-970):

```python
    _insc_qs = Inscripcion.objects.filter(comision_id__in=comision_ids)
    if cohorte_ids is not None:
        _insc_qs = _insc_qs.filter(cohorte_id__in=cohorte_ids)
    estudiantes_ids = list(_insc_qs.values_list('estudiante_id', flat=True).distinct())
```

Agregar `cohorte_ids=cohorte_ids` a **todas** las llamadas de métricas de la vista. Son 21, todas con la misma forma. Quedan así:

```python
    entrada = tasa_entrada_efectiva(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    intentos = intentos_hasta_correcto_sin_sesgo(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    persistencia = persistencia_relativa(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)
    abandono = tasa_abandono_local(
        comision_ids=comision_ids, solo_consentimiento=True, solo_practicas_cerradas=False,
        cohorte_ids=cohorte_ids,
    )
```

y, más abajo:

```python
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
```

En el dict del `render`, reemplazar las dos primeras claves y agregar `filtros`:

```python
        'filtros': filtros,
        'comisiones': comisiones,
        'comision_ids_csv': ','.join(str(cid) for cid in comision_ids),
```

y **borrar** la clave `'cohortes_disponibles': _cohortes_disponibles(comision_ids),`, que el partial reemplaza.

- [ ] **Step 4: Unificar el bloque de descarga en el template**

En `templates/analiticas/investigacion.html`:

1. Después del `</div>` del header (línea ~210, tras los links de navegación), agregar:

```html
  {% include "analiticas/_filtros.html" %}
```

2. En el bloque de descarga (línea ~72), reemplazar el `x-data` por uno que tome el filtro ya resuelto del servidor:

```html
  <div class="card" style="margin-bottom:1.5rem; padding:1.25rem 1.5rem;"
       x-data="{
         url(dataset, formato) {
           const p = new URLSearchParams('{{ filtros.qs }}');
           p.set('dataset', dataset);
           p.set('formato', formato);
           return '{% url "analiticas:descargar_investigacion" %}?' + p.toString();
         }
       }">
```

3. **Borrar** el bloque `<div style="display:flex; gap:2rem; ...">` que contiene los dos filtros propios (los checkboxes `x-model="comisiones_sel"` y el `<select x-model="cohorte_sel">`), líneas ~94-129. Los `:href="url(...)"` de los botones no cambian.

4. Agregar una línea al pie del bloque, junto a la nota existente sobre consentimiento:

```html
      Las descargas respetan el filtro de comisión y cohorte de arriba.
```

5. Los ~48 links `{% url 'analiticas:exportar' ... %}?formato=csv&comision_ids={{ comision_ids_csv }}` de cada sección pasan a usar el querystring completo. Reemplazo global en el archivo:

- Buscar: `?formato=csv&comision_ids={{ comision_ids_csv }}`
- Reemplazar: `?formato=csv&{{ filtros.qs }}`

Repetir para `formato=xlsx` y `formato=ods`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.InvestigacionFiltradaTests -v 2
```

Expected: PASS — 5 tests.

- [ ] **Step 6: Commit**

```bash
git add analiticas/views.py analiticas/tests.py templates/analiticas/investigacion.html && git commit -m "feat(analiticas): filtro unificado en la pagina de investigacion"
```

---

## Task 7: Wiring de `encuesta_resumen`

**Files:**
- Modify: `analiticas/views.py:1110-1183`
- Modify: `templates/analiticas/encuesta_resumen.html:76-86`
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `resolver_filtros` (Task 1), `_filtros.html` (Task 5).

- [ ] **Step 1: Write the failing test**

```python
# ─── Tests: resumen de encuesta filtrado ─────────────────────────────────────

class EncuestaResumenFiltradaTests(TestCase):
    """El resumen de encuesta acota por comisión y cohorte."""

    def setUp(self):
        self.com_a, _, _, _, self.ests_a = _setup_comision('EA', n_estudiantes=1)
        self.com_b, _, _, _, self.ests_b = _setup_comision('EB', n_estudiantes=1)
        _crear_encuesta(self.ests_a[0])
        _crear_encuesta(self.ests_b[0])
        self.admin = _u('admin-enc', is_staff=True)
        self.client.force_login(self.admin)

    def test_sin_filtro_cuenta_las_dos_comisiones(self):
        resp = self.client.get(reverse('analiticas:encuesta_resumen'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_est'], 2)
        self.assertEqual(resp.context['con_encuesta'], 2)

    def test_filtro_de_comision_acota(self):
        resp = self.client.get(reverse('analiticas:encuesta_resumen'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(resp.context['total_est'], 1)

    def test_filtros_en_contexto(self):
        resp = self.client.get(reverse('analiticas:encuesta_resumen'))
        self.assertIsNotNone(resp.context['filtros'])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.EncuestaResumenFiltradaTests -v 2
```

Expected: FAIL — `KeyError: 'filtros'`; `total_est` es 2 con filtro.

- [ ] **Step 3: Write the implementation**

En `analiticas/views.py`, dentro de `encuesta_resumen`, reemplazar el bloque de comisiones (líneas ~1147-1153) por:

```python
    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    comisiones = filtros.comisiones
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids
```

Acotar la población (líneas ~1156-1161):

```python
    _insc_qs = Inscripcion.objects.filter(comision_id__in=comision_ids)
    if cohorte_ids is not None:
        _insc_qs = _insc_qs.filter(cohorte_id__in=cohorte_ids)
    estudiantes_ids = list(_insc_qs.values_list('estudiante_id', flat=True).distinct())
```

Agregar `cohorte_ids=cohorte_ids` a las 7 llamadas de métricas:

```python
    nse = distribucion_nse_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    logicas = distribucion_puntaje_logicas(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    pandemia = distribucion_pandemia_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    facultades = distribucion_facultad_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    carreras = distribucion_carrera_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    cohortes = cohortes_onboarding(comision_ids, solo_consentimiento=False, cohorte_ids=cohorte_ids)
    detalle = distribuciones_encuesta_detalle(comision_ids, cohorte_ids=cohorte_ids)
```

Agregar `'filtros': filtros,` como primera clave del dict del `render`.

- [ ] **Step 4: Incluir el partial**

En `templates/analiticas/encuesta_resumen.html`, después del `</div>` que cierra el header (línea ~86), agregar:

```html
  {% include "analiticas/_filtros.html" %}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.EncuestaResumenFiltradaTests -v 2
```

Expected: PASS — 3 tests.

- [ ] **Step 6: Commit**

```bash
git add analiticas/views.py analiticas/tests.py templates/analiticas/encuesta_resumen.html && git commit -m "feat(analiticas): filtro de comision y cohorte en el resumen de encuesta"
```

---

## Task 8: Exportaciones y endpoints JSON

**Files:**
- Modify: `analiticas/views.py:1071-1107` (`red_errores_json`), `:1185-1247` (`detalle_ejercicio`), `:1249` (`_datos_exportacion`), `:1484-1541` (`exportar`), `:1637-1765` (`descargar_investigacion`)
- Delete: `analiticas/views.py:1547-1568` (`_cohortes_disponibles` y `_parse_cohorte`, reemplazados por `filtros.py`)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `resolver_filtros` (Task 1), `dataset_encuesta`/`dataset_intentos` con `cohorte_ids` (Task 4), M3/M4/M5 multi-comisión (Task 2).
- Produces: `_datos_exportacion(dataset, comision_ids, cohorte_ids)`.

- [ ] **Step 1: Write the failing test**

```python
# ─── Tests: exportaciones y endpoints con filtro ─────────────────────────────

class ExportacionesFiltradasTests(TestCase):
    """Los exports y endpoints JSON respetan el mismo filtro que la pantalla."""

    def setUp(self):
        self.com_a, _, self.pc_a, self.ep_a, self.ests_a = _setup_comision('XA', n_estudiantes=1)
        self.com_b, _, self.pc_b, self.ep_b, self.ests_b = _setup_comision('XB', n_estudiantes=1)
        _crear_encuesta(self.ests_a[0])
        _intento(self.ests_a[0], self.ep_a, False, pc=self.pc_a)
        self.admin = _u('admin-exp', is_staff=True)
        self.client.force_login(self.admin)

    def test_cohorte_inexistente_se_ignora_en_la_descarga(self):
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv',
            'comision_ids': str(self.com_a.id), 'cohorte_ids': '99999',
        })
        self.assertEqual(resp.status_code, 200)
        # Una cohorte inexistente se descarta, así que el filtro equivale a
        # "todas": la fila del estudiante tiene que seguir estando.
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 2)

    def test_descarga_encuesta_con_cohorte_real(self):
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv',
            'comision_ids': str(self.com_a.id), 'cohorte_ids': str(_cohorte().id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.content.decode('utf-8-sig').strip().splitlines()), 2)

    def test_descarga_acepta_el_alias_legacy(self):
        resp = self.client.get(reverse('analiticas:descargar_investigacion'), {
            'dataset': 'encuesta', 'formato': 'csv', 'cohorte': '2026-1',
        })
        self.assertEqual(resp.status_code, 200)

    def test_exportar_respeta_comision_ids(self):
        resp = self.client.get(
            reverse('analiticas:exportar', args=['entrada']),
            {'formato': 'csv', 'comision_ids': str(self.com_a.id)},
        )
        self.assertEqual(resp.status_code, 200)

    def test_red_errores_acepta_comision_ids_plural(self):
        resp = self.client.get(reverse('analiticas:red_errores'),
                               {'comision_ids': str(self.com_a.id)})
        self.assertEqual(resp.status_code, 200)

    def test_red_errores_sigue_aceptando_comision_id_singular(self):
        resp = self.client.get(reverse('analiticas:red_errores'),
                               {'comision_id': str(self.com_a.id)})
        self.assertEqual(resp.status_code, 200)

    def test_detalle_ejercicio_acepta_cohorte_ids(self):
        resp = self.client.get(reverse('analiticas:detalle_ejercicio'), {
            'ejercicio_id': str(self.ep_a.ejercicio_id),
            'comision_ids': str(self.com_a.id),
            'cohorte_ids': str(_cohorte().id),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('convergencia', resp.json())

    def test_detalle_ejercicio_rechaza_comision_ajena_para_docente(self):
        self.client.force_login(self.com_a.docentes.first())
        resp = self.client.get(reverse('analiticas:detalle_ejercicio'), {
            'ejercicio_id': str(self.ep_a.ejercicio_id),
            'comision_ids': str(self.com_b.id),
        })
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.ExportacionesFiltradasTests -v 2
```

Expected: FAIL — `detalle_ejercicio` exige `comision_id` singular y devuelve 400; `red_errores` no conoce `comision_ids`.

- [ ] **Step 3: `red_errores_json`**

Reemplazar el cuerpo de permisos y parseo (líneas ~1082-1106) por:

```python
    from analiticas.filtros import resolver_filtros

    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return JsonResponse({'error': 'no autorizado'}, status=403)

    filtros = resolver_filtros(request)
    if filtros.vacio_por_permisos:
        return JsonResponse({'error': 'no autorizado'}, status=403)

    data = red_errores(
        comision_ids=filtros.comision_ids,
        solo_consentimiento=True,
        cohorte_ids=filtros.cohorte_ids,
    )
    return JsonResponse(data)
```

Para que el alias singular siga funcionando, agregar en `analiticas/filtros.py`, dentro de `resolver_filtros`, justo después de leer `pedidas`:

```python
    # Alias singular heredado de los endpoints JSON (?comision_id=3).
    if not pedidas:
        pedidas = _ids_de_request(request.GET, 'comision_id')
```

> El valor `'all'` que hoy acepta `red_errores_json` deja de ser especial: `_parse_ids` lo descarta y el resultado es "todas", que es lo mismo que significaba.

Actualizar el docstring de `red_errores_json`:

```python
    """Endpoint JSON para la red de co-ocurrencia de errores.

    Query params:
        comision_ids: IDs separados por coma (default: todas las permitidas).
        cohorte_ids: IDs separados por coma (default: todas).
        comision_id: alias singular heredado.
    """
```

- [ ] **Step 4: `detalle_ejercicio`**

Reemplazar el parseo y las llamadas (líneas ~1206-1247) por:

```python
    from analiticas.filtros import resolver_filtros

    usuario = request.user
    if not (usuario.is_staff or usuario.es_docente):
        return JsonResponse({'error': 'Acceso denegado'}, status=403)

    try:
        ejercicio_id = int(request.GET['ejercicio_id'])
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Parámetros inválidos'}, status=400)

    filtros = resolver_filtros(request)
    if filtros.vacio_por_permisos or not filtros.comision_ids:
        return JsonResponse({'error': 'Acceso denegado'}, status=403)

    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids

    return JsonResponse({
        'convergencia': _convergencia_por_ejercicio(comision_ids, ejercicio_id, cohorte_ids=cohorte_ids),
        'perfil_tabla': _perfil_error_tabla(comision_ids, ejercicio_id, cohorte_ids=cohorte_ids),
        'atomizacion': _indice_atomizacion(comision_ids, ejercicio_id, cohorte_ids=cohorte_ids),
    })
```

Actualizar el docstring:

```python
    """Devuelve JSON con métricas M3/M4/M5 para un ejercicio y un recorte dado.

    GET params:
        ejercicio_id: int — ID del Ejercicio (obligatorio)
        comision_ids: IDs separados por coma (default: todas las permitidas)
        cohorte_ids: IDs separados por coma (default: todas)

    Solo accesible para docentes y admins. ``resolver_filtros`` descarta las
    comisiones ajenas; si la selección explícita queda vacía, devuelve 403.
    """
```

> Los dos consumidores JS de este endpoint (`templates/analiticas/dashboard.html` y `templates/docentes/practica_detail.html`) hoy mandan `comision_id=`. El alias del Step 3 los mantiene funcionando sin tocarlos.

- [ ] **Step 5: `_datos_exportacion` y `exportar`**

Cambiar la firma de `_datos_exportacion` (línea 1249):

```python
def _datos_exportacion(dataset, comision_ids, cohorte_ids=None):
```

Dentro, agregar `cohorte_ids=cohorte_ids` a cada llamada de `research` que arma un dataset. Todas tienen la forma `f(comision_ids=comision_ids, solo_consentimiento=True)`; queda `f(comision_ids=comision_ids, solo_consentimiento=True, cohorte_ids=cohorte_ids)`.

En `exportar`, reemplazar el bloque de permisos y parseo (líneas ~1501-1517) por:

```python
    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    headers, rows = _datos_exportacion(dataset, filtros.comision_ids, filtros.cohorte_ids)
```

Y actualizar el docstring:

```python
    """Exporta un dataset de investigación en CSV, XLSX u ODS.

    Solo datos de estudiantes con consentimiento_investigacion=True.

    Query params:
        formato: 'csv' (default) | 'xlsx' | 'ods'
        comision_ids: IDs separados por coma (default: todas las del usuario)
        cohorte_ids: IDs separados por coma (default: todas)
    """
```

- [ ] **Step 6: `descargar_investigacion`**

Reemplazar el bloque de permisos y parseo (líneas ~1663-1683) por:

```python
    from analiticas.filtros import resolver_filtros

    filtros = resolver_filtros(request)
    comision_ids = filtros.comision_ids
    cohorte_ids = filtros.cohorte_ids

    if not comision_ids:
        return HttpResponse('Sin comisiones disponibles.', status=403)
```

Borrar la línea `anio, cuatri = _parse_cohorte(request.GET.get('cohorte', ''))` y reemplazar las dos llamadas a los datasets anonimizados:

```python
        rows = dataset_encuesta(comision_ids, cohorte_ids=cohorte_ids)
```
```python
        rows = dataset_intentos(comision_ids, cohorte_ids=cohorte_ids)
```

Y la de `trabajo_nota`:

```python
        res = trabajo_vs_nota_logica(comision_ids=comision_ids, solo_consentimiento=True,
                                     cohorte_ids=cohorte_ids)
```

Actualizar el docstring:

```python
    """Descarga un dataset anonimizado (encuesta o intentos) con filtros opcionales.

    Query params:
        dataset   : 'encuesta' | 'intentos' | 'ejercicios' | 'practicas' | 'trabajo_nota'
        formato   : 'csv' | 'xlsx'  (encuesta)  /  'csv' | 'json'  (intentos)
        comision_ids : IDs separados por coma (default: todas las permitidas)
        cohorte_ids  : IDs separados por coma (default: todas)
        cohorte      : 'YYYY-C' ej. '2026-1' — alias heredado
    """
```

- [ ] **Step 7: Borrar los helpers muertos**

Borrar de `analiticas/views.py` las funciones `_cohortes_disponibles` (línea 1547) y `_parse_cohorte` (línea 1559): `filtros.py` las reemplaza. Verificar que no queden referencias:

```bash
grep -n "_cohortes_disponibles\|_parse_cohorte" analiticas/ templates/ -r
```

Expected: sin resultados.

- [ ] **Step 8: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.ExportacionesFiltradasTests -v 2
```

Expected: PASS — 8 tests.

- [ ] **Step 9: Suite completa — cierre de la parte web**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas -v 1
```

Expected: PASS. Baseline eran 100 tests; ahora deberían ser ~145. Ningún test preexistente debe fallar. Tarda ~6 minutos.

- [ ] **Step 10: Commit**

```bash
git add analiticas/views.py analiticas/filtros.py analiticas/tests.py && git commit -m "feat(analiticas): exportaciones y endpoints JSON respetan el filtro"
```

---

## Task 9: MCP — helper de normalización y las 5 herramientas de `calculos.py`

**Files:**
- Modify: `mcp_intentos.py:817-970` (las 5 herramientas), `:148` (zona de helpers internos)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `calculos.py` multi-comisión (Task 2).
- Produces: `_normalizar_comisiones(comision_id, comision_ids) -> list[int] | None`, usado también por Task 10.

- [ ] **Step 1: Write the failing test**

```python
# ─── Tests: MCP con comision_ids y cohorte_ids ───────────────────────────────

from mcp_intentos import _normalizar_comisiones


class MCPNormalizarComisionesTests(TestCase):
    """El alias singular y la lista nueva conviven sin ambigüedad."""

    def test_solo_singular(self):
        self.assertEqual(_normalizar_comisiones(3, None), [3])

    def test_solo_plural(self):
        self.assertEqual(_normalizar_comisiones(None, [1, 2]), [1, 2])

    def test_plural_gana_sobre_singular(self):
        self.assertEqual(_normalizar_comisiones(3, [1, 2]), [1, 2])

    def test_ninguno_es_none(self):
        self.assertIsNone(_normalizar_comisiones(None, None))

    def test_lista_vacia_es_none(self):
        self.assertIsNone(_normalizar_comisiones(None, []))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.MCPNormalizarComisionesTests -v 2
```

Expected: FAIL — `ImportError: cannot import name '_normalizar_comisiones'`

- [ ] **Step 3: Agregar el helper**

En `mcp_intentos.py`, en la sección "Helpers internos" (después de `_correcto_efectivo`, línea ~152):

```python
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
```

- [ ] **Step 4: Migrar las 5 herramientas de `calculos.py`**

Las cinco siguen el mismo patrón. `matriz_juicio_computo` (línea ~817) queda:

```python
@db_tool()
def matriz_juicio_computo(
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Matriz 2×2 juicio lógico × cómputo de tabla para ejercicios de tabla_verdad.

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    from analiticas.calculos import _matriz_juicio_computo
    return _matriz_juicio_computo(
        _normalizar_comisiones(comision_id, comision_ids) or [],
        cohorte_ids=cohorte_ids,
    )
```

> `or []` importa: `_matriz_juicio_computo` filtra con `__in`, y `None` no es un valor válido para `__in`. Cuando no se pide comisión hay que pasar **todas**, no una lista vacía. Ver el paso siguiente.

- [ ] **Step 5: Resolver "todas" para las funciones de `calculos.py`**

`research.py` interpreta `comision_ids=None` como "todas" vía `_resolver_comision_ids`. `calculos.py` no: espera siempre una lista. Agregar en `mcp_intentos.py`, junto a `_normalizar_comisiones`:

```python
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
```

Usar `_comisiones_o_todas` (no `_normalizar_comisiones`) en las 5 herramientas de `calculos.py`:

```python
    return _matriz_juicio_computo(
        _comisiones_o_todas(comision_id, comision_ids),
        cohorte_ids=cohorte_ids,
    )
```

Aplicar la misma forma a las otras cuatro:

```python
@db_tool()
def convergencia_por_ejercicio(
    ejercicio_id: int,
    comision_id: Optional[int] = None,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> dict:
    """Perfiles de convergencia semántica para un ejercicio de formalización.

    Args:
        ejercicio_id: ID del Ejercicio.
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    from analiticas.calculos import _convergencia_por_ejercicio
    return _convergencia_por_ejercicio(
        _comisiones_o_todas(comision_id, comision_ids),
        ejercicio_id,
        cohorte_ids=cohorte_ids,
    )
```

> **Ojo con el orden de los parámetros:** en `convergencia_por_ejercicio`, `perfil_error_tabla` e `indice_atomizacion`, hoy la firma es `(comision_id, ejercicio_id)`. Al volverse opcional `comision_id`, `ejercicio_id` (que es obligatorio) tiene que ir **primero**, si no Python rechaza el orden. Esto cambia el orden posicional; los `*_compat` pasan todo por nombre, así que no se ven afectados.

`perfil_error_tabla` e `indice_atomizacion` son idénticas a `convergencia_por_ejercicio` salvo el import y la función interna (`_perfil_error_tabla`, `_indice_atomizacion`) y el resumen del docstring.

`patron_baja_variacion` (línea ~937):

```python
@db_tool()
def patron_baja_variacion(
    comision_id: Optional[int] = None,
    min_intentos: int = 5,
    max_intervalo_seg: int = 30,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
    """Pares (estudiante, ejercicio) con práctica de baja variación entre intentos.

    Args:
        comision_id: alias singular heredado. Preferir ``comision_ids``.
        min_intentos: mínimo de intentos para activar la señal.
        max_intervalo_seg: intervalo promedio máximo, en segundos.
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
    """
    from analiticas.calculos import _patron_adivinacion
    return _patron_adivinacion(
        _comisiones_o_todas(comision_id, comision_ids),
        min_intentos=min_intentos,
        max_intervalo_seg=max_intervalo_seg,
        cohorte_ids=cohorte_ids,
    )
```

- [ ] **Step 6: Agregar el test de equivalencia**

Agregar a `MCPNormalizarComisionesTests`:

```python
    def test_comisiones_o_todas_materializa_todas(self):
        from mcp_intentos import _comisiones_o_todas
        com, _, _, _, _ = _setup_comision('MCPT', n_estudiantes=0)
        todas = _comisiones_o_todas(None, None)
        self.assertIn(com.id, todas)
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.MCPNormalizarComisionesTests -v 2
```

Expected: PASS — 6 tests.

- [ ] **Step 8: Verificar que el servidor MCP importa sin errores**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' -c "import mcp_intentos; print('ok')"
```

Expected: `ok`. Si falla con `SyntaxError: parameter without a default follows parameter with a default`, es el orden de parámetros del Step 5.

- [ ] **Step 9: Commit**

```bash
git add mcp_intentos.py analiticas/tests.py && git commit -m "feat(mcp): M2-M6 aceptan comision_ids y cohorte_ids"
```

---

## Task 10: MCP — las 7 herramientas de ORM directo

**Files:**
- Modify: `mcp_intentos.py:313` (`_listar_intentos_impl`), `:380` (`listar_intentos`), `:456` (`intentos_por_estudiante`), `:511` (`analizar_errores_ejercicio`), `:568` (`errores_compartidos`), `:614` (`estadisticas_comision`), `:679` (`buscar_respuesta`), `:719` (`categorias_error_resumen`), `:1-60` (docstring del módulo)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `_normalizar_comisiones` (Task 9).

- [ ] **Step 1: Write the failing test**

```python
class MCPHerramientasORMTests(TestCase):
    """Las 7 herramientas de ORM directo aceptan comision_ids y cohorte_ids."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('MO', n_estudiantes=1)
        self.est = self.ests[0]
        for _ in range(3):
            _intento(self.est, self.ep, False, pc=self.pc)

    def test_errores_compartidos_singular_y_plural_coinciden(self):
        from mcp_intentos import errores_compartidos
        fn = errores_compartidos.fn if hasattr(errores_compartidos, 'fn') else errores_compartidos
        singular = async_to_sync(fn)(comision_id=self.com.id, min_estudiantes=1)
        plural = async_to_sync(fn)(comision_ids=[self.com.id], min_estudiantes=1)
        self.assertEqual(singular, plural)

    def test_categorias_error_resumen_acota_por_cohorte(self):
        from mcp_intentos import categorias_error_resumen
        fn = categorias_error_resumen.fn if hasattr(categorias_error_resumen, 'fn') else categorias_error_resumen
        vacio = async_to_sync(fn)(comision_ids=[self.com.id], cohorte_ids=[99999])
        self.assertEqual(vacio, [])

    def test_estadisticas_comision_sin_argumentos_es_global(self):
        from mcp_intentos import estadisticas_comision
        fn = estadisticas_comision.fn if hasattr(estadisticas_comision, 'fn') else estadisticas_comision
        datos = async_to_sync(fn)()
        self.assertGreaterEqual(datos['total_intentos'], 3)
```

Agregar el import necesario al principio del bloque de tests del MCP:

```python
from asgiref.sync import async_to_sync
```

> `db_tool()` envuelve la función en una corrutina registrada en FastMCP. El acceso `.fn` es el escape hatch de FastMCP para llamar la función original; el `hasattr` cubre las dos versiones de la librería.

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.MCPHerramientasORMTests -v 2
```

Expected: FAIL — `TypeError: ... unexpected keyword argument 'comision_ids'`

- [ ] **Step 3: Migrar las 7 herramientas**

El patrón es idéntico en todas: agregar `comision_ids` y `cohorte_ids` a la firma, resolver el alias y encadenar los dos filtros sobre el queryset.

`_listar_intentos_impl` (línea 313) — la firma agrega los dos parámetros al final para no romper el orden posicional:

```python
def _listar_intentos_impl(
    comision_id: Optional[int] = None,
    ejercicio_id: Optional[int] = None,
    solo_incorrectos: bool = False,
    limit: int = 50,
    offset: int = 0,
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
) -> list[dict]:
```

En el cuerpo, donde hoy filtra por `comision_id`, usar:

```python
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)
```

`listar_intentos` (línea 380) replica la firma de `_listar_intentos_impl` y le pasa los dos parámetros nuevos.

Para las otras seis, reemplazar cada bloque

```python
    if comision_id is not None:
        qs = qs.filter(practica_comision__comision_id=comision_id)
```

por

```python
    _comisiones = _normalizar_comisiones(comision_id, comision_ids)
    if _comisiones is not None:
        qs = qs.filter(practica_comision__comision_id__in=_comisiones)
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)
```

y agregar a cada firma:

```python
    comision_ids: Optional[list[int]] = None,
    cohorte_ids: Optional[list[int]] = None,
```

`estadisticas_comision` (línea 614) necesita más trabajo, porque hoy toma `comision_id: int` **obligatorio** y arranca resolviendo el objeto `Comision`:

```python
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
    """
    from ejercicios.models import Intento, Progreso, PracticaComision
    from cursos.models import Comision
    from django.db.models import Count
    from ejercicios.correctitud import Q_CORRECTO as _q_correcto

    _comisiones = _normalizar_comisiones(comision_id, comision_ids)

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
```

El resto del cuerpo (conteo de estudiantes y desglose por práctica) necesita el mismo tratamiento. Concretamente, en `mcp_intentos.py:614-678` hay tres querysets más que filtrar:

1. El conteo de estudiantes, que hoy sale de `comision.estudiantes.distinct().count()` sobre el objeto `Comision` que ya no se resuelve. Reemplazar por:

```python
    from cursos.models import Inscripcion
    insc_qs = Inscripcion.objects.all()
    if _comisiones is not None:
        insc_qs = insc_qs.filter(comision_id__in=_comisiones)
    if cohorte_ids is not None:
        insc_qs = insc_qs.filter(cohorte_id__in=cohorte_ids)
    total_estudiantes = insc_qs.values('estudiante_id').distinct().count()
```

2. El desglose por práctica, que agrupa `Intento` por `practica_comision_id`: usar `qs_intentos` (ya filtrado) en vez de `Intento.objects.filter(practica_comision_id__in=pc_ids)`.

3. El conteo de `Progreso` completado: encadenar `if cohorte_ids is not None: ... .filter(cohorte_id__in=cohorte_ids)`, igual que en el dashboard (Task 5), porque `Progreso` tiene FK propia a cohorte.

Verificar que el `try/except Comision.DoesNotExist` que hoy abre la función se borra: ya no hay una comisión única que resolver.

`intentos_por_estudiante` (línea 456) y `buscar_respuesta` (línea 679) filtran sobre un `qs` que ya existe; aplicar el mismo bloque de dos filtros.

`analizar_errores_ejercicio` (línea 511) idem, después del `qs = Intento.objects.filter(ejercicio_practica__ejercicio_id=ejercicio_id)`.

En los docstrings de las siete, agregar al bloque `Args:`:

```
        comision_ids: comisiones a incluir; None = todas.
        cohorte_ids: cohortes a incluir; None = todas. Ver ``listar_cohortes``.
```

y cambiar la descripción de `comision_id` a `alias singular heredado. Preferir ``comision_ids``.`

- [ ] **Step 4: Actualizar el índice del docstring del módulo**

En `mcp_intentos.py`, el docstring del módulo lista las herramientas (líneas 9 y 52-54). Agregar una nota al final del docstring:

```
Todas las herramientas analíticas aceptan ``comision_ids`` y ``cohorte_ids``
(listas de PK; None = todas). ``comision_id`` singular sigue funcionando como
alias. Los IDs salen de ``listar_comisiones`` y ``listar_cohortes``.
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.MCPHerramientasORMTests -v 2
```

Expected: PASS — 3 tests.

- [ ] **Step 6: Verificar que el servidor MCP importa y registra las herramientas**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' -c "import mcp_intentos; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Suite completa — cierre**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas -v 1
```

Expected: PASS, ~155 tests. Baseline eran 100 y ninguno debe haber empezado a fallar.

- [ ] **Step 8: Suite global**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test -v 1
```

Expected: PASS. Esta corrida cubre `docentes`, que consume el endpoint `detalle_ejercicio` desde `practica_detail.html`.

- [ ] **Step 9: Commit**

```bash
git add mcp_intentos.py analiticas/tests.py && git commit -m "feat(mcp): las 7 herramientas de ORM aceptan comision_ids y cohorte_ids"
```

---

## Verificación manual final

Después de la Task 10, con el servidor corriendo:

- [ ] `/analiticas/dashboard/` sin filtro muestra lo mismo que antes del cambio.
- [ ] Tildar una comisión y aplicar: las tarjetas y las 12 secciones se acotan.
- [ ] Tildar una cohorte: los conteos bajan y el denominador "completaron X de N" cambia.
- [ ] "Limpiar" vuelve al estado sin filtro.
- [ ] `/analiticas/investigacion/`: el bloque de descarga ya no tiene selectores propios y los botones CSV/XLSX/ODS bajan exactamente el recorte que se ve en pantalla.
- [ ] `/analiticas/encuesta/`: idem con la barra de filtros.
- [ ] Como docente (no staff): la barra solo lista las comisiones propias.

# Filtros por comisión y cohorte en todas las analíticas

Fecha: 2026-08-25

## Objetivo

Que las tres páginas de analíticas, sus exportaciones, sus endpoints JSON y las
herramientas del servidor MCP acepten el mismo par de filtros: **comisiones**
(multi-selección) y **cohortes** (multi-selección).

Hoy las páginas agregan siempre *todas* las comisiones visibles al usuario y
*todas* las camadas. Eso mezcla en un mismo número a un estudiante de 2026-C1
con uno de 2026-C2, y a un recursante consigo mismo en dos camadas.

## Estado actual

La capa de cálculo ya está mayormente preparada; lo que falta es exponer los
filtros:

| Capa | Estado |
|---|---|
| `analiticas/research.py` | Completa. Todas las funciones públicas aceptan `comision_ids` + `cohorte_ids`. |
| `analiticas/views.py` (helpers del dashboard) | Los 8 helpers aceptan `cohorte_id` **singular**. Ningún caller se lo pasa. |
| `analiticas/calculos.py` (M2–M6) | Aceptan `comision_id` **singular**, sin cohorte. |
| `analiticas/anonimizador.py` | Acepta `anio`/`cuatri`, no `cohorte_ids`. |
| Vistas `dashboard` / `investigacion` / `encuesta_resumen` | No leen ningún filtro del querystring. |
| `mcp_intentos.py` | ~25 herramientas ya aceptan `comision_ids` + `cohorte_ids`; 12 no. |

El único filtro de UI existente (comisiones + cohorte en `investigacion.html`)
alimenta solo los links de descarga, no lo que se muestra en pantalla.

Los modelos ya tienen todo lo necesario: `Inscripcion.cohorte`, `Intento.cohorte`
y `Progreso.cohorte` son FK directas.

## Decisiones tomadas

1. **Alcance**: las 3 páginas de analíticas, los botones de exportación y los
   endpoints JSON. El panel docente (`docentes/`) queda fuera.
2. **Selección**: multi-select en ambos filtros.
3. **Persistencia**: ninguna. Cada página abre sin filtro (comportamiento actual)
   y el filtro vive solo en la URL de esa página.
4. **Bloque de descarga**: se unifica. Los selectores propios del bloque en
   `investigacion.html` desaparecen; las descargas usan el filtro de la página.
5. **Parámetro de cohorte**: `cohorte_ids=5,7` (PKs) es el canónico;
   `cohorte=YYYY-C` se sigue aceptando como alias.
6. **MCP**: las 12 herramientas rezagadas pasan a aceptar `comision_ids` y
   `cohorte_ids`; `comision_id` singular sobrevive como alias.
7. **M2–M6**: se refactorizan a multi-comisión, así que dejan de depender de que
   el usuario tenga exactamente una comisión.

## Arquitectura

### `analiticas/filtros.py` (nuevo)

Un único punto de resolución de permisos y parseo:

```python
@dataclass(frozen=True)
class FiltroAnaliticas:
    comision_ids: list[int]        # selección ∩ permitidas, o todas las permitidas
    cohorte_ids: list[int] | None  # None = todas
    comisiones: QuerySet           # permitidas, para dibujar los checkboxes
    cohortes: list[dict]           # opciones disponibles
    qs: str                        # querystring canónico para links de export
    activo: bool                   # hay filtro explícito puesto
    vacio_por_permisos: bool       # pidió comisiones y ninguna era suya

def resolver_filtros(request) -> FiltroAnaliticas: ...
```

Reglas:

- Comisiones permitidas: `is_staff` → todas; docente → `filter(docentes=user)`.
- Los IDs pedidos que no estén en el conjunto permitido se descartan.
- Sin selección → todas las permitidas, `activo=False`.
- Selección explícita que queda vacía tras el chequeo → `vacio_por_permisos=True`.
  La página muestra estado vacío con aviso; **no** se amplía en silencio a
  "todas", porque eso mentiría sobre lo que se está viendo.
- Las opciones de cohorte se calculan sobre **todas** las comisiones permitidas,
  no sobre las tildadas, para que la lista sea estable sin recargar al tildar.

`exportar`, `descargar_investigacion` y `red_errores_json` pasan a usar esta
función, eliminando las tres copias del chequeo de permisos que hoy tienen
duplicado literalmente.

### `templates/analiticas/_filtros.html` (nuevo)

Barra Alpine idéntica en las 3 páginas: checkboxes de comisiones + checkboxes de
cohortes + "Aplicar" (submit GET) y "Limpiar". Sin fetch: recarga la página, que
es donde se calcula todo.

En `investigacion.html` reemplaza a los selectores del bloque de descarga; ese
bloque pasa a construir sus URLs desde `filtros.qs`.

## Cambios por archivo

### `analiticas/views.py`

- Los 8 helpers del dashboard: `cohorte_id=None` → `cohorte_ids=None`
  (`cohorte_id__in`). Cambio mecánico, sin callers que romper.
- `dashboard`, `investigacion`, `encuesta_resumen`: llaman `resolver_filtros` y
  propagan `comision_ids` / `cohorte_ids` a cada sección.
- `_datos_exportacion(dataset, comision_ids)` → `(dataset, comision_ids, cohorte_ids)`.
- `detalle_ejercicio` y `red_errores_json`: aceptan `comision_ids` y `cohorte_ids`.

Dos números del dashboard hoy serían incorrectos bajo filtro de cohorte y hay que
arreglarlos:

- `total_estudiantes` (denominador de "completaron X de N") es hoy
  `comision.estudiantes.distinct().count()`, sobre todas las camadas. Pasa a
  contar `Inscripcion` de las cohortes filtradas.
- `completaron_map` cuenta `Progreso`, que tiene FK propia a cohorte: se filtra ahí.

### `analiticas/calculos.py`

Las 5 funciones M2–M6 (`_matriz_juicio_computo`, `_convergencia_por_ejercicio`,
`_perfil_error_tabla`, `_indice_atomizacion`, `_patron_adivinacion`) pasan a
`comision_ids: list[int]` + `cohorte_ids=None`.

Cada una usa `comision_id` en **un solo lugar**
(`practica_comision__comision_id=`), así que el refactor es una línea por función
más firma y docstring.

Consecuencia a documentar en el docstring: estas funciones agrupan por
`(estudiante, ejercicio)`. Con varias comisiones, un estudiante inscripto en más
de una ve sus intentos unificados en una sola secuencia. Es el comportamiento
correcto para "convergencia de este estudiante en este ejercicio", pero es un
cambio respecto de hoy y conviene que esté escrito.

### `analiticas/anonimizador.py`

`dataset_encuesta` y `dataset_intentos` reciben `cohorte_ids=None` además de los
`anio`/`cuatri` actuales, que se conservan.

### `analiticas/research.py`

Sin cambios.

### `mcp_intentos.py`

Las 12 herramientas rezagadas pasan a aceptar `comision_ids: list[int] | None` y
`cohorte_ids: list[int] | None`, con `comision_id: int | None` como alias:

| Herramienta | Origen |
|---|---|
| `listar_intentos` | ORM directo |
| `intentos_por_estudiante` | ORM directo |
| `analizar_errores_ejercicio` | ORM directo |
| `errores_compartidos` | ORM directo |
| `estadisticas_comision` | ORM directo |
| `buscar_respuesta` | ORM directo |
| `categorias_error_resumen` | ORM directo |
| `matriz_juicio_computo` | `calculos.py` |
| `convergencia_por_ejercicio` | `calculos.py` |
| `perfil_error_tabla` | `calculos.py` |
| `indice_atomizacion` | `calculos.py` |
| `patron_baja_variacion` | `calculos.py` |

Las 5 de `calculos.py` solo tienen que pasar los parámetros al wrapper una vez
hecho el refactor de arriba. Las 7 de ORM directo filtran sobre
`Intento.cohorte_id__in` y `practica_comision__comision_id__in`.

Un helper local `_normalizar_comisiones(comision_id, comision_ids)` resuelve el
alias en un solo lugar en vez de repetirlo 12 veces.

Cinco de estas herramientas (`estadisticas_comision`, `matriz_juicio_computo`,
`convergencia_por_ejercicio`, `perfil_error_tabla`, `indice_atomizacion`) hoy
tienen `comision_id` **obligatorio**. Al volverse opcional, llamarlas sin
comisión deja de ser un error y pasa a significar "todas las comisiones",
igual que en el resto del servidor. Es el comportamiento deseado, pero es un
cambio de contrato y va explícito en cada docstring.

El MCP se autentica con un único usuario admin (`MCP_ADMIN_USERNAME`), sin
scoping por docente: ahí no hay chequeo de permisos que replicar, solo filtros.
`filtros.py` es exclusivamente web.

Los wrappers `*_compat` existentes siguen funcionando sin cambios: pasan
`args`/`kwargs` como dict y los nombres nuevos entran por ahí.

`listar_cohortes` ya existe y devuelve los IDs a usar; su docstring ya apunta a
`cohorte_ids`. Se actualiza el índice de herramientas del docstring del módulo
(líneas 9 y 52-54) para reflejar las firmas nuevas.

## Semántica por página

**Dashboard.** Todas las secciones se acotan. Los paneles **⊞ Juicio vs. cómputo**
y **🔁 Baja variación**, que hoy solo aparecen si el usuario tiene exactamente una
comisión, pasan a mostrarse siempre gracias al refactor de M2–M6.

**Investigación.** La sección **E2. Cohortes** es un desglose *por* cohorte:
filtrar a una la colapsa a una fila. Es correcto, pero el panel se deja visible
(no oculto) para que no parezca roto.

**Encuesta.** `distribuciones_encuesta_detalle` y el resto de las funciones de
`research` ya aceptan ambos filtros.

## Tests

En `analiticas/tests.py`, que ya tiene fixtures de comisiones y cohortes:

- `resolver_filtros`: descarta comisiones ajenas para un docente, acepta todas
  para staff, parsea `cohorte_ids` y el alias `cohorte=YYYY-C`, vacío = todas,
  y marca `vacio_por_permisos` cuando corresponde.
- Una prueba por página: con dos cohortes cargadas, `?cohorte_ids=<c1>` cambia
  los números y no incluye ningún intento de C2.
- Recursante (mismo estudiante en dos cohortes de la misma comisión): el
  denominador del dashboard no lo cuenta dos veces ni mezcla camadas.
- Los links de exportación llevan el filtro y el CSV resultante coincide con lo
  mostrado en pantalla.
- M2–M6 con dos comisiones devuelven la agregación de ambas, y con
  `comision_ids=[una]` replican exactamente el resultado que hoy da
  `comision_id=una` (test de no-regresión del refactor).
- MCP: `comision_id=1` y `comision_ids=[1]` devuelven lo mismo en las 12
  herramientas tocadas.

## Fuera de alcance

- El panel docente (`docentes/views.py`, `practica_detail`).
- Persistencia del filtro entre páginas.
- Cualquier filtro que no sea comisión o cohorte.

## Estimación

Sin migraciones. Aproximadamente 400 líneas nuevas (módulo, partial, tests) y 300
modificadas repartidas entre `views.py`, `calculos.py`, `anonimizador.py`,
`mcp_intentos.py` y las 3 plantillas.

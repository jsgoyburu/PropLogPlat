# Task 3 — reporte

**Nota sobre la procedencia de este reporte.** La Task 3 la ejecutaron dos
subagentes; ninguno llegó a escribir su reporte ni a commitear (el primero se
cortó por límite de sesión en el step 14, el segundo devolvió control mientras
esperaba una corrida de tests). El controller verificó el working tree, corrió
la suite completa y commiteó. Este reporte documenta lo verificado, no lo que
los agentes dijeron haber hecho.

## Commit

`8ee8b54` — feat(cohorte): backfill, NOT NULL, clave por cohorte y write path

Base: `a1fb998`. 17 archivos, +627/−181.

## Archivos

**Nuevos:**
- `cursos/cohortes.py` — `cohorte_activa()` y `cohorte_de(estudiante, comision)`
- `cursos/migrations/0009_backfill_cohorte.py` — backfill a 2026-C1, `atomic = False`
- `cursos/migrations/0010_cohorte_not_null.py`
- `ejercicios/migrations/0028_cohorte_not_null.py`

**Modificados (producción):**
- `cursos/models.py` — `Inscripcion.unique_together` → `['estudiante', 'comision', 'cohorte']`; quitado `null=True`/`blank=True` de los campos `cohorte`
- `ejercicios/models.py` — `Progreso.unique_together` → `['estudiante', 'practica_comision', 'cohorte']`; quitado `null=True`/`blank=True`
- `ejercicios/progreso.py` — `eps_resueltos`, `esta_resuelto` y `avanzar_progreso` con `cohorte` como cuarto parámetro obligatorio
- `ejercicios/api/views.py` — resuelve cohorte vía `cohorte_de`, 403 si no hay inscripción, estampa `cohorte` en el `Intento`
- `ejercicios/views.py` — pasa cohorte a `esta_resuelto`
- `docentes/views.py` — `_avanzar_progreso_por_aprobacion_docente` pasa `intento.cohorte`

**Modificados (call sites que el plan NO había listado):**
- `accounts/views.py` — `acceso_comision` crea `Inscripcion` por auto-registro; ahora usa `cohorte_activa()`
- `ejercicios/backfill.py` — helper histórico de la migración 0024 que crea `Progreso`; guard `tiene_cohorte` siguiendo el patrón `tiene_practica` que ya existía

**Modificados (tests):** `cursos/tests.py`, `ejercicios/tests.py`, `docentes/tests.py`,
`analiticas/tests.py`, `accounts/tests.py`

## Tests

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test -v 1
Ran 283 tests in 985.142s
OK
```

**Gotcha de entorno encontrado.** Una primera corrida sin `PYTHONIOENCODING=utf-8`
y con la salida redirigida dio `FAILED (errors=3)` con
`UnicodeEncodeError: 'charmap' codec can't encode character '→'`. La suite
emite un `→` que la consola de Windows en cp1252 no puede escribir. No es un
defecto del código: con UTF-8 forzado la misma suite da OK. Cualquier corrida
futura que redirija salida en esta máquina necesita `PYTHONIOENCODING=utf-8`.

## Riesgos y dudas para el review

1. **`cohorte_activa()` puede devolver `None`.** En `accounts/views.py` el
   `get_or_create` con `cohorte=cohorte_activa()` intentaría insertar `NULL`
   contra una columna `NOT NULL` si no hubiera ninguna cohorte activa. No pasa
   hoy (el backfill crea 2026-C1 activa) pero es una arista sin guarda.
2. **Trabajo hecho por dos agentes distintos**, el primero interrumpido a mitad
   de una edición en `ejercicios/tests.py`. Vale mirar ese archivo con atención
   por si quedó algo a medias que la suite no detecte.
3. El plan no listaba los dos call sites extra; conviene confirmar que no queda
   ningún otro creador de `Inscripcion`/`Intento`/`Progreso`/`Parcial` sin
   cohorte fuera de tests.

---

# Arreglos del review (commit siguiente)

Los tres hallazgos del review se corrigieron en un solo pase. El subagente
fixer no commiteó ni escribió reporte (devolvió control esperando una corrida);
el controller verificó el diff, corrió la suite completa y commiteó.

## Hallazgo 1 (CRITICAL) — read path del estudiante sin cohorte

`ejercicios/views.py`:
- `home`: arma un `Q()` por comisión con la cohorte que `cohorte_de` resuelve
  para esa comisión, y filtra los `Progreso` con ese OR. Antes el dict se
  quedaba con una fila arbitraria cuando un recursante tenía dos.
- `practica_detail`: resuelve `cohorte_est` y lo usa tanto en el subquery
  `ultimo_intento_qs` como en el `Progreso.objects.get`.
- `ejercicio_detail`: usa el `cohorte_est` que ya calculaba para `esta_resuelto`.

Test: `ejercicios.tests.RecursanteReadPathTests`.

## Hallazgo 2 (CRITICAL) — management commands creaban Progreso sin cohorte

`reconciliar_progreso_aprobaciones.py` y `reevaluar_tablas_verdad.py` ahora
propagan `cohorte_id` derivado del propio `Intento` (que ya la tiene, NOT NULL
desde 0027). Además de los `create`/`get_or_create`, se acotó por cohorte las
queries intermedias de `Intento` y `Progreso` dentro de ambos comandos.

Test: `ejercicios.tests.ReconciliarProgresoAprobacionesCommandTests`.

## Hallazgo 3 (IMPORTANT) — cohorte_activa() None sin guarda

Cuatro call sites guardados:
- `accounts/views.py:acceso_comision` — las dos ramas (autenticada y anónima),
  con mensaje al estudiante en vez de un 500. Es endpoint público.
- `docentes/views.py:estudiante_create` y `parcial_create` — `messages.error` y
  redirect, sin crear nada.
- `docentes/views.py:_procesar_importacion_estudiantes` — `RuntimeError`, que es
  lo que `estudiantes_importar` ya capturaba para mostrar `messages.error`.

Tests: en `accounts/tests.py` (+46) y `docentes/tests.py` (+48).

## Suite completa tras los arreglos

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test -v 1
Ran 293 tests in 1411.851s
OK
```

---

# Hallazgo adicional (panel docente) — `_build_progreso_estudiantes` sin filtro de cohorte

Commit: `8817c80` — fix(cohorte): _build_progreso_estudiantes filtra el progreso
por cohorte del estudiante. Base: `60edc47`. 2 archivos, +112/−5.

## Qué cambié

`docentes/views.py:_build_progreso_estudiantes` (líneas ~343-393). El mismo
patrón que ya se había corregido en `ejercicios/views.py:home` (Hallazgo 1
arriba), pero en el panel docente en vez del read path del estudiante.
`PracticaComision` no tiene cohorte propia (pertenece a la `Comision`, que
persiste entre camadas), así que un recursante de la misma comisión tiene una
fila de `Progreso` por cohorte para el mismo `practica_comision`.
`progresos_index` armaba `pc.id -> {estudiante_id: progreso}` con un dict
comprehension sobre `pc.progresos.all()` sin filtrar por cohorte: para un
recursante con dos filas, se quedaba con una arbitraria según el orden de
iteración (sin `ORDER BY` explícito, ese orden no está garantizado). Esa fila
alimentaba `ejercicio_actual`, mostrado en la tabla de progreso del docente
(celda "Ej. N" en `templates/docentes/comision_detail.html`). No crasheaba
(`.get()` de dict), pero podía mostrar el puntero de la camada equivocada.

**Cómo acoté el índice.** En vez de llamar `cohorte_de(estudiante, comision)`
por estudiante (una query cada vez), calculé el mapeo `estudiante_id ->
cohorte_id` en una sola pasada de Python sobre `comision.inscripciones.all()`
(ya traída en una sola query, prefetcheada en `comision_detail` y consultada
una vez en `estudiante_create`/`estudiantes_importar`), ordenando por
`(fecha_inscripcion, id)` ascendente y dejando que el último sobreescriba —
mismo criterio de desempate que `cohorte_de` (más reciente por fecha, y por id
si hay empate), sin queries adicionales por estudiante. Con eso,
`progresos_index` pasó a indexar por `(estudiante_id, cohorte_id)` en vez de
solo `estudiante_id`, y el lookup de `progreso` usa la cohorte resuelta de
cada estudiante. No toqué `aprobados_count`, `resueltos_count`, `completada`
ni `porcentaje_global`: siguen acumulativas entre camadas, como están
documentadas.

Verifiqué los tres call sites (`comision_detail` con el prefetch de
`progresos` sobre `practicas_comisiones`, y `estudiante_create` /
`estudiantes_importar` sin ese prefetch): el cambio no depende del prefetch,
solo evita repetirlo mejor cuando existe; en los otros dos no había prefetch
antes y sigue sin haberlo (mismo perfil de queries que antes de este fix,
ninguna query nueva por estudiante).

## Test agregado

`docentes/tests.py:ProgresoDocenteRecursanteUsaCohorteActualTests` (2 tests).
Mismo patrón que `ejercicios.tests.RecursanteReadPathTests`: ids de `Cohorte`
creados deliberadamente al revés del orden cronológico real, para que el test
no dependa por accidente del id de cohorte. Un estudiante recursante con dos
`Inscripcion` en la misma comisión (vieja primero, actual después) y dos
`Progreso` para el mismo `practica_comision` — uno por cohorte, con punteros
distintos (`ep2` en la cohorte actual, completada/`None` en la vieja, y el de
la cohorte actual creado primero para que el bug real de orden de iteración
del dict se manifieste). Un test llama `_build_progreso_estudiantes`
directamente; el otro pasa por la vista completa `comision_detail` para cubrir
el prefetch real. Confirmé que ambos fallan sin el fix (`None != ep2`) y pasan
con el fix.

## Comando y salida

Corrida de los dos tests nuevos antes del fix (falla, confirma el bug):

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes.tests.ProgresoDocenteRecursanteUsaCohorteActualTests -v 2
...
FAIL: test_panel_docente_completo_muestra_ejercicio_actual_correcto
AssertionError: None != <EjercicioPractica: P-recursa-panel – Ej. 2: [Formalización] E2>
FAIL: test_panel_muestra_ejercicio_actual_de_la_cohorte_del_estudiante
AssertionError: None != <EjercicioPractica: P-recursa-panel – Ej. 2: [Formalización] E2> : Debería mostrar el puntero de la cohorte actual (ep2), no el de la cohorte vieja (completa, None)
Ran 2 tests in 7.864s
FAILED (failures=2)
```

Corrida tras el fix:

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes.tests.ProgresoDocenteRecursanteUsaCohorteActualTests -v 2
...
ok (x2)
Ran 2 tests in 10.924s
OK
```

Suite `docentes` completa tras el fix:

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes -v 1
Ran 86 tests in 449.689s
OK
```

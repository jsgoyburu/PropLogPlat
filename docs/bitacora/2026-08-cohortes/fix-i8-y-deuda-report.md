# Reporte: fix I8 + deuda de tests de I6/I7 (review final de rama, cohorte)

Rama `claude/desbloqueo-configurable`, base `f12c125`.

## Parte 1 — I8: doble conteo por join

### Dónde vivía el bug

- `analiticas/views.py:824` (dentro de `dashboard()`) — `total_estudiantes = comision.estudiantes.count()`.
- `analiticas/views.py:809-820` — `completaron_map`, agregado con
  `Count('pk')` sobre `Progreso` joineado contra
  `estudiante__inscripciones__comision=F('practica_comision__comision')`.
- `mcp_intentos.py:665` (dentro de `estadisticas_comision()`) — mismo
  `comision.estudiantes.count()`.

`comision.estudiantes` es un M2M a través de `Inscripcion`. Un recursante
tiene dos filas de `Inscripcion` en la misma comisión (una por cohorte), así
que el `JOIN` implícito duplica su fila tanto en el `.count()` del M2M como
en el `Count('pk')` de `completaron_map` (cada `Progreso` sale una vez por
cada `Inscripcion` que matchea el `F()`).

### Decisión: ¿"distintos de todas las camadas" o "de una camada"?

Miré las dos pantallas que consumen estos números:

1. **`analiticas/views.py::dashboard`** (`analiticas/dashboard.html`) — este
   panel **ya tenía, desde `f12c125`, una decisión explícita y documentada**
   de agregar todas las camadas sin filtrar por cohorte (ver el comentario
   en `views.py` alrededor de la línea 846-851, sobre `_estudiantes_dashboard`,
   que se pasa sin filtro de cohorte a `_ejercicios_mas_dificiles`,
   `_estudiantes_en_riesgo`, etc., "para no cambiar en silencio los números
   que este panel de investigación viene reportando"). `total_estudiantes` y
   `completaron_map` son parte de ese mismo panel agregado (mismo bloque de
   código, mismo `for comision in comisiones` sin filtro de cohorte en
   ningún otro lado de la función). Cambiarlos a "por cohorte" habría sido
   inconsistente con el resto de la misma vista.
2. **`mcp_intentos.py::estadisticas_comision`** — no tiene parámetro de
   cohorte en absoluto (`comision_id` es el único filtro), y la métrica
   hermana en la misma función (`completaron`, unas líneas más abajo) **ya
   usa `.distinct()` sobre `estudiante_id`** para no duplicar. Alinear
   `total_estudiantes` con esa misma convención (distintos, todas las
   camadas) es lo consistente dentro de la propia función.

**Decisión: en ambos casos, "estudiantes distintos de todas las camadas de
la comisión"**, no filtrado por cohorte. No es un cambio de alcance — ambos
sitios ya agregaban todas las camadas antes del bug, solo que sin
deduplicar al recursante. Lo que no puede quedar es que la misma persona
cuente dos veces, y esa parte sí se corrigió.

### Fix

- `analiticas/views.py`: `comision.estudiantes.count()` →
  `comision.estudiantes.distinct().count()`.
- `analiticas/views.py`: `completaron_map` — `Count('pk')` →
  `Count('pk', distinct=True)` (el join duplica la fila de `Progreso`, no
  crea filas de `Progreso` nuevas; `distinct` sobre el `pk` alcanza).
- `mcp_intentos.py`: `comision.estudiantes.count()` →
  `comision.estudiantes.distinct().count()`.

Comentarios agregados en el código explicando el motivo del `distinct()` en
los tres puntos.

### Verificación

Agregué `analiticas.tests.DashboardNoDoblesCuentaAlRecursanteTests` (dos
tests) cubriendo `total_estudiantes` y `completaron` con un recursante real
(dos `Inscripcion`, un solo `Progreso` completo). Confirmé que **fallan
contra el código pre-fix** (`git stash` de `analiticas/views.py` y
`mcp_intentos.py`, corrida, `2 != 1` en ambos, luego `git stash pop` para
restaurar el fix) y pasan después. `mcp_intentos.py` no tiene suite de
Django (no hay tests para MCP tools en este repo); se verificó por lectura +
el mismo patrón de `.distinct()` ya usado ahí mismo para `completaron`, y se
confirmó que el módulo sigue importando sin error tras el cambio.

## Parte 2 — Deuda de tests de I6 e I7 (commit `569b6d4`)

Referencia: `.git/sdd/fix-i6-i7-report.md`. El código de `569b6d4` estaba
correcto por lectura; los tests confirman que también lo está en ejecución
(no encontré ningún bug real al escribir estos tests).

### `ejercicios/tests.py` — los tres management commands

Siguiendo el patrón de `ReconciliarProgresoAprobacionesCommandTests` y
`ReevaluarTablasVerdadCommandTests` (comandos hermanos ya corregidos y
testeados en `60edc47`): un estudiante recursante con dos `Inscripcion` (y
dos `Progreso`, uno por cohorte) en la misma `PracticaComision`, ambos
bloqueados en el mismo ejercicio (`ep1`). Se corrige, con el comando bajo
prueba, un único `Intento` de la cohorte **actual**. Se verifica que el
`Progreso` de la cohorte actual avanza a `ep2` y que **el de la cohorte
vieja queda intacto en `ep1`** (no tiene ningún intento corregido que lo
justifique).

El `Progreso` de la cohorte vieja se crea *antes* que el de la cohorte
actual a propósito: antes del fix de `569b6d4`, `.filter(estudiante_id,
practica_comision_id).first()` (sin `cohorte_id`) hubiera devuelto esa fila
primero y la habría avanzado por error, dejando la de la cohorte actual
bloqueada — exactamente el bug que el commit corrigió.

- `ReconciliarVMayusculaCommandTests` (2 tests): escenario de formalización
  con bug de "V" mayúscula (`(JvM).~(J.M)` → `(J∨M).~(J.M)`), más
  `--dry-run` (confirma que ningún `Progreso` se toca en dry-run).
- `CorregirEjercicioJuicioCommandTests` (2 tests): escenario `tabla_verdad`
  con renombramiento de variables (mismo patrón de datos que
  `ReevaluarTablasVerdadCommandTests`, usando `--ejercicio-id`), más
  `--dry-run`.
- `RecorregirTablaVerdadCommandTests` (2 tests): mismo escenario
  `tabla_verdad`, sin `--ejercicio-id` (el comando es global), más
  `--dry-run`.

Total: 6 tests nuevos, todos verdes.

### `analiticas/tests.py` — `dataset_intentos` (I7)

`DatasetIntentosRecursanteCohorteTests` (2 tests): recursante con
`Inscripcion` en 2026-C1 y 2027-C1 en la misma comisión, con un `Intento` en
cada cohorte.

- `test_filtro_de_cohorte_excluye_los_intentos_de_la_otra_camada`: pedir
  `anio=2027, cuatri=1` devuelve solo el intento de esa cohorte.
- `test_sin_filtro_devuelve_los_intentos_de_ambas_camadas`: sin filtro
  (`anio=None`), siguen apareciendo los intentos de las dos camadas — no
  regresiona el caso default.

**Caso de `practica_comision__isnull=True` combinado con filtro de
cohorte** (mencionado en la deuda original): no lo pude construir como test.
Desde la migración `ejercicios/0026_intento_practica_comision_obligatoria`,
`Intento.practica_comision` es `NOT NULL` a nivel de columna en la base de
datos — ni siquiera un `.update(practica_comision=None)` que bypasee las
validaciones del modelo pasa la constraint de la base de test. Ese caso solo
podía existir en datos históricos pre-0026; no es reproducible con el
esquema actual, así que no hay forma de escribir un test que lo ejerza sin
manipular la base por fuera del ORM (y del ciclo de vida real de la app). Lo
dejo documentado acá en vez de forzar un test artificial.

## Comandos y salida

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'
python manage.py test analiticas.tests.DashboardNoDoblesCuentaAlRecursanteTests analiticas.tests.DatasetIntentosRecursanteCohorteTests ejercicios.tests.ReconciliarVMayusculaCommandTests ejercicios.tests.CorregirEjercicioJuicioCommandTests ejercicios.tests.RecorregirTablaVerdadCommandTests ejercicios.tests.HistorialPorCohorteTests -v 1
```
```
Ran 14 tests in 47.846s

OK
```

(`HistorialPorCohorteTests` se incluyó porque al insertar las nuevas clases
al final de `ejercicios/tests.py` corté por error, en un primer intento, el
método `test_el_encabezado_de_camada_se_renderiza` de esa clase en dos —
detectado por el `NameError: name 'resp' is not defined` en la primera
corrida, corregido reuniendo las dos líneas `assertContains` en el mismo
método, y reverificado con esta clase incluida en la corrida.)

```
python -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','logica_ipc.settings'); django.setup(); import mcp_intentos; print('ok')"
```
```
ok
```

```
python manage.py check
```
```
System check identified no issues (0 silenced).
```

Verificación de que los tests de I8 fallan sin el fix (`git stash push --
analiticas/views.py mcp_intentos.py`, correr, `git stash pop`):

```
FAIL: test_completaron_no_duplica_al_recursante ... AssertionError: 2 != 1
FAIL: test_total_estudiantes_no_duplica_al_recursante ... AssertionError: 2 != 1
FAILED (failures=2)
```

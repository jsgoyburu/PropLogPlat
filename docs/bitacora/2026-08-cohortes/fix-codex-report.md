# Fix: cuatro hallazgos del review automatizado de PR #189

Commit: `98428d19da49d7b0c5d05890e02b07d708e137b4`
Rama: `claude/desbloqueo-configurable`
Base: `3b314e54756ae95a4cbe7619543c69b7e5ceffff`

## 1. `trabajo_vs_nota_logica` elegía el primer parcial antes de filtrar cohorte

**Archivo:** `analiticas/research.py`, función `trabajo_vs_nota_logica`.

**Antes:** `primer_parcial` se armaba iterando `Parcial.objects.filter(comision_id__in=comision_ids).order_by('fecha')`
y quedándose con el primero por comisión (`setdefault(parcial.comision_id, parcial)`). El filtro de
`cohorte_ids` se aplicaba recién después, sobre `notas` (`notas.filter(parcial__cohorte_id__in=cohorte_ids)`).
Si el parcial más viejo de la comisión pertenecía a otra cohorte que la pedida, `notas` quedaba vacío
y la función devolvía `n=0` en vez de usar el primer parcial de la cohorte pedida.

**Cambio:**
- El queryset de `Parcial` se acota a `cohorte_ids` **antes** de elegir uno por comisión
  (`parciales_qs = parciales_qs.filter(cohorte_id__in=cohorte_ids)` si `cohorte_ids is not None`).
- La clave del dict `primer_parcial` pasa de `comision_id` a `(comision_id, cohorte_id)`, así que si
  se piden varias cohortes cada una aporta su propio primer parcial en vez de competir por un único
  primer parcial de la comisión entera.
- El filtro redundante `notas.filter(parcial__cohorte_id__in=cohorte_ids)` se elimina: ya no hace
  falta, porque cada `parcial` en `primer_parcial.values()` ya pertenece a una única cohorte (la que
  quedó fijada en la clave).
- Docstring actualizado para documentar el comportamiento por (comisión, cohorte).

## 2. Indicadores de uso de plataforma no acotados por cohorte

**Archivo:** `analiticas/calculos.py`, función `calcular_uso_plataforma_antes_parcial`.

**Antes:** el queryset de `Intento` filtraba por `estudiante`, `practica_comision__comision` y
`timestamp__lt=fecha_corte`, pero no por cohorte. Para un recursante, los intentos de una camada vieja
anteriores a la fecha del parcial de la camada nueva entraban en los indicadores de esfuerzo de la
camada nueva.

**Cambio:** se agrega `cohorte=parcial.cohorte` al filtro de `Intento`.

**Decisión pedida — otros llamadores:** busqué todos los usos de `calcular_uso_plataforma_antes_parcial`
en el repo (`grep -rn "calcular_uso_plataforma_antes_parcial\("`). Hay exactamente dos llamadores además
de la definición:
- `analiticas/research.py::trabajo_vs_nota_logica` (el hallazgo 1, ya cubierto arriba).
- `cursos/management/commands/exportar_cohorte.py` (línea ~141, dentro del loop de export), que llama
  `calcular_uso_plataforma_antes_parcial(est, parcial)` para cada inscripto de la cohorte que se está
  exportando.

Ambos llamadores **quieren** el comportamiento acotado por cohorte: `exportar_cohorte` ya filtra las
inscripciones por `cohorte` explícitamente (línea 87, `comision.inscripciones.filter(cohorte=cohorte)`),
así que antes del fix un recursante exportado bajo la cohorte nueva se llevaba puesto el uso de
plataforma de la cohorte vieja en su fila del CSV — el mismo bug que en `trabajo_vs_nota_logica`, solo
que sin test previo. No encontré ningún llamador que necesite el comportamiento viejo (sin acotar por
cohorte), así que el fix es incondicional dentro de la función, sin flag.

## 3. `exportar_cohorte` aceptaba `--cohorte-id`/`--parcial-id` inconsistentes

**Archivo:** `cursos/management/commands/exportar_cohorte.py`, método `handle`.

**Antes:** si se pasaban ambas opciones y el parcial pertenecía a otra cohorte que la explícita, la
explícita ganaba sin verificar nada. El CSV resultante iteraba las inscripciones de la cohorte explícita
y les adjuntaba las notas/uso del parcial de la otra cohorte para quienes recursan.

**Cambio:** cuando se pasa `--cohorte-id` y también hay un `parcial` resuelto (por `--parcial-id`), se
verifica `parcial.cohorte_id != cohorte.id` y se levanta `CommandError` con un mensaje explícito antes
de seguir.

## 4. `demora_primer_intento` duplicaba a los recursantes

**Archivo:** `analiticas/research.py`, función `demora_primer_intento`.

**Antes:** `primeros` se indexaba solo por `estudiante` (`Intento...values('estudiante').annotate(primer=Min('timestamp'))`),
pero `inscriptos` salía de `Inscripcion.objects.filter(...).values('estudiante_id', 'comision_id')`
sin deduplicar. Un recursante con dos `Inscripcion` en la misma comisión (una por cohorte) aportaba dos
filas idénticas de `inscriptos`, y como ambas resolvían al mismo `primeros[estudiante_id]`, la función
emitía dos filas estudiante×práctica idénticas para la misma persona — con `cohorte_ids=None` (default)
y también al pedir varias cohortes que incluyan las dos inscripciones del recursante.

**Cambio:** se deduplica `inscriptos` con `.values('estudiante_id', 'comision_id').distinct()`.

**Decisión pedida — deduplicar vs. incluir cohorte en la clave:** elegí **deduplicar por
`(estudiante_id, comision_id)`**, no incluir `cohorte_id` en la clave/fila devuelta. Razones:

1. La función está documentada como nivel "estudiante × práctica" (no por cohorte); el output actual
   (`comision_id`, `estudiante_id`, `dias_demora`) no tiene columna de cohorte y agregarla sería un
   cambio de esquema.
2. Es el patrón ya establecido en el repo para este mismo problema (recursante con dos `Inscripcion`
   en la misma comisión): `analiticas/anonimizador.py::dataset_intentos` usa
   `est_comision.setdefault(insc['estudiante_id'], insc['comision_id'])` — primera inscripción gana,
   una fila por estudiante — y el test `DashboardNoDoblesCuentaAlRecursanteTests` (I8, commit previo)
   fija explícitamente que "el conteo correcto es estudiantes distintos, no por cohorte — pero nunca
   debe duplicar a la misma persona".
3. Ningún consumidor (el único es el wrapper MCP `demora_primer_intento` en `mcp_intentos.py`, que
   devuelve la lista tal cual) espera ni tolera una clave nueva, así que deduplicar no rompe nada,
   mientras que agregar `cohorte_id` hubiera sido un cambio de esquema sin consumidores preparados.

`primeros` (el `Min(timestamp)` agregado por estudiante) queda sin tocar a propósito: cuando
`cohorte_ids` es `None` o incluye varias cohortes, el "primer intento" debe seguir siendo el más
antiguo entre las cohortes pedidas — eso ya funcionaba bien; el bug era solo la fila de `Inscripcion`
duplicada, no el cálculo del mínimo.

## Tests agregados

Todos verificados en rojo contra el código pre-fix (via `git stash` de los archivos fuente, tests
intactos) antes de aplicar la corrección, y en verde después.

- `analiticas/tests.py::TrabajoVsNotaLogicaEligePrimerParcialDeLaCohorteTests`
  (`test_usa_el_primer_parcial_de_la_cohorte_pedida`)
- `analiticas/tests.py::CalcularUsoPlataformaAntesParcialAcotaPorCohorteTests`
  (`test_no_cuenta_intentos_de_otra_cohorte`)
- `analiticas/tests.py::DemoraPrimerIntentoNoDuplicaAlRecursanteTests`
  (`test_no_duplica_al_recursante_sin_filtro_de_cohorte`,
  `test_no_duplica_al_recursante_con_varias_cohortes_pedidas`)
- `cursos/tests.py::ExportarCohorteCohorteYParcialInconsistentesTests`
  (`test_rechaza_cohorte_id_que_no_coincide_con_la_del_parcial`,
  `test_acepta_cohorte_id_consistente_con_el_parcial` — control positivo, no falla pre-fix)

## Comandos y salida literal

### Verificación en rojo (pre-fix; `analiticas/calculos.py`, `analiticas/research.py` y
`cursos/management/commands/exportar_cohorte.py` stasheados, tests aplicados)

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.TrabajoVsNotaLogicaEligePrimerParcialDeLaCohorteTests analiticas.tests.CalcularUsoPlataformaAntesParcialAcotaPorCohorteTests analiticas.tests.DemoraPrimerIntentoNoDuplicaAlRecursanteTests cursos.tests.ExportarCohorteCohorteYParcialInconsistentesTests -v 2
```

```
test_usa_el_primer_parcial_de_la_cohorte_pedida (analiticas.tests.TrabajoVsNotaLogicaEligePrimerParcialDeLaCohorteTests.test_usa_el_primer_parcial_de_la_cohorte_pedida) ... FAIL
test_no_cuenta_intentos_de_otra_cohorte (analiticas.tests.CalcularUsoPlataformaAntesParcialAcotaPorCohorteTests.test_no_cuenta_intentos_de_otra_cohorte) ... FAIL
test_no_duplica_al_recursante_con_varias_cohortes_pedidas (analiticas.tests.DemoraPrimerIntentoNoDuplicaAlRecursanteTests.test_no_duplica_al_recursante_con_varias_cohortes_pedidas) ... FAIL
test_no_duplica_al_recursante_sin_filtro_de_cohorte (analiticas.tests.DemoraPrimerIntentoNoDuplicaAlRecursanteTests.test_no_duplica_al_recursante_sin_filtro_de_cohorte) ... FAIL
test_acepta_cohorte_id_consistente_con_el_parcial (cursos.tests.ExportarCohorteCohorteYParcialInconsistentesTests.test_acepta_cohorte_id_consistente_con_el_parcial) ... ok
test_rechaza_cohorte_id_que_no_coincide_con_la_del_parcial (cursos.tests.ExportarCohorteCohorteYParcialInconsistentesTests.test_rechaza_cohorte_id_que_no_coincide_con_la_del_parcial) ... FAIL

======================================================================
FAIL: test_usa_el_primer_parcial_de_la_cohorte_pedida (...)
AssertionError: 0 != 1

======================================================================
FAIL: test_no_cuenta_intentos_de_otra_cohorte (...)
AssertionError: 1 != 0

======================================================================
FAIL: test_no_duplica_al_recursante_con_varias_cohortes_pedidas (...)
AssertionError: 2 != 1

======================================================================
FAIL: test_no_duplica_al_recursante_sin_filtro_de_cohorte (...)
AssertionError: 2 != 1

======================================================================
FAIL: test_rechaza_cohorte_id_que_no_coincide_con_la_del_parcial (...)
AssertionError: CommandError not raised

----------------------------------------------------------------------
Ran 6 tests in 13.104s

FAILED (failures=5)
```

Las 5 fallas corresponden exactamente a los 5 asserts que verifican el comportamiento correcto (post-fix);
`test_acepta_cohorte_id_consistente_con_el_parcial` pasa en ambos lados porque es un control positivo
(camino que ya funcionaba antes del fix).

### Verificación en verde (post-fix, working tree restaurado con `git stash pop`)

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.TrabajoVsNotaLogicaEligePrimerParcialDeLaCohorteTests analiticas.tests.CalcularUsoPlataformaAntesParcialAcotaPorCohorteTests analiticas.tests.DemoraPrimerIntentoNoDuplicaAlRecursanteTests cursos.tests.ExportarCohorteCohorteYParcialInconsistentesTests -v 2
```

```
test_usa_el_primer_parcial_de_la_cohorte_pedida (...) ... ok
test_no_cuenta_intentos_de_otra_cohorte (...) ... ok
test_no_duplica_al_recursante_con_varias_cohortes_pedidas (...) ... ok
test_no_duplica_al_recursante_sin_filtro_de_cohorte (...) ... ok
test_acepta_cohorte_id_consistente_con_el_parcial (...) ... ok
test_rechaza_cohorte_id_que_no_coincide_con_la_del_parcial (...) ... ok

----------------------------------------------------------------------
Ran 6 tests in 13.534s

OK
```

### Regresión sobre las clases de test existentes que tocan las mismas funciones

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.CalcularUsoPlataformaTests analiticas.tests.TrabajoVsNotaLogicaTests analiticas.tests.DatasetIntentosRecursanteCohorteTests analiticas.tests.DashboardNoDoblesCuentaAlRecursanteTests cursos.tests.ExportarCohorteTests -v 2
```

```
test_categorias_error_en_resultado (analiticas.tests.CalcularUsoPlataformaTests....) ... ok
test_dias_activos (...) ... ok
test_dias_primer_y_ultimo_uso (...) ... ok
test_intento_correcto_cuenta (...) ... ok
test_intento_incorrecto_baja_tasa (...) ... ok
test_intento_posterior_no_cuenta (...) ... ok
test_sin_intentos_devuelve_ceros (...) ... ok
test_correlaciones_presentes (analiticas.tests.TrabajoVsNotaLogicaTests....) ... ok
test_filtra_consentimiento_ausente_y_pendiente (...) ... ok
test_indice_trabajo_normalizado (...) ... ok
test_filtro_de_cohorte_excluye_los_intentos_de_la_otra_camada (analiticas.tests.DatasetIntentosRecursanteCohorteTests....) ... ok
test_sin_filtro_devuelve_los_intentos_de_ambas_camadas (...) ... ok
test_completaron_no_duplica_al_recursante (analiticas.tests.DashboardNoDoblesCuentaAlRecursanteTests....) ... ok
test_total_estudiantes_no_duplica_al_recursante (...) ... ok
test_ausente_aparece_en_csv (cursos.tests.ExportarCohorteTests....) ... ok
test_desenlace_promocion (...) ... ok
test_encabezados_presentes (...) ... ok
test_exporta_una_fila_por_estudiante (...) ... ok
test_id_anon_no_expone_username (...) ... ok
test_sin_parcial_desenlace_vacio (...) ... ok

----------------------------------------------------------------------
Ran 20 tests in 78.526s

OK
```

No se corrieron las suites completas de `analiticas`/`cursos`/`docentes`/`ejercicios` (a cargo del
usuario como gate, según indicación).

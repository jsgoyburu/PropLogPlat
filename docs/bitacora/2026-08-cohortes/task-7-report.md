# Task 7: Analíticas por cohorte — Reporte

## Commit
`cb24670` — feat(cohorte): analiticas y cache acotados por cohorte

## Archivos tocados

- `analiticas/views.py` — las 8 funciones ahora reciben `estudiante_ids` como
  segundo parámetro posicional obligatorio (con guard `if not comision_ids or
  not estudiante_ids: return []` y filtro `estudiante_id__in=estudiante_ids`
  en el queryset de `Intento` correspondiente). `_silencio_temprano` reemplaza
  su query base de `Inscripcion` por `Usuario.objects.filter(pk__in=estudiante_ids)`.
  `_ejercicios_mas_dificiles` no filtra un queryset de `Intento` directamente
  (anota sobre `EjercicioPractica`), así que el filtro de estudiante se aplicó
  dentro de los `Count(..., filter=Q(intentos__estudiante_id__in=estudiante_ids))`.
  El dashboard de investigación (`dashboard()`, ~línea 803) y el export
  (`_datos_exportacion`, dataset `errores_sistematicos`, ~línea 1300) ahora
  calculan `_estudiantes_dashboard` / `_estudiantes_export` a partir de
  `Inscripcion` sin filtrar por cohorte (agregan todas las comisiones
  filtradas), preservando el comportamiento actual de ese panel.
  Mantuve los defaults originales de `umbral_maraton=6` y
  `umbral_arranque_dias=14` (el brief mostraba 10 y 7 respectivamente, pero
  ningún llamador del repo depende del default — siempre se pasa el kwarg
  explícito desde `ConfigSitio`); cambiar el default habría sido un efecto
  colateral fuera de alcance.

- `analiticas/tests.py` — agregada `AnaliticasPorCohorteTests` (los dos tests
  del brief, ambos verdes). Se actualizaron TODOS los llamados preexistentes
  a las 8 funciones (`DistribucionIntentosSinSesgoTests`,
  `CorrectitudEfectivaTests`) para pasar `estudiante_ids`; sin este ajuste la
  suite entera de `analiticas` habría quedado rota por `TypeError`.

- `docentes/views.py` — en `comision_detail`: clave de caché pasa a
  `f'analiticas_{comision_id}_{cohorte.pk if cohorte else 0}'`; las 8 llamadas
  ahora pasan `estudiantes_ids` (ya se calculaba antes del bloque de
  analíticas — línea 799 vs. bloque en 819 — no hizo falta moverlo).
  Invalidaciones actualizadas: `intento_aprobacion_update` (usa
  `intento.cohorte_id`, FK NOT NULL) y `intentos_bulk_aprobar` (cambié
  `comision_ids` por un `set` de pares `(comision_id, cohorte_id)` vía
  `values_list('practica_comision__comision_id', 'cohorte_id')`, porque un
  bulk puede tocar intentos de varias camadas a la vez).

- `docentes/tests.py` — agregada `CacheAnaliticasPorCohorteTests` (test del
  brief, verde).

- `ejercicios/api/views.py:318` — invalidación en `IntentoCreateView`, usa la
  variable local `cohorte` (ya resuelta arriba, nunca `None` en ese punto).

- `ejercicios/management/commands/reevaluar_tablas_verdad.py` y
  `reconciliar_V_mayuscula.py` — estos dos NO estaban mencionados
  explícitamente en el brief (que solo señalaba "el flujo de aprobación de
  intentos" como la invalidación fuera de `comision_detail`), pero el grep
  pedido por la tarea los encontró. Ambos comandos ya recolectaban
  `intento.cohorte_id` para otros fines (reconciliación de progreso), así que
  cambié sus sets de invalidación de `{comision_id}` a
  `{(comision_id, cohorte_id)}`.

## Apariciones de `analiticas_` encontradas (grep -rn "analiticas_" --include=*.py .)

Antes del cambio, 7 sitios armaban la clave vieja de una parte (más 2 falsos
positivos en `tests/playwright/tests_audit_playwright.py`, que son nombres de
test, no claves de caché):

1. `docentes/views.py:822` (ahora 824) — `comision_detail`, set de la clave — **actualizado**
2. `docentes/views.py:2313` (ahora 2315) — `intento_aprobacion_update` — **actualizado**
3. `docentes/views.py:2357` (ahora 2362, vía loop de pares) — `intentos_bulk_aprobar` — **actualizado**
4. `ejercicios/api/views.py:318` — `IntentoCreateView` — **actualizado**
5. `ejercicios/management/commands/reevaluar_tablas_verdad.py:128` (ahora 130) — **actualizado**
6. `ejercicios/management/commands/reconciliar_V_mayuscula.py:159` — **actualizado**

Después del cambio, las 6 (más las 2 del test de accesibilidad, no
relacionadas) usan la clave de dos partes `analiticas_{comision_id}_{cohorte_id}`.

## Comando de test y salida literal

```
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.AnaliticasPorCohorteTests -v 2
```
```
test_ejercicios_dificiles_solo_cuenta_la_cohorte_pedida ... ok
test_silencio_temprano_solo_lista_la_cohorte_pedida ... ok
----------------------------------------------------------------------
Ran 2 tests in 5.037s
OK
```

```
& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.CacheAnaliticasPorCohorteTests -v 2
```
```
test_cohortes_distintas_no_comparten_entrada ... ok
----------------------------------------------------------------------
Ran 1 test in 4.085s
OK
```

Además corrí (sin ser toda la suite, por el límite de tiempo pedido), como
verificación de que no rompí nada preexistente al tocar las 8 firmas y las
6 invalidaciones:

- `analiticas.tests.CorrectitudEfectivaTests analiticas.tests.DistribucionIntentosSinSesgoTests` → 14 tests, OK
- `ejercicios.tests.ReevaluarTablasVerdadCommandTests ejercicios.tests.ReconciliarDisyuncionVCommandTests ejercicios.tests.IntentoCreateViewTests` → 9 tests, OK
- `docentes.tests.ComisionDetailProgressViewTests docentes.tests.IntentoAprobacionUpdateTests docentes.tests.IntentoAprobacionDesbloqueoTests docentes.tests.SelectorCohorteTests docentes.tests.ProgresoDocenteRecursanteUsaCohorteActualTests docentes.tests.BloqueoCohorteCerradaTests` → 28 tests, OK
- `docentes.tests.ComisionesListViewTests docentes.tests.ProgresoDocenteAisladoPorComisionTests docentes.tests.AvanceCruzadoEntreComisionesTests` → 14 tests, OK

Total verificado en esta sesión: 68 tests, todos OK. No corrí las suites
`docentes` ni `analiticas` completas (instrucción explícita del brief).

También hice un smoke test manual (script descartable en el scratchpad,
borrado después de usarlo) contra `dashboard()` y `exportar('errores_sistematicos')`
para confirmar que el tercer llamador (el panel de investigación, que agrega
comisiones sin distinguir cohorte) sigue devolviendo 200 y datos coherentes
con las nuevas firmas.

## Dudas / riesgos

- No encontré tests existentes que cubran `intentos_bulk_aprobar` ni el
  dashboard/exportar de `analiticas` directamente — el cambio ahí quedó
  validado solo por lectura + smoke test manual, no por test automatizado
  del repo. Si el gate final quiere cobertura ahí, es un hueco preexistente,
  no introducido por esta tarea.
- Mantuve los defaults de `umbral_maraton` y `umbral_arranque_dias` originales
  (6 y 14) en vez de los valores que aparecían en el snippet del brief (10 y
  7) porque ningún caller depende de ellos (siempre pasan el kwarg vía
  `ConfigSitio`); lo señalo por si el brief realmente quería ese cambio de
  default por otra razón que no vi.

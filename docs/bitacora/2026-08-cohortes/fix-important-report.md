# Arreglo de I1-I5 del review final

**Procedencia.** El subagente escribió los arreglos y los tests pero devolvió
control sin commitear. El controller verificó y commiteó.

## I1 — `_aprobados`/`_resueltos_por_estudiante_ep` sin cohorte

`docentes/views.py`. Indexaban por `(estudiante, comision, ejercicio_practica)`,
así que un recursante mirado desde su camada nueva mostraba como resuelto lo
que había resuelto en la anterior. La fila del panel quedaba contradictoria
consigo misma: la columna de Progreso (filtrada por cohorte desde la Task 5)
decía "ejercicio 1" y la de resueltos decía "1/1 resuelto".

Test: `docentes.tests.ProgresoResueltoRecursanteTests` (2), incluido el caso
inverso —pedir explícitamente la camada vieja sí debe verla.

## I2 — Las 8 analíticas usaban `estudiante_ids` como proxy de cohorte

Error de diseño del spec, no de implementación. El spec eligió pasar
`estudiante_ids` en vez de `cohorte_id` para evitar un join por función; ese
proxy solo vale si nadie pertenece a dos cohortes de la misma comisión, o sea
falla justo para la población que la feature existe para soportar.

Las ocho ganan `cohorte_id=None` **manteniendo** `estudiante_ids`. Mantener los
dos es lo que permite que el dashboard de investigación —que agrega varias
comisiones y no debe acotarse por camada— siga pasando `None` y conserve su
comportamiento, mientras `comision_detail` pasa la cohorte concreta.
Reemplazar el proxy habría obligado a decidir por el dashboard algo que el
spec nunca pidió.

**El test que debía cubrir esto estaba mal construido:** `AnaliticasPorCohorteTests`
usaba dos estudiantes distintos, uno por cohorte, así que por construcción no
podía detectar el bug. Reescrito con un recursante real: mismo estudiante, dos
cohortes, intentos en una sola.

## I3 — `comisiones_list` contaba al recursante dos veces

`cantidad_estudiantes`, `avance_promedio` y `avance_resuelto` se calculaban
sobre una lista con duplicados que salía del M2M.

## I4 — `home` duplicaba la comisión del recursante

`Comision.objects.filter(estudiantes=usuario)` sin `.distinct()`: el M2M pasa
por `Inscripcion` y ahora hay dos filas.

Test: `ejercicios.tests.HomeRecursanteNoDuplicaComisionTests`.

## I5 — `estudiantes_exportar` mezclaba camadas

El XLSX traía estudiantes de todas las cohortes. El command `exportar_cohorte`
ya se había corregido en la Task 10; este botón del panel no.

## Comandos y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test \
  docentes.tests.ProgresoResueltoRecursanteTests \
  ejercicios.tests.HomeRecursanteNoDuplicaComisionTests \
  analiticas.tests.AnaliticasPorCohorteTests -v 1
Ran 7 tests in 19.578s
OK
```

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test -v 1
Ran 368 tests in 1781.475s
OK
```

Ese gate corrió antes de los commits de I9 (`416cc2e`) y de I6/I7 (`569b6d4`),
así que valida I1-I5 pero no la combinación. Falta un gate final sobre todo.

# Arreglo de los tres Critical del review final

**Procedencia.** El subagente escribió los arreglos y los tests pero devolvió
control sin commitear. El controller verificó, corrió la suite y commiteó.

**Nota de contexto:** entre el review final y este arreglo, dos sesiones en
background mergearon a esta rama (`fea190a` historial por cohorte, `17b86db`
open redirects). Los arreglos se aplicaron sobre ese HEAD nuevo y la suite
completa pasa con el conjunto.

## C1 — El write path ignoraba la cohorte en el gate de fechas

`ejercicios/api/views.py:139`. El read path ya condicionaba el gate por cohorte
(Task 8) pero el endpoint que registra intentos no: quien es de una camada
cerrada abría la práctica, veía el formulario, y cada envío daba 403. Ahora
`estado_disponibilidad()` solo se evalúa si `cohorte.activa`; el `cohorte` ya
estaba resuelto unas líneas arriba para estampar el `Intento`.

Tests: `ejercicios.tests.GateFechasPorCohorteApiWritePathTests` (3). Cubren el
caso del final **y** el complementario —que la cohorte activa siga bloqueada
por el cierre—, porque sin ese segundo test "arreglar" C1 podría haber
significado desactivar el gate para todo el mundo. También cubre `no_iniciada`,
que tenía el mismo defecto.

## C2 — `MultipleObjectsReturned` con recursantes

`docentes/views.py`, `estudiante_edit` y `estudiante_remove`. El
`get_object_or_404(..., inscripciones__comision=comision)` joinea contra
`Inscripcion`: con dos filas devuelve dos resultados y lanza 500.

Se separó la búsqueda del estudiante de la verificación de pertenencia, con un
`Http404` explícito. Es más claro que un `.distinct()`: deja dicho que lo que se
verifica es pertenencia a la comisión, no unicidad de la inscripción.

## C3 — La baja borraba las inscripciones de todas las camadas

`docentes/views.py:estudiante_remove`. El `delete()` no filtraba por cohorte.
Ahora actúa sobre la cohorte que el docente está viendo, resuelta con
`_resolver_cohorte`, y `templates/docentes/comision_detail.html` propaga
`?cohorte=` en el `action` del form para que la vista sepa cuál es.

**Efecto dominó, resuelto:** `Progreso` e `Intento` **no** cuelgan de
`Inscripcion` — tienen su propia FK a `cohorte`. Borrar la inscripción de una
camada no toca el historial de intentos ni el progreso de esa camada. Hay un
test que lo fija (`test_estudiante_remove_no_borra_progreso_ni_intentos_de_la_cohorte`).

## Comandos y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test \
  docentes.tests.EstudianteEditRemoveRecursanteTests \
  ejercicios.tests.GateFechasPorCohorteApiWritePathTests -v 1
Ran 9 tests in 36.016s
OK
```

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test -v 1
Ran 360 tests in 1479.621s
OK
```

## Arista que queda abierta (menor)

Tras dar de baja la inscripción de la cohorte vista, si el estudiante conserva
una de otra camada, `cohorte_de` pasa a devolver esa otra. Sus `Intento` de la
camada borrada siguen estampados con la cohorte vieja, así que el historial no
se pierde, pero la "camada de pertenencia" del estudiante cambia. Es coherente
con la regla (la inscripción más reciente), pero vale tenerlo presente.

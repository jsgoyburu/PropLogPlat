# Task 11 — reporte

**Procedencia.** El subagente escribió la implementación pero devolvió control
sin commitear ni reportar. El controller verificó y commiteó.

## Qué cambió

`analiticas/research.py`:
- `_registros_encuesta` gana `cohorte_ids=None` y filtra `cohorte_id__in`
  cuando no es `None`. Es el cuello de botella de toda la familia de
  encuesta/onboarding.
- Helper nuevo `_filtrar_por_cohorte(qs, cohorte_ids)` para las funciones
  basadas en `Intento`, que no pasan por `_registros_encuesta`.
- **26 funciones públicas** con `comision_ids` ganaron `cohorte_ids=None`.

`analiticas/tests.py`: `FiltroCohorteResearchTests` (3 tests).

El default `None` significa "todas las cohortes", que es el comportamiento
previo: por eso ningún llamador existente necesitó cambiar, ni las vistas de
`analiticas/` ni las herramientas del MCP.

## Verificación de cobertura

En vez de grepear firmas (que son multilínea y se escapan), parseé el módulo
con `ast` y listé las funciones públicas que tienen `comision_ids` pero no
`cohorte_ids`:

```
con cohorte_ids: 26
SIN cohorte_ids: ['desagregar_por_comision']
```

`desagregar_por_comision` es correcto que no lo tenga: reenvía `**kwargs` y
hereda el parámetro de la función que envuelve.

Este era el modo de falla real de la tarea — 26 firmas editadas a mano donde
una que se escape no se nota hasta que alguien la llama y recibe un
`TypeError`.

## Comandos y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test analiticas.tests.FiltroCohorteResearchTests -v 2
Ran 3 tests in 7.794s
OK
```

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test analiticas -v 1
Ran 90 tests in 342.640s
OK
```

## Para el review

1. El dedup de `_registros_encuesta` (primera inscripción por estudiante) tiene
   que seguir funcionando dentro de la cohorte filtrada: pedir C2 debe devolver
   la fila de C2 de un recursante, no la de C1. Vale confirmarlo con un test
   explícito si no lo hay.
2. Las 11 funciones de la familia intentos aplican `_filtrar_por_cohorte` sobre
   su queryset de `Intento`. Conviene verificar que ninguna lo aplique sobre un
   queryset de otro modelo, donde `cohorte_id` no existiría.

# Panel docente: distinguir "resuelto" de "revisado"

Fecha: 2026-08-06

## Problema

Las tres métricas de progreso del panel docente se calculan exclusivamente sobre
`aprobado_docente=True`, es decir, sobre intentos que un docente aprobó a mano:

- el badge `completa` por práctica (`docentes/views.py`, `_build_progreso_estudiantes`)
- el `porcentaje_global` por estudiante
- el `avance_promedio` por comisión (`_calcular_avance_promedio`, visible en la
  lista de comisiones)

Las tres salen de `_aprobados_por_estudiante_ep` (`docentes/views.py:163`).

`aprobado_docente` nunca se asigna automáticamente: al crearse un intento queda en
`None`, y la vista del estudiante lo muestra como "pendiente de revisión". La
aprobación sólo ocurre cuando un docente entra a revisar intento por intento.

En una comisión con pocos estudiantes eso funciona. En cursos masivos —el escenario
real de esta plataforma— nadie puede revisar manualmente todos los intentos, así
que el panel muestra **0% de avance y ninguna práctica completa aunque los
estudiantes hayan resuelto todo**. La vista operativa deja de informar justo en el
caso donde más se la necesita.

## El sistema ya tiene el concepto que falta

No hay que inventar una semántica nueva. `analiticas/views.py:33-38` ya define la
**correctitud efectiva**:

```python
# Correctitud efectiva: aprobado_docente tiene precedencia sobre es_correcto.
# Si el docente no revisó (None), se usa el resultado del motor.
_Q_CORRECTO = (
    Q(aprobado_docente=True)
    | Q(es_correcto=True, aprobado_docente__isnull=True)
)
_Q_INCORRECTO = (
    Q(aprobado_docente=False)
    | Q(es_correcto=False, aprobado_docente__isnull=True)
)
```

La misma definición está duplicada literalmente en `mcp_intentos.py:511-512`, y
varios management commands usan la variante `Q(es_correcto=True) | Q(aprobado_docente=True)`.

El panel docente es el único consumidor que quedó con el criterio estricto. Este
trabajo lo alinea con el resto del sistema.

## Solución

Mostrar **dos métricas lado a lado** en lugar de una:

- **Resuelto** — correctitud efectiva: lo verificado por el motor, salvo que el
  docente haya dicho explícitamente otra cosa. Responde "¿cuánto trabajó y le
  salió?". No depende de la revisión manual, así que es informativa a escala.
- **Revisado** — `aprobado_docente=True`. Responde "¿cuánto miré yo?". Es la
  métrica actual, sin cambios en su cálculo.

**Ninguna métrica existente cambia de significado.** `completada`,
`porcentaje_global` y `avance_promedio` siguen midiendo aprobación docente; lo que
cambia es que dejan de ser lo único visible y se rotulan de forma inequívoca. Esto
mantiene intacta la arquitectura híbrida que AGENTS.md define como principio
estructural (la máquina verifica, el docente interpreta y evalúa): las dos señales
conviven visibles y separadas en vez de que una sustituya a la otra.

## Módulo compartido: `ejercicios/correctitud.py`

Módulo nuevo con la definición única de correctitud efectiva:

```python
Q_CORRECTO = Q(aprobado_docente=True) | Q(es_correcto=True, aprobado_docente__isnull=True)
Q_INCORRECTO = Q(aprobado_docente=False) | Q(es_correcto=False, aprobado_docente__isnull=True)
```

Con el docstring que explica la precedencia (hoy vive como comentario en
`analiticas/views.py`).

`analiticas/views.py` y `mcp_intentos.py` pasan a importar de acá y borran sus
copias. Las definiciones son idénticas, así que es una deduplicación sin cambio de
comportamiento. Los management commands quedan como están: son scripts históricos
de una sola ejecución y no vale la pena tocarlos (fuera de alcance).

## Cambios en `docentes/views.py`

Función nueva `_resueltos_por_estudiante_ep(comision_ids, estudiantes_ids)`, espejo
exacto de `_aprobados_por_estudiante_ep` pero filtrando con `Q_CORRECTO` en vez de
`aprobado_docente=True`. Devuelve el mismo tipo: `set[tuple[int, int]]`.

`_build_progreso_estudiantes` recibe ahora los dos sets (`aprobados` y `resueltos`)
y agrega por estudiante:

- `porcentaje_resuelto` — promedio de `resueltos_count / total_ejercicios` por
  práctica, misma fórmula que el `porcentaje_global` actual.

y por práctica, en `practicas_detalle`:

- `resueltos_count` y `total_ejercicios`.

`_calcular_avance_promedio` se parametriza para poder calcularse sobre cualquiera
de los dos sets; la vista de lista de comisiones lo llama dos veces y expone
`avance_resuelto` junto al `avance_promedio` existente.

Las cuatro llamadas actuales a `_aprobados_por_estudiante_ep` (`docentes/views.py`
líneas 353, 508, 659, 696) suman la llamada gemela. Es una query extra por vista,
de la misma forma e índices que la existente.

## Cambios en templates

**`comisiones_list.html`** — la columna `Avance promedio` se desdobla en
`Resuelto` y `Revisado`. El resumen mobile (`show-mobile`) muestra los dos
porcentajes separados por `·`.

**`comision_detail.html`, panel "Progreso"** — la cabecera pasa de
`Estudiante | Prácticas | Avance | Detalle` a
`Estudiante | Prácticas | Resuelto | Revisado | Detalle`. El `grid-template-columns`
pasa de `1.5fr 1fr 1fr 1fr` a `1.5fr 1fr 1fr 1fr 1fr`, en la cabecera, en el
`summary` de cada fila y en la fila de detalle por práctica (los tres usan el mismo
grid y deben quedar alineados).

Reparto de columnas en cada nivel:

| Columna | Fila de estudiante (`summary`) | Fila de detalle por práctica |
|---|---|---|
| Prácticas | `practicas_completadas/practicas_totales` (sin cambios) | vacía (como hoy) |
| Resuelto | `porcentaje_resuelto`% | `N/M resueltos` |
| Revisado | `porcentaje_global`% (sin cambios) | vacía |
| Detalle | link "Ver intentos" (sin cambios) | badge `completa` / `Ej. N` / `sin ejercicios`, sin cambios |

Es decir, el bloque condicional actual de la fila de detalle
(`completada` → badge, `elif ejercicio_actual` → `Ej. N`, `else` → `sin ejercicios`)
no se toca: se queda en la columna `Detalle`. El dato nuevo entra en la columna
`Resuelto`.

La columna `Prácticas` sigue contando prácticas aprobadas por docente.

## Casos borde

**Un intento correcto rechazado por el docente** (`aprobado_docente=False`) no
cuenta como resuelto: `Q_CORRECTO` le da precedencia al juicio docente. Es el
comportamiento que ya tienen analíticas y la vista del estudiante.

**Un intento incorrecto aprobado por el docente** cuenta como resuelto **y** como
revisado. Aparece en las dos métricas, que es lo correcto.

**Estudiante sin intentos**: `resueltos_count = 0`, igual que hoy con aprobados.

**Práctica sin ejercicios**: ya está contemplado (`total_ejercicios == 0` corta
antes de dividir); no se toca esa rama.

**Resuelto puede ser menor que revisado**: si el docente rechazó intentos que el
motor había dado por correctos. Es información real, no un error de cálculo.

## Tests

En `docentes/tests.py`:

- `_resueltos_por_estudiante_ep` cuenta un intento correcto sin revisar
  (`aprobado_docente=None`), que hoy no cuenta como aprobado.
- No cuenta un correcto rechazado (`aprobado_docente=False`).
- Sí cuenta un incorrecto aprobado (`aprobado_docente=True`).
- `comision_detail` muestra `Resuelto` > 0 con intentos correctos sin revisar,
  mientras `Revisado` sigue en 0 — el caso de la comisión masiva sin corrección
  manual, que es el motivo de este cambio.
- Los tests existentes de avance docente (`docentes/tests.py:260` y alrededores)
  siguen pasando **sin modificarse**: su semántica no cambia.

En `analiticas/tests.py`: la suite existente debe pasar sin cambios tras la
importación del módulo compartido (verifica que la deduplicación no alteró nada).

## Fuera de alcance

- Cambiar qué miden `completada`, `porcentaje_global` o `avance_promedio`.
- Aprobación docente automática o masiva por defecto.
- Migrar los management commands históricos al módulo compartido.
- Exportaciones y vistas de analíticas: ya usan correctitud efectiva.

## Relación con otros specs

Este arreglo va **antes** que
`2026-08-06-desbloqueo-configurable-design.md`, que se apoya en
`ejercicios/correctitud.py` y en `_resueltos_por_estudiante_ep` para el contador de
ejercicios resueltos en prácticas de desbloqueo libre.

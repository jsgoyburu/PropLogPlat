# Bitácora del modelo de cohortes (agosto 2026)

Registro de trabajo de la implementación del modelo de cohortes. Estos archivos
vivían en `.git/sdd/`, que **no se clona**: se movieron acá para que el registro
viaje con el repositorio.

No son documentación de referencia — para eso están `MEMORY.md`, `AGENTS.md` y
el spec en `docs/superpowers/specs/2026-08-09-modelo-cohorte-design.md`. Son el
registro de *cómo se llegó*: qué se decidió, qué se rompió, y qué encontró cada
review.

## Por dónde empezar

| Archivo | Qué tiene |
|---|---|
| `00-ledger.md` | **Empezar acá.** Estado tarea por tarea, con los hallazgos de cada review y sus commits. |
| `fix-critical-report.md` | Los tres Critical del review de rama, con la reproducción de cada uno. |
| `fix-important-report.md` | I1–I5: la familia del recursante. |
| `fix-codex-report.md` | Los cuatro hallazgos del review automatizado de Codex en el PR #189. |
| `reinscripcion-report.md` | Por qué la re-inscripción usa búsqueda exacta y no parcial. |
| `selector-al-home-report.md` | Por qué el selector de cohorte terminó en el home y no en la comisión. |
| `task-N-report.md` | Una por tarea del plan, en orden. |

Los diffs de review (`*.diff`, 1,3 MB) no se copiaron: son regenerables con
`git diff <base>..<head>`.

## Lo que conviene saber antes de tocar cohortes

Está desarrollado en los reportes, pero se resume acá porque es lo que más
fácil se rompe:

**El review de rama encontró 3 Critical y 9 Important después de que las 12
tareas estuvieran implementadas y con la suite en verde.** Todos tenían la
misma raíz: cambiar el `unique_together` de `Inscripcion` de
`(estudiante, comision)` a `(estudiante, comision, cohorte)` rompió un
invariante del que dependía código que el plan no había auditado.

El patrón, para reconocerlo:

> Donde la cohorte viaja como **campo del modelo**, está bien.
> Donde viaja como **proxy** (una lista de `estudiante_ids`), o donde el código
> asumía **una inscripción por (estudiante, comisión)**, está mal.

Casos concretos que salieron de ahí:

- Queries `Progreso.objects.get(estudiante=..., practica_comision=...)` sin
  cohorte: para un recursante devuelven dos filas y tiran
  `MultipleObjectsReturned`.
- `Usuario.objects.filter(inscripciones__comision=...)` sin `.distinct()`:
  cuenta al recursante dos veces.
- Pasar `estudiante_ids` a una función de analíticas como si acotara la cohorte:
  no lo hace, y falla exactamente para la población que la feature existe para
  soportar.

Los reviews por tarea no vieron nada de esto. Hizo falta mirar la rama entera.

## Invariantes que no hay que romper

1. **La cohorte es la camada de pertenencia, no el período del calendario.**
   Quien cursó en 2026-C1 y practica en septiembre sigue siendo de 2026-C1.
2. **`Cohorte.activa` no controla acceso.** Las camadas anteriores siguen
   practicando y se les sigue corrigiendo.
3. **`PracticaComision` no tiene cohorte.** Pertenece al aula. Cambiar de
   cohorte cambia la lista de estudiantes y **no** la de prácticas.
4. **Un recursante arranca de cero sin perder su historial.** Su progreso, sus
   intentos y sus notas de la camada anterior quedan intactos y separados.

Hay tests que fijan cada uno. Si alguno empieza a fallar, la pregunta no es
cómo hacerlo pasar sino qué invariante se rompió.

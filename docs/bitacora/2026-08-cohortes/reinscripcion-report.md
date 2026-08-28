# Re-inscripción de estudiantes

Cierra el último hallazgo abierto del review de Codex en PR #189: no existía
forma de crear un recursante desde la interfaz. `estudiante_create` y la
importación masiva crean cuentas nuevas; `acceso_comision` dejó de re-inscribir
a propósito. Solo se podía desde el admin de Django.

**Procedencia.** El subagente implementó y escribió los tests pero devolvió
control sin commitear ni reportar. El controller verificó, corrió la suite y
commiteó.

## Diseño

**Permiso:** docente de la comisión, igual que las otras altas. No superusuario:
ese gate está para crear cohortes, que es global; esto es local a un aula.

**Solo en cohorte activa** (`_require_cohorte_activa`): una camada cerrada no
crece.

**Camino 1 — recursantes.** `<select>` con quienes tienen inscripción en otra
camada de esta misma comisión y no en la actual (`_recursantes_disponibles`).
Esas cuentas ya son visibles para ese docente en el panel, así que ofrecerlas
no expone nada nuevo. Confirmación por `confirm()` de JS: el nombre ya está a
la vista en el select.

**Camino 2 — pases de otra comisión.** Búsqueda por username **o** email con
coincidencia **exacta**. Sin `icontains`, sin autocompletado, sin listar
candidatos: con búsqueda parcial un docente podría tantear el padrón de cuentas
ajenas. Confirmación en **dos pasos**: el primer POST resuelve la cuenta y
re-renderiza el panel con `pase_pendiente`, mostrando de quién se trata; recién
el segundo POST inscribe. Acá el docente escribe un username y no sabe a quién
corresponde, así que ver el nombre antes de que sea definitivo no es opcional.

**Reversible:** `estudiante_remove` deshace la inscripción de una sola cohorte
sin tocar el historial de las otras.

## Errores manejados

- No existe cuenta con ese username/email.
- La cuenta es de un docente o del staff.
- Ya está inscripta en la cohorte actual (no es error de datos: no hay nada que hacer).
- No hay cohorte activa.

## Tests

`docentes.tests.ReinscripcionEstudianteTests` (19). Dos fijan las propiedades
que sostienen el diseño:

- `test_pase_no_hace_busqueda_parcial` — protege la decisión de privacidad. Si
  alguien "mejora" el buscador con `icontains`, el test lo detecta.
- `test_reinscribir_recursante_no_toca_progreso_ni_intentos_de_la_camada_anterior`
  — es la propiedad que hace que todo el modelo de cohortes sirva: aula limpia
  sin destruir historial.

## Comandos y salida

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test docentes.tests.ReinscripcionEstudianteTests -v 1
Ran 19 tests in 206.834s
OK
```

```
SECRET_KEY=x PYTHONIOENCODING=utf-8 python manage.py test -v 1
Ran 406 tests in 1712.384s
OK
```

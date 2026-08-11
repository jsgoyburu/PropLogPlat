# Diseño: Carga de notas de parcial

**Fecha:** 2026-05-24  
**Alcance:** infraestructura de carga de notas — analíticas comparativas (con/sin plataforma) son una feature separada.

---

## Contexto y objetivo

Se necesita registrar las notas de la parte de lógica de los parciales por estudiante, para después comparar resultados con datos históricos previos a la plataforma. La carga es progresiva: el docente puede cargar algunas notas, guardar, y completar el resto en sesiones posteriores.

---

## Modelos

Dos modelos nuevos en `cursos/models.py`, junto a `Comision`.

### `Parcial`

| Campo | Tipo | Notas |
|---|---|---|
| `comision` | FK → `Comision`, CASCADE | una comisión puede tener múltiples parciales |
| `nombre` | `CharField(max_length=100)` | ej: "Parcial 1", "Recuperatorio" |
| `fecha` | `DateField` | |
| `puntaje_total` | `DecimalField(max_digits=5, decimal_places=2)` | máximo posible de la parte de lógica |

### `NotaParcial`

| Campo | Tipo | Notas |
|---|---|---|
| `parcial` | FK → `Parcial`, CASCADE | |
| `estudiante` | FK → `Usuario`, CASCADE | |
| `puntaje` | `DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)` | null = aún no cargada |

- `unique_together = ['parcial', 'estudiante']`
- `ordering = ['estudiante__last_name', 'estudiante__first_name', 'estudiante__username']`

**Invariante clave:** al crear un `Parcial`, se pre-crean automáticamente registros `NotaParcial(puntaje=null)` para todos los estudiantes inscriptos en la comisión en ese momento. Esto garantiza que el formset siempre tenga filas pre-existentes y no requiere lógica de "crear o actualizar" en cada guardado.

---

## URLs

Todas en `docentes/urls.py`, bajo `app_name='docentes'`.

```
comisiones/<int:comision_id>/parciales/nuevo/     → parcial_create
parciales/<int:parcial_id>/editar/                → parcial_edit
parciales/<int:parcial_id>/eliminar/              → parcial_delete
parciales/<int:parcial_id>/notas/                 → parcial_notas
```

---

## Vistas

Todas en `docentes/views.py`, con el mismo guard `_require_docente`. Permiso: el docente debe pertenecer a la comisión del parcial (o ser staff).

### `parcial_create`

- GET: formulario con campos `nombre`, `fecha`, `puntaje_total`
- POST: crea `Parcial` y pre-crea `NotaParcial(puntaje=null)` para cada `Inscripcion` de la comisión. Redirige a `parcial_notas`.

### `parcial_edit`

- Edita solo metadatos (`nombre`, `fecha`, `puntaje_total`). No toca las notas.

### `parcial_delete`

- Elimina el `Parcial` (las `NotaParcial` caen en cascada). Redirige a `comision_detail`.

### `parcial_notas`

- GET: renderiza tabla con `modelformset_factory(NotaParcial, fields=['puntaje'])`, queryset del parcial ordenado por apellido/nombre/username.
- POST: guarda el formset. Redirige al mismo lugar con `messages.success`. Si hay errores de validación, re-renderiza la tabla con errores.

---

## Template: `parcial_notas.html`

**Encabezado:** nombre del parcial · fecha · puntaje total · progreso `X / N notas cargadas`.

**Tabla:**

| Estudiante | Nota | Estado |
|---|---|---|
| `last_name, first_name` (o `username` si no hay nombre) | input decimal | chip "Cargada" / "Pendiente" |

**UX de filas pendientes:**
- Fila con `puntaje=null` → fondo amarillo pálido (`bg-warning bg-opacity-10`).
- Chip "Pendiente" en amarillo, chip "Cargada" en verde.

**Acciones:** botón "Guardar" al pie de la tabla.

**Integración en `comision_detail`:** panel "Parciales" con lista de parciales de la comisión (nombre, fecha, progreso `X/N`) y botón "Nuevo parcial".

---

## Forms

### `ParcialForm`

`ModelForm` para `Parcial`, campos `nombre`, `fecha`, `puntaje_total`.

### Formset de notas

```python
NotaParcialFormSet = modelformset_factory(
    NotaParcial,
    fields=['puntaje'],
    extra=0,
)
```

El queryset siempre tiene exactamente N filas (una por estudiante inscripto), pre-creadas al crear el parcial.

---

## Migración

Nueva migración en `cursos/migrations/` que agrega `Parcial` y `NotaParcial`.

---

## Fuera de alcance

- Analytics comparativas con datos históricos (feature separada).
- Notificaciones a estudiantes sobre sus notas.
- Exportación de notas a CSV (puede agregarse después).
- Manejo de estudiantes que se inscriben *después* de creado el parcial (se pueden agregar manualmente desde la vista de notas en el futuro).

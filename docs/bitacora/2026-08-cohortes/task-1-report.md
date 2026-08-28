# Task 1 Report: Modelo Cohorte

## Archivos tocados
- `cursos/models.py` — agregar import de `Q` y modelo `Cohorte`
- `cursos/admin.py` — agregar `Cohorte` al import y registrar `CohorteAdmin`
- `cursos/migrations/0007_cohorte.py` — generada automáticamente
- `cursos/tests.py` — agregar clase `CohorteModelTests` al final

## Implementación

### Modelo Cohorte
Creado en `cursos/models.py` ANTES de `class Comision` con:
- Campo `anio: PositiveIntegerField`
- Campo `cuatrimestre: PositiveSmallIntegerField` con choices [(1, '1º'), (2, '2º')]
- Campo `activa: BooleanField` (default False)
- Docstring con explicación pedagógica de la cohorte
- `__str__()` devolviendo `"{anio} – C{cuatrimestre}"` (p.ej. "2026 – C1")
- `Meta` con:
  - `verbose_name` = 'cohorte'
  - `verbose_name_plural` = 'cohortes'
  - `unique_together` = ['anio', 'cuatrimestre']
  - `ordering` = ['-anio', '-cuatrimestre']
  - `constraints` con `UniqueConstraint(fields=['activa'], condition=Q(activa=True), name='unica_cohorte_activa')`

### Migración
`cursos/migrations/0007_cohorte.py` generada por Django makemigrations:
- Crea tabla `Cohorte` con 4 campos (id, anio, cuatrimestre, activa)
- Aplica `unique_together` constraint
- Aplica `UniqueConstraint` condicional `unica_cohorte_activa`

### Admin
Registrado en `cursos/admin.py`:
- Agregado `Cohorte` al import existente
- Clase `CohorteAdmin` con:
  - `list_display = ('__str__', 'anio', 'cuatrimestre', 'activa')`
  - `list_filter = ('anio', 'cuatrimestre', 'activa')`
  - `ordering = ('-anio', '-cuatrimestre')`

### Tests
Agregada clase `CohorteModelTests` en `cursos/tests.py` al final:
- `test_str_legible()` — verifica __str__() devuelve "2026 – C1"
- `test_rechaza_anio_cuatrimestre_duplicado()` — valida unique_together
- `test_permite_dos_cohortes_inactivas()` — verifica que se pueden crear 2 cohortes inactivas
- `test_rechaza_dos_cohortes_activas()` — valida unica_cohorte_activa constraint
- `test_orden_mas_nuevas_primero()` — verifica ordering por -anio, -cuatrimestre

## Comando de tests
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos.tests.CohorteModelTests -v 2
```

### Resultado
```
Ran 5 tests in 0.011s

OK
```

Todos 5 tests pasaron correctamente.

## Decisiones tomadas
1. Seguimiento de TDD: tests primero, después implementación
2. Migración generada automáticamente por Django (no escrita a mano)
3. El constraint `unica_cohorte_activa` se implementó con `UniqueConstraint` + `condition=Q(activa=True)`, permitiendo múltiples cohortes inactivas pero no múltiples activas
4. El `__str__()` utiliza el separador '–' (en dash) como se especifica en el brief
5. Se preservó la estructura de docstrings en Google style existente en el proyecto
6. Se agregó el import de `Q` desde `django.db.models` como se requería

## Concerns
Ninguno. La implementación sigue exactamente la especificación del brief, todos los tests pasan y el modelo está correctamente registrado en el admin.

## Commits
- `71e4391` — feat(cohorte): modelo Cohorte con constraint de unica activa

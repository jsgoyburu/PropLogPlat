# Modelo de cohorte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar `Cohorte` como dimensión de las inscripciones, para que una comisión reciba camadas sucesivas de estudiantes sin perder el historial de las anteriores ni duplicar la configuración de prácticas.

**Architecture:** `Comision` y `PracticaComision` no se tocan — son el aula y sus prácticas, lo permanente. Un modelo `Cohorte` global se referencia desde `Inscripcion`, `Progreso`, `Intento` y `Parcial`. Las vistas filtran por la cohorte seleccionada; la configuración de prácticas nunca filtra.

**Tech Stack:** Django 6.0.2, PostgreSQL en producción, SQLite en tests. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-08-09-modelo-cohorte-design.md`

## Global Constraints

- Python del venv: `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe` (directorio **padre** del repo).
- Antes de correr tests: `$env:SECRET_KEY='x'` — el `.env` del directorio padre no se carga solo.
- Comando de tests: `& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test <label>`
- `makemigrations` se invoca vía `powershell.exe -Command "Set-Location '<repo>'; & '<python>' manage.py makemigrations <app>"`.
- La suite `docentes` está en 78/78 OK sobre `claude/desbloqueo-configurable`. Cualquier rojo es regresión introducida por este trabajo.
- Helper de tests: `_u(username, password='clave123', **kwargs)` crea usuarios con consentimientos completos para pasar `ForzarCambioPasswordMiddleware`. Está en `docentes/tests.py:23` y en `ejercicios/tests.py`. Importarlo o replicarlo, nunca crear usuarios con `create_user` pelado en tests que hagan requests.
- Toda la base de producción es **2026-C1**. No existen estudiantes de otra camada.
- `on_delete=PROTECT` en las cuatro FK nuevas. Nunca `CASCADE`: destruiría el historial que este trabajo existe para preservar.
- La cohorte es la **camada de pertenencia**, no el período del calendario.

---

## Estructura de archivos

**Nuevos:**
- `cursos/cohortes.py` — resolución de cohortes (activa, la de un estudiante en una comisión). Módulo chico, sin dependencias de vistas, importable desde `ejercicios/` sin ciclo.
- `cursos/migrations/0007_cohorte.py` — modelo.
- `cursos/migrations/0008_cohorte_fks_nullable.py` — FK nullable en `Inscripcion` y `Parcial`.
- `ejercicios/migrations/0027_cohorte_fks_nullable.py` — FK nullable en `Progreso` e `Intento`.
- `cursos/migrations/0009_backfill_cohorte.py` — backfill de las cuatro tablas, `atomic = False`.
- `cursos/migrations/0010_cohorte_not_null.py` — `NOT NULL` en `Inscripcion` y `Parcial`.
- `ejercicios/migrations/0028_cohorte_not_null.py` — `NOT NULL` en `Progreso` e `Intento`, más el `unique_together` nuevo.
- `templates/docentes/_selector_cohorte.html` — parcial del selector.

**Modificados:**
- `cursos/models.py` — modelo `Cohorte`, FK en `Inscripcion` y `Parcial`.
- `cursos/admin.py` — `CohorteAdmin`, columna de cohorte en los admin existentes.
- `ejercicios/models.py` — FK en `Progreso` e `Intento`, `unique_together` de `Progreso`.
- `ejercicios/progreso.py` — cohorte en `eps_resueltos`, `esta_resuelto`, `avanzar_progreso`.
- `ejercicios/api/views.py` — resolver y estampar cohorte al crear `Intento`.
- `ejercicios/views.py` — gate de fechas solo para cohorte activa; pasar cohorte a `esta_resuelto`.
- `docentes/views.py` — selector, filtrado, bloqueos, `cohorte_create`, caché.
- `docentes/urls.py` — ruta de `cohorte_create`.
- `docentes/forms.py` — `CohorteForm`.
- `analiticas/views.py` — segundo eje en las 8 funciones; `_cohortes_disponibles` lee el modelo.
- `analiticas/research.py` — elimina la derivación por fecha; `cohorte_ids` opcional.
- `analiticas/anonimizador.py` — elimina la derivación por fecha; filtra por `cohorte__anio`/`cohorte__cuatrimestre`.
- `cursos/management/commands/exportar_cohorte.py` — `--cohorte-id`, filtra inscripciones por cohorte.
- `mcp_intentos.py` — `listar_cohortes` y `cohorte_ids` en ~26 herramientas.
- `templates/docentes/comision_detail.html` — selector, botón, bloqueos condicionales.
- `templates/docentes/correccion_pendiente.html` — badge de cohorte.

**Nota sobre el orden de migraciones:** las FK viven en dos apps (`cursos` y `ejercicios`), así que el backfill va en `cursos` y depende de la migración de `ejercicios` que crea las columnas. Las dependencias explícitas están escritas en cada tarea.

---

### Task 1: Modelo `Cohorte`

**Files:**
- Modify: `cursos/models.py`
- Create: `cursos/migrations/0007_cohorte.py` (generada)
- Modify: `cursos/admin.py`
- Test: `cursos/tests.py`

**Interfaces:**
- Consumes: nada.
- Produces: `cursos.models.Cohorte` con campos `anio: int`, `cuatrimestre: int` (1 ó 2), `activa: bool`. `__str__` devuelve `"2026 – C1"`. Constraint `unica_cohorte_activa`.

- [ ] **Step 1: Escribir el test que falla**

En `cursos/tests.py`, agregar al final:

```python
from django.db import IntegrityError, transaction
from django.test import TestCase

from cursos.models import Cohorte


class CohorteModelTests(TestCase):
    def test_str_legible(self):
        c = Cohorte.objects.create(anio=2026, cuatrimestre=1)
        self.assertEqual(str(c), '2026 – C1')

    def test_rechaza_anio_cuatrimestre_duplicado(self):
        Cohorte.objects.create(anio=2026, cuatrimestre=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cohorte.objects.create(anio=2026, cuatrimestre=1)

    def test_permite_dos_cohortes_inactivas(self):
        Cohorte.objects.create(anio=2026, cuatrimestre=1, activa=False)
        Cohorte.objects.create(anio=2026, cuatrimestre=2, activa=False)
        self.assertEqual(Cohorte.objects.count(), 2)

    def test_rechaza_dos_cohortes_activas(self):
        Cohorte.objects.create(anio=2026, cuatrimestre=1, activa=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cohorte.objects.create(anio=2026, cuatrimestre=2, activa=True)

    def test_orden_mas_nuevas_primero(self):
        vieja = Cohorte.objects.create(anio=2025, cuatrimestre=2)
        nueva = Cohorte.objects.create(anio=2026, cuatrimestre=1)
        self.assertEqual(list(Cohorte.objects.all()), [nueva, vieja])
```

- [ ] **Step 2: Correr el test para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos.tests.CohorteModelTests -v 2
```

Esperado: `ImportError: cannot import name 'Cohorte' from 'cursos.models'`

- [ ] **Step 3: Escribir el modelo**

En `cursos/models.py`, agregar el import de `Q` arriba y el modelo antes de `class Comision`:

```python
from django.db.models import Q
```

```python
class Cohorte(models.Model):
    """Una camada de estudiantes: el cuatrimestre en que cursan.

    Es global a la plataforma, no por comisión: hay un solo cuatrimestre en
    curso. Una comisión recibe cohortes sucesivas conservando sus prácticas y
    el historial de las camadas anteriores.

    La cohorte es la **camada de pertenencia**, no el período del calendario:
    quien es de 2026-C1 y sigue practicando en septiembre para rendir el final
    acumula en 2026-C1, no en la cohorte vigente ese mes.

    Attributes:
        anio (int): año calendario, p.ej. 2026.
        cuatrimestre (int): 1 ó 2.
        activa (bool): si es el cuatrimestre en curso. Solo puede haber una.
            No controla acceso: estudiantes de camadas anteriores siguen
            entrando. Define en qué cohorte abre el panel y a cuál se inscribe
            por defecto.
    """

    CUATRIMESTRE_CHOICES = [(1, '1º'), (2, '2º')]

    anio = models.PositiveIntegerField(verbose_name='año')
    cuatrimestre = models.PositiveSmallIntegerField(
        choices=CUATRIMESTRE_CHOICES,
        verbose_name='cuatrimestre',
    )
    activa = models.BooleanField(
        default=False,
        verbose_name='cohorte activa',
        help_text='El cuatrimestre en curso. Solo puede haber una activa.',
    )

    class Meta:
        verbose_name = 'cohorte'
        verbose_name_plural = 'cohortes'
        unique_together = ['anio', 'cuatrimestre']
        ordering = ['-anio', '-cuatrimestre']
        constraints = [
            models.UniqueConstraint(
                fields=['activa'],
                condition=Q(activa=True),
                name='unica_cohorte_activa',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.anio} – C{self.cuatrimestre}'
```

- [ ] **Step 4: Generar la migración**

```bash
powershell.exe -Command "Set-Location 'C:\Users\Angeles\Documents\IPC-Logica\IPC-Logica'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations cursos"
```

Esperado: crea `cursos/migrations/0007_cohorte.py` con `CreateModel` y `AddConstraint`.

- [ ] **Step 5: Correr el test para verificar que pasa**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos.tests.CohorteModelTests -v 2
```

Esperado: `OK` (5 tests).

- [ ] **Step 6: Registrar en el admin**

En `cursos/admin.py`, agregar `Cohorte` al import y registrar:

```python
from cursos.models import Cohorte, Comision, Inscripcion, NotaParcial, Parcial


@admin.register(Cohorte)
class CohorteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'anio', 'cuatrimestre', 'activa')
    list_filter = ('anio', 'cuatrimestre', 'activa')
    ordering = ('-anio', '-cuatrimestre')
```

- [ ] **Step 7: Commit**

```bash
git add cursos/models.py cursos/admin.py cursos/migrations/0007_cohorte.py cursos/tests.py
git commit -m "feat(cohorte): modelo Cohorte con constraint de unica activa"
```

---

### Task 2: FK nullable en los cuatro modelos

**Files:**
- Modify: `cursos/models.py` (`Inscripcion`, `Parcial`)
- Modify: `ejercicios/models.py` (`Progreso`, `Intento`)
- Create: `cursos/migrations/0008_cohorte_fks_nullable.py` (generada)
- Create: `ejercicios/migrations/0027_cohorte_fks_nullable.py` (generada)

**Interfaces:**
- Consumes: `cursos.models.Cohorte` de la Task 1.
- Produces: campo `cohorte` (nullable, `PROTECT`) en `Inscripcion`, `Parcial`, `Progreso`, `Intento`. `related_name` respectivamente: `inscripciones`, `parciales`, `progresos`, `intentos`.

Nullable primero, siempre: sin esto la migración no puede correr sobre una base con datos.

- [ ] **Step 1: Agregar el campo a `Inscripcion` y `Parcial`**

En `cursos/models.py`, dentro de `class Inscripcion`, después de `comision`:

```python
    cohorte = models.ForeignKey(
        'Cohorte',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inscripciones',
        verbose_name='cohorte',
    )
```

Dentro de `class Parcial`, después de `comision`:

```python
    cohorte = models.ForeignKey(
        'Cohorte',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='parciales',
        verbose_name='cohorte',
    )
```

- [ ] **Step 2: Agregar el campo a `Progreso` e `Intento`**

En `ejercicios/models.py`, dentro de `class Intento`, después de `practica_comision`:

```python
    cohorte = models.ForeignKey(
        'cursos.Cohorte',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='intentos',
        verbose_name='cohorte',
    )
```

Dentro de `class Progreso`, después de `practica_comision`:

```python
    cohorte = models.ForeignKey(
        'cursos.Cohorte',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='progresos',
        verbose_name='cohorte',
    )
```

**No tocar todavía** el `unique_together` de `Progreso`. Va en la Task 3, después del backfill: con filas en `cohorte=NULL` el constraint nuevo no se puede aplicar.

- [ ] **Step 3: Generar las migraciones**

```bash
powershell.exe -Command "Set-Location 'C:\Users\Angeles\Documents\IPC-Logica\IPC-Logica'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations cursos ejercicios"
```

Esperado: `cursos/migrations/0008_...` y `ejercicios/migrations/0027_...`, ambas con `AddField`.

- [ ] **Step 4: Verificar que la suite sigue verde**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos ejercicios docentes -v 1
```

Esperado: `OK`. Los campos son nullable y nadie los usa todavía, así que nada debe romperse. Si algo falla acá, es una regresión y hay que resolverla antes de seguir.

- [ ] **Step 5: Commit**

```bash
git add cursos/models.py ejercicios/models.py cursos/migrations/0008_*.py ejercicios/migrations/0027_*.py
git commit -m "feat(cohorte): FK nullable en Inscripcion, Parcial, Progreso e Intento"
```

---

### Task 3: Backfill, `NOT NULL` y write path

**Files:**
- Create: `cursos/migrations/0009_backfill_cohorte.py` (a mano)
- Create: `cursos/cohortes.py`
- Create: `cursos/migrations/0010_cohorte_not_null.py` (generada)
- Create: `ejercicios/migrations/0028_cohorte_not_null.py` (generada)
- Modify: `cursos/models.py` (`Inscripcion.Meta.unique_together`, quitar `null=True`)
- Modify: `ejercicios/models.py` (`Progreso.Meta.unique_together`, quitar `null=True`)
- Modify: `ejercicios/progreso.py`
- Modify: `ejercicios/api/views.py:288-292`
- Modify: `docentes/views.py:2063-2065`
- Modify: `ejercicios/views.py:288`
- Test: `cursos/tests.py`, `ejercicios/tests.py`

**Interfaces:**
- Consumes: las FK nullable de la Task 2.
- Produces:
  - `cursos.cohortes.cohorte_activa() -> Cohorte | None`
  - `cursos.cohortes.cohorte_de(estudiante, comision) -> Cohorte | None`
  - `ejercicios.progreso.eps_resueltos(estudiante, pc, cohorte) -> set[int]`
  - `ejercicios.progreso.esta_resuelto(estudiante, ep, pc, cohorte) -> bool`
  - `ejercicios.progreso.avanzar_progreso(estudiante, ep, pc, cohorte) -> tuple[bool, int]`
  - `Progreso.unique_together == ('estudiante', 'practica_comision', 'cohorte')`
  - `Inscripcion.unique_together == ('estudiante', 'comision', 'cohorte')`

**Esta tarea es indivisible.** Aplicar el `NOT NULL` sin arreglar los call sites deja la suite en rojo; arreglar los call sites sin el `NOT NULL` deja el bug de recursantes vivo. El orden de los steps está pensado para que el único commit quede verde.

Las tres funciones de `progreso.py` ganan un cuarto parámetro **posicional obligatorio**. Sin default: un default silencioso reintroduciría exactamente el bug que esta tarea evita.

- [ ] **Step 1: Escribir la migración de backfill a mano**

Crear `cursos/migrations/0009_backfill_cohorte.py`:

```python
"""Backfill de cohorte: toda la base existente es 2026-C1.

No hay estudiantes de otra camada todavía, así que no hace falta derivar la
cohorte de ninguna fecha. La guarda del principio existe porque esta migración
corre contra producción sobre un supuesto que no es verificable desde el
repositorio: si el supuesto no vale, aborta en vez de etiquetar mal en silencio.

atomic = False porque PostgreSQL no permite ALTER TABLE en la misma transacción
que INSERTs con FK deferred pendientes (mismo motivo que ejercicios/0015).
"""
from django.db import migrations

ANIO = 2026
CUATRIMESTRE = 1


def backfill(apps, schema_editor):
    Cohorte = apps.get_model('cursos', 'Cohorte')
    Inscripcion = apps.get_model('cursos', 'Inscripcion')
    Parcial = apps.get_model('cursos', 'Parcial')
    Progreso = apps.get_model('ejercicios', 'Progreso')
    Intento = apps.get_model('ejercicios', 'Intento')

    fuera = Inscripcion.objects.exclude(fecha_inscripcion__year=ANIO).count()
    if fuera:
        raise RuntimeError(
            f'{fuera} inscripciones fuera de {ANIO}. El backfill asume que toda '
            f'la base es {ANIO}-C{CUATRIMESTRE}. Revisar antes de migrar.'
        )

    cohorte, _ = Cohorte.objects.get_or_create(
        anio=ANIO,
        cuatrimestre=CUATRIMESTRE,
        defaults={'activa': True},
    )

    for modelo in (Inscripcion, Parcial, Progreso, Intento):
        modelo.objects.filter(cohorte__isnull=True).update(cohorte=cohorte)

    # Corte temprano: si algo quedó sin atribuir, fallar acá y no en el NOT NULL.
    for modelo in (Inscripcion, Parcial, Progreso, Intento):
        faltan = modelo.objects.filter(cohorte__isnull=True).count()
        if faltan:
            raise RuntimeError(
                f'{modelo.__name__}: {faltan} filas sin cohorte tras el backfill.'
            )


def revertir(apps, schema_editor):
    for app, nombre in (
        ('cursos', 'Inscripcion'), ('cursos', 'Parcial'),
        ('ejercicios', 'Progreso'), ('ejercicios', 'Intento'),
    ):
        apps.get_model(app, nombre).objects.update(cohorte=None)


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('cursos', '0008_cohorte_fks_nullable'),
        ('ejercicios', '0027_cohorte_fks_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill, revertir),
    ]
```

Ajustar los nombres en `dependencies` a los que haya generado `makemigrations` en la Task 2.

- [ ] **Step 2: Correr la migración**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py migrate
```

Esperado: aplica sin error. Sobre una base vacía la guarda cuenta 0 y el `update` no toca nada.

- [ ] **Step 3: Escribir el test del backfill y de `PROTECT`**

En `cursos/tests.py`. Si el helper `_u` no está en el archivo, replicarlo de `docentes/tests.py:23`:

```python
class BackfillCohorteTests(TestCase):
    """Verifica el estado post-migración sobre la base de tests."""

    def test_existe_cohorte_2026_c1_activa(self):
        from cursos.models import Cohorte
        cohorte = Cohorte.objects.filter(anio=2026, cuatrimestre=1).first()
        self.assertIsNotNone(cohorte, 'el backfill debe crear 2026-C1')
        self.assertTrue(cohorte.activa)


class CohortePROTECTTests(TestCase):
    def test_no_se_puede_borrar_cohorte_con_inscripciones(self):
        from django.db.models import ProtectedError
        from cursos.models import Cohorte, Comision, Inscripcion

        cohorte = Cohorte.objects.create(anio=2027, cuatrimestre=1)
        comision = Comision.objects.create(nombre='Prueba')
        est = _u('protegido')
        Inscripcion.objects.create(estudiante=est, comision=comision, cohorte=cohorte)

        with self.assertRaises(ProtectedError):
            cohorte.delete()
```

- [ ] **Step 4: Escribir el test de `cursos/cohortes.py`**

En `cursos/tests.py`, agregando arriba del archivo:

```python
from datetime import timedelta
from django.utils import timezone
```

```python
class ResolucionCohorteTests(TestCase):
    def setUp(self):
        from cursos.models import Cohorte, Comision
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.comision = Comision.objects.create(nombre='IPC Noche')

    def test_cohorte_activa_devuelve_la_marcada(self):
        from cursos.cohortes import cohorte_activa
        self.assertEqual(cohorte_activa(), self.c1)

    def test_cohorte_de_sin_inscripcion_devuelve_none(self):
        from cursos.cohortes import cohorte_de
        est = _u('sin-inscripcion')
        self.assertIsNone(cohorte_de(est, self.comision))

    def test_cohorte_de_devuelve_la_de_su_inscripcion(self):
        from cursos.cohortes import cohorte_de
        from cursos.models import Inscripcion
        est = _u('camada-vieja')
        Inscripcion.objects.create(estudiante=est, comision=self.comision, cohorte=self.c1)
        self.assertEqual(cohorte_de(est, self.comision), self.c1)

    def test_recursante_resuelve_a_la_inscripcion_mas_reciente(self):
        from cursos.cohortes import cohorte_de
        from cursos.models import Inscripcion
        est = _u('recursa')
        vieja = Inscripcion.objects.create(estudiante=est, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.filter(pk=vieja.pk).update(
            fecha_inscripcion=timezone.now() - timedelta(days=200)
        )
        Inscripcion.objects.create(estudiante=est, comision=self.comision, cohorte=self.c2)
        self.assertEqual(cohorte_de(est, self.comision), self.c2)
```

- [ ] **Step 5: Correr para verificar que fallan**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos.tests -v 2
```

Esperado: `ModuleNotFoundError: No module named 'cursos.cohortes'`, y `test_recursante_...` con `IntegrityError` — `Inscripcion.unique_together` es hoy `['estudiante', 'comision']` y bloquea la segunda inscripción. Los dos son reales y se arreglan en los steps siguientes.

- [ ] **Step 6: Ampliar el `unique_together` de `Inscripcion`**

El requisito de recursantes es incompatible con la constraint actual. En `cursos/models.py`, `class Inscripcion`, `class Meta`:

```python
        unique_together = ['estudiante', 'comision', 'cohorte']
```

- [ ] **Step 7: Escribir `cursos/cohortes.py`**

```python
"""Resolución de cohortes.

Módulo sin dependencias de vistas ni de la app ``ejercicios``, para que
``ejercicios`` pueda importarlo sin ciclo.
"""

from cursos.models import Cohorte, Inscripcion


def cohorte_activa():
    """La cohorte del cuatrimestre en curso, o ``None`` si no hay ninguna.

    El constraint ``unica_cohorte_activa`` garantiza que haya a lo sumo una.
    """
    return Cohorte.objects.filter(activa=True).first()


def cohorte_de(estudiante, comision):
    """Cohorte de ``estudiante`` en ``comision``, o ``None`` si no cursa ahí.

    Es la de su **inscripción más reciente** en esa comisión. Resuelve los dos
    casos de una sola regla:

    - Quien es de una camada anterior y sigue practicando para rendir el final
      acumula en su propia cohorte, no en la vigente.
    - Quien recursa tiene una inscripción nueva y acumula en la cohorte nueva,
      arrancando de cero.

    El desempate por ``-id`` cubre el caso de dos inscripciones con el mismo
    ``fecha_inscripcion`` (posible si se crean en el mismo request).
    """
    inscripcion = (
        Inscripcion.objects
        .filter(estudiante=estudiante, comision=comision)
        .order_by('-fecha_inscripcion', '-id')
        .first()
    )
    return inscripcion.cohorte if inscripcion else None
```

- [ ] **Step 8: Escribir el test del aislamiento de recursantes**

En `ejercicios/tests.py`:

```python
class RecursanteAisladoTests(TestCase):
    """Lo resuelto en una cohorte no cuenta como resuelto en la siguiente."""

    def setUp(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        from ejercicios.models import Ejercicio, EjercicioPractica, Practica, PracticaComision

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.est = _u('recursa-progreso')
        self.comision = Comision.objects.create(nombre='IPC Noche')
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c1)

        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)

    def test_intento_correcto_de_c1_no_cuenta_en_c2(self):
        from ejercicios.models import Intento
        from ejercicios.progreso import esta_resuelto

        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )
        self.assertTrue(esta_resuelto(self.est, self.ep, self.pc, self.c1))
        self.assertFalse(esta_resuelto(self.est, self.ep, self.pc, self.c2))

    def test_eps_resueltos_acota_por_cohorte(self):
        from ejercicios.models import Intento
        from ejercicios.progreso import eps_resueltos

        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )
        self.assertEqual(eps_resueltos(self.est, self.pc, self.c1), {self.ep.pk})
        self.assertEqual(eps_resueltos(self.est, self.pc, self.c2), set())

    def test_avanzar_progreso_crea_fila_por_cohorte(self):
        from ejercicios.models import Intento, Progreso
        from ejercicios.progreso import avanzar_progreso

        Intento.objects.create(
            estudiante=self.est, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.c1, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.est, self.ep, self.pc, self.c1)
        avanzar_progreso(self.est, self.ep, self.pc, self.c2)

        self.assertEqual(
            Progreso.objects.filter(estudiante=self.est, practica_comision=self.pc).count(), 2,
        )
```

Y el test del constraint nuevo de `Progreso`:

```python
class ProgresoClavePorCohorteTests(TestCase):
    """El progreso es por terna (estudiante, practica_comision, cohorte)."""

    def setUp(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        from ejercicios.models import Ejercicio, EjercicioPractica, Practica, PracticaComision

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.est = _u('recursante')
        self.comision = Comision.objects.create(nombre='IPC Noche')
        Inscripcion.objects.create(estudiante=self.est, comision=self.comision, cohorte=self.c1)
        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)

    def test_acepta_mismo_par_en_dos_cohortes(self):
        from ejercicios.models import Progreso
        Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c1)
        Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c2)
        self.assertEqual(Progreso.objects.filter(estudiante=self.est).count(), 2)

    def test_rechaza_duplicado_dentro_de_una_cohorte(self):
        from django.db import IntegrityError, transaction
        from ejercicios.models import Progreso
        Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Progreso.objects.create(estudiante=self.est, practica_comision=self.pc, cohorte=self.c1)
```

- [ ] **Step 9: Agregar cohorte a las tres funciones de `progreso.py`**

En `ejercicios/progreso.py`, reemplazar las tres firmas y sus queries:

```python
def eps_resueltos(estudiante, pc, cohorte) -> set[int]:
    """Ids de los EjercicioPractica ya resueltos por ``estudiante`` en ``pc``.

    Acota por ``practica_comision`` y por ``cohorte``: ni lo resuelto en otra
    comisión que comparta la práctica canónica, ni lo resuelto en una camada
    anterior de esta misma comisión, cuenta acá.

    Usa la correctitud efectiva de :mod:`ejercicios.correctitud`: el juicio
    docente tiene precedencia sobre el resultado del motor.
    """
    return set(
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, practica_comision=pc, cohorte=cohorte)
        .values_list('ejercicio_practica_id', flat=True)
        .distinct()
    )


def esta_resuelto(estudiante, ep, pc, cohorte) -> bool:
    """True si ``estudiante`` resolvió ``ep`` en ``pc`` dentro de ``cohorte``."""
    return (
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, ejercicio_practica=ep,
                practica_comision=pc, cohorte=cohorte)
        .exists()
    )
```

En `avanzar_progreso`, cambiar la firma:

```python
def avanzar_progreso(estudiante, ep, pc, cohorte) -> tuple[bool, int]:
```

Agregar al docstring, en `Args:`:

```
        cohorte: la :class:`~cursos.models.Cohorte` del estudiante en esa
            comisión. Define qué fila de progreso se avanza: quien recursa
            tiene una fila por camada.
```

Dentro del `with transaction.atomic():`, agregar `cohorte=cohorte` a las tres queries de `Progreso`:

```python
        progreso = (
            Progreso.objects
            .select_for_update()
            .filter(estudiante=estudiante, practica_comision=pc, cohorte=cohorte)
            .first()
        )
        if progreso is None:
            progreso, _ = Progreso.objects.get_or_create(
                estudiante=estudiante,
                practica_comision=pc,
                cohorte=cohorte,
                defaults={'ejercicio_practica_actual': ep},
            )
            progreso = (
                Progreso.objects
                .select_for_update()
                .get(estudiante=estudiante, practica_comision=pc, cohorte=cohorte)
            )
```

Y en la rama de modo libre:

```python
            resueltos = eps_resueltos(estudiante, pc, cohorte)
```

- [ ] **Step 10: Actualizar los tres call sites**

`ejercicios/api/views.py` — después del bloque que resuelve `pc` (línea ~118), agregar:

```python
        from cursos.cohortes import cohorte_de

        cohorte = cohorte_de(request.user, pc.comision)
        if cohorte is None:
            return Response(
                {'detail': 'No estás inscripto en esta comisión.'},
                status=status.HTTP_403_FORBIDDEN,
            )
```

En el `Intento.objects.create(...)` de la línea ~289, agregar `cohorte=cohorte,` después de `practica_comision=pc,`.

Y en la llamada a `avanzar_progreso` de ese mismo archivo, pasar `cohorte` como cuarto argumento.

`docentes/views.py:2063` — reemplazar:

```python
def _avanzar_progreso_por_aprobacion_docente(intento):
    """Avanza el progreso cuando el docente aprueba a mano un intento incorrecto.

    Delega en :func:`ejercicios.progreso.avanzar_progreso`. La comisión, el modo
    de desbloqueo y la cohorte salen del propio intento.
    """
    avanzar_progreso(
        intento.estudiante, intento.ejercicio_practica, intento.practica_comision,
        intento.cohorte,
    )
```

`ejercicios/views.py:288` — reemplazar:

```python
        from cursos.cohortes import cohorte_de
        cohorte_est = cohorte_de(usuario, pc.comision)
        ya_resuelto = esta_resuelto(usuario, ep, pc, cohorte_est)
```

Buscar el resto de llamadas con:

```bash
grep -rn "esta_resuelto\|eps_resueltos\|avanzar_progreso" --include=*.py .
```

Cada una tiene que pasar cohorte. Ninguna debe quedar con la firma vieja.

- [ ] **Step 11: Cambiar el `unique_together` de `Progreso`**

En `ejercicios/models.py`, en `class Progreso`, `class Meta`:

```python
        unique_together = ['estudiante', 'practica_comision', 'cohorte']
```

Y actualizar el docstring de la clase: donde dice "Una fila por par ``(estudiante, practica_comision)``", cambiar a "Una fila por terna ``(estudiante, practica_comision, cohorte)``: el progreso es del cursado **de una camada**. Quien recursa la misma comisión en otra cohorte arranca con una fila nueva y su progreso anterior queda intacto."

- [ ] **Step 12: Quitar `null=True` de los cuatro campos**

En `cursos/models.py` y `ejercicios/models.py`, borrar `null=True,` y `blank=True,` de los cuatro campos `cohorte`.

- [ ] **Step 13: Generar las migraciones restantes**

```bash
powershell.exe -Command "Set-Location 'C:\Users\Angeles\Documents\IPC-Logica\IPC-Logica'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations cursos ejercicios"
```

Django puede pedir un default para las filas existentes. Como el backfill ya las llenó, editar a mano la migración generada para que **no** pida default y para que dependa de `cursos.0009_backfill_cohorte`.

Verificar que la migración de `ejercicios` contenga tanto los `AlterField` como el `AlterUniqueTogether`:

```python
        migrations.AlterUniqueTogether(
            name='progreso',
            unique_together={('estudiante', 'practica_comision', 'cohorte')},
        ),
```

Y la de `cursos` el `AlterUniqueTogether` de `inscripcion`.

- [ ] **Step 14: Actualizar los tests existentes que crean filas sin cohorte**

```bash
grep -rn "Inscripcion.objects.create\|Intento.objects.create\|Progreso.objects.create\|Parcial.objects.create" --include=*.py .
```

Cada uno en un test necesita `cohorte=`. En los `setUp`, agregar:

```python
        from cursos.models import Cohorte
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
```

y pasar `cohorte=self.cohorte`.

- [ ] **Step 15: Correr la suite completa — tiene que quedar verde**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test -v 1
```

Esperado: `OK`. Este es el gate de la tarea: no commitear con nada rojo. Si queda algún fallo, es un call site o un test sin actualizar — arreglarlo antes de seguir, no dejarlo para después.

- [ ] **Step 16: Commit**

```bash
git add cursos/ ejercicios/ docentes/views.py
git commit -m "feat(cohorte): backfill, NOT NULL, clave por cohorte y write path"
```

---

### Task 4: Crear cohorte (solo superusuarios)

**Files:**
- Modify: `docentes/forms.py`
- Modify: `docentes/views.py`
- Modify: `docentes/urls.py`
- Test: `docentes/tests.py`

**Interfaces:**
- Consumes: `cursos.cohortes.cohorte_activa`.
- Produces: vista `docentes:cohorte_create`, `CohorteForm` con campos `anio` y `cuatrimestre`.

- [ ] **Step 1: Escribir los tests de permisos**

En `docentes/tests.py`:

```python
class CohorteCreateTests(TestCase):
    def setUp(self):
        from cursos.models import Cohorte, Comision
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.docente = _u('doc-cohorte', es_docente=True)
        self.staff_no_super = _u('staff-cohorte', is_staff=True, is_superuser=False)
        self.superuser = _u('super-cohorte', is_staff=True, is_superuser=True)
        self.comision = Comision.objects.create(nombre='IPC Noche')
        self.comision.docentes.add(self.docente)
        self.url = reverse('docentes:cohorte_create')

    def _post(self, anio=2026, cuatrimestre=2):
        return self.client.post(self.url, {'anio': anio, 'cuatrimestre': cuatrimestre})

    def test_docente_recibe_403(self):
        from cursos.models import Cohorte
        self.client.login(username='doc-cohorte', password='clave123')
        self.assertEqual(self._post().status_code, 403)
        self.assertEqual(Cohorte.objects.count(), 1)

    def test_staff_no_superusuario_recibe_403(self):
        """La distinción que este diseño introduce: is_staff no alcanza."""
        from cursos.models import Cohorte
        self.client.login(username='staff-cohorte', password='clave123')
        self.assertEqual(self._post().status_code, 403)
        self.assertEqual(Cohorte.objects.count(), 1)

    def test_superusuario_crea_y_activa(self):
        from cursos.models import Cohorte
        self.client.login(username='super-cohorte', password='clave123')
        self._post()
        nueva = Cohorte.objects.get(anio=2026, cuatrimestre=2)
        self.c1.refresh_from_db()
        self.assertTrue(nueva.activa)
        self.assertFalse(self.c1.activa)

    def test_duplicada_no_crea_ni_cambia_activa(self):
        from cursos.models import Cohorte
        self.client.login(username='super-cohorte', password='clave123')
        self._post(anio=2026, cuatrimestre=1)
        self.c1.refresh_from_db()
        self.assertEqual(Cohorte.objects.count(), 1)
        self.assertTrue(self.c1.activa)

    def test_rechazo_no_deja_cohorte_creada(self):
        from cursos.models import Cohorte
        self.client.login(username='doc-cohorte', password='clave123')
        self._post(anio=2027, cuatrimestre=1)
        self.assertFalse(Cohorte.objects.filter(anio=2027).exists())
```

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.CohorteCreateTests -v 2
```

Esperado: `NoReverseMatch: Reverse for 'cohorte_create' not found`

- [ ] **Step 3: Escribir el form**

En `docentes/forms.py`:

```python
from cursos.models import Cohorte


class CohorteForm(forms.ModelForm):
    """Alta de cohorte. Solo la usan superusuarios."""

    class Meta:
        model = Cohorte
        fields = ['anio', 'cuatrimestre']

    def clean(self):
        cleaned = super().clean()
        anio = cleaned.get('anio')
        cuatrimestre = cleaned.get('cuatrimestre')
        if anio and cuatrimestre:
            if Cohorte.objects.filter(anio=anio, cuatrimestre=cuatrimestre).exists():
                raise forms.ValidationError(
                    f'La cohorte {anio} – C{cuatrimestre} ya existe.'
                )
        return cleaned
```

- [ ] **Step 4: Escribir la vista**

En `docentes/views.py`:

```python
def _siguiente_cohorte():
    """(anio, cuatrimestre) del cuatrimestre siguiente al activo.

    Si la activa es C1, propone C2 del mismo año; si es C2, propone C1 del
    año siguiente. Sin cohorte activa, propone el cuatrimestre en curso según
    la fecha de hoy.
    """
    from cursos.cohortes import cohorte_activa
    activa = cohorte_activa()
    if activa is None:
        hoy = timezone.localdate()
        return hoy.year, (1 if hoy.month <= 7 else 2)
    if activa.cuatrimestre == 1:
        return activa.anio, 2
    return activa.anio + 1, 1


@login_required
@require_POST
def cohorte_create(request):
    """Crea una cohorte y la marca activa. Solo superusuarios.

    Crear una cohorte es global: cambia cuál es la cohorte activa para toda la
    plataforma, no solo para la comisión desde la que se dispara. Por eso el
    gate es ``is_superuser`` y no ``is_staff`` como en el resto del panel.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    form = CohorteForm(request.POST)
    destino = request.POST.get('next') or reverse('docentes:comisiones_list')

    if not form.is_valid():
        for error in form.errors.get('__all__', []) or ['No se pudo crear la cohorte.']:
            messages.error(request, error)
        return redirect(destino)

    with transaction.atomic():
        Cohorte.objects.filter(activa=True).update(activa=False)
        cohorte = form.save(commit=False)
        cohorte.activa = True
        cohorte.save()

    messages.success(request, f'Cohorte {cohorte} creada y marcada como activa.')
    return redirect(destino)
```

Agregar a los imports de `docentes/views.py`:

```python
from django.urls import reverse
from django.utils import timezone

from cursos.models import Cohorte
from docentes.forms import CohorteForm
```

(Ajustar según cómo estén ya escritos los imports del archivo; `Cohorte` va junto a `Comision, Inscripcion, NotaParcial, Parcial` en la línea 24.)

- [ ] **Step 5: Agregar la ruta**

En `docentes/urls.py`, después de la línea de `comision_create`:

```python
    path('cohortes/nueva/', views.cohorte_create, name='cohorte_create'),
```

- [ ] **Step 6: Correr los tests**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.CohorteCreateTests -v 2
```

Esperado: `OK` (5 tests).

- [ ] **Step 7: Commit**

```bash
git add docentes/forms.py docentes/views.py docentes/urls.py docentes/tests.py
git commit -m "feat(cohorte): alta de cohorte restringida a superusuarios"
```

---

### Task 5: Selector de cohorte en el panel

**Files:**
- Modify: `docentes/views.py:634-754` (`comision_detail`)
- Create: `templates/docentes/_selector_cohorte.html`
- Modify: `templates/docentes/comision_detail.html`
- Test: `docentes/tests.py`

**Interfaces:**
- Consumes: `cursos.cohortes.cohorte_activa`, vista `docentes:cohorte_create`.
- Produces: `comision_detail` acepta `?cohorte=<id>`; context gana `cohorte_actual`, `cohortes_disponibles`, `es_cohorte_activa`, `siguiente_cohorte`.

- [ ] **Step 1: Escribir los tests**

En `docentes/tests.py`:

```python
class SelectorCohorteTests(TestCase):
    def setUp(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.docente = _u('doc-sel', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC Noche')
        self.comision.docentes.add(self.docente)

        self.est_c1 = _u('est-c1')
        self.est_c2 = _u('est-c2')
        Inscripcion.objects.create(estudiante=self.est_c1, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est_c2, comision=self.comision, cohorte=self.c2)

        Cohorte.objects.filter(pk=self.c1.pk).update(activa=False)
        Cohorte.objects.filter(pk=self.c2.pk).update(activa=True)

        self.client.login(username='doc-sel', password='clave123')
        self.url = reverse('docentes:comision_detail', args=[self.comision.id])

    def test_default_muestra_la_cohorte_activa(self):
        resp = self.client.get(self.url)
        usernames = [e.username for e in resp.context['estudiantes']]
        self.assertEqual(usernames, ['est-c2'])

    def test_querystring_cambia_la_cohorte(self):
        resp = self.client.get(self.url, {'cohorte': self.c1.pk})
        usernames = [e.username for e in resp.context['estudiantes']]
        self.assertEqual(usernames, ['est-c1'])

    def test_practicas_no_cambian_entre_cohortes(self):
        """El requisito central: el aula conserva sus prácticas."""
        from ejercicios.models import Practica, PracticaComision
        practica = Practica.objects.create(titulo='P1')
        PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)

        activa = self.client.get(self.url)
        vieja = self.client.get(self.url, {'cohorte': self.c1.pk})

        titulos_activa = [i['pc'].practica.titulo for i in activa.context['practicas_con_form']]
        titulos_vieja = [i['pc'].practica.titulo for i in vieja.context['practicas_con_form']]
        self.assertEqual(titulos_activa, ['P1'])
        self.assertEqual(titulos_activa, titulos_vieja)

    def test_cohorte_inexistente_cae_a_la_activa(self):
        resp = self.client.get(self.url, {'cohorte': 99999})
        self.assertEqual(resp.context['cohorte_actual'], self.c2)

    def test_solo_lista_cohortes_con_inscripciones_en_esta_comision(self):
        from cursos.models import Cohorte
        Cohorte.objects.create(anio=2027, cuatrimestre=1)
        resp = self.client.get(self.url)
        self.assertEqual(
            [c.pk for c in resp.context['cohortes_disponibles']],
            [self.c2.pk, self.c1.pk],
        )

    def test_parciales_filtran_por_cohorte(self):
        from cursos.models import Parcial
        from datetime import date
        Parcial.objects.create(
            comision=self.comision, cohorte=self.c1, nombre='P1 vieja',
            fecha=date(2026, 5, 1), puntaje_total=10,
        )
        activa = self.client.get(self.url)
        vieja = self.client.get(self.url, {'cohorte': self.c1.pk})
        self.assertEqual(list(activa.context['parciales']), [])
        self.assertEqual([p.nombre for p in vieja.context['parciales']], ['P1 vieja'])
```

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.SelectorCohorteTests -v 2
```

Esperado: `KeyError: 'cohorte_actual'`

- [ ] **Step 3: Escribir el helper de resolución**

En `docentes/views.py`, antes de `comision_detail`:

```python
def _cohortes_de_comision(comision):
    """Cohortes con al menos una inscripción en esta comisión, más nuevas primero."""
    return list(
        Cohorte.objects
        .filter(inscripciones__comision=comision)
        .distinct()
        .order_by('-anio', '-cuatrimestre')
    )


def _resolver_cohorte(param, comision):
    """Cohorte a mostrar: la del querystring si es válida, si no la activa.

    Un id inexistente o sin inscripciones en esta comisión cae a la activa en
    silencio: es navegación, no un error del que haya que avisar.
    """
    from cursos.cohortes import cohorte_activa

    disponibles = _cohortes_de_comision(comision)
    if param and str(param).isdigit():
        elegida = next((c for c in disponibles if c.pk == int(param)), None)
        if elegida is not None:
            return elegida, disponibles
    activa = cohorte_activa()
    if activa is not None:
        return activa, disponibles
    return (disponibles[0] if disponibles else None), disponibles
```

- [ ] **Step 4: Filtrar en `comision_detail`**

En `docentes/views.py:637`, reemplazar el `Prefetch` de `inscripciones` para que filtre por cohorte. Resolver la cohorte **antes** del `get_object_or_404`:

```python
    comision = get_object_or_404(Comision, pk=comision_id)
    if not request.user.is_staff and not comision.docentes.filter(pk=request.user.pk).exists():
        raise PermissionDenied

    cohorte, cohortes_disponibles = _resolver_cohorte(request.GET.get('cohorte'), comision)

    comision = get_object_or_404(
        Comision.objects.prefetch_related(
            'docentes',
            Prefetch(
                'inscripciones',
                queryset=Inscripcion.objects
                    .filter(cohorte=cohorte)
                    .select_related('estudiante', 'estudiante__encuesta')
                    .order_by('estudiante__last_name', 'estudiante__first_name', 'estudiante__username'),
            ),
            Prefetch(
                'practicas_comisiones',
                queryset=PracticaComision.objects.order_by('orden').select_related('practica').prefetch_related(
                    Prefetch(
                        'practica__ejercicio_practicas',
                        queryset=EjercicioPractica.objects.order_by('orden'),
                    ),
                    Prefetch(
                        'progresos',
                        queryset=Progreso.objects.filter(cohorte=cohorte).select_related('ejercicio_practica_actual'),
                    ),
                ),
            ),
        ),
        pk=comision_id,
    )
```

El `Prefetch` de `practicas_comisiones` **no filtra por cohorte** — las prácticas son del aula. Solo su `progresos` anidado filtra.

Filtrar los parciales:

```python
    parciales = (
        Parcial.objects
        .filter(comision=comision, cohorte=cohorte)
        .order_by('fecha', 'nombre')
        .annotate(
            total_notas=Count('notas'),
            notas_cargadas=Count('notas', filter=Q(notas__puntaje__isnull=False)),
        )
    )
```

Agregar al context del `render`:

```python
        'cohorte_actual': cohorte,
        'cohortes_disponibles': cohortes_disponibles,
        'es_cohorte_activa': bool(cohorte and cohorte.activa),
        'siguiente_cohorte': _siguiente_cohorte(),
        'cohorte_form': CohorteForm(),
```

- [ ] **Step 5: Escribir el parcial del selector**

Crear `templates/docentes/_selector_cohorte.html`:

```html
{% if cohortes_disponibles|length > 1 %}
  <form method="get" style="display:inline-flex; align-items:center; gap:0.5rem; margin:0.5rem 0;">
    <label for="cohorte" style="font-size:0.9rem; color:#555;">Cohorte</label>
    <select name="cohorte" id="cohorte" onchange="this.form.submit()"
            style="padding:0.3rem 0.5rem; border-radius:4px; border:1px solid #ccc;">
      {% for c in cohortes_disponibles %}
        <option value="{{ c.pk }}" {% if c.pk == cohorte_actual.pk %}selected{% endif %}>
          {{ c }}{% if c.activa %} · en curso{% endif %}
        </option>
      {% endfor %}
    </select>
    <noscript><button type="submit">Ver</button></noscript>
  </form>
{% endif %}

{% if not es_cohorte_activa %}
  <p style="margin:0.5rem 0; padding:0.5rem 0.75rem; background:#fff4e0; border-left:3px solid #c07000; font-size:0.9rem;">
    Estás viendo una cohorte cerrada. No se pueden agregar estudiantes ni crear parciales.
    Sí podés corregir intentos y cargar notas de parciales existentes.
  </p>
{% endif %}

{% if user.is_superuser %}
  <form method="post" action="{% url 'docentes:cohorte_create' %}" style="display:inline-block; margin:0.5rem 0;">
    {% csrf_token %}
    <input type="hidden" name="anio" value="{{ siguiente_cohorte.0 }}">
    <input type="hidden" name="cuatrimestre" value="{{ siguiente_cohorte.1 }}">
    <input type="hidden" name="next" value="{{ request.get_full_path }}">
    <button type="submit"
            onclick="return confirm('Crear la cohorte {{ siguiente_cohorte.0 }} – C{{ siguiente_cohorte.1 }} y marcarla activa? Afecta a TODAS las comisiones de la plataforma.');"
            style="padding:0.4rem 0.8rem; border-radius:4px; border:1px solid #2a7a2a; background:#f0f8f0; color:#2a7a2a; cursor:pointer;">
      + Nueva cohorte ({{ siguiente_cohorte.0 }} – C{{ siguiente_cohorte.1 }})
    </button>
  </form>
{% endif %}
```

- [ ] **Step 6: Incluir el parcial en la vista**

En `templates/docentes/comision_detail.html`, después del `<h1>` de la línea 41:

```html
    {% include 'docentes/_selector_cohorte.html' %}
```

- [ ] **Step 7: Correr los tests**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.SelectorCohorteTests -v 2
```

Esperado: `OK` (6 tests).

- [ ] **Step 8: Commit**

```bash
git add docentes/views.py templates/docentes/ docentes/tests.py
git commit -m "feat(cohorte): selector de cohorte en el panel de comision"
```

---

### Task 6: Bloqueo de altas y parciales en cohortes cerradas

**Files:**
- Modify: `docentes/views.py` (`estudiante_create`, `estudiantes_importar`, `parcial_create`, `_procesar_importacion_estudiantes`)
- Modify: `templates/docentes/comision_detail.html`
- Test: `docentes/tests.py`

**Interfaces:**
- Consumes: `_resolver_cohorte` de la Task 5.
- Produces: `_require_cohorte_activa(cohorte)` que lanza `PermissionDenied` si la cohorte no está activa.

Las altas se hacen **sobre la cohorte que se está viendo**, que en una cohorte activa es la activa. El bloqueo es sobre el estado `activa`, no sobre "es la última".

- [ ] **Step 1: Escribir los tests**

En `docentes/tests.py`:

```python
class BloqueoCohorteCerradaTests(TestCase):
    def setUp(self):
        from cursos.models import Cohorte, Comision
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        Cohorte.objects.filter(pk=self.c1.pk).update(activa=False)
        Cohorte.objects.filter(pk=self.c2.pk).update(activa=True)

        self.docente = _u('doc-bloqueo', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC Noche')
        self.comision.docentes.add(self.docente)
        self.client.login(username='doc-bloqueo', password='clave123')

    def test_alta_en_cohorte_cerrada_devuelve_403(self):
        url = reverse('docentes:estudiante_create', args=[self.comision.id])
        resp = self.client.post(f'{url}?cohorte={self.c1.pk}', {
            'username': 'nuevo', 'email': 'n@e.com', 'password': 'clave123',
            'first_name': 'N', 'last_name': 'E',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Usuario.objects.filter(username='nuevo').exists())

    def test_alta_en_cohorte_activa_funciona_e_inscribe_en_ella(self):
        from cursos.models import Inscripcion
        url = reverse('docentes:estudiante_create', args=[self.comision.id])
        self.client.post(url, {
            'username': 'nuevo2', 'email': 'n2@e.com', 'password': 'clave123',
            'first_name': 'N', 'last_name': 'E',
        })
        inscripcion = Inscripcion.objects.get(estudiante__username='nuevo2')
        self.assertEqual(inscripcion.cohorte, self.c2)

    def test_parcial_en_cohorte_cerrada_devuelve_403(self):
        from cursos.models import Parcial
        url = reverse('docentes:parcial_create', args=[self.comision.id])
        resp = self.client.post(f'{url}?cohorte={self.c1.pk}', {
            'nombre': 'P1', 'fecha': '2026-05-01', 'puntaje_total': '10',
            'umbral_aprobacion': '4', 'umbral_promocion': '7',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Parcial.objects.filter(nombre='P1').exists())

    def test_importacion_en_cohorte_cerrada_devuelve_403(self):
        url = reverse('docentes:estudiantes_importar', args=[self.comision.id])
        resp = self.client.post(f'{url}?cohorte={self.c1.pk}', {})
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.BloqueoCohorteCerradaTests -v 2
```

Esperado: los tests de 403 fallan con 200 ó 302.

- [ ] **Step 3: Escribir la guarda**

En `docentes/views.py`, junto a `_require_docente`:

```python
def _require_cohorte_activa(cohorte):
    """Impide modificar la composición de una camada cerrada.

    Una cohorte no activa no crece ni suma instancias de evaluación. Sí se le
    siguen corrigiendo intentos y cargando notas de parciales existentes, así
    que esta guarda va solo en las altas.
    """
    if cohorte is None or not cohorte.activa:
        raise PermissionDenied
```

- [ ] **Step 4: Aplicar la guarda en las tres vistas**

En `estudiante_create` (línea ~797), después del check de permisos:

```python
    cohorte, _ = _resolver_cohorte(request.GET.get('cohorte'), comision)
    if request.method == 'POST':
        _require_cohorte_activa(cohorte)
```

Y en el `Inscripcion.objects.create` de la línea 807:

```python
            Inscripcion.objects.create(estudiante=estudiante, comision=comision, cohorte=cohorte)
```

En `estudiantes_importar` (línea ~830), igual:

```python
    cohorte, _ = _resolver_cohorte(request.GET.get('cohorte'), comision)
    if request.method == 'POST':
        _require_cohorte_activa(cohorte)
```

Y pasar la cohorte al helper:

```python
            reporte = _procesar_importacion_estudiantes(form.cleaned_data['archivo'], comision, cohorte)
```

En `_procesar_importacion_estudiantes` (línea 957), cambiar la firma y el `create`:

```python
def _procesar_importacion_estudiantes(archivo, comision, cohorte):
```

```python
                Inscripcion.objects.create(estudiante=estudiante, comision=comision, cohorte=cohorte)
```

En `parcial_create` (línea ~1560), después del check de permisos, la misma guarda, y pasar `cohorte=cohorte` al `Parcial.objects.create(...)`.

Los dos `render` de fallback de `estudiante_create` y `estudiantes_importar` (líneas 813-826 y 851-865) filtran estudiantes sin cohorte. Cambiar las dos queries de `Usuario.objects.filter(inscripciones__comision=comision)` a:

```python
        Usuario.objects.filter(inscripciones__comision=comision, inscripciones__cohorte=cohorte)
```

- [ ] **Step 5: Ocultar los formularios en el template**

En `templates/docentes/comision_detail.html`, envolver la sección "Agregar estudiante" (desde el `<h2>` de la línea 545 hasta el cierre de la importación masiva, línea ~615) en:

```html
{% if es_cohorte_activa %}
  ... (sección existente sin cambios) ...
{% endif %}
```

Lo mismo con el botón/formulario de crear parcial de la sección "Parciales" (línea ~264).

Ocultar el form no alcanza: la guarda del Step 3 es lo que realmente protege. El `{% if %}` es para que no se vea una acción que va a fallar.

- [ ] **Step 6: Correr los tests**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.BloqueoCohorteCerradaTests -v 2
```

Esperado: `OK` (4 tests).

- [ ] **Step 7: Commit**

```bash
git add docentes/views.py templates/docentes/comision_detail.html docentes/tests.py
git commit -m "feat(cohorte): bloquear altas y parciales en cohortes cerradas"
```

---

### Task 7: Analíticas por cohorte

**Files:**
- Modify: `analiticas/views.py:55-...` (8 funciones)
- Modify: `docentes/views.py:680-713` (llamadas y caché), `docentes/views.py:2123` (invalidación)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `estudiante_ids` resuelto en `comision_detail`.
- Produces: las 8 funciones pasan de `f(comision_ids, ...)` a `f(comision_ids, estudiante_ids, ...)`, con `estudiante_ids` como segundo parámetro posicional obligatorio.

Se pasa la lista de estudiantes y no el `cohorte_id` para que cada función no tenga que hacer su propio join contra `Inscripcion`. `_silencio_temprano` ya la necesita porque incluye a quienes nunca intentaron.

- [ ] **Step 1: Escribir el test del aislamiento**

En `analiticas/tests.py`:

```python
class AnaliticasPorCohorteTests(TestCase):
    def setUp(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        from ejercicios.models import Ejercicio, EjercicioPractica, Intento, Practica, PracticaComision

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.comision = Comision.objects.create(nombre='IPC Noche')

        self.est_c1 = _u('ana-c1')
        self.est_c2 = _u('ana-c2')
        Inscripcion.objects.create(estudiante=self.est_c1, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est_c2, comision=self.comision, cohorte=self.c2)

        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        self.ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(practica=practica, comision=self.comision, orden=1)

        for _ in range(4):
            Intento.objects.create(
                estudiante=self.est_c1, ejercicio_practica=self.ep, practica_comision=self.pc,
                cohorte=self.c1, respuesta_raw='q', es_correcto=False,
            )

    def test_ejercicios_dificiles_solo_cuenta_la_cohorte_pedida(self):
        from analiticas.views import _ejercicios_mas_dificiles

        con_c1 = _ejercicios_mas_dificiles([self.comision.id], [self.est_c1.id], min_intentos=1)
        con_c2 = _ejercicios_mas_dificiles([self.comision.id], [self.est_c2.id], min_intentos=1)

        self.assertEqual(len(con_c1), 1)
        self.assertEqual(con_c1[0]['total'], 4)
        self.assertEqual(con_c2, [])

    def test_silencio_temprano_solo_lista_la_cohorte_pedida(self):
        from analiticas.views import _silencio_temprano

        filas = _silencio_temprano([self.comision.id], [self.est_c2.id])
        self.assertEqual([f['username'] for f in filas], ['ana-c2'])
```

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.AnaliticasPorCohorteTests -v 2
```

Esperado: `TypeError: _ejercicios_mas_dificiles() takes ... positional arguments`

- [ ] **Step 3: Agregar el parámetro a las 8 funciones**

En `analiticas/views.py`, cada firma pasa de `(comision_ids, ...)` a `(comision_ids, estudiante_ids, ...)`:

```python
def _ejercicios_mas_dificiles(comision_ids, estudiante_ids, top_n=5, min_intentos=3):
def _estudiantes_en_riesgo(comision_ids, estudiante_ids, umbral_riesgo=5):
def _distribucion_intentos(comision_ids, estudiante_ids):
def _evolucion_temporal(comision_ids, estudiante_ids, semanas=_SEMANAS):
def _silencio_temprano(comision_ids, estudiante_ids):
def _errores_sistematicos(comision_ids, estudiante_ids, min_estudiantes=3):
def _concentracion_practica(comision_ids, estudiante_ids, umbral_maraton=10):
def _velocidad_arranque(comision_ids, estudiante_ids, umbral_arranque_dias=7):
```

En cada una, agregar el filtro al queryset de `Intento`:

```python
        .filter(
            practica_comision__comision_id__in=comision_ids,
            estudiante_id__in=estudiante_ids,
        )
```

En `_silencio_temprano`, que parte de los inscriptos y no de los intentos, reemplazar la query de estudiantes por `Usuario.objects.filter(pk__in=estudiante_ids)`.

Agregar el guard temprano al principio de cada función:

```python
    if not comision_ids or not estudiante_ids:
        return []
```

En cada docstring, agregar bajo `Args:`:

```
        estudiante_ids: IDs de los estudiantes de la cohorte a considerar.
            Acotar por cohorte acá y no por comisión evita que los intentos de
            una camada anterior entren en las métricas de la actual.
```

- [ ] **Step 4: Actualizar las llamadas en `comision_detail`**

En `docentes/views.py`, mover el cálculo de `estudiantes_ids` **antes** del bloque de analíticas, y cambiar la clave de caché:

```python
    _cache_key = f'analiticas_{comision_id}_{cohorte.pk if cohorte else 0}'
    analiticas = cache.get(_cache_key)
    if analiticas is None:
        _silencio_cd = _silencio_temprano(_ids, estudiantes_ids)
        analiticas = {
            'ejercicios_dificiles':  _ejercicios_mas_dificiles(
                _ids, estudiantes_ids, min_intentos=cfg.umbral_min_intentos,
            ),
            'en_riesgo':             _estudiantes_en_riesgo(
                _ids, estudiantes_ids, umbral_riesgo=cfg.umbral_riesgo,
            ),
            'distribucion_intentos': _distribucion_intentos(_ids, estudiantes_ids),
            'evolucion_temporal':    _evolucion_temporal(_ids, estudiantes_ids),
            'errores_sistematicos':  _errores_sistematicos(
                _ids, estudiantes_ids, min_estudiantes=cfg.error_consenso_min,
            ),
            'silencio':              _silencio_cd,
            'silencio_resumen':      _silencio_resumen(
                _silencio_cd, umbral_silencio_dias=cfg.umbral_silencio_dias,
            ),
            'concentracion':         _concentracion_practica(
                _ids, estudiantes_ids, umbral_maraton=cfg.umbral_maraton,
            ),
            'velocidad':             _velocidad_arranque(
                _ids, estudiantes_ids, umbral_arranque_dias=cfg.umbral_arranque_dias,
            ),
        }
        cache.set(_cache_key, analiticas, _ANALITICAS_TTL)
```

- [ ] **Step 5: Arreglar la invalidación de caché**

En `docentes/views.py:2123`, la invalidación usa la clave vieja y ahora no acierta ninguna entrada:

```python
    cache.delete(f'analiticas_{intento.practica_comision.comision_id}_{intento.cohorte_id}')
```

Buscar el resto de invalidaciones:

```bash
grep -rn "analiticas_" --include=*.py .
```

Todas tienen que usar la clave de dos partes.

- [ ] **Step 6: Escribir el test de la caché**

En `docentes/tests.py`:

```python
class CacheAnaliticasPorCohorteTests(TestCase):
    """El caché no debe servir los números de una camada dentro de otra."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        from cursos.models import Cohorte, Comision, Inscripcion
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        Cohorte.objects.filter(pk=self.c1.pk).update(activa=False)
        Cohorte.objects.filter(pk=self.c2.pk).update(activa=True)

        self.docente = _u('doc-cache', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC Noche')
        self.comision.docentes.add(self.docente)
        self.est_c1 = _u('cache-c1')
        Inscripcion.objects.create(estudiante=self.est_c1, comision=self.comision, cohorte=self.c1)
        self.client.login(username='doc-cache', password='clave123')

    def test_cohortes_distintas_no_comparten_entrada(self):
        url = reverse('docentes:comision_detail', args=[self.comision.id])
        activa = self.client.get(url)
        vieja = self.client.get(url, {'cohorte': self.c1.pk})
        self.assertEqual(list(activa.context['silencio']), [])
        self.assertEqual([f['username'] for f in vieja.context['silencio']], ['cache-c1'])
```

- [ ] **Step 7: Correr la suite completa**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test cursos ejercicios docentes analiticas accounts -v 1
```

Esperado: `OK`.

El dashboard de `analiticas` (`analiticas/views.py:731-740`) también llama a estas funciones y hay que actualizarlo. Ese dashboard agrega varias comisiones y **no** es por cohorte: mantener su comportamiento actual pasando todos los estudiantes inscriptos en las comisiones filtradas, sin importar la camada. Antes del `render`:

```python
    _estudiantes_dashboard = list(
        Inscripcion.objects
        .filter(comision_id__in=comision_ids)
        .values_list('estudiante_id', flat=True)
        .distinct()
    )
```

Y pasarlo como segundo argumento en las nueve llamadas de ese bloque:

```python
    _silencio = _silencio_temprano(comision_ids, _estudiantes_dashboard)
    return render(request, 'analiticas/dashboard.html', {
        'comisiones_data':      comisiones_data,
        'ejercicios_dificiles': _ejercicios_mas_dificiles(
            comision_ids, _estudiantes_dashboard, min_intentos=cfg.umbral_min_intentos,
        ),
        'en_riesgo':            _estudiantes_en_riesgo(
            comision_ids, _estudiantes_dashboard, umbral_riesgo=cfg.umbral_riesgo,
        ),
        'distribucion_intentos': _distribucion_intentos(comision_ids, _estudiantes_dashboard),
        ...
```

Se elige preservar el comportamiento y no acotar a la cohorte activa porque el spec no pidió cambiar el dashboard de investigación. Acotarlo cambiaría en silencio los números que ese panel viene reportando.

- [ ] **Step 8: Commit**

```bash
git add analiticas/ docentes/ 
git commit -m "feat(cohorte): analiticas y cache acotados por cohorte"
```

---

### Task 8: Gate de fechas solo para la cohorte activa

**Files:**
- Modify: `ejercicios/views.py:130-147` (`practica_detail`), `ejercicios/views.py:268-285` (`ejercicio_detail`)
- Test: `ejercicios/tests.py`

**Interfaces:**
- Consumes: `cursos.cohortes.cohorte_de`.
- Produces: nada nuevo. Cambia el comportamiento del gate existente.

`fecha_apertura` y `fecha_cierre` viven en `PracticaComision`, compartida entre cohortes. Sin esta condición, ponerle fechas a las prácticas para la cursada nueva dejaría afuera a quien prepara un final de la camada anterior.

- [ ] **Step 1: Escribir los tests**

En `ejercicios/tests.py`:

```python
class GateFechasPorCohorteTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from cursos.models import Cohorte, Comision, Inscripcion
        from ejercicios.models import Ejercicio, EjercicioPractica, Practica, PracticaComision

        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        Cohorte.objects.filter(pk=self.c1.pk).update(activa=False)
        Cohorte.objects.filter(pk=self.c2.pk).update(activa=True)

        self.comision = Comision.objects.create(nombre='IPC Noche')
        self.est_vieja = _u('final-c1')
        self.est_actual = _u('cursa-c2')
        Inscripcion.objects.create(estudiante=self.est_vieja, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est_actual, comision=self.comision, cohorte=self.c2)

        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
            fecha_cierre=timezone.now() - timedelta(days=1),
        )
        self.url = reverse('ejercicios:practica_detail', args=[self.pc.pk])

    def test_camada_vieja_entra_aunque_este_cerrada(self):
        self.client.login(username='final-c1', password='clave123')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'no está disponible')

    def test_cohorte_activa_si_queda_afuera(self):
        self.client.login(username='cursa-c2', password='clave123')
        resp = self.client.get(self.url)
        self.assertContains(resp, 'cerrada')

    def test_camada_vieja_sigue_viendo_el_aula_en_home(self):
        """`home` no filtra por cohorte: quien tiene inscripción ve su comisión."""
        self.client.login(username='final-c1', password='clave123')
        resp = self.client.get(reverse('ejercicios:home'))
        self.assertContains(resp, 'IPC Noche')
```

Ajustar el `reverse` y el texto del assert a los nombres reales de `ejercicios/urls.py` y `templates/ejercicios/practica_no_disponible.html`.

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.GateFechasPorCohorteTests -v 2
```

Esperado: `test_camada_vieja_entra_aunque_este_cerrada` falla — hoy el gate la frena.

- [ ] **Step 3: Condicionar el gate**

En `ejercicios/views.py`, en `practica_detail` (línea ~130), reemplazar:

```python
        # Control de período de disponibilidad (solo para estudiantes)
        estado_disp = pc.estado_disponibilidad()
```

por:

```python
        # Control de período de disponibilidad (solo para estudiantes).
        # Las fechas viven en PracticaComision, compartida entre cohortes, así
        # que solo aplican a la camada en curso. Quien es de una cohorte
        # anterior sigue practicando para rendir el final sin quedar afuera por
        # el calendario de la cursada nueva.
        from cursos.cohortes import cohorte_de
        cohorte_est = cohorte_de(usuario, pc.comision)
        estado_disp = (
            pc.estado_disponibilidad()
            if cohorte_est is not None and cohorte_est.activa
            else 'abierta'
        )
```

`'abierta'` es el literal exacto que devuelve `estado_disponibilidad()` en el caso disponible (`ejercicios/models.py:289`); los otros dos son `'no_iniciada'` y `'cerrada'`. No inventar `'disponible'`: las dos ramas de abajo comparan contra esos literales y un valor distinto las saltearía por accidente, dando el resultado correcto por la razón equivocada.

Aplicar el mismo cambio en `ejercicio_detail` (línea ~268). En esa vista `cohorte_est` ya se calcula para `esta_resuelto` (Task 3, Step 10): reusarlo en vez de recalcular.

- [ ] **Step 4: Correr los tests**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.GateFechasPorCohorteTests -v 2
```

Esperado: `OK` (3 tests).

- [ ] **Step 5: Commit**

```bash
git add ejercicios/views.py ejercicios/tests.py
git commit -m "feat(cohorte): el gate de fechas solo aplica a la cohorte activa"
```

---

### Task 9: Badge de cohorte en corrección

**Files:**
- Modify: `docentes/views.py` (`correccion_pendiente`)
- Modify: `templates/docentes/correccion_pendiente.html`
- Test: `docentes/tests.py`

**Interfaces:**
- Consumes: `Intento.cohorte` de la Task 3.
- Produces: nada nuevo. Es visual.

La corrección ya cruza todas las cohortes (`docentes/views.py:549` filtra solo por docente de la comisión) y así tiene que seguir: hay que poder corregirle a quien rinde final. Solo falta ver de qué camada es cada quien.

- [ ] **Step 1: Escribir el test**

En `docentes/tests.py`:

```python
class BadgeCohorteCorreccionTests(TestCase):
    def test_lista_intentos_de_todas_las_cohortes_con_su_etiqueta(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        from ejercicios.models import Ejercicio, EjercicioPractica, Intento, Practica, PracticaComision

        c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        docente = _u('doc-badge', es_docente=True)
        comision = Comision.objects.create(nombre='IPC Noche')
        comision.docentes.add(docente)

        est = _u('badge-est')
        Inscripcion.objects.create(estudiante=est, comision=comision, cohorte=c1)

        practica = Practica.objects.create(titulo='P1')
        ejercicio = Ejercicio.objects.create(
            enunciado='Formalizar', formula_solucion='p', tipo='formalizacion',
        )
        ep = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio, orden=1)
        pc = PracticaComision.objects.create(practica=practica, comision=comision, orden=1)
        Intento.objects.create(
            estudiante=est, ejercicio_practica=ep, practica_comision=pc,
            cohorte=c1, respuesta_raw='p', es_correcto=True,
        )

        self.client.login(username='doc-badge', password='clave123')
        resp = self.client.get(reverse('docentes:correccion_pendiente'))
        self.assertContains(resp, '2026 – C1')
```

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.BadgeCohorteCorreccionTests -v 2
```

Esperado: `Couldn't find '2026 – C1' in response`

- [ ] **Step 3: Agregar `cohorte` al `select_related`**

En `docentes/views.py`, en `correccion_pendiente`, agregar `'cohorte'` a la lista del `select_related` del queryset de intentos.

- [ ] **Step 4: Mostrar el badge**

En `templates/docentes/correccion_pendiente.html`, en la celda donde se muestra el estudiante de cada fila:

```html
<span style="font-size:0.75rem; background:#eef2f7; color:#445; padding:0.1rem 0.4rem; border-radius:3px; margin-left:0.4rem;">
  {{ intento.cohorte }}
</span>
```

Ajustar el nombre de la variable de loop al que use el template.

- [ ] **Step 5: Correr los tests**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.BadgeCohorteCorreccionTests -v 2
```

Esperado: `OK`.

- [ ] **Step 6: Correr la suite completa**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test -v 1
```

Esperado: `OK`. Este es el gate final: nada rojo antes de dar el trabajo por terminado.

- [ ] **Step 7: Commit**

```bash
git add docentes/views.py templates/docentes/correccion_pendiente.html docentes/tests.py
git commit -m "feat(cohorte): badge de cohorte en el panel de correcciones"
```

---

### Task 10: Unificar la noción de cohorte

**Files:**
- Modify: `analiticas/research.py:781-824` (`_cohorte_de_fecha`, `_registros_encuesta`)
- Modify: `analiticas/anonimizador.py:243-247`, `:274-294`, `:344-355`
- Modify: `analiticas/views.py:1399-1415` (`_cohortes_disponibles`)
- Modify: `cursos/management/commands/exportar_cohorte.py:80-83`
- Modify: `analiticas/tests.py:418-420`
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `Inscripcion.cohorte` de la Task 3.
- Produces: `_cohorte_de_fecha` **eliminada** de `research.py` y de `anonimizador.py`. Las claves de salida `anio` y `cuatri` no cambian, así que los consumidores río abajo no se tocan.

Con el modelo `Cohorte` en la base, dejar las derivaciones por fecha deja dos definiciones de cohorte compitiendo. Hoy hay cuatro copias y ya discrepan entre sí: tres usan `fecha_inscripcion` con corte en mes ≤ 7, y `exportar_cohorte` usa la fecha del **parcial** con corte en mes ≤ 6. Esta tarea las reemplaza a todas por la lectura del campo.

- [ ] **Step 1: Escribir el test de que la cohorte sale del campo, no de la fecha**

En `analiticas/tests.py`:

```python
class CohorteExplicitaTests(TestCase):
    """La cohorte sale de Inscripcion.cohorte, no de fecha_inscripcion."""

    def test_inscripcion_tardia_conserva_su_cohorte(self):
        from datetime import timedelta
        from django.utils import timezone
        from cursos.models import Cohorte, Comision, Inscripcion
        from analiticas.research import cohortes_onboarding

        c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        comision = Comision.objects.create(nombre='IPC Noche')
        est = _u('tardio', consentimiento_investigacion=True)
        _crear_encuesta(est)

        inscripcion = Inscripcion.objects.create(
            estudiante=est, comision=comision, cohorte=c1,
        )
        # Inscripto en noviembre: la regla vieja lo mandaría a C2.
        Inscripcion.objects.filter(pk=inscripcion.pk).update(
            fecha_inscripcion=timezone.now().replace(month=11, day=15)
        )

        filas = cohortes_onboarding([comision.id], solo_consentimiento=True)
        self.assertEqual(filas, [{'anio': 2026, 'cuatri': 1, 'count': 1}])
```

`_crear_encuesta(est)` es un helper que ya existe en `analiticas/tests.py` para crear una `EncuestaEstudiante` mínima; si tiene otro nombre, usar el que esté. `_registros_encuesta` exige `estudiante__encuesta__isnull=False`, así que sin encuesta la fila no aparece y el test pasaría en falso.

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.CohorteExplicitaTests -v 2
```

Esperado: falla con `[{'anio': 2026, 'cuatri': 2, 'count': 1}]` — la derivación por fecha lo manda a C2.

- [ ] **Step 3: Reemplazar la derivación en `research.py`**

Borrar `_cohorte_de_fecha` (líneas 781-786) y en `_registros_encuesta` reemplazar:

```python
        anio, cuatri = _cohorte_de_fecha(inscripcion.fecha_inscripcion)
```

por:

```python
        cohorte = inscripcion.cohorte
        anio, cuatri = cohorte.anio, cohorte.cuatrimestre
```

Agregar `'cohorte'` al `select_related` del queryset (línea 801):

```python
        .select_related('estudiante', 'estudiante__encuesta', 'comision', 'cohorte')
```

Sin eso son N+1 queries: una por inscripción.

Actualizar el docstring del módulo o de la función donde mencione la derivación por fecha.

- [ ] **Step 4: Reemplazar la derivación en `anonimizador.py`**

Borrar `_cohorte_de_fecha` (líneas 243-247). En `dataset_encuesta`, reemplazar:

```python
        anio_insc, cuatri_insc = _cohorte_de_fecha(insc.fecha_inscripcion)
```

por:

```python
        anio_insc, cuatri_insc = insc.cohorte.anio, insc.cohorte.cuatrimestre
```

Y los dos filtros por rango de meses (líneas 279-286 y 344-350) pasan a filtrar por el campo:

```python
    if anio is not None:
        qs_insc = qs_insc.filter(cohorte__anio=anio)
        if cuatri is not None:
            qs_insc = qs_insc.filter(cohorte__cuatrimestre=cuatri)
```

Agregar `'cohorte'` al `select_related` de la línea 276.

- [ ] **Step 5: Reemplazar `_cohortes_disponibles`**

En `analiticas/views.py:1399`, reemplazar la función entera:

```python
def _cohortes_disponibles(comision_ids):
    """Lista de {'anio', 'cuatri', 'label'} con cohortes de esas comisiones."""
    from cursos.models import Cohorte
    return [
        {'anio': c.anio, 'cuatri': c.cuatrimestre, 'label': f'{c.anio} – C{c.cuatrimestre}'}
        for c in Cohorte.objects
            .filter(inscripciones__comision_id__in=comision_ids)
            .distinct()
            .order_by('anio', 'cuatrimestre')
    ]
```

El `order_by` ascendente conserva el orden que tenía el `sorted()` original.

- [ ] **Step 6: Arreglar `exportar_cohorte`**

En `cursos/management/commands/exportar_cohorte.py`, agregar el argumento:

```python
        parser.add_argument('--cohorte-id', type=int, default=None,
                            help='Cohorte a exportar. Por defecto: la del parcial, o la activa.')
```

Y reemplazar el bloque de las líneas 80-83:

```python
        # Cohorte: explícita, la del parcial, o la activa. Nunca derivada de fechas.
        from cursos.cohortes import cohorte_activa
        from cursos.models import Cohorte

        if options['cohorte_id']:
            try:
                cohorte = Cohorte.objects.get(pk=options['cohorte_id'])
            except Cohorte.DoesNotExist:
                raise CommandError(f'Cohorte {options["cohorte_id"]} no existe.')
        elif parcial:
            cohorte = parcial.cohorte
        else:
            cohorte = cohorte_activa()

        if cohorte is None:
            raise CommandError(
                'No hay cohorte activa ni parcial indicado. Pasar --cohorte-id.'
            )

        anio = cohorte.anio
        cuatri = cohorte.cuatrimestre
```

Y filtrar las inscripciones por cohorte (línea 55):

```python
        inscripciones = (
            comision.inscripciones
            .filter(cohorte=cohorte)
            .select_related('estudiante')
            .order_by(
                'estudiante__last_name',
                'estudiante__first_name',
                'estudiante__username',
            )
        )
```

Sin este filtro el CSV mezcla camadas, que es el bug que este comando tenía de origen.

Actualizar el docstring del módulo con el argumento nuevo.

- [ ] **Step 7: Arreglar los tests de `analiticas` que crean inscripciones sin cohorte**

`analiticas/tests.py:418-420` y cualquier otro `Inscripcion.objects.create(...)` sin `cohorte`. Buscar:

```bash
grep -rn "Inscripcion.objects.create" --include=*.py .
```

Cada uno necesita `cohorte=`. En los setUp, agregar arriba:

```python
        from cursos.models import Cohorte
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
```

y pasar `cohorte=self.cohorte`.

- [ ] **Step 8: Verificar que no queda ninguna derivación por fecha**

```bash
grep -rn "_cohorte_de_fecha\|month <= 6\|month <= 7\|month__gte\|month__lte" --include=*.py .
```

Esperado: sin resultados en `analiticas/` ni en `cursos/`. Si aparece alguno, es una quinta copia que no estaba en el inventario y hay que convertirla igual.

- [ ] **Step 9: Correr la suite completa**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test -v 1
```

Esperado: `OK`.

- [ ] **Step 10: Commit**

```bash
git add analiticas/ cursos/
git commit -m "fix(cohorte): unificar la nocion de cohorte leyendo Inscripcion.cohorte"
```

---

### Task 11: `cohorte_ids` en `analiticas/research.py`

**Files:**
- Modify: `analiticas/research.py` (2 cuellos de botella + ~25 funciones públicas)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: Task 10.
- Produces: cada función pública de `research.py` acepta `cohorte_ids: list[int] | None = None` como **keyword-only con default `None`**. `None` = todas las cohortes, que es el comportamiento actual. Ningún llamador existente cambia.

El default `None` es lo que hace esta tarea no-disruptiva: las vistas de `analiticas/` y las herramientas del MCP siguen funcionando sin tocarse hasta que alguien pase el parámetro.

- [ ] **Step 1: Escribir el test**

En `analiticas/tests.py`:

```python
class FiltroCohorteResearchTests(TestCase):
    def setUp(self):
        from cursos.models import Cohorte, Comision, Inscripcion
        self.c1 = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.c2 = Cohorte.objects.create(anio=2026, cuatrimestre=2)
        self.comision = Comision.objects.create(nombre='IPC Noche')

        self.est_c1 = _u('res-c1', consentimiento_investigacion=True)
        self.est_c2 = _u('res-c2', consentimiento_investigacion=True)
        _crear_encuesta(self.est_c1)
        _crear_encuesta(self.est_c2)
        Inscripcion.objects.create(estudiante=self.est_c1, comision=self.comision, cohorte=self.c1)
        Inscripcion.objects.create(estudiante=self.est_c2, comision=self.comision, cohorte=self.c2)

    def test_sin_cohorte_ids_devuelve_todas(self):
        from analiticas.research import perfiles_encuesta_onboarding
        filas = perfiles_encuesta_onboarding([self.comision.id])
        self.assertEqual(len(filas), 2)

    def test_cohorte_ids_acota(self):
        from analiticas.research import perfiles_encuesta_onboarding
        filas = perfiles_encuesta_onboarding([self.comision.id], cohorte_ids=[self.c1.pk])
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['cuatri'], 1)

    def test_cohorte_ids_en_funcion_de_intentos(self):
        from analiticas.research import tasa_entrada_efectiva
        sin_filtro = tasa_entrada_efectiva([self.comision.id])
        con_filtro = tasa_entrada_efectiva([self.comision.id], cohorte_ids=[self.c1.pk])
        self.assertIsInstance(sin_filtro, list)
        self.assertIsInstance(con_filtro, list)
```

- [ ] **Step 2: Correr para verificar que falla**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.FiltroCohorteResearchTests -v 2
```

Esperado: `TypeError: perfiles_encuesta_onboarding() got an unexpected keyword argument 'cohorte_ids'`

- [ ] **Step 3: Agregar el filtro al cuello de botella de encuesta**

En `analiticas/research.py`, `_registros_encuesta`:

```python
def _registros_encuesta(comision_ids=None, solo_consentimiento=True, cohorte_ids=None):
    """Devuelve un registro único por estudiante con encuesta en las comisiones dadas.

    ``cohorte_ids=None`` incluye todas las camadas. Acotar por cohorte permite
    comparar camadas entre sí en vez de mezclarlas en un solo agregado.

    El campo ``'pseudonimo'`` contiene el hex del ``research_id``; es ``None``
    para estudiantes sin consentimiento de investigación.
    El campo privado ``'_eid'`` (PK interna) se usa solo como clave de join
    con ``_metricas_desempeno_por_estudiante`` y nunca se incluye en outputs.
    """
    cids = _resolver_comision_ids(comision_ids)
    qs = (
        Inscripcion.objects
        .filter(comision_id__in=cids, estudiante__encuesta__isnull=False)
        .select_related('estudiante', 'estudiante__encuesta', 'comision', 'cohorte')
        .order_by('estudiante_id', 'fecha_inscripcion', 'id')
    )
    if cohorte_ids is not None:
        qs = qs.filter(cohorte_id__in=cohorte_ids)
    if solo_consentimiento:
        qs = qs.filter(estudiante__consentimiento_investigacion=True)
```

El resto de la función no cambia.

**Ojo con la deduplicación:** `_registros_encuesta` se queda con la **primera** inscripción de cada estudiante. Al filtrar por cohorte, un recursante deduplica dentro de la cohorte pedida, que es lo correcto: pedir C2 devuelve su fila de C2 aunque también tenga una de C1.

- [ ] **Step 4: Agregar un helper para las funciones de intentos**

Las funciones basadas en `Intento` no pasan por `_registros_encuesta`. Agregar junto a `_resolver_comision_ids`:

```python
def _filtrar_por_cohorte(qs, cohorte_ids):
    """Acota un queryset de Intento por cohorte. ``None`` = todas."""
    if cohorte_ids is None:
        return qs
    return qs.filter(cohorte_id__in=cohorte_ids)
```

- [ ] **Step 5: Propagar el parámetro a las funciones públicas**

Cada una de estas gana `cohorte_ids=None` en la firma, una línea en el docstring bajo `Args:`, y el filtro aplicado:

Familia encuesta (pasan `cohorte_ids` a `_registros_encuesta`):
`perfiles_encuesta_onboarding`, `distribucion_nse_onboarding`, `distribucion_puntaje_logicas`, `distribucion_pandemia_onboarding`, `cohortes_onboarding`, `cohortes_nse_onboarding`, `cohortes_pandemia_onboarding`, `distribucion_facultad_onboarding`, `distribucion_carrera_onboarding`, `desempeno_por_nse_onboarding`, `desempeno_por_pandemia_onboarding`, `desempeno_por_puntaje_logicas`, `distribuciones_encuesta_detalle`, `nube_ciencia`, `correlaciones_encuesta`, `_metricas_desempeno_por_estudiante`.

Familia intentos (aplican `_filtrar_por_cohorte` a su queryset de `Intento`):
`tasa_entrada_efectiva`, `demora_primer_intento`, `persistencia_relativa`, `intentos_hasta_correcto_sin_sesgo`, `desacople_docente_maquina`, `desacople_por_tipo`, `tasa_abandono_local`, `indice_pared`, `errores_compartidos_semanticos`, `red_errores`, `trabajo_vs_nota_logica`.

Línea de docstring, idéntica en todas:

```
        cohorte_ids: cohortes a incluir; None = todas.
```

`desagregar_por_comision` (línea 73) reenvía `**kwargs`, así que hereda el parámetro sin cambios.

- [ ] **Step 6: Correr los tests**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas -v 2
```

Esperado: `OK`. Cualquier `TypeError` es una función a la que le falta el parámetro.

- [ ] **Step 7: Verificar que no quedó ninguna afuera**

```bash
grep -n "^def [a-z]" analiticas/research.py | grep -v "^.*def _"
```

Cada función pública de la lista del Step 5 debe tener `cohorte_ids` en su firma.

- [ ] **Step 8: Commit**

```bash
git add analiticas/research.py analiticas/tests.py
git commit -m "feat(cohorte): filtro cohorte_ids opcional en analiticas/research"
```

---

### Task 12: Exponer cohortes en el MCP

**Files:**
- Modify: `mcp_intentos.py` (~25 herramientas + una nueva)
- Test: manual, vía el cliente MCP

**Interfaces:**
- Consumes: Task 11.
- Produces: herramienta `listar_cohortes()`; parámetro `cohorte_ids: list[int] | None = None` en las herramientas que envuelven `analiticas/research.py`.

Los wrappers `_compat` **no se tocan**: `_compat_kwargs` (`mcp_intentos.py:1476`) reenvía `**kwargs` tal cual, así que heredan el parámetro nuevo automáticamente.

- [ ] **Step 1: Agregar `listar_cohortes`**

En `mcp_intentos.py`, junto a `listar_comisiones` (línea ~181):

```python
@db_tool()
def listar_cohortes() -> list[dict]:
    """Lista las cohortes (camadas) con su ID, año, cuatrimestre y si está en curso.

    Usar los IDs devueltos en el parámetro ``cohorte_ids`` de las demás
    herramientas para comparar camadas entre sí en vez de mezclarlas.

    Una cohorte es la camada de pertenencia de un estudiante, no un rango de
    fechas: quien cursó en 2026-C1 y siguió practicando en septiembre para
    rendir el final sigue perteneciendo a 2026-C1.
    """
    from cursos.models import Cohorte
    return [
        {
            "id": c.pk,
            "anio": c.anio,
            "cuatrimestre": c.cuatrimestre,
            "label": f"{c.anio} – C{c.cuatrimestre}",
            "activa": c.activa,
        }
        for c in Cohorte.objects.order_by("-anio", "-cuatrimestre")
    ]
```

- [ ] **Step 2: Agregar el parámetro a las herramientas de la familia encuesta**

Para cada una de estas herramientas en `mcp_intentos.py`, agregar el parámetro, la línea de docstring y el pass-through:

`perfiles_encuesta_onboarding`, `distribucion_nse_onboarding`, `distribucion_puntaje_logicas_onboarding`, `distribucion_pandemia_onboarding`, `distribucion_facultad_onboarding`, `distribucion_carrera_onboarding`, `cohortes_onboarding`, `cohortes_nse_onboarding`, `cohortes_pandemia_onboarding`, `desempeno_por_nse_onboarding`, `desempeno_por_pandemia_onboarding`, `desempeno_por_puntaje_logicas`, `distribuciones_encuesta_detalle`, `nube_ciencia`, `correlaciones_encuesta`.

El patrón, tomando `distribucion_nse_onboarding` como ejemplo (líneas 1232-1247):

```python
@db_tool()
def distribucion_nse_onboarding(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
    cohorte_ids: list[int] | None = None,
) -> list[dict]:
    """Distribución de estudiantes por categoría de nivel socioeconómico (NSE).

    Args:
        comision_ids: comisiones; None = todas.
        solo_consentimiento: filtrar por consentimiento_investigacion=True.
        cohorte_ids: cohortes; None = todas. Ver ``listar_cohortes``.

    Returns:
        Lista de dicts con ``categoria_nse``, ``n``, ``porcentaje``.
    """
    from analiticas.research import distribucion_nse_onboarding as _f
    return _f(
        comision_ids=comision_ids,
        solo_consentimiento=solo_consentimiento,
        cohorte_ids=cohorte_ids,
    )
```

`cohorte_ids` va **último** en la firma para no romper llamadas posicionales existentes.

- [ ] **Step 3: Agregar el parámetro a las herramientas de la familia intentos**

Mismo patrón para: `tasa_entrada_efectiva`, `demora_primer_intento`, `persistencia_relativa`, `intentos_hasta_correcto_sin_sesgo`, `desacople_docente_maquina`, `desacople_por_tipo`, `tasa_abandono_local`, `indice_pared`, `errores_compartidos_semanticos`, `red_errores`, `trabajo_vs_nota_logica`.

- [ ] **Step 4: Verificar que los `_compat` no necesitan cambios**

Leer un par de wrappers (`mcp_intentos.py:1682` en adelante) y confirmar que la forma es:

```python
@mcp.tool()
async def X_compat(args: dict | None = None, kwargs: dict | None = None) -> list[dict]:
    return await X(**_compat_kwargs(args=args, kwargs=kwargs))
```

Si es así, no tocar ninguno: reenvían `cohorte_ids` solo. Si alguno enumera parámetros a mano, ese sí hay que actualizarlo.

- [ ] **Step 5: Verificar que el módulo carga**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' -c "import mcp_intentos; print('herramientas OK')"
```

Esperado: `herramientas OK`, sin `SyntaxError` ni `ImportError`.

- [ ] **Step 6: Prueba de humo de la firma**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' -c "
import inspect, mcp_intentos
faltan = []
for nombre in ['distribucion_nse_onboarding', 'cohortes_onboarding', 'tasa_entrada_efectiva', 'red_errores']:
    fn = getattr(mcp_intentos, nombre)
    origen = inspect.unwrap(fn)
    if 'cohorte_ids' not in inspect.signature(origen).parameters:
        faltan.append(nombre)
print('faltan:', faltan or 'ninguna')
"
```

Esperado: `faltan: ninguna`.

- [ ] **Step 7: Correr la suite completa**

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test -v 1
```

Esperado: `OK`.

- [ ] **Step 8: Commit**

```bash
git add mcp_intentos.py
git commit -m "feat(cohorte): listar_cohortes y filtro cohorte_ids en las herramientas MCP"
```

---

## Hallazgos durante la escritura del plan

Cuatro cosas que el spec no cubría y que están incorporadas:

1. **`eps_resueltos` y `esta_resuelto` necesitaban cohorte** (Task 3). El spec decía "lo mismo en el avance de `Progreso`", pero estas dos funciones son las que deciden si un ejercicio cuenta como resuelto. Sin tocarlas, quien recursa arrancaría con `Progreso` en cero pero la práctica se marcaría completa de inmediato, porque sus intentos de C1 seguían contando.

2. **`Inscripcion.unique_together` bloqueaba a los recursantes** (Task 3, Step 6). Era `['estudiante', 'comision']`, así que nadie podía inscribirse dos veces en la misma comisión. Pasa a `['estudiante', 'comision', 'cohorte']`.

3. **Cuatro derivaciones de cohorte por fecha, ya discrepantes entre sí** (Task 10). Tres usan `fecha_inscripcion` con corte en mes ≤ 7 (`research.py:781`, `anonimizador.py:243`, `views.py:1411`) y `exportar_cohorte.py:83` usa la fecha del **parcial** con corte en mes ≤ 6. Dejarlas junto al modelo nuevo daría dos definiciones de cohorte compitiendo en el mismo sistema. Además `exportar_cohorte` no filtraba las inscripciones por cohorte, así que su CSV mezclaba camadas.

4. **El MCP no estaba en el spec** (Tasks 11 y 12). Envuelve ~26 funciones de `analiticas/research.py`, incluidas las tres `cohortes_*_onboarding` que dependían de la derivación por fecha. Los wrappers `_compat` no necesitan cambios: `_compat_kwargs` (`mcp_intentos.py:1476`) reenvía `**kwargs` tal cual y heredan el parámetro nuevo solo.

## Punto abierto heredado del spec

Con la creación de parciales bloqueada en cohortes cerradas, no hay dónde asentar la nota de un final rendido por alguien de una camada anterior. Editar notas de parciales existentes sí funciona. No bloquea este plan.

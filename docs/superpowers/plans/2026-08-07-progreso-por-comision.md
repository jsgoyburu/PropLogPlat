# Progreso por comisión — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cambiar la clave de `Progreso` de `(estudiante, practica)` a `(estudiante, practica_comision)`, para que dos comisiones que comparten una `Practica` canónica dejen de leer y escribir la misma fila.

**Architecture:** El campo nuevo se agrega primero como nullable y conviven los dos (`practica` y `practica_comision`) mientras se migra consumidor por consumidor. `practica` se elimina recién en la última tarea. Eso mantiene la suite verde en cada commit en vez de romper todo de una. La atribución del backfill vive en `ejercicios/backfill.py` como funciones puras que reciben las clases de modelo por parámetro, para que la migración las llame con `apps.get_model(...)` y los tests con los modelos reales.

**Tech Stack:** Django 5, DRF, PostgreSQL en producción, SQLite en local. Alpine.js en el frontend. Sin dependencias nuevas.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-07-progreso-por-comision-design.md`.
- Rama base: `claude/desbloqueo-configurable` (PR #187). Este PR queda apilado y **no es mergeable hasta que #187 entre**.
- Correr tests: `$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test`
- Un solo test: agregar `ejercicios.tests.NombreClase.test_nombre` al final del comando.
- `makemigrations`: `& 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations ejercicios`
- El venv está en el directorio **padre** del repo (`C:\Users\Angeles\Documents\IPC-Logica\`), no adentro.
- Test roto de antes en master: `docentes.tests.ComisionesListViewTests.test_admin_ve_todas_las_comisiones`. Si falla, no lo rompiste vos.
- La suite completa tarda ~18 minutos. Durante las tareas correr solo los módulos afectados; la suite completa va en la Task 9.
- Correctitud efectiva siempre vía `ejercicios.correctitud.Q_CORRECTO`, nunca `es_correcto=True` a secas.
- El invariante `practica_comision.practica == ejercicio_practica.practica` vale para `Intento` y ahora también para `Progreso`.

---

### Task 1: Reglas de atribución del backfill

Funciones puras, sin tocar el esquema. Es la lógica que decide a qué `PracticaComision` pertenece cada `Intento` y cada `Progreso`. Se testea sola porque es el paso peligroso del PR: una atribución mal hecha le saca a un estudiante un ejercicio que ya resolvió.

**Files:**
- Create: `ejercicios/backfill.py`
- Test: `ejercicios/tests.py` (agregar al final)

**Interfaces:**
- Consumes: nada (primera tarea).
- Produces:
  - `construir_indices(PracticaComision, Inscripcion) -> tuple[dict[int, list[tuple[int, int]]], dict[int, set[int]]]`
  - `pc_para_intento(pcs_por_practica, comisiones_por_estudiante, practica_id, estudiante_id) -> int | None`
  - `pcs_candidatos(pcs_por_practica, comisiones_por_estudiante, practica_id, estudiante_id) -> list[int]`
  - `puntero_reconstruido(EjercicioPractica, Intento, estudiante_id, pc_id, practica_id) -> int | None`

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `ejercicios/tests.py`:

```python
class BackfillIndicesTests(TestCase):
    """construir_indices() arma los dos mapas que usan las reglas."""

    def setUp(self):
        self.docente = _u('doc-bf-idx', es_docente=True)
        self.estudiante = _u('est-bf-idx')
        self.comision = Comision.objects.create(nombre='C-bf-idx')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision)
        self.practica = Practica.objects.create(titulo='P-bf-idx', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )

    def test_indices_mapean_practica_a_pcs_y_estudiante_a_comisiones(self):
        from ejercicios.backfill import construir_indices
        pcs_por_practica, comisiones_por_estudiante = construir_indices(
            PracticaComision, Inscripcion,
        )

        self.assertEqual(
            pcs_por_practica[self.practica.id],
            [(self.pc.id, self.comision.id)],
        )
        self.assertEqual(
            comisiones_por_estudiante[self.estudiante.id],
            {self.comision.id},
        )


class BackfillAtribucionIntentoTests(TestCase):
    """pc_para_intento(): reglas 1 (inscripción única) y 2 (práctica única)."""

    def setUp(self):
        self.docente = _u('doc-bf-int', es_docente=True)
        self.estudiante = _u('est-bf-int')
        self.comision_a = Comision.objects.create(nombre='C-bf-A')
        self.comision_b = Comision.objects.create(nombre='C-bf-B')
        self.practica = Practica.objects.create(titulo='P-bf-int', creada_por=self.docente)

    def _indices(self):
        from ejercicios.backfill import construir_indices
        return construir_indices(PracticaComision, Inscripcion)

    def test_regla_1_inscripcion_unica(self):
        from ejercicios.backfill import pc_para_intento
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a)
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        # La práctica también está en B, pero el estudiante no está en B.
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertEqual(resultado, pc_a.id)

    def test_regla_2_desinscripto_con_practica_en_una_sola_comision(self):
        from ejercicios.backfill import pc_para_intento
        # El estudiante no está inscripto en ninguna comisión.
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertEqual(resultado, pc_a.id)

    def test_ambiguo_devuelve_none(self):
        from ejercicios.backfill import pc_para_intento
        # Inscripto en las dos comisiones que comparten la práctica.
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b)
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertIsNone(resultado)

    def test_desinscripto_y_practica_en_dos_comisiones_devuelve_none(self):
        from ejercicios.backfill import pc_para_intento
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        resultado = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            self.practica.id, self.estudiante.id,
        )

        self.assertIsNone(resultado)


class BackfillCandidatosProgresoTests(TestCase):
    """pcs_candidatos(): solo inscripción, sin el fallback de la regla 2."""

    def setUp(self):
        self.docente = _u('doc-bf-cand', es_docente=True)
        self.estudiante = _u('est-bf-cand')
        self.comision_a = Comision.objects.create(nombre='C-cand-A')
        self.comision_b = Comision.objects.create(nombre='C-cand-B')
        self.practica = Practica.objects.create(titulo='P-cand', creada_por=self.docente)

    def _indices(self):
        from ejercicios.backfill import construir_indices
        return construir_indices(PracticaComision, Inscripcion)

    def test_n1_devuelve_un_candidato(self):
        from ejercicios.backfill import pcs_candidatos
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a)
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        self.assertEqual(
            pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                           self.practica.id, self.estudiante.id),
            [pc_a.id],
        )

    def test_n0_sin_inscripcion_devuelve_vacio(self):
        from ejercicios.backfill import pcs_candidatos
        PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        self.assertEqual(
            pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                           self.practica.id, self.estudiante.id),
            [],
        )

    def test_n2_devuelve_los_dos(self):
        from ejercicios.backfill import pcs_candidatos
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b)
        pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        pcs_por_practica, comisiones_por_estudiante = self._indices()

        self.assertEqual(
            sorted(pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                                  self.practica.id, self.estudiante.id)),
            sorted([pc_a.id, pc_b.id]),
        )


class BackfillPunteroTests(TestCase):
    """puntero_reconstruido(): primer EP por orden sin resolver en ese pc."""

    def setUp(self):
        self.docente = _u('doc-bf-pt', es_docente=True)
        self.estudiante = _u('est-bf-pt')
        self.comision = Comision.objects.create(nombre='C-pt')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision)
        self.practica = Practica.objects.create(titulo='P-pt', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )
        self.eps = []
        for i in (1, 2, 3):
            ej = Ejercicio.objects.create(
                enunciado=f'E{i}', formula_solucion='p',
                tipo='formalizacion', creado_por=self.docente,
            )
            self.eps.append(EjercicioPractica.objects.create(
                practica=self.practica, ejercicio=ej, orden=i,
            ))

    def test_sin_intentos_apunta_al_primero(self):
        from ejercicios.backfill import puntero_reconstruido
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[0].id)

    def test_resuelto_el_primero_apunta_al_segundo(self):
        from ejercicios.backfill import puntero_reconstruido
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc, respuesta_raw='p',
            es_correcto=True, aprobado_docente=None,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[1].id)

    def test_incorrecto_aprobado_por_docente_cuenta_como_resuelto(self):
        from ejercicios.backfill import puntero_reconstruido
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc, respuesta_raw='zzz',
            es_correcto=False, aprobado_docente=True,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[1].id)

    def test_correcto_rechazado_por_docente_no_cuenta(self):
        from ejercicios.backfill import puntero_reconstruido
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc, respuesta_raw='p',
            es_correcto=True, aprobado_docente=False,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[0].id)

    def test_todos_resueltos_devuelve_none(self):
        from ejercicios.backfill import puntero_reconstruido
        for ep in self.eps:
            Intento.objects.create(
                estudiante=self.estudiante, ejercicio_practica=ep,
                practica_comision=self.pc, respuesta_raw='p',
                es_correcto=True, aprobado_docente=None,
            )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertIsNone(resultado)

    def test_intento_de_otro_pc_no_cuenta(self):
        from ejercicios.backfill import puntero_reconstruido
        otra_comision = Comision.objects.create(nombre='C-pt-otra')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=otra_comision)
        pc_otro = PracticaComision.objects.create(
            practica=self.practica, comision=otra_comision, orden=1,
        )
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=pc_otro, respuesta_raw='p',
            es_correcto=True, aprobado_docente=None,
        )
        resultado = puntero_reconstruido(
            EjercicioPractica, Intento,
            self.estudiante.id, self.pc.id, self.practica.id,
        )
        self.assertEqual(resultado, self.eps[0].id)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.BackfillIndicesTests ejercicios.tests.BackfillAtribucionIntentoTests ejercicios.tests.BackfillCandidatosProgresoTests ejercicios.tests.BackfillPunteroTests
```
Expected: FAIL — `ModuleNotFoundError: No module named 'ejercicios.backfill'`

- [ ] **Step 3: Escribir la implementación**

Crear `ejercicios/backfill.py`:

```python
"""Reglas de atribución del backfill de Progreso a PracticaComision.

Funciones puras que reciben las clases de modelo por parámetro, para que la
migración de datos las invoque con ``apps.get_model(...)`` (modelos históricos)
y los tests con los modelos reales, sin duplicar la regla en dos lados.

La atribución de ``Intento`` es el paso peligroso del cambio: si un intento
queda asignado a la comisión equivocada, ``eps_resueltos`` deja de contarlo y
el estudiante pierde un ejercicio que ya había resuelto. Por eso las reglas
exigen unicidad y devuelven ``None`` en vez de adivinar.
"""

from ejercicios.correctitud import Q_CORRECTO


def construir_indices(PracticaComision, Inscripcion):
    """Arma los dos mapas que necesitan las reglas, en dos queries.

    Args:
        PracticaComision: la clase del modelo (real o histórica).
        Inscripcion: la clase del modelo (real o histórica).

    Returns:
        tuple: ``(pcs_por_practica, comisiones_por_estudiante)`` donde
        ``pcs_por_practica`` mapea ``practica_id -> [(pc_id, comision_id), ...]``
        y ``comisiones_por_estudiante`` mapea ``estudiante_id -> {comision_id}``.
    """
    pcs_por_practica = {}
    for row in PracticaComision.objects.values('id', 'practica_id', 'comision_id'):
        pcs_por_practica.setdefault(row['practica_id'], []).append(
            (row['id'], row['comision_id'])
        )

    comisiones_por_estudiante = {}
    for row in Inscripcion.objects.values('estudiante_id', 'comision_id'):
        comisiones_por_estudiante.setdefault(row['estudiante_id'], set()).add(
            row['comision_id']
        )

    return pcs_por_practica, comisiones_por_estudiante


def pcs_candidatos(pcs_por_practica, comisiones_por_estudiante,
                   practica_id, estudiante_id):
    """PCs de ``practica_id`` en comisiones donde el estudiante está inscripto.

    Returns:
        list[int]: ids de PracticaComision, posiblemente vacía.
    """
    comisiones = comisiones_por_estudiante.get(estudiante_id, set())
    return [
        pc_id
        for pc_id, comision_id in pcs_por_practica.get(practica_id, [])
        if comision_id in comisiones
    ]


def pc_para_intento(pcs_por_practica, comisiones_por_estudiante,
                    practica_id, estudiante_id):
    """PracticaComision al que corresponde un intento, o ``None`` si es ambiguo.

    Reglas, en orden:

    1. PCs de la práctica donde el estudiante está inscripto: si hay
       exactamente uno, ése.
    2. Si no hay ninguno (estudiante desinscripto): PCs de la práctica en
       total, si hay exactamente uno.
    3. Si sigue ambiguo, ``None``.
    """
    candidatos = pcs_candidatos(
        pcs_por_practica, comisiones_por_estudiante, practica_id, estudiante_id,
    )
    if len(candidatos) == 1:
        return candidatos[0]

    if not candidatos:
        todos = pcs_por_practica.get(practica_id, [])
        if len(todos) == 1:
            return todos[0][0]

    return None


def puntero_reconstruido(EjercicioPractica, Intento,
                         estudiante_id, pc_id, practica_id):
    """Primer EjercicioPractica por ``orden`` sin resolver en ese PracticaComision.

    Usa la correctitud efectiva (:data:`ejercicios.correctitud.Q_CORRECTO`): el
    juicio docente tiene precedencia sobre el motor. Es el mismo recálculo que
    hace ``avanzar_progreso`` en modo libre.

    Returns:
        int | None: id del EjercicioPractica, o ``None`` si están todos
        resueltos (práctica completa).
    """
    resueltos = set(
        Intento.objects
        .filter(Q_CORRECTO, estudiante_id=estudiante_id, practica_comision_id=pc_id)
        .values_list('ejercicio_practica_id', flat=True)
        .distinct()
    )
    siguiente = (
        EjercicioPractica.objects
        .filter(practica_id=practica_id)
        .exclude(pk__in=resueltos)
        .order_by('orden')
        .values_list('pk', flat=True)
        .first()
    )
    return siguiente
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.BackfillIndicesTests ejercicios.tests.BackfillAtribucionIntentoTests ejercicios.tests.BackfillCandidatosProgresoTests ejercicios.tests.BackfillPunteroTests
```
Expected: PASS — 14 tests OK

- [ ] **Step 5: Commit**

```bash
git add ejercicios/backfill.py ejercicios/tests.py
git commit -m "feat(ejercicios): reglas de atribucion para el backfill de Progreso"
```

---

### Task 2: Campo nuevo y migración de datos

Agrega `Progreso.practica_comision` como nullable y lo backfillea, junto con los `Intento` que tengan la FK en NULL. `Progreso.practica` sigue existiendo: se elimina en la Task 9. La suite queda verde porque nada lo consume todavía.

**Files:**
- Modify: `ejercicios/models.py` (clase `Progreso`)
- Create: `ejercicios/migrations/0023_progreso_practica_comision.py` (generada)
- Create: `ejercicios/migrations/0024_backfill_progreso_por_comision.py` (a mano)

**Interfaces:**
- Consumes: `ejercicios.backfill.construir_indices`, `pc_para_intento`, `pcs_candidatos`, `puntero_reconstruido` (Task 1).
- Produces: campo `Progreso.practica_comision` (FK a `PracticaComision`, `null=True`, `related_name='progresos'`).

- [ ] **Step 1: Agregar el campo al modelo y soltar el unique_together viejo**

En `ejercicios/models.py`, dentro de la clase `Progreso`, agregar justo después del campo `practica`:

```python
    practica_comision = models.ForeignKey(
        PracticaComision,
        on_delete=models.CASCADE,
        related_name='progresos',
        verbose_name='práctica en comisión',
        null=True,   # nullable durante la migración de datos; ver 0025
        blank=True,
    )
```

Y en el `Meta` de `Progreso`, **eliminar** la línea `unique_together = ['estudiante', 'practica']`, dejando:

```python
    class Meta:
        verbose_name = 'progreso'
        verbose_name_plural = 'progresos'
```

Esto es necesario, no cosmético: la rama n≥2 del backfill (Step 3) crea filas
adicionales con el mismo `(estudiante, practica)` y el mismo puntero por
comisión distinta. Con la constraint vieja todavía activa, ese `create` explota
con `IntegrityError`. La clave nueva entra en la `0025`; entre la `0023` y la
`0025` no hay unicidad sobre `Progreso`, que es la ventana de migración.

- [ ] **Step 2: Generar la migración de esquema**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations ejercicios --name progreso_practica_comision
```
Expected: crea `ejercicios/migrations/0023_progreso_practica_comision.py` con dos operaciones: `AlterUniqueTogether` (a `set()`) y `AddField` sobre `progreso`.

Verificar que ambas estén y que no toque otros modelos. `AlterUniqueTogether` tiene que ir antes del `AddField` o al menos antes de que corra la `0024`; el autodetector lo pone primero.

- [ ] **Step 3: Escribir la migración de datos a mano**

Crear `ejercicios/migrations/0024_backfill_progreso_por_comision.py`:

```python
"""Backfill de la atribución por comisión.

Primero atribuye los Intento con practica_comision en NULL, porque el backfill
de Progreso reconstruye punteros a partir de esos intentos y necesita que estén
ya atribuidos. Las reglas viven en ejercicios/backfill.py.
"""

from django.db import migrations

from ejercicios.backfill import (
    construir_indices,
    pc_para_intento,
    pcs_candidatos,
    puntero_reconstruido,
)


def _backfill_intentos(apps, schema_editor):
    Intento = apps.get_model('ejercicios', 'Intento')
    PracticaComision = apps.get_model('ejercicios', 'PracticaComision')
    Inscripcion = apps.get_model('cursos', 'Inscripcion')

    pcs_por_practica, comisiones_por_estudiante = construir_indices(
        PracticaComision, Inscripcion,
    )

    atribuidos = 0
    sin_atribuir = 0
    for intento in Intento.objects.filter(practica_comision__isnull=True).select_related(
        'ejercicio_practica'
    ):
        pc_id = pc_para_intento(
            pcs_por_practica, comisiones_por_estudiante,
            intento.ejercicio_practica.practica_id, intento.estudiante_id,
        )
        if pc_id is None:
            sin_atribuir += 1
            continue
        intento.practica_comision_id = pc_id
        intento.save(update_fields=['practica_comision'])
        atribuidos += 1

    print(f'  Intento: {atribuidos} atribuidos, {sin_atribuir} sin atribuir')


def _backfill_progresos(apps, schema_editor):
    Progreso = apps.get_model('ejercicios', 'Progreso')
    EjercicioPractica = apps.get_model('ejercicios', 'EjercicioPractica')
    Intento = apps.get_model('ejercicios', 'Intento')
    PracticaComision = apps.get_model('ejercicios', 'PracticaComision')
    Inscripcion = apps.get_model('cursos', 'Inscripcion')

    pcs_por_practica, comisiones_por_estudiante = construir_indices(
        PracticaComision, Inscripcion,
    )

    n1 = n0 = n2 = 0
    for progreso in Progreso.objects.all():
        candidatos = pcs_candidatos(
            pcs_por_practica, comisiones_por_estudiante,
            progreso.practica_id, progreso.estudiante_id,
        )

        if len(candidatos) == 1:
            # Caso normal: se asigna el pc y el puntero se conserva verbatim.
            progreso.practica_comision_id = candidatos[0]
            progreso.save(update_fields=['practica_comision'])
            n1 += 1
        elif not candidatos:
            # Fila inalcanzable: práctica desasignada o estudiante desinscripto.
            progreso.delete()
            n0 += 1
        else:
            # Ambiguo: se abre en una fila por pc, con el puntero reconstruido
            # desde los intentos ya atribuidos a cada uno.
            for i, pc_id in enumerate(candidatos):
                ep_id = puntero_reconstruido(
                    EjercicioPractica, Intento,
                    progreso.estudiante_id, pc_id, progreso.practica_id,
                )
                if i == 0:
                    progreso.practica_comision_id = pc_id
                    progreso.ejercicio_practica_actual_id = ep_id
                    progreso.save(update_fields=[
                        'practica_comision', 'ejercicio_practica_actual',
                    ])
                else:
                    Progreso.objects.create(
                        estudiante_id=progreso.estudiante_id,
                        practica_id=progreso.practica_id,
                        practica_comision_id=pc_id,
                        ejercicio_practica_actual_id=ep_id,
                    )
            n2 += 1

    print(f'  Progreso: {n1} inequivocos, {n0} huerfanos borrados, {n2} ambiguos abiertos')


class Migration(migrations.Migration):

    dependencies = [
        ('ejercicios', '0023_progreso_practica_comision'),
        ('cursos', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(_backfill_intentos, migrations.RunPython.noop),
        migrations.RunPython(_backfill_progresos, migrations.RunPython.noop),
    ]
```

Nota sobre la reversa: es `noop` a propósito. Volver atrás requeriría colapsar N filas en una y no hay criterio para elegir el puntero ganador; el rollback real es restaurar backup.

- [ ] **Step 4: Verificar que las migraciones aplican**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py migrate ejercicios
```
Expected: aplica `0023` y `0024` sin error. La base local está vacía, así que los contadores impresos van a ser todos 0.

- [ ] **Step 5: Correr la suite de ejercicios**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios
```
Expected: PASS. Nada consume el campo nuevo todavía.

- [ ] **Step 6: Commit**

```bash
git add ejercicios/models.py ejercicios/migrations/0023_progreso_practica_comision.py ejercicios/migrations/0024_backfill_progreso_por_comision.py
git commit -m "feat(ejercicios): campo practica_comision en Progreso con backfill"
```

---

### Task 3: `ejercicios/progreso.py` keyeado por comisión

El módulo de avance pasa a operar sobre `(estudiante, practica_comision)`. `avanzar_progreso` pierde el kwarg `secuencial` porque lo deduce del `pc`.

**Files:**
- Modify: `ejercicios/progreso.py` (archivo completo)
- Modify: `ejercicios/api/views.py:298` (llamada)
- Modify: `docentes/views.py:2062-2071` (`_avanzar_progreso_por_aprobacion_docente`)
- Modify: `ejercicios/views.py:276` (única llamada a `esta_resuelto` fuera de tests)
- Test: `ejercicios/tests.py` (`ProgresoModuloTests`, línea ~772)
- Test: `docentes/tests.py:435,1106` (fixtures de `Progreso` sin `practica_comision`)

**Interfaces:**
- Consumes: campo `Progreso.practica_comision` (Task 2).
- Produces:
  - `eps_resueltos(estudiante, pc) -> set[int]`
  - `esta_resuelto(estudiante, ep, pc) -> bool`
  - `avanzar_progreso(estudiante, ep, pc) -> tuple[bool, int]`

- [ ] **Step 1: Actualizar los tests existentes y agregar el de aislamiento**

En `ejercicios/tests.py`, clase `ProgresoModuloTests` (línea ~772), reemplazar las tres llamadas a `Progreso.objects.create(... practica=self.practica ...)` por `practica=self.practica, practica_comision=self.pc`, las tres a `Progreso.objects.get(estudiante=..., practica=self.practica)` por `practica_comision=self.pc`, y las llamadas `avanzar_progreso(self.estudiante, ep, secuencial=X)` por `avanzar_progreso(self.estudiante, ep, self.pc)`.

Para que `self.pc` tenga el modo correcto, agregar este helper a la clase:

```python
    def _modo(self, secuencial):
        """Fija el modo de desbloqueo del pc de la práctica."""
        self.pc.desbloqueo_secuencial = secuencial
        self.pc.save(update_fields=['desbloqueo_secuencial'])
```

y llamarlo al principio de cada test (`self._modo(True)` donde antes iba `secuencial=True`, `self._modo(False)` donde iba `secuencial=False`).

Agregar además, al final de `ejercicios/tests.py`, la clase de caracterización del comportamiento nuevo:

```python
class ProgresoCruzadoEntreComisionesTests(TestCase):
    """Dos comisiones que comparten una Practica canónica no comparten Progreso."""

    def setUp(self):
        self.docente = _u('doc-cruz', es_docente=True)
        self.estudiante = _u('est-cruz')
        self.comision_sec = Comision.objects.create(nombre='C-cruz-sec')
        self.comision_libre = Comision.objects.create(nombre='C-cruz-libre')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_sec)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_libre)

        # La MISMA practica canónica en las dos (lo que hace practica_importar).
        self.practica = Practica.objects.create(titulo='P-cruz', creada_por=self.docente)
        self.pc_sec = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_sec, orden=1,
            desbloqueo_secuencial=True,
        )
        self.pc_libre = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_libre, orden=1,
            desbloqueo_secuencial=False,
        )
        self.eps = []
        for i in (1, 2, 3):
            ej = Ejercicio.objects.create(
                enunciado=f'E{i}', formula_solucion='p',
                tipo='formalizacion', creado_por=self.docente,
            )
            self.eps.append(EjercicioPractica.objects.create(
                practica=self.practica, ejercicio=ej, orden=i,
            ))

    def test_hay_una_fila_de_progreso_por_comision(self):
        from ejercicios.progreso import avanzar_progreso
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_sec, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.estudiante, self.eps[0], self.pc_sec)

        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_libre, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.estudiante, self.eps[0], self.pc_libre)

        self.assertEqual(
            Progreso.objects.filter(estudiante=self.estudiante).count(), 2,
        )

    def test_intento_en_la_libre_no_mueve_el_puntero_de_la_secuencial(self):
        from ejercicios.progreso import avanzar_progreso
        # La secuencial arranca en el ejercicio 1.
        Progreso.objects.create(
            estudiante=self.estudiante, practica=self.practica,
            practica_comision=self.pc_sec, ejercicio_practica_actual=self.eps[0],
        )
        # El estudiante resuelve el TERCERO en la comisión libre.
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[2],
            practica_comision=self.pc_libre, respuesta_raw='p', es_correcto=True,
        )
        avanzar_progreso(self.estudiante, self.eps[2], self.pc_libre)

        progreso_sec = Progreso.objects.get(
            estudiante=self.estudiante, practica_comision=self.pc_sec,
        )
        self.assertEqual(
            progreso_sec.ejercicio_practica_actual, self.eps[0],
            'la comisión secuencial no debería moverse por un intento de la libre',
        )

    def test_eps_resueltos_no_cuenta_lo_resuelto_en_la_otra_comision(self):
        from ejercicios.progreso import eps_resueltos
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_sec, respuesta_raw='p', es_correcto=True,
        )

        self.assertEqual(eps_resueltos(self.estudiante, self.pc_sec), {self.eps[0].id})
        self.assertEqual(eps_resueltos(self.estudiante, self.pc_libre), set())

    def test_esta_resuelto_es_por_comision(self):
        from ejercicios.progreso import esta_resuelto
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.eps[0],
            practica_comision=self.pc_sec, respuesta_raw='p', es_correcto=True,
        )

        self.assertTrue(esta_resuelto(self.estudiante, self.eps[0], self.pc_sec))
        self.assertFalse(esta_resuelto(self.estudiante, self.eps[0], self.pc_libre))
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.ProgresoCruzadoEntreComisionesTests ejercicios.tests.ProgresoModuloTests
```
Expected: FAIL — `TypeError: avanzar_progreso() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Reescribir `ejercicios/progreso.py`**

Reemplazar el archivo completo por:

```python
"""Avance del :class:`~ejercicios.models.Progreso` de un estudiante en una práctica.

Centraliza la lógica que antes estaba duplicada en ``ejercicios/api/views.py``
(intento correcto del estudiante) y en ``docentes/views.py`` (aprobación manual
de un intento incorrecto).

El progreso es **por cursado, no por práctica canónica**: la clave es
``(estudiante, practica_comision)``. Una misma :class:`Practica` asignada a dos
comisiones tiene una fila de progreso en cada una, con su propio modo de
desbloqueo y su propio puntero.

Hay dos modos, definidos por ``PracticaComision.desbloqueo_secuencial``:

- **secuencial**: el progreso avanza al siguiente ejercicio por ``orden`` sólo
  cuando el estudiante resuelve el que tiene desbloqueado.
- **libre**: todos los ejercicios están disponibles, así que el "actual" se
  recalcula como el primero sin resolver. Sin este recálculo, un estudiante que
  resuelve fuera de orden dejaría el progreso clavado en el primer ejercicio y
  la práctica nunca se marcaría completa.
"""

from django.db import transaction

from ejercicios.correctitud import Q_CORRECTO
from ejercicios.models import EjercicioPractica, Intento, Progreso


def eps_resueltos(estudiante, pc) -> set[int]:
    """Ids de los EjercicioPractica ya resueltos por ``estudiante`` en ``pc``.

    Acota por ``practica_comision``: lo resuelto en otra comisión que comparta
    la misma práctica canónica no cuenta acá.

    Usa la correctitud efectiva de :mod:`ejercicios.correctitud`: el juicio
    docente tiene precedencia sobre el resultado del motor.
    """
    return set(
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, practica_comision=pc)
        .values_list('ejercicio_practica_id', flat=True)
        .distinct()
    )


def esta_resuelto(estudiante, ep, pc) -> bool:
    """True si ``estudiante`` ya resolvió ``ep`` en ``pc`` (correctitud efectiva)."""
    return (
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, ejercicio_practica=ep,
                practica_comision=pc)
        .exists()
    )


def avanzar_progreso(estudiante, ep, pc) -> tuple[bool, int]:
    """Actualiza el Progreso de ``estudiante`` en ``pc`` tras resolverse ``ep``.

    Args:
        estudiante: el usuario estudiante.
        ep: el :class:`~ejercicios.models.EjercicioPractica` recién resuelto.
        pc: el :class:`~ejercicios.models.PracticaComision` desde el que se
            resolvió. Define el modo de desbloqueo y la fila de progreso.

    Returns:
        tuple[bool, int]: ``(practica_completa, ejercicios_pendientes)``.

    Raises:
        ValueError: si ``pc`` no corresponde a la práctica de ``ep``.
    """
    if pc.practica_id != ep.practica_id:
        raise ValueError(
            f'PracticaComision {pc.pk} (práctica {pc.practica_id}) no corresponde '
            f'al EjercicioPractica {ep.pk} (práctica {ep.practica_id}).'
        )

    secuencial = pc.desbloqueo_secuencial
    practica_id = pc.practica_id
    total = EjercicioPractica.objects.filter(practica_id=practica_id).count()

    with transaction.atomic():
        # Lock pesimista: evita la race condition entre dos requests simultáneos
        # sobre el mismo (estudiante, practica_comision).
        progreso = (
            Progreso.objects
            .select_for_update()
            .filter(estudiante=estudiante, practica_comision=pc)
            .first()
        )
        if progreso is None:
            progreso, _ = Progreso.objects.get_or_create(
                estudiante=estudiante,
                practica_comision=pc,
                # practica se elimina en la migración 0025; hasta entonces es
                # NOT NULL y hay que seguir poblándola.
                defaults={'ejercicio_practica_actual': ep, 'practica_id': practica_id},
            )
            progreso = (
                Progreso.objects
                .select_for_update()
                .get(estudiante=estudiante, practica_comision=pc)
            )

        if secuencial:
            if progreso.ejercicio_practica_actual == ep:
                siguiente = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id, orden__gt=ep.orden)
                    .order_by('orden')
                    .first()
                )
                progreso.ejercicio_practica_actual = siguiente
                progreso.save(update_fields=['ejercicio_practica_actual'])
            actual = progreso.ejercicio_practica_actual
            # En secuencial, todo lo anterior al actual está resuelto.
            pendientes = 0 if actual is None else total - actual.orden + 1
        else:
            resueltos = eps_resueltos(estudiante, pc)
            siguiente = (
                EjercicioPractica.objects
                .filter(practica_id=practica_id)
                .exclude(pk__in=resueltos)
                .order_by('orden')
                .first()
            )
            progreso.ejercicio_practica_actual = siguiente
            progreso.save(update_fields=['ejercicio_practica_actual'])
            pendientes = total - len(resueltos)

    return progreso.ejercicio_practica_actual is None, max(pendientes, 0)
```

- [ ] **Step 4: Actualizar los dos llamadores**

En `ejercicios/api/views.py`, línea ~298, reemplazar:

```python
                practica_completa, ejercicios_pendientes = avanzar_progreso(
                    request.user, ep, secuencial=pc.desbloqueo_secuencial,
                )
```

por:

```python
                practica_completa, ejercicios_pendientes = avanzar_progreso(
                    request.user, ep, pc,
                )
```

En `docentes/views.py`, reemplazar la función completa `_avanzar_progreso_por_aprobacion_docente` (línea ~2062) por:

```python
def _avanzar_progreso_por_aprobacion_docente(intento):
    """Avanza el progreso cuando el docente aprueba a mano un intento incorrecto.

    Delega en :func:`ejercicios.progreso.avanzar_progreso`. La comisión y el modo
    de desbloqueo salen de la PracticaComision del intento.
    """
    avanzar_progreso(
        intento.estudiante, intento.ejercicio_practica, intento.practica_comision,
    )
```

En `ejercicios/views.py`, línea ~276, pasar el `pc` que la vista ya tiene en scope:

```python
        ya_resuelto = esta_resuelto(usuario, ep, pc)
```

Es la única llamada a `esta_resuelto` fuera de los tests. El resto de esa vista
(los lookups de `Progreso`, el subquery de último intento, `home()`) se toca en
la Task 5; acá sólo se ajusta la firma para no dejar la suite roja.

En `docentes/tests.py`, agregar `practica_comision=self.pc,` a los dos
`Progreso.objects.create(...)` de las líneas ~435 y ~1106. Sin eso,
`avanzar_progreso` no encuentra la fila del fixture (busca por
`practica_comision`) y crea una segunda, así que el `refresh_from_db()` del test
lee la fila vieja sin avanzar. Las dos siguen necesitando `practica=` hasta la
Task 9.

- [ ] **Step 5: Correr los tests**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios docentes
```
Expected: PASS (salvo `docentes.tests.ComisionesListViewTests.test_admin_ve_todas_las_comisiones`, roto de antes).

- [ ] **Step 6: Commit**

```bash
git add ejercicios/progreso.py ejercicios/api/views.py docentes/views.py ejercicios/tests.py
git commit -m "refactor(ejercicios): avanzar_progreso opera sobre practica_comision"
```

---

### Task 4: Contrato de la API

`POST /api/intentos/` deja de adivinar la comisión con `.first()` y pasa a recibir `practica_comision_id`.

**Files:**
- Modify: `ejercicios/api/serializers.py` (`IntentoInputSerializer`)
- Modify: `ejercicios/api/views.py:107-116` (resolución del `pc`)
- Modify: `templates/ejercicios/ejercicio.html:37,986,1279,1288,1297`
- Test: `ejercicios/tests.py:203,378,596,619` (call sites) + tests nuevos

**Interfaces:**
- Consumes: `avanzar_progreso(estudiante, ep, pc)` (Task 3).
- Produces: contrato de la API con `practica_comision_id: int` requerido.

- [ ] **Step 1: Escribir los tests de validación**

Agregar al final de `ejercicios/tests.py`:

```python
class APIPracticaComisionRequeridaTests(TestCase):
    """POST /api/intentos/ exige practica_comision_id y lo valida."""

    def setUp(self):
        self.docente = _u('doc-api-pc', es_docente=True)
        self.estudiante = _u('est-api-pc')
        self.comision = Comision.objects.create(nombre='C-api-pc')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision)
        self.practica = Practica.objects.create(titulo='P-api-pc', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
        )
        ej = Ejercicio.objects.create(
            enunciado='E', formula_solucion='p',
            tipo='formalizacion', creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=ej, orden=1,
        )
        self.client.login(username='est-api-pc', password='clave123')

    def test_sin_practica_comision_id_devuelve_400(self):
        resp = self.client.post(
            '/api/intentos/',
            data={'ejercicio_practica_id': self.ep.id, 'respuesta_raw': 'p'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('practica_comision_id', resp.json())

    def test_pc_de_otra_practica_devuelve_400(self):
        otra_practica = Practica.objects.create(titulo='Otra', creada_por=self.docente)
        pc_otra = PracticaComision.objects.create(
            practica=otra_practica, comision=self.comision, orden=2,
        )
        resp = self.client.post(
            '/api/intentos/',
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': pc_otra.id,
                'respuesta_raw': 'p',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_pc_de_comision_ajena_devuelve_403(self):
        otra_comision = Comision.objects.create(nombre='C-ajena')
        pc_ajeno = PracticaComision.objects.create(
            practica=self.practica, comision=otra_comision, orden=1,
        )
        resp = self.client.post(
            '/api/intentos/',
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': pc_ajeno.id,
                'respuesta_raw': 'p',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_pc_valido_guarda_el_intento_con_esa_comision(self):
        resp = self.client.post(
            '/api/intentos/',
            data={
                'ejercicio_practica_id': self.ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': 'p',
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        intento = Intento.objects.get(pk=resp.json()['intento_id'])
        self.assertEqual(intento.practica_comision, self.pc)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.APIPracticaComisionRequeridaTests
```
Expected: FAIL — `test_sin_practica_comision_id_devuelve_400` da 200 en vez de 400 (hoy la API adivina).

- [ ] **Step 3: Agregar el campo al serializer**

En `ejercicios/api/serializers.py`, dentro de `IntentoInputSerializer`, agregar justo después de `ejercicio_practica_id`:

```python
    practica_comision_id = serializers.IntegerField(
        help_text='ID del PracticaComision desde el que se está resolviendo. '
                  'Determina la comisión del intento y su fila de progreso.',
    )
```

Y en el docstring de la clase, agregar bajo `Attributes:` después de la entrada de `ejercicio_practica_id`:

```
        practica_comision_id (int): ID del :class:`~ejercicios.models.PracticaComision`
            desde el que el estudiante está resolviendo. Determina la comisión
            del intento, el modo de desbloqueo y la fila de ``Progreso``.
```

- [ ] **Step 4: Reemplazar la resolución del `pc` en la view**

En `ejercicios/api/views.py`, reemplazar el bloque de resolución (líneas ~106-116):

```python
        # --- Verificar que el estudiante esté inscripto en alguna comisión con esta práctica ---
        pc = (
            PracticaComision.objects
            .filter(practica=ep.practica, comision__estudiantes=request.user)
            .select_related('comision')
            .first()
        )
        if pc is None:
            return Response(
                {'detail': 'No estás inscripto en esta comisión.'},
                status=status.HTTP_403_FORBIDDEN,
            )
```

por:

```python
        # --- Resolver la PracticaComision explícita del request ---
        # No se deduce: un estudiante puede cursar dos comisiones que comparten
        # la misma práctica canónica, y el pc define contra qué fila de Progreso
        # se escribe.
        pc = get_object_or_404(
            PracticaComision.objects.select_related('comision', 'practica'),
            pk=serializer.validated_data['practica_comision_id'],
        )
        if pc.practica_id != ep.practica_id:
            return Response(
                {'detail': 'La práctica del ejercicio no coincide con la comisión indicada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not pc.comision.estudiantes.filter(pk=request.user.pk).exists():
            return Response(
                {'detail': 'No estás inscripto en esta comisión.'},
                status=status.HTTP_403_FORBIDDEN,
            )
```

- [ ] **Step 5: Actualizar el template**

En `templates/ejercicios/ejercicio.html`:

1. Línea ~38, agregar `{{ pc.id }}` como segundo argumento de `ejercicioApp`:

```html
       x-data="ejercicioApp(
         {{ ep.id }},
         {{ pc.id }},
         '{% url 'ejercicios:practica' pc.id %}',
```

2. Línea ~986, agregar `pcId` como segundo parámetro:

```javascript
  Alpine.data('ejercicioApp', (epId, pcId, practicaUrl, initialFormula, initialDiccionario, tipo, initialEnunciados, initialJuicio, initialValoresVerdad, initialValorVerdad) => {
```

3. Líneas ~1279, ~1288 y ~1297: agregar `practica_comision_id: pcId,` inmediatamente después de cada `ejercicio_practica_id: epId,`. Son **tres** ocurrencias (tabla_verdad, determinacion_verdad, y el caso general).

- [ ] **Step 6: Actualizar los 4 call sites de tests existentes**

En `ejercicios/tests.py`, agregar `'practica_comision_id'` al dict de cada POST:

- Línea ~203, en `DesbloqueoProgresivoTests._intento` (la clase ya tiene `self.pc` en su `setUp`, línea ~180):

```python
            data={
                'ejercicio_practica_id': ep.id,
                'practica_comision_id': self.pc.id,
                'respuesta_raw': respuesta,
                'diccionario': diccionario,
            },
```

- Línea ~378: `data={'ejercicio_practica_id': self.ep.id, 'respuesta_raw': respuesta}` → `data={'ejercicio_practica_id': self.ep.id, 'practica_comision_id': self.pc.id, 'respuesta_raw': respuesta}`
- Líneas ~596 y ~619: idem, agregando `'practica_comision_id': self.pc.id,` al dict.

Si al correr los tests alguna de esas clases da `AttributeError` sobre `self.pc`,
crearlo en su `setUp` con
`self.pc = PracticaComision.objects.create(practica=self.practica, comision=self.comision, orden=1)`.

- [ ] **Step 7: Correr los tests**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add ejercicios/api/serializers.py ejercicios/api/views.py templates/ejercicios/ejercicio.html ejercicios/tests.py
git commit -m "feat(api): POST /api/intentos/ recibe practica_comision_id explicito"
```

---

### Task 5: Read path del estudiante

Las tres vistas de `ejercicios/views.py` buscan `Progreso` por `practica_comision` y acotan el estado visible por comisión.

**Files:**
- Modify: `ejercicios/views.py:56-58` (`home`), `:145-172` (`practica_detail`), `:263-290` (`ejercicio_detail`)
- Test: `ejercicios/tests.py`

**Interfaces:**
- Consumes: `esta_resuelto(estudiante, ep, pc)` (Task 3), campo `Progreso.practica_comision` (Task 2).
- Produces: nada que consuman tareas posteriores.

- [ ] **Step 1: Escribir los tests de aislamiento visual**

Agregar al final de `ejercicios/tests.py`:

```python
class ReadPathAisladoPorComisionTests(TestCase):
    """El estado que ve el estudiante no cruza entre comisiones."""

    def setUp(self):
        self.docente = _u('doc-rp', es_docente=True)
        self.estudiante = _u('est-rp')
        self.comision_a = Comision.objects.create(nombre='C-rp-A')
        self.comision_b = Comision.objects.create(nombre='C-rp-B')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b)

        self.practica = Practica.objects.create(titulo='P-rp', creada_por=self.docente)
        self.pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
            desbloqueo_secuencial=False,
        )
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
            desbloqueo_secuencial=False,
        )
        ej = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p',
            tipo='formalizacion', creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=self.practica, ejercicio=ej, orden=1,
        )
        # Resuelto SOLO en la comisión A.
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc_a, respuesta_raw='p',
            es_correcto=True, aprobado_docente=True,
        )
        self.client.login(username='est-rp', password='clave123')

    def test_practica_detail_en_B_no_muestra_el_ejercicio_como_aprobado(self):
        resp = self.client.get(reverse('ejercicios:practica', args=[self.pc_b.id]))
        estados = [d['estado'] for d in resp.context['eps_data']]
        self.assertEqual(estados, ['actual'])

    def test_practica_detail_en_A_si_lo_muestra_aprobado(self):
        resp = self.client.get(reverse('ejercicios:practica', args=[self.pc_a.id]))
        estados = [d['estado'] for d in resp.context['eps_data']]
        self.assertEqual(estados, ['aprobado'])

    def test_ejercicio_detail_en_B_deja_enviar(self):
        resp = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc_b.id, self.ep.id])
        )
        self.assertTrue(resp.context['puede_enviar'])

    def test_ejercicio_detail_en_A_no_deja_reenviar(self):
        resp = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc_a.id, self.ep.id])
        )
        self.assertFalse(resp.context['puede_enviar'])

    def test_home_marca_completa_solo_la_comision_donde_se_completo(self):
        from ejercicios.progreso import avanzar_progreso
        avanzar_progreso(self.estudiante, self.ep, self.pc_a)

        resp = self.client.get(reverse('ejercicios:home'))
        estados = {}
        for cd in resp.context['comisiones_data']:
            for pd in cd['practicas']:
                estados[pd['pc'].id] = pd['estado']

        self.assertEqual(estados[self.pc_a.id], 'completa')
        self.assertIsNone(estados[self.pc_b.id])
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.ReadPathAisladoPorComisionTests
```
Expected: FAIL — `test_practica_detail_en_B_no_muestra_el_ejercicio_como_aprobado` da `['aprobado']`.

- [ ] **Step 3: Actualizar `home()`**

En `ejercicios/views.py`, reemplazar el loop de `comisiones_data` (líneas ~49-60) por:

```python
    # Un solo queryset de progresos indexado por pc, en vez de un get() por práctica.
    progresos_por_pc = {
        p.practica_comision_id: p
        for p in Progreso.objects.filter(
            estudiante=usuario,
            practica_comision__comision__in=comisiones,
        )
    }

    comisiones_data = []
    for comision in comisiones:
        practicas_data = []
        for pc in comision.practicas_comisiones.all():
            progreso = progresos_por_pc.get(pc.id)
            if progreso is None:
                estado = None
            else:
                estado = 'completa' if progreso.ejercicio_practica_actual is None else 'en_curso'
            practicas_data.append({'pc': pc, 'practica': pc.practica, 'estado': estado})
        comisiones_data.append({'comision': comision, 'practicas': practicas_data})
```

- [ ] **Step 4: Actualizar `practica_detail()`**

En `ejercicios/views.py`, dentro de `practica_detail`, en el subquery del último intento (línea ~146), agregar el filtro por comisión:

```python
        ultimo_intento_qs = (
            Intento.objects
            .filter(estudiante=usuario, ejercicio_practica=OuterRef('pk'),
                    practica_comision=pc)
            .order_by('-timestamp')
            .values('es_correcto', 'aprobado_docente')[:1]
        )
```

Y reemplazar el bloque de lookup del Progreso (líneas ~165-172) por:

```python
        # EP actual según Progreso
        progreso_existe = False
        ep_actual_id = eps[0].pk if eps else None  # default: sin progreso
        try:
            progreso = Progreso.objects.get(estudiante=usuario, practica_comision=pc)
            progreso_existe = True
            ep_actual_id = progreso.ejercicio_practica_actual_id  # None = completa
        except Progreso.DoesNotExist:
            pass
```

Además, en el docstring de `practica_detail`, agregar al párrafo que explica el estado:

```
    El estado se calcula sobre los intentos de **esta** comisión: lo resuelto en
    otra comisión que comparta la misma práctica canónica no se refleja acá.
```

- [ ] **Step 5: Actualizar `ejercicio_detail()`**

En `ejercicios/views.py`, dentro de `ejercicio_detail`, reemplazar el bloque de gating (líneas ~262-290) por:

```python
        # Correctitud efectiva: el juicio docente tiene precedencia sobre el motor.
        ya_resuelto = esta_resuelto(usuario, ep, pc)

        if not pc.desbloqueo_secuencial:
            # Modo libre: todos los ejercicios están abiertos, no hay gating por orden.
            puede_enviar = not ya_resuelto
        else:
            try:
                progreso = Progreso.objects.get(estudiante=usuario, practica_comision=pc)
                if progreso.ejercicio_practica_actual is None:
                    puede_enviar = not ya_resuelto
                elif ep.orden > progreso.ejercicio_practica_actual.orden:
                    return redirect('ejercicios:practica', pc_id=pc_id)
                else:
                    puede_enviar = not ya_resuelto
            except Progreso.DoesNotExist:
                first_ep = practica.ejercicio_practicas.order_by('orden').first()
                if first_ep and ep.pk == first_ep.pk:
                    puede_enviar = True
                else:
                    return redirect('ejercicios:practica', pc_id=pc_id)
```

Y el historial de intentos (línea ~295) se acota a la comisión:

```python
        intentos = list(
            Intento.objects.filter(estudiante=usuario, ejercicio_practica=ep,
                                   practica_comision=pc)
            .order_by('-timestamp')
        )
```

- [ ] **Step 6: Correr los tests**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add ejercicios/views.py ejercicios/tests.py
git commit -m "fix(ejercicios): el estado que ve el estudiante no cruza entre comisiones"
```

---

### Task 6: Panel docente

Los prefetch pasan por `PracticaComision` en vez de por `Practica`, y dejan de traerse los progresos de las otras comisiones.

**Files:**
- Modify: `docentes/views.py:481` (prefetch de `comisiones_list`)
- Modify: `docentes/views.py:655-660` (prefetch de `comision_detail`)
- Modify: `docentes/views.py:343-446` (`_build_progreso_estudiantes`)
- Test: `docentes/tests.py`

**Interfaces:**
- Consumes: campo `Progreso.practica_comision` (Task 2).
- Produces: nada que consuman tareas posteriores.

- [ ] **Step 1: Escribir el test**

Agregar al final de `docentes/tests.py`:

```python
class ProgresoDocenteAisladoPorComisionTests(TestCase):
    """El panel docente lee el Progreso de su comisión, no el de la otra."""

    def setUp(self):
        self.docente = _u('doc-panel-aisl', es_docente=True)
        self.estudiante = _u('est-panel-aisl')
        self.comision_a = Comision.objects.create(nombre='C-panel-A')
        self.comision_b = Comision.objects.create(nombre='C-panel-B')
        self.comision_a.docentes.add(self.docente)
        self.comision_b.docentes.add(self.docente)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b)

        self.practica = Practica.objects.create(titulo='P-panel', creada_por=self.docente)
        self.pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        self.eps = []
        for i in (1, 2):
            ej = Ejercicio.objects.create(
                enunciado=f'E{i}', formula_solucion='p',
                tipo='formalizacion', creado_por=self.docente,
            )
            self.eps.append(EjercicioPractica.objects.create(
                practica=self.practica, ejercicio=ej, orden=i,
            ))
        # En A el estudiante ya va por el ejercicio 2; en B no arrancó.
        Progreso.objects.create(
            estudiante=self.estudiante, practica=self.practica,
            practica_comision=self.pc_a, ejercicio_practica_actual=self.eps[1],
        )

    def test_comision_b_no_hereda_el_ejercicio_actual_de_a(self):
        from docentes.views import _build_progreso_estudiantes
        comision_b = Comision.objects.get(pk=self.comision_b.pk)

        filas = _build_progreso_estudiantes(comision_b, set(), set())

        detalle = filas[0]['practicas_detalle'][0]
        self.assertEqual(
            detalle['ejercicio_actual'], self.eps[0],
            'B debería arrancar en el ejercicio 1, no heredar el puntero de A',
        )
```

Verificar que `docentes/tests.py` importe `Progreso` y `Practica` desde `ejercicios.models`; si no, agregarlos al import existente.

- [ ] **Step 2: Correr el test para verificar que falla**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ProgresoDocenteAisladoPorComisionTests
```
Expected: FAIL — devuelve `self.eps[1]` (hereda el puntero de A).

- [ ] **Step 3: Actualizar los dos prefetch**

En `docentes/views.py`, línea ~481, reemplazar:

```python
            'practicas_comisiones__practica__progresos__ejercicio_practica_actual',
```

por:

```python
            'practicas_comisiones__progresos__ejercicio_practica_actual',
```

Y en `comision_detail`, líneas ~655-660, reemplazar el `Prefetch` anidado:

```python
                    Prefetch(
                        'practica__progresos',
                        queryset=Progreso.objects.select_related('ejercicio_practica_actual'),
                    ),
```

por:

```python
                    Prefetch(
                        'progresos',
                        queryset=Progreso.objects.select_related('ejercicio_practica_actual'),
                    ),
```

- [ ] **Step 4: Actualizar `_build_progreso_estudiantes`**

En `docentes/views.py`, reemplazar el bloque de índices (líneas ~367-384) por:

```python
    pcs = list(comision.practicas_comisiones.select_related('practica').all())
    practicas = [pc.practica for pc in pcs]
    practicas_por_id = {practica.id: practica for practica in practicas}

    # Índice de progresos por PracticaComision: el progreso es por cursado, así
    # que dos comisiones que comparten una práctica canónica tienen filas
    # distintas y no se pisan.
    progresos_index = {
        pc.id: {progreso.estudiante_id: progreso for progreso in pc.progresos.all()}
        for pc in pcs
    }
```

Reemplazar el `for practica in practicas:` (línea ~392) por `for pc in pcs:` y, como primera línea del loop:

```python
            practica = pc.practica
```

Reemplazar `progreso = progresos_index[practica.id].get(estudiante.id)` por:

```python
            progreso = progresos_index[pc.id].get(estudiante.id)
```

Reemplazar las dos ocurrencias de `'desbloqueo_secuencial': modo_por_practica.get(practica.id, True),` por:

```python
                    'desbloqueo_secuencial': pc.desbloqueo_secuencial,
```

y eliminar el dict `modo_por_practica` completo (líneas ~380-384), que queda sin uso.

Actualizar el docstring de `_build_progreso_estudiantes`, reemplazando la línea de `Args:` que dice `comisión con inscripciones, prácticas y progresos prefetchados` por:

```
        comision: Comisión con inscripciones, practicas_comisiones y sus
            progresos prefetchados.
```

- [ ] **Step 5: Correr los tests**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes
```
Expected: PASS (salvo `ComisionesListViewTests.test_admin_ve_todas_las_comisiones`, roto de antes).

- [ ] **Step 6: Commit**

```bash
git add docentes/views.py docentes/tests.py
git commit -m "fix(docentes): el panel lee el Progreso de su comision"
```

---

### Task 7: Analíticas y MCP

Tres consultas que hoy joinean `practica__practicas_comisiones__comision` pasan a `practica_comision__comision`. De paso dejan de contar dos veces al estudiante inscripto en varias comisiones.

**Files:**
- Modify: `analiticas/views.py:676,694-707`
- Modify: `analiticas/research.py:1019-1021`
- Modify: `mcp_intentos.py:616-625`
- Test: `analiticas/tests.py` (clase nueva + `practica_comision=self.pc` en los
  fixtures de las líneas ~496, ~497 y ~559)

**Interfaces:**
- Consumes: campo `Progreso.practica_comision` (Task 2).
- Produces: nada que consuman tareas posteriores.

- [ ] **Step 1: Escribir el test del doble conteo**

Agregar al final de `analiticas/tests.py`:

```python
class CompletaronNoSeDuplicaEntreComisionesTests(TestCase):
    """Una práctica completada cuenta en su comisión, no en las dos."""

    def setUp(self):
        self.docente = _u('doc-an-dup', es_docente=True)
        self.estudiante = _u('est-an-dup')
        self.comision_a = Comision.objects.create(nombre='C-an-A')
        self.comision_b = Comision.objects.create(nombre='C-an-B')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_a)
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision_b)

        self.practica = Practica.objects.create(titulo='P-an-dup', creada_por=self.docente)
        self.pc_a = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_a, orden=1,
        )
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision_b, orden=1,
        )
        # Completó SOLO en A.
        Progreso.objects.create(
            estudiante=self.estudiante, practica=self.practica,
            practica_comision=self.pc_a, ejercicio_practica_actual=None,
        )

    def test_mcp_estadisticas_comision_no_cuenta_la_completada_de_otra_comision(self):
        from mcp_intentos import estadisticas_comision

        stats_a = estadisticas_comision(self.comision_a.id)
        stats_b = estadisticas_comision(self.comision_b.id)

        self.assertEqual(stats_a['completaron_alguna_practica'], 1)
        self.assertEqual(stats_b['completaron_alguna_practica'], 0)
```

La clave es `completaron_alguna_practica` (ver el dict de retorno de
`estadisticas_comision`, `mcp_intentos.py:~640`), no `completaron`.

Verificar que `analiticas/tests.py` importe `_u`, `Comision`, `Inscripcion`,
`Practica`, `PracticaComision` y `Progreso`; si falta alguno, agregarlo.

- [ ] **Step 2: Correr el test para verificar que falla**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.CompletaronNoSeDuplicaEntreComisionesTests
```
Expected: FAIL — `stats_b['completaron']` da 1 en vez de 0.

- [ ] **Step 3: Actualizar `mcp_intentos.py`**

En `mcp_intentos.py`, reemplazar el bloque `completaron` (líneas ~616-625) por:

```python
    completaron = (
        Progreso.objects
        .filter(
            practica_comision__comision_id=comision_id,
            ejercicio_practica_actual__isnull=True,
        )
        .values("estudiante_id")
        .distinct()
        .count()
    )
```

El `.distinct()` se mantiene: deduplica entre prácticas (un estudiante que completa tres prácticas tiene tres filas), no entre comisiones.

- [ ] **Step 4: Actualizar `analiticas/views.py`**

Reemplazar el bloque de `completaron_map` (líneas ~694-707) por:

```python
    completaron_map = {
        row['practica_comision_id']: row['n']
        for row in (
            Progreso.objects
            .filter(
                practica_comision_id__in=all_pc_ids,
                ejercicio_practica_actual__isnull=True,
            )
            .values('practica_comision_id').annotate(n=Count('pk'))
        )
    }
```

Y eliminar la línea ~676, que queda sin uso:

```python
    pc_by_practica_comision = {(pc['practica_id'], pc['comision_id']): pc['id'] for pc in all_pcs}
```

- [ ] **Step 5: Actualizar `analiticas/research.py`**

Reemplazar el filtro (líneas ~1019-1021) por:

```python
    qs_progreso = Progreso.objects.filter(
        practica_comision__comision_id__in=cids,
        ejercicio_practica_actual__isnull=True,
        estudiante__research_id__isnull=False,
    )
```

- [ ] **Step 6: Correr los tests**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add analiticas/views.py analiticas/research.py mcp_intentos.py analiticas/tests.py
git commit -m "fix(analiticas): completaron se cuenta por comision y no se duplica"
```

---

### Task 8: Management commands

Los cuatro comandos agrupan por `(estudiante_id, practica_comision_id)`. La FK ya está en `Intento`, así que la clave sale directo de ahí.

**Files:**
- Modify: `ejercicios/management/commands/reconciliar_progreso_aprobaciones.py`
- Modify: `ejercicios/management/commands/reevaluar_tablas_verdad.py`
- Modify: `ejercicios/management/commands/corregir_ejercicio_juicio.py`
- Modify: `ejercicios/management/commands/reconciliar_V_mayuscula.py`

**Interfaces:**
- Consumes: campo `Progreso.practica_comision` (Task 2).
- Produces: nada que consuman tareas posteriores.

- [ ] **Step 1: `reconciliar_progreso_aprobaciones.py`**

En `handle()`, reemplazar el queryset de pares y el loop (líneas ~41-55) por:

```python
        # Estudiantes con al menos un intento incorrecto aprobado
        pares = (
            Intento.objects
            .filter(es_correcto=False, aprobado_docente=True)
            .values('estudiante_id', 'practica_comision_id',
                    'ejercicio_practica__practica_id')
            .distinct()
        )

        for par in pares:
            estudiante_id = par['estudiante_id']
            pc_id = par['practica_comision_id']
            practica_id = par['ejercicio_practica__practica_id']

            avanzado = self._reconciliar(estudiante_id, pc_id, practica_id, dry_run)
```

Reemplazar la firma y el cuerpo de `_reconciliar` (línea ~66) por:

```python
    def _reconciliar(self, estudiante_id, pc_id, practica_id, dry_run):
        """Avanza el Progreso de un (estudiante, practica_comision) hasta el
        primer ejercicio sin intento aprobado. Devuelve True si hubo cambios."""
        with transaction.atomic():
            progreso = (
                Progreso.objects
                .select_for_update()
                .filter(estudiante_id=estudiante_id, practica_comision_id=pc_id)
                .first()
            )

            if progreso is None:
                primer_ep = (
                    EjercicioPractica.objects
                    .filter(practica_id=practica_id)
                    .order_by('orden')
                    .first()
                )
                if primer_ep is None:
                    return False
                progreso, _ = Progreso.objects.get_or_create(
                    estudiante_id=estudiante_id,
                    practica_comision_id=pc_id,
                    defaults={
                        'ejercicio_practica_actual': primer_ep,
                        'practica_id': practica_id,
                    },
                )
                progreso = (
                    Progreso.objects
                    .select_for_update()
                    .get(estudiante_id=estudiante_id, practica_comision_id=pc_id)
                )
```

En el resto de `_reconciliar`, acotar el `Intento.objects.filter(...)` interno agregando `practica_comision_id=pc_id`:

```python
                tiene_aprobado = Intento.objects.filter(
                    estudiante_id=estudiante_id,
                    ejercicio_practica=ep_actual,
                    practica_comision_id=pc_id,
                    aprobado_docente=True,
                ).exists()
```

y cambiar el mensaje de salida `f'  Estudiante {estudiante_id} | Práctica {practica_id}: '` por `f'  Estudiante {estudiante_id} | PC {pc_id}: '`.

- [ ] **Step 2: `reevaluar_tablas_verdad.py`**

Línea ~87, reemplazar:

```python
                pares_a_reconciliar.add((intento.estudiante_id, intento.ejercicio_practica.practica_id))
```

por:

```python
                pares_a_reconciliar.add((
                    intento.estudiante_id,
                    intento.practica_comision_id,
                    intento.ejercicio_practica.practica_id,
                ))
```

Línea ~116:

```python
        for estudiante_id, pc_id, practica_id in pares_a_reconciliar:
            if self._reconciliar_progreso(estudiante_id, pc_id, practica_id, dry_run):
```

Y en `_reconciliar_progreso` (línea ~169) cambiar la firma a
`def _reconciliar_progreso(self, estudiante_id, pc_id, practica_id, dry_run):`,
agregar `practica_comision_id=pc_id` al filtro de `Intento`:

```python
                resuelto = (
                    Intento.objects
                    .filter(estudiante_id=estudiante_id, ejercicio_practica=ep,
                            practica_comision_id=pc_id)
                    .filter(Q(es_correcto=True) | Q(aprobado_docente=True))
                    .exists()
                )
```

cambiar el filtro de `Progreso` a `practica_comision_id=pc_id`, y el `create` a:

```python
                    Progreso.objects.create(
                        estudiante_id=estudiante_id,
                        practica_comision_id=pc_id,
                        practica_id=practica_id,
                        ejercicio_practica_actual=ejercicio_actual,
                    )
```

- [ ] **Step 3: `corregir_ejercicio_juicio.py`**

Línea ~115, reemplazar:

```python
                pares_afectados.add((intento.estudiante_id, intento.ejercicio_practica.practica_id))
```

por:

```python
                pares_afectados.add((
                    intento.estudiante_id,
                    intento.practica_comision_id,
                    intento.ejercicio_practica.practica_id,
                ))
```

Línea ~136:

```python
        for estudiante_id, pc_id, practica_id in pares_afectados:
            if self._reconciliar_progreso(estudiante_id, pc_id, practica_id, dry_run):
```

En `_reconciliar_progreso` (línea ~145), cambiar la firma a
`def _reconciliar_progreso(self, estudiante_id, pc_id, practica_id, dry_run):`,
el filtro de `Progreso` a `practica_comision_id=pc_id`, y agregar
`practica_comision_id=pc_id` al filtro de `Intento`:

```python
                tiene_correcto = Intento.objects.filter(
                    estudiante_id=estudiante_id,
                    ejercicio_practica=ep_actual,
                    practica_comision_id=pc_id,
                ).filter(
                    Q(es_correcto=True) | Q(aprobado_docente=True)
                ).exists()
```

Cambiar el mensaje `f'  Progreso estudiante {estudiante_id} | práctica {practica_id}: '` por `f'  Progreso estudiante {estudiante_id} | PC {pc_id}: '`.

- [ ] **Step 4: `reconciliar_V_mayuscula.py`**

Línea ~134, reemplazar:

```python
            key = (intento.estudiante_id, ep.practica_id)
```

por:

```python
            key = (intento.estudiante_id, intento.practica_comision_id, ep.practica_id)
```

Línea ~146, cambiar el desempaquetado del loop a:

```python
            for (student_id, pc_id, practica_id), eps in progreso_pendiente.items():
```

y la llamada de la línea ~153 a `self._avanzar_progreso(student_id, pc_id, practica_id, ep)`.

En `_avanzar_progreso` (línea ~186), cambiar la firma a
`def _avanzar_progreso(student_id: int, pc_id: int, practica_id: int, ep: EjercicioPractica) -> bool:`
y el filtro de `Progreso` a `.filter(estudiante_id=student_id, practica_comision_id=pc_id)`.

- [ ] **Step 5: Correr los tests de los comandos**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios docentes
```
Expected: PASS (salvo el test roto de antes en docentes).

- [ ] **Step 6: Commit**

```bash
git add ejercicios/management/commands/
git commit -m "fix(commands): reconciliar el progreso por comision"
```

---

### Task 9: Eliminar `Progreso.practica` y cerrar el esquema

Última tarea: se va el campo viejo, entra la clave nueva, y `Intento.practica_comision` pasa a obligatoria. Acá es donde el esquema deja de permitir el bug.

**Files:**
- Modify: `ejercicios/models.py` (clase `Progreso`: campo, `Meta`, docstring; clase `Intento`: `practica_comision`)
- Modify: `ejercicios/admin.py:78-83` (`ProgresoAdmin`)
- Modify: `ejercicios/progreso.py` (sacar `practica_id` del `defaults`)
- Modify: `ejercicios/management/commands/reconciliar_progreso_aprobaciones.py`, `reevaluar_tablas_verdad.py` (sacar `practica_id` de los `create`/`defaults`)
- Modify: `ejercicios/tests.py`, `docentes/tests.py`, `analiticas/tests.py` (sacar `practica=` de los `Progreso.objects.create`)
- Create: `ejercicios/migrations/0025_progreso_clave_por_comision.py` (generada)
- Create: `ejercicios/migrations/0026_intento_practica_comision_obligatoria.py` (generada)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `Progreso` con clave `(estudiante, practica_comision)` y sin campo `practica`.

- [ ] **Step 1: Actualizar el modelo `Progreso`**

En `ejercicios/models.py`, en la clase `Progreso`: eliminar el campo `practica` completo, quitar `null=True, blank=True` de `practica_comision` (y el comentario `# nullable durante la migración de datos; ver 0025`), y reemplazar el `Meta`:

```python
    class Meta:
        verbose_name = 'progreso'
        verbose_name_plural = 'progresos'
        unique_together = ['estudiante', 'practica_comision']
```

Reemplazar el `__str__`:

```python
    def __str__(self) -> str:
        if self.ejercicio_practica_actual is None:
            estado = 'completada'
        else:
            estado = f'en ej. {self.ejercicio_practica_actual.orden}'
        return f'{self.estudiante} | {self.practica_comision} | {estado}'
```

Y en el docstring de la clase, reemplazar el primer párrafo:

```
    """Registra hasta qué ejercicio llegó un estudiante en una práctica.

    Una fila por par ``(estudiante, practica_comision)``: el progreso es del
    cursado, no de la práctica canónica. Una misma :class:`Practica` asignada a
    dos comisiones tiene una fila en cada una, con su propio modo de desbloqueo
    y su propio puntero. El campo ``ejercicio_practica_actual`` apunta al último
    ejercicio desbloqueado; cuando vale ``None``, la práctica está completa.
```

y la entrada de `Attributes:` que dice `practica (ForeignKey): la práctica canónica.` por:

```
        practica_comision (ForeignKey): la asignación de la práctica a la
            comisión desde la que el estudiante la está cursando.
```

En la clase `Intento`, quitar `null=True,` y `blank=True,` del campo `practica_comision`, y borrar el comentario `# nullable durante la migración de datos`.

En `docentes/views.py`, línea ~2130, el guard `if intento.practica_comision_id:`
que protege la invalidación de caché queda muerto: con la FK obligatoria nunca
es falso. Simplificarlo a la invalidación directa.

- [ ] **Step 2: Sacar `practica_id` de los sitios que lo poblaban a mano**

En `ejercicios/progreso.py`, en `avanzar_progreso`, reemplazar:

```python
                defaults={'ejercicio_practica_actual': ep, 'practica_id': practica_id},
```

por:

```python
                defaults={'ejercicio_practica_actual': ep},
```

y borrar el comentario de dos líneas que lo explicaba.

En `reconciliar_progreso_aprobaciones.py`, en el `get_or_create`, dejar
`defaults={'ejercicio_practica_actual': primer_ep},`.

En `reevaluar_tablas_verdad.py`, en el `Progreso.objects.create(...)`, borrar la línea `practica_id=practica_id,`.

- [ ] **Step 3: Sacar `practica=` de los tests**

Buscar todos los `Progreso.objects.create(` que pasen `practica=`:

```bash
grep -rn "Progreso.objects.create" ejercicios/tests.py docentes/tests.py analiticas/tests.py
```

En cada uno, eliminar el argumento `practica=...` dejando `practica_comision=...`.

Los tres de `analiticas/tests.py` (líneas ~496, ~497 y ~559) **ya recibieron
`practica_comision=self.pc` en la Task 7** — sin eso, el cambio de query de
`research.py` los dejaba sin match y dos tests fallaban. Acá sólo hay que
sacarles el `practica=`, quedando:

```python
        Progreso.objects.create(estudiante=self.est_alto, practica_comision=self.pc, ejercicio_practica_actual=None)
        Progreso.objects.create(estudiante=self.est_bajo, practica_comision=self.pc, ejercicio_practica_actual=self.ep)
```

y, en la línea ~559:

```python
        Progreso.objects.create(estudiante=self.est_sin_consent, practica_comision=self.pc, ejercicio_practica_actual=None)
```

- [ ] **Step 4: Actualizar el admin**

En `ejercicios/admin.py`, reemplazar `ProgresoAdmin`:

```python
@admin.register(Progreso)
class ProgresoAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'practica_comision', 'ejercicio_practica_actual')
    list_filter = ('practica_comision__comision',)
    search_fields = ('estudiante__username',)
```

- [ ] **Step 5: Generar las dos migraciones**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations ejercicios --name progreso_clave_por_comision
```

Verificar en el archivo generado que `AlterUniqueTogether` aparezca **antes** de `RemoveField('progreso', 'practica')`: el `unique_together` viejo referencia `practica` y borrar el campo primero rompe. Si el autodetector los ordenó al revés, reordenar las operaciones a mano.

Si esa misma corrida generó también el `AlterField` de `Intento.practica_comision`, separarlo a un segundo archivo `0026_intento_practica_comision_obligatoria.py` con `dependencies = [('ejercicios', '0025_progreso_clave_por_comision')]`. Si no lo generó, correr de nuevo:

```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations ejercicios --name intento_practica_comision_obligatoria
```

- [ ] **Step 6: Verificar que aplican**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py migrate ejercicios
```
Expected: aplica `0025` y `0026` sin error.

- [ ] **Step 7: Correr la suite completa**

Run:
```bash
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test
```
Expected: PASS, salvo `docentes.tests.ComisionesListViewTests.test_admin_ve_todas_las_comisiones` (roto de antes en master). Tarda ~18 minutos.

Verificar además que no queden referencias al campo eliminado:

```bash
grep -rn "progreso.practica\b\|practica__progresos\|Progreso.objects.filter(.*practica=" --include=*.py .
```
Expected: sin resultados.

- [ ] **Step 8: Commit**

```bash
git add ejercicios/models.py ejercicios/admin.py ejercicios/progreso.py ejercicios/migrations/ ejercicios/management/commands/ ejercicios/tests.py docentes/tests.py analiticas/tests.py
git commit -m "feat(ejercicios): Progreso keyeado por (estudiante, practica_comision)"
```

---

## Verificación final

Antes de abrir el PR:

1. La suite completa pasa (Task 9, Step 7).
2. `grep` del Step 7 sin resultados.
3. Las migraciones `0023`→`0026` aplican en orden sobre una base limpia:
   ```bash
   $env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py migrate
   ```
4. El PR se abre contra `claude/desbloqueo-configurable`, **no** contra `master`.

# Desbloqueo configurable por práctica — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada práctica pueda elegir entre desbloqueo secuencial (el actual) y libre (todos los ejercicios abiertos desde el inicio).

**Architecture:** Un `BooleanField` en `PracticaComision` elige el modo. La lógica de avance de `Progreso`, hoy duplicada en dos lugares, se extrae a `ejercicios/progreso.py` y aprende el modo libre recalculando el ejercicio actual como el primero sin resolver. Las vistas de estudiante saltean el gating por orden cuando el modo es libre.

**Tech Stack:** Django 6.0.6, PostgreSQL en producción / SQLite en tests, DRF, templates Django con Alpine.js.

**Spec:** `docs/superpowers/specs/2026-08-06-desbloqueo-configurable-design.md`

## Global Constraints

- Python: `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe` (venv en el directorio **padre** del repo).
- Antes de correr tests: `$env:SECRET_KEY='x'` en la misma línea de PowerShell.
- Para `makemigrations`, usar el mismo intérprete con ruta absoluta.
- El default de `desbloqueo_secuencial` es `True`: **ninguna práctica existente cambia de comportamiento**. Los tests actuales de `DesbloqueoProgresivoTests` deben pasar sin modificarse.
- `ejercicios/correctitud.py` (`Q_CORRECTO`) ya existe en master; no redefinir el predicado.
- AGENTS.md §4 obliga a documentar cambios de **gestión docente** en `README.md` y registrar la intervención en `MEMORY.md`. Es la Task 7; no es opcional.
- Textos de UI en español rioplatense.

---

### Task 1: Campo `desbloqueo_secuencial` en `PracticaComision`

**Files:**
- Modify: `ejercicios/models.py` (clase `PracticaComision`, después de `fecha_cierre`)
- Create: `ejercicios/migrations/0021_practicacomision_desbloqueo_secuencial.py` (generada)
- Test: `ejercicios/tests.py` (clase nueva)

**Interfaces:**
- Consumes: nada.
- Produces: `PracticaComision.desbloqueo_secuencial` (`BooleanField`, `default=True`).

- [ ] **Step 1: Write the failing test**

Agregar al final de `ejercicios/tests.py`:

```python
class DesbloqueoConfigurableModeloTests(TestCase):
    def test_default_es_secuencial(self):
        docente = _u('doc-modo', es_docente=True)
        comision = Comision.objects.create(nombre='IPC Modo')
        practica = Practica.objects.create(titulo='P', creada_por=docente)
        pc = PracticaComision.objects.create(practica=practica, comision=comision, orden=1)

        self.assertTrue(pc.desbloqueo_secuencial)

    def test_se_puede_poner_en_libre(self):
        docente = _u('doc-modo-libre', es_docente=True)
        comision = Comision.objects.create(nombre='IPC Modo Libre')
        practica = Practica.objects.create(titulo='P', creada_por=docente)
        pc = PracticaComision.objects.create(
            practica=practica, comision=comision, orden=1,
            desbloqueo_secuencial=False,
        )
        pc.refresh_from_db()

        self.assertFalse(pc.desbloqueo_secuencial)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.DesbloqueoConfigurableModeloTests
```

Expected: FAIL — `TypeError: PracticaComision() got unexpected keyword arguments: 'desbloqueo_secuencial'`

- [ ] **Step 3: Agregar el campo**

En `ejercicios/models.py`, dentro de `PracticaComision`, inmediatamente después del campo `fecha_cierre` y antes de `class Meta`:

```python
    desbloqueo_secuencial = models.BooleanField(
        default=True,
        verbose_name='desbloqueo secuencial',
        help_text=(
            'Si está marcado, cada ejercicio se habilita al resolver correctamente '
            'el anterior. Si no, todos los ejercicios están disponibles desde el inicio.'
        ),
    )
```

- [ ] **Step 4: Generar la migración**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py makemigrations ejercicios
```

Expected: crea `ejercicios/migrations/0021_practicacomision_desbloqueo_secuencial.py` con un solo `AddField`. No hace falta `atomic = False`: es un `ALTER TABLE ADD COLUMN` con default, sin inserts pendientes.

- [ ] **Step 5: Run test to verify it passes**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.DesbloqueoConfigurableModeloTests
```

Expected: PASS — `Ran 2 tests` / `OK`

- [ ] **Step 6: Commit**

```bash
git add ejercicios/models.py ejercicios/migrations/0021_practicacomision_desbloqueo_secuencial.py ejercicios/tests.py
git commit -m "feat(ejercicios): campo desbloqueo_secuencial en PracticaComision"
```

---

### Task 2: Módulo `ejercicios/progreso.py`

Unifica las dos copias de la lógica de avance y le agrega el modo libre.

**Files:**
- Create: `ejercicios/progreso.py`
- Test: `ejercicios/tests.py` (clase nueva)

**Interfaces:**
- Consumes: `ejercicios.correctitud.Q_CORRECTO`, `ejercicios.models.{EjercicioPractica, Intento, Progreso}`.
- Produces:
  - `eps_resueltos(estudiante, practica) -> set[int]`
  - `esta_resuelto(estudiante, ep) -> bool`
  - `avanzar_progreso(estudiante, ep, *, secuencial: bool) -> tuple[bool, int]` que devuelve `(practica_completa, ejercicios_pendientes)`

- [ ] **Step 1: Write the failing test**

Agregar al final de `ejercicios/tests.py`:

```python
class ProgresoModuloTests(TestCase):
    """avanzar_progreso() en ambos modos, sin pasar por la API."""

    def setUp(self):
        self.docente = _u('doc-mod', es_docente=True)
        self.estudiante = _u('est-mod')
        self.comision = Comision.objects.create(nombre='IPC Mod')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision)
        self.practica = Practica.objects.create(titulo='P-mod', creada_por=self.docente)
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

    def _resolver(self, ep, aprobado_docente=None, es_correcto=True):
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=ep,
            practica_comision=self.pc, respuesta_raw='p',
            es_correcto=es_correcto, aprobado_docente=aprobado_docente,
        )

    def test_secuencial_avanza_al_siguiente(self):
        from ejercicios.progreso import avanzar_progreso
        Progreso.objects.create(
            estudiante=self.estudiante, practica=self.practica,
            ejercicio_practica_actual=self.eps[0],
        )
        self._resolver(self.eps[0])

        completa, pendientes = avanzar_progreso(self.estudiante, self.eps[0], secuencial=True)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica=self.practica)
        self.assertEqual(progreso.ejercicio_practica_actual, self.eps[1])
        self.assertFalse(completa)
        self.assertEqual(pendientes, 2)

    def test_secuencial_no_retrocede_al_reintentar_resuelto(self):
        from ejercicios.progreso import avanzar_progreso
        Progreso.objects.create(
            estudiante=self.estudiante, practica=self.practica,
            ejercicio_practica_actual=self.eps[2],
        )
        self._resolver(self.eps[0])

        avanzar_progreso(self.estudiante, self.eps[0], secuencial=True)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica=self.practica)
        self.assertEqual(progreso.ejercicio_practica_actual, self.eps[2])

    def test_libre_resolver_el_tercero_deja_el_actual_en_el_primero(self):
        from ejercicios.progreso import avanzar_progreso
        self._resolver(self.eps[2])

        completa, pendientes = avanzar_progreso(self.estudiante, self.eps[2], secuencial=False)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica=self.practica)
        self.assertEqual(progreso.ejercicio_practica_actual, self.eps[0])
        self.assertFalse(completa)
        self.assertEqual(pendientes, 2)

    def test_libre_resolver_el_ultimo_pendiente_completa_la_practica(self):
        from ejercicios.progreso import avanzar_progreso
        for ep in self.eps:
            self._resolver(ep)

        completa, pendientes = avanzar_progreso(self.estudiante, self.eps[1], secuencial=False)

        progreso = Progreso.objects.get(estudiante=self.estudiante, practica=self.practica)
        self.assertIsNone(progreso.ejercicio_practica_actual)
        self.assertTrue(completa)
        self.assertEqual(pendientes, 0)

    def test_esta_resuelto_respeta_el_juicio_docente(self):
        from ejercicios.progreso import esta_resuelto
        # correcto pero rechazado por el docente → no cuenta
        self._resolver(self.eps[0], aprobado_docente=False)
        self.assertFalse(esta_resuelto(self.estudiante, self.eps[0]))
        # incorrecto pero aprobado a mano → cuenta
        self._resolver(self.eps[1], es_correcto=False, aprobado_docente=True)
        self.assertTrue(esta_resuelto(self.estudiante, self.eps[1]))
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.ProgresoModuloTests
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ejercicios.progreso'`

- [ ] **Step 3: Crear el módulo**

Crear `ejercicios/progreso.py`:

```python
"""Avance del :class:`~ejercicios.models.Progreso` de un estudiante en una práctica.

Centraliza la lógica que antes estaba duplicada en ``ejercicios/api/views.py``
(intento correcto del estudiante) y en ``docentes/views.py`` (aprobación manual
de un intento incorrecto).

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


def eps_resueltos(estudiante, practica) -> set[int]:
    """Ids de los EjercicioPractica de ``practica`` ya resueltos por ``estudiante``.

    Usa la correctitud efectiva de :mod:`ejercicios.correctitud`: el juicio
    docente tiene precedencia sobre el resultado del motor.
    """
    return set(
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, ejercicio_practica__practica=practica)
        .values_list('ejercicio_practica_id', flat=True)
        .distinct()
    )


def esta_resuelto(estudiante, ep) -> bool:
    """True si ``estudiante`` ya resolvió ``ep`` (correctitud efectiva)."""
    return (
        Intento.objects
        .filter(Q_CORRECTO, estudiante=estudiante, ejercicio_practica=ep)
        .exists()
    )


def avanzar_progreso(estudiante, ep, *, secuencial: bool) -> tuple[bool, int]:
    """Actualiza el Progreso de ``estudiante`` tras resolverse ``ep``.

    Args:
        estudiante: el usuario estudiante.
        ep: el :class:`~ejercicios.models.EjercicioPractica` recién resuelto.
        secuencial: modo de desbloqueo de la práctica en esa comisión.

    Returns:
        tuple[bool, int]: ``(practica_completa, ejercicios_pendientes)``.
    """
    practica = ep.practica
    total = EjercicioPractica.objects.filter(practica=practica).count()

    with transaction.atomic():
        # Lock pesimista: evita la race condition entre dos requests simultáneos
        # sobre el mismo (estudiante, practica).
        progreso = (
            Progreso.objects
            .select_for_update()
            .filter(estudiante=estudiante, practica=practica)
            .first()
        )
        if progreso is None:
            progreso, _ = Progreso.objects.get_or_create(
                estudiante=estudiante,
                practica=practica,
                defaults={'ejercicio_practica_actual': ep},
            )
            progreso = (
                Progreso.objects
                .select_for_update()
                .get(estudiante=estudiante, practica=practica)
            )

        if secuencial:
            if progreso.ejercicio_practica_actual == ep:
                siguiente = (
                    EjercicioPractica.objects
                    .filter(practica=practica, orden__gt=ep.orden)
                    .order_by('orden')
                    .first()
                )
                progreso.ejercicio_practica_actual = siguiente
                progreso.save(update_fields=['ejercicio_practica_actual'])
            actual = progreso.ejercicio_practica_actual
            # En secuencial, todo lo anterior al actual está resuelto.
            pendientes = 0 if actual is None else total - actual.orden + 1
        else:
            resueltos = eps_resueltos(estudiante, practica)
            siguiente = (
                EjercicioPractica.objects
                .filter(practica=practica)
                .exclude(pk__in=resueltos)
                .order_by('orden')
                .first()
            )
            progreso.ejercicio_practica_actual = siguiente
            progreso.save(update_fields=['ejercicio_practica_actual'])
            pendientes = total - len(resueltos)

    return progreso.ejercicio_practica_actual is None, max(pendientes, 0)
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.ProgresoModuloTests
```

Expected: PASS — `Ran 5 tests` / `OK`

- [ ] **Step 5: Commit**

```bash
git add ejercicios/progreso.py ejercicios/tests.py
git commit -m "feat(ejercicios): modulo progreso con modos secuencial y libre"
```

---

### Task 3: Los dos call sites usan el módulo

Elimina la duplicación y hace que ambos caminos respeten el modo.

**Files:**
- Modify: `ejercicios/api/views.py:296` y `ejercicios/api/views.py:355`; borrar `_avanzar_progreso` (líneas 358-415)
- Modify: `docentes/views.py:2051` (`_avanzar_progreso_por_aprobacion_docente`) y su llamador en la línea 2151
- Test: `ejercicios/tests.py` (`DesbloqueoProgresivoTests`), `docentes/tests.py`

**Interfaces:**
- Consumes: `ejercicios.progreso.avanzar_progreso` (Task 2), `PracticaComision.desbloqueo_secuencial` (Task 1).
- Produces: la respuesta de la API suma la clave `ejercicios_pendientes` (`int`).

- [ ] **Step 1: Write the failing test**

Agregar a la clase `DesbloqueoProgresivoTests` en `ejercicios/tests.py` (usa el helper `_intento` que ya existe ahí):

```python
    def test_modo_libre_permite_resolver_fuera_de_orden(self):
        self.pc.desbloqueo_secuencial = False
        self.pc.save(update_fields=['desbloqueo_secuencial'])

        resp = self._intento(self.ep2, 'q')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['correcto'])
        # ep1 sigue sin resolver, así que el progreso queda apuntando ahí
        progreso = Progreso.objects.get(estudiante=self.estudiante, practica=self.practica)
        self.assertEqual(progreso.ejercicio_practica_actual, self.ep1)
        self.assertEqual(resp.json()['ejercicios_pendientes'], 1)

    def test_modo_libre_completa_al_resolver_el_ultimo_pendiente(self):
        self.pc.desbloqueo_secuencial = False
        self.pc.save(update_fields=['desbloqueo_secuencial'])

        self._intento(self.ep2, 'q')
        resp = self._intento(self.ep1, 'p')

        self.assertTrue(resp.json()['practica_completa'])
        self.assertEqual(resp.json()['ejercicios_pendientes'], 0)
        progreso = Progreso.objects.get(estudiante=self.estudiante, practica=self.practica)
        self.assertIsNone(progreso.ejercicio_practica_actual)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.DesbloqueoProgresivoTests
```

Expected: FAIL — `KeyError: 'ejercicios_pendientes'`

- [ ] **Step 3: Actualizar la API**

En `ejercicios/api/views.py`, agregar el import junto a los otros de `ejercicios`:

```python
from ejercicios.progreso import avanzar_progreso
```

Reemplazar la línea 296:

```python
                practica_completa = self._avanzar_progreso(request.user, ep)
```

por:

```python
                practica_completa, ejercicios_pendientes = avanzar_progreso(
                    request.user, ep, secuencial=pc.desbloqueo_secuencial,
                )
```

`pc` ya está resuelto en la línea 111 de esa misma vista, así que no hace falta consultarlo de nuevo.

Inicializar `ejercicios_pendientes = None` donde hoy se inicializa `practica_completa` (buscar su asignación previa al bloque `if resultado.get('correcto')`), y sumar la clave a la respuesta de la línea 355:

```python
            'practica_completa': practica_completa,
            'ejercicios_pendientes': ejercicios_pendientes,
```

Borrar el método estático `_avanzar_progreso` completo (líneas 358-415), incluido su docstring.

- [ ] **Step 4: Actualizar la aprobación docente**

En `docentes/views.py`, reemplazar el cuerpo entero de `_avanzar_progreso_por_aprobacion_docente` (línea 2051 en adelante) por:

```python
def _avanzar_progreso_por_aprobacion_docente(intento):
    """Avanza el progreso cuando el docente aprueba a mano un intento incorrecto.

    Delega en :func:`ejercicios.progreso.avanzar_progreso`. El modo de desbloqueo
    sale de la PracticaComision del intento; los intentos viejos anteriores a esa
    FK no la tienen, y para ésos se asume el comportamiento histórico (secuencial).
    """
    pc = intento.practica_comision
    secuencial = pc.desbloqueo_secuencial if pc is not None else True
    avanzar_progreso(intento.estudiante, intento.ejercicio_practica, secuencial=secuencial)
```

Agregar el import correspondiente arriba del archivo:

```python
from ejercicios.progreso import avanzar_progreso
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.DesbloqueoProgresivoTests docentes.tests
```

Expected: PASS. Los tests preexistentes de `DesbloqueoProgresivoTests` deben pasar **sin haber sido modificados**.

- [ ] **Step 6: Commit**

```bash
git add ejercicios/api/views.py docentes/views.py ejercicios/tests.py
git commit -m "refactor: unificar el avance de progreso en ejercicios/progreso.py"
```

---

### Task 4: Vistas de estudiante respetan el modo

**Files:**
- Modify: `ejercicios/views.py:182-185` (`practica_detail`) y `ejercicios/views.py:260-286` (`ejercicio_detail`)
- Test: `ejercicios/tests.py` (clase nueva)

**Interfaces:**
- Consumes: `PracticaComision.desbloqueo_secuencial` (Task 1), `ejercicios.progreso.esta_resuelto` (Task 2).
- Produces: el contexto de `ejercicio.html` suma `desbloqueo_secuencial` (`bool`).

- [ ] **Step 1: Write the failing test**

Agregar al final de `ejercicios/tests.py`:

```python
class DesbloqueoLibreVistasTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-libre', es_docente=True)
        self.estudiante = _u('est-libre')
        self.comision = Comision.objects.create(nombre='IPC Libre')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision)
        self.practica = Practica.objects.create(titulo='P-libre', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
            desbloqueo_secuencial=False,
        )
        ej1 = Ejercicio.objects.create(enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente)
        ej2 = Ejercicio.objects.create(enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente)
        self.ep1 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej1, orden=1)
        self.ep2 = EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej2, orden=2)
        self.client.login(username='est-libre', password='clave123')

    def test_ningun_ejercicio_queda_bloqueado(self):
        response = self.client.get(reverse('ejercicios:practica', args=[self.pc.id]))

        self.assertEqual(response.status_code, 200)
        estados = [d['estado'] for d in response.context['eps_data']]
        self.assertNotIn('bloqueado', estados)

    def test_se_puede_entrar_al_segundo_sin_resolver_el_primero(self):
        response = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc.id, self.ep2.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['puede_enviar'])

    def test_secuencial_sigue_bloqueando(self):
        self.pc.desbloqueo_secuencial = True
        self.pc.save(update_fields=['desbloqueo_secuencial'])

        detalle = self.client.get(reverse('ejercicios:practica', args=[self.pc.id]))
        self.assertIn('bloqueado', [d['estado'] for d in detalle.context['eps_data']])

        response = self.client.get(
            reverse('ejercicios:ejercicio', args=[self.pc.id, self.ep2.id])
        )
        self.assertEqual(response.status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.DesbloqueoLibreVistasTests
```

Expected: FAIL — `test_ningun_ejercicio_queda_bloqueado` encuentra `'bloqueado'`, y `test_se_puede_entrar_al_segundo_sin_resolver_el_primero` recibe 302 en vez de 200.

- [ ] **Step 3: `practica_detail`**

En `ejercicios/views.py`, reemplazar el bloque de las líneas 182-185:

```python
            desbloqueado = (
                practica_marcada_completa
                or (ep_actual_orden is not None and ep.orden <= ep_actual_orden)
            )
```

por:

```python
            desbloqueado = (
                not pc.desbloqueo_secuencial
                or practica_marcada_completa
                or (ep_actual_orden is not None and ep.orden <= ep_actual_orden)
            )
```

- [ ] **Step 4: `ejercicio_detail`**

En la misma vista, reemplazar el bloque que calcula `ya_resuelto` y decide `puede_enviar` (líneas 260-286) por:

```python
        ya_resuelto = esta_resuelto(usuario, ep)

        if not pc.desbloqueo_secuencial:
            puede_enviar = not ya_resuelto
        else:
            try:
                progreso = Progreso.objects.get(estudiante=usuario, practica=practica)
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

Agregar el import arriba del archivo:

```python
from ejercicios.progreso import esta_resuelto
```

Y sumar `desbloqueo_secuencial` al contexto del `render` de `ejercicio.html`:

```python
        'desbloqueo_secuencial': pc.desbloqueo_secuencial,
```

Nota: `esta_resuelto` reemplaza al cálculo manual de `intento_correcto_vigente`. Es un cambio de comportamiento deliberado documentado en el spec — un intento incorrecto aprobado a mano por el docente ahora cuenta como resuelto y deja de admitir envíos.

- [ ] **Step 5: Run tests to verify they pass**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios
```

Expected: PASS en toda la app `ejercicios`.

- [ ] **Step 6: Commit**

```bash
git add ejercicios/views.py ejercicios/tests.py
git commit -m "feat(ejercicios): las vistas de estudiante respetan el modo de desbloqueo"
```

---

### Task 5: Formulario docente

**Files:**
- Modify: `docentes/forms.py:59` (`PracticaComisionForm.Meta.fields`) y su `__init__`
- Modify: los templates que renderizan ese form (buscarlos con el grep del Step 3)
- Test: `docentes/tests.py`

**Interfaces:**
- Consumes: `PracticaComision.desbloqueo_secuencial` (Task 1).
- Produces: el form acepta y persiste `desbloqueo_secuencial`.

- [ ] **Step 1: Write the failing test**

Agregar al final de `docentes/tests.py`:

```python
class PracticaComisionFormModoTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-form-modo', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC Form Modo')
        self.comision.docentes.add(self.docente)

    def _data(self, **extra):
        data = {'comision': self.comision.id, 'orden': 1}
        data.update(extra)
        return data

    def test_sin_marcar_queda_en_libre(self):
        from docentes.forms import PracticaComisionForm
        form = PracticaComisionForm(data=self._data(), usuario=self.docente)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data['desbloqueo_secuencial'])

    def test_marcado_queda_en_secuencial(self):
        from docentes.forms import PracticaComisionForm
        form = PracticaComisionForm(
            data=self._data(desbloqueo_secuencial='on'), usuario=self.docente,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data['desbloqueo_secuencial'])
```

Nota sobre checkboxes en Django: un `BooleanField` con `default=True` renderiza marcado, pero si el POST no trae la clave el form lo interpreta como `False`. Por eso el primer test espera `False` — es el comportamiento estándar y el que hace que desmarcar funcione.

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.PracticaComisionFormModoTests
```

Expected: FAIL — `KeyError: 'desbloqueo_secuencial'` en `cleaned_data`.

- [ ] **Step 3: Agregar el campo al form y al template**

En `docentes/forms.py`, línea 59:

```python
        fields = ['comision', 'orden', 'fecha_apertura', 'fecha_cierre', 'desbloqueo_secuencial']
```

Y en su `__init__`, junto a los otros ajustes de labels:

```python
        self.fields['desbloqueo_secuencial'].label = (
            'Desbloqueo secuencial: cada ejercicio se habilita al resolver el anterior'
        )
        self.fields['desbloqueo_secuencial'].help_text = (
            'Desmarcá esta opción para que todos los ejercicios estén disponibles desde el inicio.'
        )
```

Localizar los templates que renderizan el form campo por campo:

```bash
grep -rln "fecha_apertura" templates/docentes/
```

En cada uno, agregar el checkbox donde ya aparecen `fecha_apertura` / `fecha_cierre`, siguiendo el markup que use ese archivo para los demás campos. Si el template renderiza el form completo (`{{ form.as_p }}` o similar), no hay nada que agregar: el campo aparece solo.

- [ ] **Step 4: Run test to verify it passes**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.PracticaComisionFormModoTests
```

Expected: PASS — `Ran 2 tests` / `OK`

- [ ] **Step 5: Commit**

```bash
git add docentes/forms.py docentes/tests.py templates/docentes/
git commit -m "feat(docentes): elegir el modo de desbloqueo al asignar una practica"
```

---

### Task 6: Ajustes de UI

Dos textos que mienten en modo libre.

**Files:**
- Modify: `templates/ejercicios/ejercicio.html` (líneas 438, 519, 631)
- Modify: `docentes/views.py` (`_build_progreso_estudiantes`, líneas 392 y 429) y `templates/docentes/comision_detail.html:401`
- Test: `docentes/tests.py`

**Interfaces:**
- Consumes: `desbloqueo_secuencial` del contexto (Task 4), `ejercicios_pendientes` de la API (Task 3).
- Produces: `practicas_detalle` suma la clave `desbloqueo_secuencial` (`bool`).

- [ ] **Step 1: Write the failing test**

Agregar al final de `docentes/tests.py`:

```python
class PanelModoLibreTests(TestCase):
    def setUp(self):
        self.docente = _u('doc-panel-libre', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC Panel Libre')
        self.comision.docentes.add(self.docente)
        self.estudiante = _u('est-panel-libre')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision)
        self.practica = Practica.objects.create(titulo='P-panel', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=self.practica, comision=self.comision, orden=1,
            desbloqueo_secuencial=False,
        )
        ej = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        EjercicioPractica.objects.create(practica=self.practica, ejercicio=ej, orden=1)

    def test_no_muestra_ejercicio_actual_en_practicas_libres(self):
        self.client.login(username='doc-panel-libre', password='clave123')
        response = self.client.get(reverse('docentes:comision_detail', args=[self.comision.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Ej. 1')
        detalle = response.context['progreso_estudiantes'][0]['practicas_detalle'][0]
        self.assertFalse(detalle['desbloqueo_secuencial'])

    def test_si_lo_muestra_en_practicas_secuenciales(self):
        self.pc.desbloqueo_secuencial = True
        self.pc.save(update_fields=['desbloqueo_secuencial'])

        self.client.login(username='doc-panel-libre', password='clave123')
        response = self.client.get(reverse('docentes:comision_detail', args=[self.comision.id]))

        self.assertContains(response, 'Ej. 1')
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.PanelModoLibreTests
```

Expected: FAIL — `'Ej. 1'` aparece en la respuesta del primer test.

- [ ] **Step 3: Exponer el modo en `practicas_detalle`**

`_build_progreso_estudiantes` itera sobre `practicas`, que son `Practica` canónicas, así que necesita el mapa de modos por práctica. Antes del bucle de estudiantes, junto a `progresos_index`:

```python
    modo_por_practica = {
        pc.practica_id: pc.desbloqueo_secuencial
        for pc in comision.practicas_comisiones.all()
    }
```

Y sumar la clave en los **dos** `practicas_detalle.append(...)` (líneas 392 y 429):

```python
                    'desbloqueo_secuencial': modo_por_practica.get(practica.id, True),
```

- [ ] **Step 4: Condicionar el `Ej. N` en el template**

En `templates/docentes/comision_detail.html`, línea 401, cambiar:

```html
                {% elif detalle.ejercicio_actual %}
```

por:

```html
                {% elif detalle.ejercicio_actual and detalle.desbloqueo_secuencial %}
```

En prácticas libres esa celda queda vacía y el avance lo informa la columna `Resuelto`.

- [ ] **Step 5: Mensaje al estudiante**

En `templates/ejercicios/ejercicio.html`, los tres bloques de las líneas 438, 519 y 631 dicen hoy:

```html
        ✓ <strong>¡Correcto!</strong>
        Avanzás al siguiente ejercicio.
```

Reemplazar los tres por:

```html
        ✓ <strong>¡Correcto!</strong>
        {% if desbloqueo_secuencial %}
          Avanzás al siguiente ejercicio.
        {% else %}
          <span x-show="resultado?.ejercicios_pendientes === 1">Te queda 1 ejercicio por resolver.</span>
          <span x-show="resultado?.ejercicios_pendientes > 1"
                x-text="'Te quedan ' + resultado.ejercicios_pendientes + ' ejercicios por resolver.'"></span>
        {% endif %}
```

El caso de cero pendientes no se contempla acá: lo cubre el cartel de "¡Práctica completa!" que ya existe abajo, condicionado por `resultado?.practica_completa`.

- [ ] **Step 6: Run tests to verify they pass**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes ejercicios
```

Expected: PASS en ambas apps.

- [ ] **Step 7: Commit**

```bash
git add docentes/views.py templates/docentes/comision_detail.html templates/ejercicios/ejercicio.html docentes/tests.py
git commit -m "feat: ajustar la UI al modo de desbloqueo libre"
```

---

### Task 7: Documentación y verificación final

AGENTS.md §4 lo exige para cambios de gestión docente. No es opcional.

**Files:**
- Modify: `README.md` (secciones "Estado actual del sitio", "Docentes" y "Estudiantes")
- Modify: `MEMORY.md` (snapshot §3 + entrada de bitácora)
- Modify: `ejercicios/models.py` y `ejercicios/views.py` (docstrings desactualizados)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: documentación consistente y evidencia de que la suite no regresó.

- [ ] **Step 1: Actualizar docstrings**

Tres docstrings describen el desbloqueo como si fuera siempre secuencial y citan "AGENTS.md §7", una referencia que quedó vieja por una renumeración (la §7 actual habla de analítica educativa). Reemplazar la cita por la descripción de las reglas en el propio docstring:

- `Progreso` en `ejercicios/models.py` (bloque "Reglas de desbloqueo").
- `EjercicioPractica` en `ejercicios/models.py` (el párrafo sobre `orden`).
- `practica_detail` y `ejercicio_detail` en `ejercicios/views.py`.

En los cuatro, aclarar que el modo lo define `PracticaComision.desbloqueo_secuencial`.

- [ ] **Step 2: Actualizar README**

En "Estado actual del sitio", cambiar la línea que dice "Prácticas con desbloqueo secuencial, orden explícito…" por una que refleje que el desbloqueo es configurable por práctica.

En "Docentes", agregar a la lista:

```md
- Elegir, por práctica y comisión, si los ejercicios se desbloquean de a uno al resolver el anterior o si están todos disponibles desde el inicio.
```

En "Estudiantes", cambiar "Resolver ejercicios en secuencia con desbloqueo progresivo" por una redacción que contemple ambos modos.

- [ ] **Step 3: Registrar en MEMORY**

Agregar al snapshot funcional §3 una línea sobre el modo configurable, y una entrada de bitácora con el formato de §4 (pedido, cambios, tests/checks, commit, PR).

- [ ] **Step 4: Correr la suite completa**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test
```

Expected: OK, sin fallos. Master quedó verde tras el PR #183, así que **cualquier** fallo acá es una regresión de este trabajo y hay que arreglarla antes de seguir.

- [ ] **Step 5: Verificar que no quedó lógica de avance duplicada**

```bash
grep -rn "ejercicio_practica_actual = siguiente" --include=*.py . | grep -v "ejercicios/progreso.py"
```

Expected: sin resultados fuera de `ejercicios/progreso.py` (los management commands históricos quedan fuera de alcance; si aparecen, dejarlos).

- [ ] **Step 6: Commit**

```bash
git add README.md MEMORY.md ejercicios/models.py ejercicios/views.py
git commit -m "docs: registrar el desbloqueo configurable en README y MEMORY"
```

---

## Self-Review

**Cobertura del spec:**

| Sección del spec | Tarea |
|---|---|
| Campo `desbloqueo_secuencial` + migración | Task 1 |
| Módulo `ejercicios/progreso.py` (`eps_resueltos`, `esta_resuelto`, `avanzar_progreso`) | Task 2 |
| Predicado unificado desde `ejercicios/correctitud.py` | Task 2, step 3 |
| API: `avanzar_progreso` + `ejercicios_pendientes` | Task 3, step 3 |
| Aprobación docente usa el módulo compartido | Task 3, step 4 |
| `practica_detail`: nada bloqueado en modo libre | Task 4, step 3 |
| `ejercicio_detail`: sin redirects en modo libre | Task 4, step 4 |
| Cambio deliberado en `ya_resuelto` | Task 4, step 4 |
| Formulario docente | Task 5 |
| Ocultar `Ej. N` en prácticas libres | Task 6, steps 3-4 |
| Mensaje con ejercicios pendientes | Task 6, step 5 |
| Docstrings + cita vieja a AGENTS.md §7 | Task 7, step 1 |
| Caso borde: cambio de modo a mitad de cursada | Task 2 (el recálculo del modo libre lo cubre; test en Task 2 step 1) |
| Caso borde: práctica sin ejercicios | Task 6, step 3 (la rama `total_ejercicios == 0` recibe la clave nueva) |

**Consistencia de tipos:** `avanzar_progreso` devuelve `tuple[bool, int]` en Task 2 y se desempaqueta así en Tasks 3 step 3 y 3 step 4. `eps_resueltos` devuelve `set[int]` de ids de EP y se usa con `exclude(pk__in=...)` y `len()`. `esta_resuelto` devuelve `bool` y se usa en Task 4. La clave `desbloqueo_secuencial` aparece con ese nombre en el modelo, el form, el contexto de `ejercicio.html` y `practicas_detalle`.

**Riesgo señalado:** Task 3 borra `_avanzar_progreso` de la API. Si algún test lo llamaba directamente, hay que actualizarlo; el step 5 de esa tarea corre `docentes.tests` completo justamente para detectarlo.

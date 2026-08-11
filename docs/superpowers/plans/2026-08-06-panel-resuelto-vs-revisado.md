# Panel docente: "Resuelto" vs "Revisado" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar al panel docente una métrica de avance que no dependa de la corrección manual, para que las comisiones masivas dejen de ver 0%.

**Architecture:** Se centraliza en `ejercicios/correctitud.py` la definición de "correctitud efectiva" que hoy está duplicada en `analiticas/views.py` y `mcp_intentos.py`. Con ella se construye `_resueltos_por_estudiante_ep`, espejo del `_aprobados_por_estudiante_ep` existente. El panel pasa a mostrar dos columnas, **Resuelto** y **Revisado**, sin cambiar el cálculo ni el significado de ninguna métrica actual.

**Tech Stack:** Django 5, PostgreSQL en producción / SQLite en tests, templates Django con CSS inline, Alpine.js en el frontend.

## Global Constraints

- Python: `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe` (venv en el directorio **padre** del repo).
- Antes de correr tests: `$env:SECRET_KEY='x'` en la misma línea de PowerShell (el `.env` del directorio padre no se carga solo).
- **Test roto preexistente en master:** `docentes.tests.ComisionesListViewTests.test_admin_ve_todas_las_comisiones` falla desde antes de este trabajo. No intentar arreglarlo; verificar solamente que sigue siendo el único que falla.
- No cambiar qué miden `completada`, `porcentaje_global` ni `avance_promedio`: siguen siendo aprobación docente. Los tests existentes que los cubren deben pasar **sin modificarse**.
- No tocar los management commands históricos (`reconciliar_*`, `recorregir_*`, `reevaluar_*`, `corregir_*`).
- Textos de UI en español rioplatense, consistentes con el resto del panel.

---

### Task 1: Módulo compartido `ejercicios/correctitud.py`

Crea la definición única de correctitud efectiva y elimina las dos copias existentes. Sin cambio de comportamiento: las definiciones son literalmente idénticas.

**Files:**
- Create: `ejercicios/correctitud.py`
- Modify: `analiticas/views.py:33-42`
- Modify: `mcp_intentos.py:511-512` y `mcp_intentos.py:608`
- Test: `ejercicios/tests.py` (clase nueva al final del archivo)

**Interfaces:**
- Consumes: nada (primera tarea).
- Produces: `ejercicios.correctitud.Q_CORRECTO` y `ejercicios.correctitud.Q_INCORRECTO`, ambos objetos `django.db.models.Q` aplicables a un queryset de `ejercicios.models.Intento`.

- [ ] **Step 1: Write the failing test**

Agregar al final de `ejercicios/tests.py`:

```python
class CorrectitudEfectivaTests(TestCase):
    """El juicio docente tiene precedencia sobre el resultado del motor."""

    def setUp(self):
        self.estudiante = _u('alu-correctitud')
        docente = _u('doc-correctitud', es_docente=True)
        comision = Comision.objects.create(nombre='IPC Correctitud')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=comision)
        practica = Practica.objects.create(titulo='P', creada_por=docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='E', formula_solucion='p', tipo='formalizacion', creado_por=docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )

    def _intento(self, es_correcto, aprobado_docente):
        return Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            respuesta_raw='p',
            es_correcto=es_correcto,
            aprobado_docente=aprobado_docente,
        )

    def test_correcto_sin_revisar_cuenta_como_correcto(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=True, aprobado_docente=None)
        self.assertTrue(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_correcto_rechazado_por_docente_no_cuenta(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=True, aprobado_docente=False)
        self.assertFalse(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_incorrecto_aprobado_por_docente_cuenta_como_correcto(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=False, aprobado_docente=True)
        self.assertTrue(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_incorrecto_sin_revisar_no_cuenta(self):
        from ejercicios.correctitud import Q_CORRECTO
        intento = self._intento(es_correcto=False, aprobado_docente=None)
        self.assertFalse(Intento.objects.filter(Q_CORRECTO, pk=intento.pk).exists())

    def test_q_incorrecto_es_el_complemento(self):
        from ejercicios.correctitud import Q_CORRECTO, Q_INCORRECTO
        self._intento(es_correcto=True, aprobado_docente=None)
        self._intento(es_correcto=True, aprobado_docente=False)
        self._intento(es_correcto=False, aprobado_docente=True)
        self._intento(es_correcto=False, aprobado_docente=None)

        correctos = Intento.objects.filter(Q_CORRECTO).count()
        incorrectos = Intento.objects.filter(Q_INCORRECTO).count()

        self.assertEqual(correctos, 2)
        self.assertEqual(incorrectos, 2)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.CorrectitudEfectivaTests
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ejercicios.correctitud'`

- [ ] **Step 3: Create the module**

Crear `ejercicios/correctitud.py`:

```python
"""Definición única de la correctitud efectiva de un intento.

Un intento cuenta como correcto cuando el docente lo aprobó explícitamente, o
cuando el motor lo dio por correcto y el docente todavía no lo revisó. El juicio
docente tiene precedencia sobre el resultado del motor: un correcto rechazado
cuenta como incorrecto, y un incorrecto aprobado cuenta como correcto.

Este es el criterio que usan las analíticas, el servidor MCP y el panel docente.
No confundirlo con ``aprobado_docente=True`` a secas, que mide otra cosa: cuánto
revisó el docente a mano. En cursos masivos esa revisión no llega a todos los
intentos, así que no sirve como medida de avance.
"""

from django.db.models import Q

Q_CORRECTO = (
    Q(aprobado_docente=True)
    | Q(es_correcto=True, aprobado_docente__isnull=True)
)

Q_INCORRECTO = (
    Q(aprobado_docente=False)
    | Q(es_correcto=False, aprobado_docente__isnull=True)
)
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test ejercicios.tests.CorrectitudEfectivaTests
```

Expected: PASS — `Ran 5 tests` / `OK`

- [ ] **Step 5: Eliminar la copia en `analiticas/views.py`**

Reemplazar el bloque de `analiticas/views.py:33-42`:

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

por:

```python
# Correctitud efectiva: ver ejercicios/correctitud.py. Los alias con guión bajo
# se mantienen porque el resto del módulo ya los usa con ese nombre.
from ejercicios.correctitud import Q_CORRECTO as _Q_CORRECTO  # noqa: E402
from ejercicios.correctitud import Q_INCORRECTO as _Q_INCORRECTO  # noqa: E402
```

No cambiar ninguna otra línea del archivo: todos los usos siguen llamándose `_Q_CORRECTO` / `_Q_INCORRECTO`.

- [ ] **Step 6: Eliminar las copias en `mcp_intentos.py`**

En `mcp_intentos.py:511-512`, reemplazar:

```python
    _q_incorrecto = Q(aprobado_docente=False) | Q(es_correcto=False, aprobado_docente__isnull=True)
    _q_correcto = Q(aprobado_docente=True) | Q(es_correcto=True, aprobado_docente__isnull=True)
```

por:

```python
    from ejercicios.correctitud import Q_CORRECTO as _q_correcto
    from ejercicios.correctitud import Q_INCORRECTO as _q_incorrecto
```

En `mcp_intentos.py:608`, reemplazar:

```python
    _q_correcto = Q(aprobado_docente=True) | Q(es_correcto=True, aprobado_docente__isnull=True)
```

por:

```python
    from ejercicios.correctitud import Q_CORRECTO as _q_correcto
```

El import va dentro de la función, siguiendo el estilo del archivo (los imports de Django ya son locales, ver `mcp_intentos.py:500`).

Después de editar, verificar que `Q` siga usándose en esas funciones; si en alguna quedó sin uso, quitarlo del `from django.db.models import Count, Q` correspondiente.

- [ ] **Step 7: Verificar que la deduplicación no cambió nada**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas ejercicios.tests.CorrectitudEfectivaTests
```

Expected: PASS — la suite de analíticas pasa igual que antes del cambio.

- [ ] **Step 8: Commit**

```bash
git add ejercicios/correctitud.py ejercicios/tests.py analiticas/views.py mcp_intentos.py
git commit -m "refactor: centralizar la correctitud efectiva en ejercicios/correctitud.py"
```

---

### Task 2: `_resueltos_por_estudiante_ep`

Índice de pares (estudiante, ejercicio) resueltos, espejo del de aprobados.

**Files:**
- Modify: `docentes/views.py` (import nuevo + función nueva después de `_aprobados_por_estudiante_ep`, que termina en la línea 188)
- Test: `docentes/tests.py` (clase nueva)

**Interfaces:**
- Consumes: `ejercicios.correctitud.Q_CORRECTO` (Task 1).
- Produces: `docentes.views._resueltos_por_estudiante_ep(comision_ids, estudiantes_ids) -> set[tuple[int, int]]`, con los pares `(estudiante_id, ejercicio_practica_id)`. Mismo tipo de retorno que `_aprobados_por_estudiante_ep`.

- [ ] **Step 1: Write the failing test**

Agregar al final de `docentes/tests.py`:

```python
class ResueltosPorEstudianteEpTests(TestCase):
    """El índice de resueltos no depende de la corrección manual del docente."""

    def setUp(self):
        self.docente = _u('doc-resueltos', es_docente=True)
        self.comision = Comision.objects.create(nombre='IPC Resueltos')
        self.comision.docentes.add(self.docente)
        self.estudiante = _u('alu-resueltos')
        Inscripcion.objects.create(estudiante=self.estudiante, comision=self.comision)

        practica = Practica.objects.create(titulo='P', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='E', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )

    def _intento(self, es_correcto, aprobado_docente):
        Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ep,
            practica_comision=self.pc,
            respuesta_raw='p',
            es_correcto=es_correcto,
            aprobado_docente=aprobado_docente,
        )

    def _resueltos(self):
        from docentes.views import _resueltos_por_estudiante_ep
        return _resueltos_por_estudiante_ep([self.comision.id], [self.estudiante.id])

    def test_cuenta_correcto_sin_revisar(self):
        from docentes.views import _aprobados_por_estudiante_ep
        self._intento(es_correcto=True, aprobado_docente=None)

        self.assertIn((self.estudiante.id, self.ep.id), self._resueltos())
        # El índice de aprobados, en cambio, no lo cuenta: ése es el problema
        # que motiva este cambio.
        self.assertNotIn(
            (self.estudiante.id, self.ep.id),
            _aprobados_por_estudiante_ep([self.comision.id], [self.estudiante.id]),
        )

    def test_no_cuenta_correcto_rechazado(self):
        self._intento(es_correcto=True, aprobado_docente=False)
        self.assertNotIn((self.estudiante.id, self.ep.id), self._resueltos())

    def test_cuenta_incorrecto_aprobado(self):
        self._intento(es_correcto=False, aprobado_docente=True)
        self.assertIn((self.estudiante.id, self.ep.id), self._resueltos())

    def test_no_cuenta_incorrecto_sin_revisar(self):
        self._intento(es_correcto=False, aprobado_docente=None)
        self.assertNotIn((self.estudiante.id, self.ep.id), self._resueltos())

    def test_devuelve_vacio_sin_estudiantes_o_comisiones(self):
        from docentes.views import _resueltos_por_estudiante_ep
        self._intento(es_correcto=True, aprobado_docente=None)

        self.assertEqual(_resueltos_por_estudiante_ep([], [self.estudiante.id]), set())
        self.assertEqual(_resueltos_por_estudiante_ep([self.comision.id], []), set())
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ResueltosPorEstudianteEpTests
```

Expected: FAIL — `ImportError: cannot import name '_resueltos_por_estudiante_ep' from 'docentes.views'`

- [ ] **Step 3: Implementar la función**

Agregar el import cerca del resto de imports de `ejercicios` en `docentes/views.py`:

```python
from ejercicios.correctitud import Q_CORRECTO
```

Agregar la función inmediatamente después de `_aprobados_por_estudiante_ep` (que termina en la línea 188):

```python
def _resueltos_por_estudiante_ep(comision_ids, estudiantes_ids):
    """Devuelve el conjunto de pares (estudiante_id, ejercicio_practica_id) resueltos.

    Un par se considera resuelto si existe al menos un Intento con correctitud
    efectiva (ver :mod:`ejercicios.correctitud`): aprobado por el docente, o
    correcto según el motor y todavía sin revisar.

    A diferencia de :func:`_aprobados_por_estudiante_ep`, no depende de que el
    docente haya corregido a mano, así que sigue siendo informativa en comisiones
    masivas donde revisar todos los intentos no es viable.

    Args:
        comision_ids: IDs de comisiones a considerar.
        estudiantes_ids: IDs de estudiantes a considerar.

    Returns:
        set[tuple[int, int]]: conjunto de (estudiante_id, ejercicio_practica_id).
    """
    if not comision_ids or not estudiantes_ids:
        return set()
    rows = (
        Intento.objects
        .filter(
            Q_CORRECTO,
            estudiante_id__in=estudiantes_ids,
            practica_comision__comision_id__in=comision_ids,
        )
        .values('estudiante_id', 'ejercicio_practica_id')
        .distinct()
    )
    return {(r['estudiante_id'], r['ejercicio_practica_id']) for r in rows}
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ResueltosPorEstudianteEpTests
```

Expected: PASS — `Ran 5 tests` / `OK`

- [ ] **Step 5: Commit**

```bash
git add docentes/views.py docentes/tests.py
git commit -m "feat(docentes): índice de ejercicios resueltos por correctitud efectiva"
```

---

### Task 3: Columna "Resuelto" en el detalle de comisión

Expone el avance resuelto por estudiante y por práctica, y lo muestra junto a "Revisado".

**Files:**
- Modify: `docentes/views.py:238-330` (`_build_progreso_estudiantes`)
- Modify: `docentes/views.py:508-509`, `docentes/views.py:659+665`, `docentes/views.py:696+702` (los tres call sites)
- Modify: `templates/docentes/comision_detail.html:356-397`
- Test: `docentes/tests.py` (`ComisionDetailProgressViewTests`)

**Interfaces:**
- Consumes: `_resueltos_por_estudiante_ep` (Task 2).
- Produces: `_build_progreso_estudiantes(comision, aprobados, resueltos)` — tercer parámetro **posicional obligatorio**. Cada fila suma la clave `porcentaje_resuelto` (`float | None`); cada dict de `practicas_detalle` suma `resueltos_count` (`int`) y `total_ejercicios` (`int`).

- [ ] **Step 1: Write the failing test**

Agregar a la clase `ComisionDetailProgressViewTests` en `docentes/tests.py`:

```python
    def test_muestra_resuelto_aunque_el_docente_no_haya_revisado(self):
        """El caso de la comisión masiva: nadie corrige a mano y el panel igual informa."""
        Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ejercicio_practica_1,
            practica_comision=self.pc,
            respuesta_raw='p',
            es_correcto=True,
            aprobado_docente=None,
        )

        self.client.login(username='doc-prog', password='clave123')
        response = self.client.get(reverse('docentes:comision_detail', args=[self.comision.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resuelto')
        self.assertContains(response, 'Revisado')
        self.assertContains(response, '1/2')  # resueltos_count/total_ejercicios

        # Los porcentajes se verifican en el contexto y no en el HTML: '0,0%' es
        # substring de '50,0%', así que un assertContains pasaría por accidente.
        fila = response.context['progreso_estudiantes'][0]
        self.assertEqual(fila['porcentaje_resuelto'], 50.0)
        self.assertEqual(fila['porcentaje_global'], 0.0)

    def test_resuelto_ignora_intentos_rechazados_por_el_docente(self):
        Intento.objects.create(
            estudiante=self.estudiante,
            ejercicio_practica=self.ejercicio_practica_1,
            practica_comision=self.pc,
            respuesta_raw='p',
            es_correcto=True,
            aprobado_docente=False,
        )

        self.client.login(username='doc-prog', password='clave123')
        response = self.client.get(reverse('docentes:comision_detail', args=[self.comision.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0/2')
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ComisionDetailProgressViewTests
```

Expected: FAIL — `Couldn't find 'Resuelto' in the following response`

- [ ] **Step 3: Actualizar `_build_progreso_estudiantes`**

Reemplazar la firma y el docstring (`docentes/views.py:238-253`):

```python
def _build_progreso_estudiantes(comision, aprobados, resueltos):
    """Construye el resumen de progreso por estudiante para una comisión.

    Calcula dos métricas por par (estudiante, práctica), sobre el mismo total de
    ejercicios:

    - **revisado**: ``aprobados_docente / total_ejercicios``. Cuánto miró el
      docente. Alimenta ``porcentaje_global``, ``completada`` y
      ``practicas_completadas``.
    - **resuelto**: ``resueltos / total_ejercicios``, con correctitud efectiva
      (ver :mod:`ejercicios.correctitud`). Cuánto le salió al estudiante. No
      depende de la corrección manual, así que sigue siendo informativa en
      comisiones masivas.

    Args:
        comision: Comisión con inscripciones, prácticas y progresos prefetchados.
        aprobados: set de (estudiante_id, ejercicio_practica_id) aprobados,
            generado por ``_aprobados_por_estudiante_ep``.
        resueltos: set de (estudiante_id, ejercicio_practica_id) resueltos,
            generado por ``_resueltos_por_estudiante_ep``.

    Returns:
        list[dict]: lista con métricas por estudiante para render de tabla.
    """
```

Dentro del bucle por estudiante, agregar el acumulador de resueltos junto a los existentes (`docentes/views.py:268-271`):

```python
        practicas_detalle = []
        practicas_completadas = 0
        total_ratio = 0
        total_ratio_resuelto = 0
        total_practicas_computables = 0
```

En la rama de práctica sin ejercicios (`docentes/views.py:278-284`), agregar las claves nuevas para que el template nunca reciba un dict incompleto:

```python
            if total_ejercicios == 0:
                practicas_detalle.append({
                    'practica': practica,
                    'ejercicio_actual': None,
                    'completada': False,
                    'resueltos_count': 0,
                    'total_ejercicios': 0,
                })
                continue
```

Después del bloque de aprobados (`docentes/views.py:294-311`), calcular resueltos y sumar las claves nuevas:

```python
            # Avance basado en aprobados por docente
            aprobados_count = sum(
                1 for ep in ejercicio_practicas
                if (estudiante.id, ep.id) in aprobados
            )
            completada = aprobados_count == total_ejercicios

            # Avance basado en correctitud efectiva (no requiere corrección manual)
            resueltos_count = sum(
                1 for ep in ejercicio_practicas
                if (estudiante.id, ep.id) in resueltos
            )

            if completada:
                practicas_completadas += 1

            total_ratio += aprobados_count / total_ejercicios
            total_ratio_resuelto += resueltos_count / total_ejercicios
            total_practicas_computables += 1

            practicas_detalle.append({
                'practica': practica,
                'ejercicio_actual': ejercicio_actual,
                'completada': completada,
                'resueltos_count': resueltos_count,
                'total_ejercicios': total_ejercicios,
            })
```

Y en el armado de la fila (`docentes/views.py:313-323`):

```python
        porcentaje_global = None
        porcentaje_resuelto = None
        if total_practicas_computables > 0:
            porcentaje_global = round((total_ratio / total_practicas_computables) * 100, 1)
            porcentaje_resuelto = round((total_ratio_resuelto / total_practicas_computables) * 100, 1)

        filas.append({
            'estudiante': estudiante,
            'practicas_completadas': practicas_completadas,
            'practicas_totales': len(practicas_por_id),
            'practicas_detalle': practicas_detalle,
            'porcentaje_global': porcentaje_global,
            'porcentaje_resuelto': porcentaje_resuelto,
        })
```

- [ ] **Step 4: Actualizar los tres call sites**

En `comision_detail` (`docentes/views.py:508-509`):

```python
    aprobados = _aprobados_por_estudiante_ep([comision.id], estudiantes_ids)
    resueltos = _resueltos_por_estudiante_ep([comision.id], estudiantes_ids)
    progreso_estudiantes = _build_progreso_estudiantes(comision, aprobados, resueltos)
```

En `estudiante_create` (`docentes/views.py:659` y `665`):

```python
    _aprobados = _aprobados_por_estudiante_ep([comision.id], _estudiantes_ids)
    _resueltos = _resueltos_por_estudiante_ep([comision.id], _estudiantes_ids)
```

y en el `render`:

```python
        'progreso_estudiantes': _build_progreso_estudiantes(comision, _aprobados, _resueltos),
```

En `estudiantes_importar` (`docentes/views.py:696` y `702`): exactamente los mismos dos cambios que en `estudiante_create`.

- [ ] **Step 5: Actualizar el template**

En `templates/docentes/comision_detail.html`, la cabecera (línea 356):

```html
      <div class="stat-row stat-header" style="grid-template-columns: 1.5fr 1fr 1fr 1fr 1fr;">
        <span>Estudiante</span>
        <span class="stat-num">Prácticas</span>
        <span class="stat-num">Resuelto</span>
        <span class="stat-num">Revisado</span>
        <span class="stat-num">Detalle</span>
      </div>
```

El `summary` de cada fila (línea 364 en adelante):

```html
          <summary style="display:grid; grid-template-columns: 1.5fr 1fr 1fr 1fr 1fr; gap:1rem; align-items:center; padding:0.65rem 0; font-size:0.92rem; cursor:pointer; list-style:none;">
            <span style="font-weight:500; display:flex; align-items:center; gap:0.4rem;">
              <span class="progreso-chevron" style="font-size:0.7rem; opacity:0.5; transition:transform 0.15s;">▶</span>
              {{ fila.estudiante.nombre_display }}
            </span>
            <span class="stat-num">{{ fila.practicas_completadas }}/{{ fila.practicas_totales }}</span>
            <span class="stat-num">
              {% if fila.porcentaje_resuelto is not None %}
                {{ fila.porcentaje_resuelto }}%
              {% else %}
                —
              {% endif %}
            </span>
            <span class="stat-num">
              {% if fila.porcentaje_global is not None %}
                {{ fila.porcentaje_global }}%
              {% else %}
                —
              {% endif %}
            </span>
            <span class="stat-num">
              <a href="{% url 'docentes:estudiante_detail' fila.estudiante.id %}"
                 style="font-size:0.85rem;"
                 onclick="event.stopPropagation()">Ver intentos</a>
            </span>
          </summary>
```

La fila de detalle por práctica (línea 385 en adelante):

```html
            <div style="display:grid; grid-template-columns: 1.5fr 1fr 1fr 1fr 1fr; gap:1rem; padding:0.2rem 0 0.2rem 1.5rem; font-size:0.82rem; color:#666; border-top:1px solid #f8f8f8;">
              <span style="color:#888;">{{ detalle.practica.titulo }}</span>
              <span></span>
              <span class="stat-num">{{ detalle.resueltos_count }}/{{ detalle.total_ejercicios }}</span>
              <span></span>
              <span style="text-align:right;">
                {% if detalle.completada %}
                  <span class="badge badge-ok">completa</span>
                {% elif detalle.ejercicio_actual %}
                  Ej. {{ detalle.ejercicio_actual.orden }}
                {% else %}
                  <span class="badge badge-bloqueado">sin ejercicios</span>
                {% endif %}
              </span>
            </div>
```

Los tres grids deben quedar idénticos (`1.5fr 1fr 1fr 1fr 1fr`) o las columnas no se alinean. No hace falta tocar mobile: `base.html:331` colapsa `.stat-row` a una columna y `base.html:334` oculta `.stat-header`.

- [ ] **Step 6: Run tests to verify they pass**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ComisionDetailProgressViewTests
```

Expected: PASS — incluido `test_muestra_metricas_de_progreso_por_estudiante`, que **no se modificó**: `0/1`, `Ej. 1` y `50,0%` siguen presentes.

- [ ] **Step 7: Commit**

```bash
git add docentes/views.py docentes/tests.py templates/docentes/comision_detail.html
git commit -m "feat(docentes): columna Resuelto junto a Revisado en el detalle de comisión"
```

---

### Task 4: Avance resuelto en la lista de comisiones

Misma distinción en la vista operativa que lista todas las comisiones.

**Files:**
- Modify: `docentes/views.py:191-235` (`_calcular_avance_promedio`)
- Modify: `docentes/views.py:348-363` (vista `comisiones_list`)
- Modify: `templates/docentes/comisiones_list.html:25-50` y el bloque `<style>` (línea 262 en adelante)
- Test: `docentes/tests.py` (`ComisionesListViewTests`)

**Interfaces:**
- Consumes: `_resueltos_por_estudiante_ep` (Task 2).
- Produces: `_calcular_avance_promedio(comision, estudiantes_ids, pares)` — el tercer parámetro pasa a llamarse `pares` y acepta cualquiera de los dos índices. Cada dict de `comisiones_data` suma la clave `avance_resuelto` (`float | None`).

- [ ] **Step 1: Write the failing test**

Agregar a la clase `ComisionesListViewTests` en `docentes/tests.py`:

```python
    def test_muestra_avance_resuelto_sin_correccion_manual(self):
        estudiante = _u('est-sin-revisar')
        Inscripcion.objects.create(estudiante=estudiante, comision=self.comision_docente)

        practica = Practica.objects.create(titulo='Práctica 1', creada_por=self.docente)
        pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision_docente, orden=1,
        )
        ejercicio_1 = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p', tipo='formalizacion', creado_por=self.docente,
        )
        ejercicio_2 = Ejercicio.objects.create(
            enunciado='E2', formula_solucion='q', tipo='formalizacion', creado_por=self.docente,
        )
        ep1 = EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio_1, orden=1)
        EjercicioPractica.objects.create(practica=practica, ejercicio=ejercicio_2, orden=2)

        # Correcto pero sin revisar: cuenta como resuelto, no como revisado.
        Intento.objects.create(
            estudiante=estudiante, ejercicio_practica=ep1, practica_comision=pc,
            respuesta_raw='p', es_correcto=True, aprobado_docente=None,
        )

        self.client.login(username='docente-list', password='clave123')
        response = self.client.get(reverse('docentes:comisiones_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resuelto')
        self.assertContains(response, 'Revisado')

        # Igual que en el detalle: los porcentajes se verifican en el contexto
        # porque '0,0%' es substring de '50,0%'.
        item = next(
            i for i in response.context['comisiones_data']
            if i['comision'].id == self.comision_docente.id
        )
        self.assertEqual(item['avance_resuelto'], 50.0)
        self.assertEqual(item['avance_promedio'], 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ComisionesListViewTests.test_muestra_avance_resuelto_sin_correccion_manual
```

Expected: FAIL — `Couldn't find 'Resuelto' in the following response`

- [ ] **Step 3: Parametrizar `_calcular_avance_promedio`**

Reemplazar la firma y el docstring (`docentes/views.py:191-211`):

```python
def _calcular_avance_promedio(comision, estudiantes_ids, pares):
    """Calcula el avance promedio de una comisión para la vista operativa docente.

    La métrica se define como el promedio de avance por par
    ``(estudiante, práctica)`` donde:

    ``avance = ejercicios_contados / total_ejercicios_practica``.

    Qué se cuenta depende del índice que se pase en ``pares``: con
    ``_aprobados_por_estudiante_ep`` la métrica es "revisado" (cuánto corrigió el
    docente a mano) y con ``_resueltos_por_estudiante_ep`` es "resuelto" (cuánto
    le salió al estudiante, sin depender de la corrección manual).

    Args:
        comision: instancia de ``Comision`` con prefetched de prácticas.
        estudiantes_ids: IDs de estudiantes de la comisión.
        pares: set de (estudiante_id, ejercicio_practica_id) que cuentan como
            avance.

    Returns:
        float | None: porcentaje promedio [0, 100], o ``None`` si no hay
        suficientes datos para computar (sin estudiantes o sin ejercicios).
    """
```

Y en el cuerpo (`docentes/views.py:225-230`), renombrar la variable local:

```python
        for estudiante_id in estudiantes_ids:
            pares_count = sum(
                1 for ep_id in eps if (estudiante_id, ep_id) in pares
            )
            total_ratio += pares_count / total_ejercicios
            total_pares += 1
```

- [ ] **Step 4: Calcular las dos métricas en la vista**

En `comisiones_list` (`docentes/views.py:348-363`):

```python
    # Precalcular aprobados y resueltos para todas las comisiones de una vez
    todos_los_estudiantes_ids = list(
        {est.id for c in comisiones for est in c.estudiantes.all()}
    )
    todas_las_comisiones_ids = [c.id for c in comisiones]
    aprobados = _aprobados_por_estudiante_ep(todas_las_comisiones_ids, todos_los_estudiantes_ids)
    resueltos = _resueltos_por_estudiante_ep(todas_las_comisiones_ids, todos_los_estudiantes_ids)
```

y en el dict de cada comisión:

```python
            'avance_promedio': _calcular_avance_promedio(comision, estudiantes_ids, aprobados),
            'avance_resuelto': _calcular_avance_promedio(comision, estudiantes_ids, resueltos),
```

- [ ] **Step 5: Actualizar el template**

En `templates/docentes/comisiones_list.html`, la cabecera (línea 25):

```html
      <div class="stat-row stat-header comisiones-row">
        <span>Comisión</span>
        <span class="stat-num hide-mobile">Estudiantes</span>
        <span class="stat-num hide-mobile">Prácticas</span>
        <span class="stat-num hide-mobile">Resuelto</span>
        <span class="stat-num hide-mobile">Revisado</span>
        <span class="stat-num"></span>
      </div>
```

La fila de datos (línea 33 en adelante), agregando la celda nueva y el resumen mobile:

```html
            <span class="show-mobile" style="display:none; font-size:0.82rem; color:#555;">
              {{ item.cantidad_estudiantes }} est. · {{ item.cantidad_practicas }} prác.
              {% if item.avance_resuelto is not None %} · {{ item.avance_resuelto }}% resuelto{% endif %}
              {% if item.avance_promedio is not None %} · {{ item.avance_promedio }}% revisado{% endif %}
            </span>
          </span>
          <span class="stat-num hide-mobile">{{ item.cantidad_estudiantes }}</span>
          <span class="stat-num hide-mobile">{{ item.cantidad_practicas }}</span>
          <span class="stat-num hide-mobile">
            {% if item.avance_resuelto is not None %}
              {{ item.avance_resuelto }}%
            {% else %}
              —
            {% endif %}
          </span>
          <span class="stat-num hide-mobile">
            {% if item.avance_promedio is not None %}
              {{ item.avance_promedio }}%
            {% else %}
              —
            {% endif %}
          </span>
```

`.comisiones-row` no define su propio grid: hereda las 5 columnas de `.stat-row` (`base.html:257`, `2fr 1fr 1fr 1fr 7rem`). Con la columna nueva son 6, así que hay que declararlo. Agregar en el bloque `<style>` de `comisiones_list.html`, **antes** del `@media (max-width: 640px)` que empieza en la línea 276:

```css
  .comisiones-row {
    grid-template-columns: 2fr 1fr 1fr 1fr 1fr 7rem;
  }
```

La regla mobile existente (`grid-template-columns: 1fr auto !important`) sigue ganando en pantallas chicas; no se toca.

También actualizar el texto introductorio de la línea 18:

```html
    <p style="margin-top:0;">Vista operativa: <strong>resuelto</strong> es lo que verificó el sistema; <strong>revisado</strong>, lo que corregiste a mano.</p>
```

- [ ] **Step 6: Run tests to verify they pass**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test docentes.tests.ComisionesListViewTests
```

Expected: PASS en todos menos `test_admin_ve_todas_las_comisiones`, que ya fallaba antes de este trabajo (ver Global Constraints). `test_muestra_metricas_operativas_y_avance_promedio` debe pasar **sin modificarse**: el `75,0%` sigue siendo el avance revisado.

- [ ] **Step 7: Commit**

```bash
git add docentes/views.py docentes/tests.py templates/docentes/comisiones_list.html
git commit -m "feat(docentes): avance resuelto junto al revisado en la lista de comisiones"
```

---

### Task 5: Verificación final

**Files:**
- Modify: ninguno salvo que aparezca una regresión.

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: evidencia de que la suite queda como estaba salvo por lo agregado.

- [ ] **Step 1: Correr la suite completa**

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test
```

Expected: el único fallo es `docentes.tests.ComisionesListViewTests.test_admin_ve_todas_las_comisiones`. Si falla cualquier otro, es una regresión de este trabajo: arreglarla antes de seguir.

- [ ] **Step 2: Verificar que no quedaron copias del predicado**

```bash
grep -rn "aprobado_docente=True) | Q(es_correcto=True" --include=*.py .
```

Expected: sin resultados fuera de `ejercicios/correctitud.py`. Los management commands usan la variante `Q(es_correcto=True) | Q(aprobado_docente=True)` y quedan fuera de alcance a propósito.

- [ ] **Step 3: Revisión visual del panel**

Levantar el servidor y mirar las dos vistas con una comisión que tenga intentos correctos sin revisar:

```powershell
$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py runserver
```

Comprobar en `/docentes/comisiones/` y en el detalle de una comisión: las columnas alineadas, "Resuelto" mayor o igual que "Revisado" en el caso típico, y el layout mobile (ventana angosta) sin desbordes.

- [ ] **Step 4: Commit final si hubo ajustes**

```bash
git add -A
git commit -m "fix(docentes): ajustes de la revisión visual del panel"
```

---

## Self-Review

**Cobertura del spec:**

| Sección del spec | Tarea |
|---|---|
| Módulo compartido `ejercicios/correctitud.py` | Task 1 |
| Dedupe en `analiticas/views.py` y `mcp_intentos.py` | Task 1, steps 5-6 |
| `_resueltos_por_estudiante_ep` | Task 2 |
| `porcentaje_resuelto` + `resueltos_count`/`total_ejercicios` | Task 3, step 3 |
| Los tres call sites de `_build_progreso_estudiantes` | Task 3, step 4 |
| `_calcular_avance_promedio` parametrizado + `avance_resuelto` | Task 4, steps 3-4 |
| Reparto de columnas de `comision_detail.html` | Task 3, step 5 |
| Columnas de `comisiones_list.html` | Task 4, step 5 |
| Tests de los cuatro casos del predicado | Task 1, step 1 y Task 2, step 1 |
| Test de la comisión masiva sin corrección manual | Task 3, step 1 y Task 4, step 1 |
| Tests existentes sin modificar | Task 3 step 6, Task 4 step 6, Task 5 step 1 |
| Caso borde: práctica sin ejercicios | Task 3, step 3 (rama `total_ejercicios == 0`) |
| Caso borde: resuelto < revisado por rechazo docente | Task 3, step 1 (`test_resuelto_ignora_intentos_rechazados_por_el_docente`) |

**Consistencia de tipos:** `_resueltos_por_estudiante_ep` devuelve `set[tuple[int, int]]`, igual que `_aprobados_por_estudiante_ep`, y se consume de la misma forma (`(estudiante_id, ep_id) in ...`) en Tasks 3 y 4. `_build_progreso_estudiantes` recibe `resueltos` como tercer posicional en los tres call sites. `_calcular_avance_promedio` mantiene aridad 3 y sólo renombra el tercer parámetro, así que las llamadas existentes por posición siguen siendo válidas.

**Nombres de claves de template:** `porcentaje_resuelto`, `resueltos_count`, `total_ejercicios`, `avance_resuelto` — usados con el mismo nombre en views y templates de las Tasks 3 y 4.

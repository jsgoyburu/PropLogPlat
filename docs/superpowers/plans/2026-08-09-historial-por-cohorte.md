# Historial por cohorte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El historial de intentos se agrupa por cohorte, de modo que un recursante vea sus camadas separadas en vez de colapsadas en un solo grupo.

**Architecture:** Primero se unifica en `ejercicios/historial.py` la lógica de agrupación, hoy duplicada entre `ejercicios/views.py::mi_historial` y `docentes/views.py::_build_estudiante_intentos_context`. Recién sobre esa única copia se cambia la clave de agrupación de `ep_id` a `(cohorte_id, ep_id)` y el contexto pasa a ser una lista de secciones por cohorte. Dos tasks, un commit cada una.

**Tech Stack:** Django 5, SQLite en tests, Alpine.js en el template.

## Global Constraints

- Worktree: `C:\Users\Angeles\Documents\IPC-Logica\IPC-Logica\.claude\worktrees\historial-por-cohorte`, rama `claude/historial-por-cohorte`.
- Python: `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe` (venv en el directorio PADRE del repo).
- Los tests necesitan `SECRET_KEY` en el entorno: el `.env` del directorio padre no se carga solo.
- Comando de test, desde el worktree:
  `$env:SECRET_KEY='x'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test <ruta> -v 2`
- `Intento.cohorte` es NOT NULL desde `ejercicios/migrations/0028_cohorte_not_null.py`: no hay que contemplar intentos sin cohorte.
- `Cohorte.__str__` devuelve `f'{anio} – C{cuatrimestre}'` (guion largo). El template no formatea la cohorte a mano.
- Mensajes de commit sin tildes ni ñ, como el resto del historial del repo.

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `ejercicios/historial.py` (nuevo) | Única implementación del armado del historial: filtros, query, enriquecido y agrupación. Sin dependencias de vistas. |
| `ejercicios/views.py` | `mi_historial` queda reducido a resolver comisiones del estudiante, delegar y renderizar. |
| `docentes/views.py` | Se borra `_build_estudiante_intentos_context`; `estudiante_detail` importa el helper de `ejercicios.historial`. |
| `templates/docentes/estudiante_detail.html` | Loop externo por cohorte con encabezado de sección. |
| `ejercicios/tests.py` | Tests del helper y de `mi_historial`. |
| `docentes/tests.py` | Tests de `estudiante_detail` contra el mismo helper. |

---

### Task 1: Unificar la agrupación en `ejercicios/historial.py`

Movimiento puro, sin cambio de comportamiento — salvo un bug que se cae solo: `mi_historial` no calculaba `diccionario_con_valores`, así que el estudiante veía sus propios intentos de `determinacion_verdad` peor renderizados que el docente. Ese es el test en rojo de esta task.

**Files:**
- Create: `ejercicios/historial.py`
- Modify: `ejercicios/views.py:394-483` (cuerpo de `mi_historial`)
- Modify: `docentes/views.py:1050-1153` (borrar `_build_estudiante_intentos_context`), `docentes/views.py:1179-1187` (import y llamada en `estudiante_detail`)
- Test: `ejercicios/tests.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `ejercicios.historial.build_historial_context(estudiante, comisiones, comision_id=None, pc_id=None) -> dict`. El dict tiene las claves `filtro_comision_id` (int o `''`), `filtro_pc_id` (int o `''`), `comisiones_disponibles` (list[Comision]), `practicas_disponibles` (list[PracticaComision]) e `intentos_agrupados` (list[dict] con claves `ejercicio_practica`, `comision`, `ultimo_intento`, `intentos_anteriores`, `total_intentos`). La Task 2 reemplaza `intentos_agrupados` por `historial_por_cohorte`.

- [ ] **Step 1: Escribir el test que falla**

En `ejercicios/tests.py`, al final del archivo:

```python
class HistorialUnificadoTests(TestCase):
    """El historial propio del estudiante y el del docente salen del mismo
    helper, asi que el estudiante ve su intento de determinacion_verdad con
    el mismo enriquecido que ve el docente (diccionario_con_valores)."""

    def setUp(self):
        self.docente = _u('doc-hist-unif', es_docente=True)
        self.estudiante = _u('est-hist-unif')
        self.cohorte = Cohorte.objects.get(anio=2026, cuatrimestre=1)
        self.comision = Comision.objects.create(nombre='IPC Unif')
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte,
        )

        practica = Practica.objects.create(titulo='P-unif', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='Determinar', formula_solucion='p', tipo='determinacion_verdad',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte,
            respuesta_raw='p', es_correcto=True,
            diccionario={'p': 'llueve'}, valores_verdad={'p': True},
        )
        self.client.login(username='est-hist-unif', password='clave123')

    def test_vista_propia_enriquece_determinacion_verdad(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        self.assertEqual(resp.status_code, 200)
        grupo = resp.context['intentos_agrupados'][0]
        self.assertEqual(
            grupo['ultimo_intento'].diccionario_con_valores,
            [{'letra': 'p', 'frase': 'llueve', 'valor': True}],
        )
```

- [ ] **Step 2: Correr el test y verificar que falla**

```bash
cd .claude/worktrees/historial-por-cohorte && SECRET_KEY=x python manage.py test ejercicios.tests.HistorialUnificadoTests -v 2
```

Esperado: FAIL con `AttributeError: 'Intento' object has no attribute 'diccionario_con_valores'` — `mi_historial` no lo setea.

- [ ] **Step 3: Crear `ejercicios/historial.py`**

```python
"""Armado del historial de intentos de un estudiante.

Vive en ``ejercicios`` porque los datos son ``Intento``; ``docentes`` lo
importa para su panel. Mismo criterio que ``cursos/cohortes.py``: un modulo
sin dependencias de vistas, importable desde las dos apps sin ciclo.
"""

import json

from ejercicios.models import Intento, PracticaComision


def _enriquecer_intento(intento):
    """Agrega atributos parseados al intento para la presentacion en template."""
    tipo = intento.ejercicio_practica.ejercicio.tipo

    if tipo == 'tabla_verdad':
        try:
            intento.enunciados_parsed = json.loads(intento.respuesta_raw)
        except (ValueError, TypeError):
            intento.enunciados_parsed = None
    else:
        intento.enunciados_parsed = None

    # Para determinacion_verdad: combinar diccionario + valores_verdad en una
    # lista legible.
    if tipo == 'determinacion_verdad':
        dic = intento.diccionario or {}
        vv = intento.valores_verdad or {}
        intento.diccionario_con_valores = [
            {
                'letra': letra,
                'frase': frase,
                'valor': vv.get(letra),  # True / False / None
            }
            for letra, frase in dic.items()
        ]
    else:
        intento.diccionario_con_valores = None

    # tabla_json ya es un JSONField nativo (list o None): no necesita parseo.
    return intento


def build_historial_context(estudiante, comisiones, comision_id=None, pc_id=None):
    """Contexto del historial de ``estudiante``, agrupado por ejercicio.

    Args:
        estudiante: usuario del que se muestran los intentos.
        comisiones: queryset/lista de comisiones disponibles para filtrar.
        comision_id: id de comision seleccionada (opcional).
        pc_id: id de PracticaComision seleccionada (opcional).

    Returns:
        dict: filtros activos, opciones y lista de grupos de intentos.
    """
    comisiones = list(comisiones)
    comisiones_por_id = {comision.id: comision for comision in comisiones}
    comision_seleccionada = comisiones_por_id.get(comision_id)

    pcs_queryset = (
        PracticaComision.objects
        .filter(comision__in=comisiones)
        .select_related('practica', 'comision')
        .order_by('comision__nombre', 'orden')
    )
    if comision_seleccionada is not None:
        pcs_queryset = pcs_queryset.filter(comision=comision_seleccionada)
    pcs = list(pcs_queryset)
    pcs_por_id = {pc.id: pc for pc in pcs}
    pc_seleccionado = pcs_por_id.get(pc_id)

    intentos_queryset = (
        Intento.objects.filter(
            estudiante=estudiante,
            practica_comision__comision__in=comisiones,
        )
        .select_related(
            'ejercicio_practica__practica',
            'ejercicio_practica__ejercicio',
            'practica_comision__comision',
        )
        .order_by(
            'practica_comision__comision__nombre',
            'practica_comision__orden',
            'ejercicio_practica__orden',
            '-timestamp',
        )
    )
    if comision_seleccionada is not None:
        intentos_queryset = intentos_queryset.filter(
            practica_comision__comision=comision_seleccionada,
        )
    if pc_seleccionado is not None:
        intentos_queryset = intentos_queryset.filter(practica_comision=pc_seleccionado)

    grupos = []
    grupos_por_ep = {}
    for intento in intentos_queryset:
        _enriquecer_intento(intento)
        ep_id = intento.ejercicio_practica_id
        if ep_id not in grupos_por_ep:
            grupo = {
                'ejercicio_practica': intento.ejercicio_practica,
                'comision': intento.practica_comision.comision if intento.practica_comision else None,
                'ultimo_intento': intento,
                'intentos_anteriores': [],
                'total_intentos': 1,
            }
            grupos_por_ep[ep_id] = grupo
            grupos.append(grupo)
        else:
            grupos_por_ep[ep_id]['intentos_anteriores'].append(intento)
            grupos_por_ep[ep_id]['total_intentos'] += 1

    return {
        'filtro_comision_id': comision_seleccionada.id if comision_seleccionada else '',
        'filtro_pc_id': pc_seleccionado.id if pc_seleccionado else '',
        'comisiones_disponibles': comisiones,
        'practicas_disponibles': pcs,
        'intentos_agrupados': grupos,
    }
```

Nota: el `select_related` incluye `ejercicio_practica__practica`, que la versión de `docentes` no tenía. El template usa `grupo.ejercicio_practica.practica.titulo`, así que sin eso el panel docente hacía una query por grupo.

- [ ] **Step 4: Reemplazar el cuerpo de `mi_historial`**

En `ejercicios/views.py`, reemplazar las líneas 394-483 completas por:

```python
@login_required
def mi_historial(request):
    """Muestra al estudiante autenticado su historial de intentos por ejercicio."""
    usuario = request.user
    if usuario.is_staff or usuario.es_docente:
        return redirect('docentes:comisiones_list')

    comisiones = (
        Comision.objects.filter(estudiantes=usuario)
        .order_by('nombre')
        .distinct()
    )

    comision_id = request.GET.get('comision')
    pc_id = request.GET.get('pc')
    context = build_historial_context(
        estudiante=usuario,
        comisiones=comisiones,
        comision_id=int(comision_id) if comision_id and comision_id.isdigit() else None,
        pc_id=int(pc_id) if pc_id and pc_id.isdigit() else None,
    )

    return render(request, 'docentes/estudiante_detail.html', {
        'estudiante': usuario,
        'vista_propia_estudiante': True,
        **context,
    })
```

Y agregar el import arriba, junto a los otros imports del módulo:

```python
from ejercicios.historial import build_historial_context
```

- [ ] **Step 5: Borrar el helper duplicado de `docentes/views.py`**

Borrar `_build_estudiante_intentos_context` completa (líneas 1050-1153, incluida su `_enriquecer_intento` anidada). Agregar el import junto a los otros imports del módulo:

```python
from ejercicios.historial import build_historial_context
```

`Intento` y `PracticaComision` siguen usándose en otras vistas del módulo (`docentes/views.py:240`, `:82`), así que el import de la línea 27 queda como está.

En `estudiante_detail`, cambiar la llamada:

```python
    context = build_historial_context(
        estudiante=estudiante,
        comisiones=comisiones,
        comision_id=int(comision_id) if comision_id and comision_id.isdigit() else None,
        pc_id=int(pc_id) if pc_id and pc_id.isdigit() else None,
    )
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

```bash
cd .claude/worktrees/historial-por-cohorte && SECRET_KEY=x python manage.py test ejercicios docentes -v 1
```

Esperado: OK. Si algún test de `docentes` referenciaba `_build_estudiante_intentos_context` por nombre, actualizar el import en el test — el comportamiento no cambió.

- [ ] **Step 7: Commit**

```bash
git add ejercicios/historial.py ejercicios/views.py docentes/views.py ejercicios/tests.py
git commit -m "refactor(historial): unificar el armado del historial en ejercicios/historial.py"
```

---

### Task 2: Agrupar por `(cohorte, ejercicio_practica)` y anidar el contexto

**Files:**
- Modify: `ejercicios/historial.py` (query, clave de agrupación y forma del return)
- Modify: `templates/docentes/estudiante_detail.html:85-86` y `:391` (loop externo)
- Test: `ejercicios/tests.py`, `docentes/tests.py`

**Interfaces:**
- Consumes: `ejercicios.historial.build_historial_context(estudiante, comisiones, comision_id=None, pc_id=None)` de la Task 1.
- Produces: el mismo `build_historial_context`, pero el dict devuelve `historial_por_cohorte` (list[dict] con claves `cohorte` → instancia de `Cohorte` y `grupos` → list[dict] con la misma forma de grupo que la Task 1) **en lugar de** `intentos_agrupados`. La clave `intentos_agrupados` deja de existir.

- [ ] **Step 1: Escribir los tests que fallan**

En `ejercicios/tests.py`, al final del archivo:

```python
class HistorialPorCohorteTests(TestCase):
    """El historial separa las camadas: un recursante con intentos del mismo
    ejercicio en dos cohortes ve dos grupos, no uno con todo mezclado."""

    def setUp(self):
        self.docente = _u('doc-hist-coh', es_docente=True)
        self.estudiante = _u('est-hist-coh')

        # Ids al reves del orden cronologico real, como en
        # RecursanteReadPathTests: si algun query cae en "el ultimo por id
        # gana", este orden lo expone en vez de taparlo.
        self.cohorte_actual = Cohorte.objects.create(anio=2030, cuatrimestre=1)
        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC Hist Coh')
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja,
        )
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual,
        )

        practica = Practica.objects.create(titulo='P-hist-coh', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p', tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )

        self.intento_viejo = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte_vieja,
            respuesta_raw='p', es_correcto=True,
        )
        self.intento_nuevo = Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte_actual,
            respuesta_raw='q', es_correcto=False,
        )
        self.client.login(username='est-hist-coh', password='clave123')

    def test_dos_camadas_dan_dos_secciones_la_reciente_primero(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        self.assertEqual(resp.status_code, 200)
        secciones = resp.context['historial_por_cohorte']
        self.assertEqual(
            [s['cohorte'].pk for s in secciones],
            [self.cohorte_actual.pk, self.cohorte_vieja.pk],
        )

    def test_cada_seccion_lleva_el_ultimo_intento_de_su_cohorte(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        secciones = resp.context['historial_por_cohorte']
        # Un grupo por seccion: el mismo ejercicio, pero camadas distintas.
        # Sin el cambio de clave los dos intentos caerian en un unico grupo.
        self.assertEqual([len(s['grupos']) for s in secciones], [1, 1])
        self.assertEqual(
            secciones[0]['grupos'][0]['ultimo_intento'].pk, self.intento_nuevo.pk,
        )
        self.assertEqual(
            secciones[1]['grupos'][0]['ultimo_intento'].pk, self.intento_viejo.pk,
        )
        # Y ninguno arrastra al otro como "intento anterior".
        self.assertEqual(secciones[0]['grupos'][0]['intentos_anteriores'], [])
        self.assertEqual(secciones[1]['grupos'][0]['intentos_anteriores'], [])

    def test_una_sola_cohorte_igual_da_su_seccion(self):
        otro = _u('est-una-camada')
        Inscripcion.objects.create(
            estudiante=otro, comision=self.comision, cohorte=self.cohorte_actual,
        )
        Intento.objects.create(
            estudiante=otro, ejercicio_practica=self.ep, practica_comision=self.pc,
            cohorte=self.cohorte_actual, respuesta_raw='p', es_correcto=True,
        )
        self.client.login(username='est-una-camada', password='clave123')

        resp = self.client.get(reverse('ejercicios:mi_historial'))

        secciones = resp.context['historial_por_cohorte']
        self.assertEqual(len(secciones), 1)
        self.assertEqual(secciones[0]['cohorte'].pk, self.cohorte_actual.pk)

    def test_el_encabezado_de_camada_se_renderiza(self):
        resp = self.client.get(reverse('ejercicios:mi_historial'))

        self.assertContains(resp, '2030 – C1')
        self.assertContains(resp, '2020 – C1')
```

En `docentes/tests.py`, al final del archivo:

```python
class EstudianteDetailPorCohorteTests(TestCase):
    """La vista docente comparte el helper, asi que tambien separa camadas."""

    def setUp(self):
        self.docente = _u('doc-detail-coh', es_docente=True)
        self.estudiante = _u('est-detail-coh')

        self.cohorte_actual = Cohorte.objects.create(anio=2030, cuatrimestre=1)
        self.cohorte_vieja = Cohorte.objects.create(anio=2020, cuatrimestre=1)

        self.comision = Comision.objects.create(nombre='IPC Detail Coh')
        self.comision.docentes.add(self.docente)
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_vieja,
        )
        Inscripcion.objects.create(
            estudiante=self.estudiante, comision=self.comision, cohorte=self.cohorte_actual,
        )

        practica = Practica.objects.create(titulo='P-detail-coh', creada_por=self.docente)
        self.pc = PracticaComision.objects.create(
            practica=practica, comision=self.comision, orden=1,
        )
        ejercicio = Ejercicio.objects.create(
            enunciado='E1', formula_solucion='p', tipo='formalizacion',
            creado_por=self.docente,
        )
        self.ep = EjercicioPractica.objects.create(
            practica=practica, ejercicio=ejercicio, orden=1,
        )
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte_vieja,
            respuesta_raw='p', es_correcto=True,
        )
        Intento.objects.create(
            estudiante=self.estudiante, ejercicio_practica=self.ep,
            practica_comision=self.pc, cohorte=self.cohorte_actual,
            respuesta_raw='q', es_correcto=False,
        )
        self.client.login(username='doc-detail-coh', password='clave123')

    def test_el_panel_docente_separa_las_camadas(self):
        resp = self.client.get(
            reverse('docentes:estudiante_detail', args=[self.estudiante.id]),
        )

        self.assertEqual(resp.status_code, 200)
        secciones = resp.context['historial_por_cohorte']
        self.assertEqual(
            [s['cohorte'].pk for s in secciones],
            [self.cohorte_actual.pk, self.cohorte_vieja.pk],
        )
        self.assertEqual([len(s['grupos']) for s in secciones], [1, 1])
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
cd .claude/worktrees/historial-por-cohorte && SECRET_KEY=x python manage.py test ejercicios.tests.HistorialPorCohorteTests docentes.tests.EstudianteDetailPorCohorteTests -v 2
```

Esperado: FAIL con `KeyError: 'historial_por_cohorte'` en todos menos `test_el_encabezado_de_camada_se_renderiza`, que falla con el assertContains porque el template todavía no emite el encabezado.

- [ ] **Step 3: Cambiar query, clave y return en `ejercicios/historial.py`**

Agregar `'cohorte'` al `select_related` y anteponer la cohorte al `order_by`:

```python
        .select_related(
            'cohorte',
            'ejercicio_practica__practica',
            'ejercicio_practica__ejercicio',
            'practica_comision__comision',
        )
        .order_by(
            '-cohorte__anio',
            '-cohorte__cuatrimestre',
            'practica_comision__comision__nombre',
            'practica_comision__orden',
            'ejercicio_practica__orden',
            '-timestamp',
        )
```

`Cohorte.Meta.ordering` no se aplica al atravesar la FK desde `Intento`, por eso el orden va explícito.

Reemplazar el bloque de agrupación y el return:

```python
    secciones = []
    secciones_por_cohorte = {}
    grupos_por_clave = {}
    for intento in intentos_queryset:
        _enriquecer_intento(intento)

        cohorte_id = intento.cohorte_id
        if cohorte_id not in secciones_por_cohorte:
            seccion = {'cohorte': intento.cohorte, 'grupos': []}
            secciones_por_cohorte[cohorte_id] = seccion
            secciones.append(seccion)

        # La clave lleva la cohorte: sin eso, las dos camadas de un recursante
        # colapsan en un grupo y ultimo_intento sale de la que ordene primero.
        clave = (cohorte_id, intento.ejercicio_practica_id)
        if clave not in grupos_por_clave:
            grupo = {
                'ejercicio_practica': intento.ejercicio_practica,
                'comision': intento.practica_comision.comision if intento.practica_comision else None,
                'ultimo_intento': intento,
                'intentos_anteriores': [],
                'total_intentos': 1,
            }
            grupos_por_clave[clave] = grupo
            secciones_por_cohorte[cohorte_id]['grupos'].append(grupo)
        else:
            grupos_por_clave[clave]['intentos_anteriores'].append(intento)
            grupos_por_clave[clave]['total_intentos'] += 1

    return {
        'filtro_comision_id': comision_seleccionada.id if comision_seleccionada else '',
        'filtro_pc_id': pc_seleccionado.id if pc_seleccionado else '',
        'comisiones_disponibles': comisiones,
        'practicas_disponibles': pcs,
        'historial_por_cohorte': secciones,
    }
```

Actualizar el docstring del `Returns:` para que diga `lista de secciones por cohorte` en vez de `lista de grupos de intentos`.

- [ ] **Step 4: Agregar el loop externo en el template**

En `templates/docentes/estudiante_detail.html`, reemplazar las líneas 85-86:

```
  {% if intentos_agrupados %}
    {% for grupo in intentos_agrupados %}
```

por:

```
  {% if historial_por_cohorte %}
    {% for seccion in historial_por_cohorte %}
      <h2 style="margin:1.5rem 0 0.5rem; padding-bottom:0.3rem; border-bottom:2px solid #ddd; font-size:1.2rem; color:#444;">
        {{ seccion.cohorte }}
      </h2>
      {% for grupo in seccion.grupos %}
```

Y en la línea 391, donde hoy cierra el loop:

```
    {% endfor %}
  {% else %}
```

por:

```
      {% endfor %}
    {% endfor %}
  {% else %}
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

```bash
cd .claude/worktrees/historial-por-cohorte && SECRET_KEY=x python manage.py test ejercicios.tests.HistorialPorCohorteTests docentes.tests.EstudianteDetailPorCohorteTests -v 2
```

Esperado: OK, 5 tests.

- [ ] **Step 6: Correr la suite completa**

```bash
cd .claude/worktrees/historial-por-cohorte && SECRET_KEY=x python manage.py test ejercicios docentes cursos accounts analiticas -v 1
```

Esperado: OK. El test de la Task 1, `HistorialUnificadoTests.test_vista_propia_enriquece_determinacion_verdad`, lee `resp.context['intentos_agrupados']` y ahora rompe: actualizarlo a `resp.context['historial_por_cohorte'][0]['grupos'][0]`. Es el único consumidor del nombre viejo que queda.

- [ ] **Step 7: Commit**

```bash
git add ejercicios/historial.py templates/docentes/estudiante_detail.html ejercicios/tests.py docentes/tests.py
git commit -m "feat(historial): separar el historial del estudiante por cohorte"
```

---

## Notas de revisión

- El defecto que esto arregla es de agrupación, no de filtrado: los intentos de las dos camadas ya venían en el queryset. Por eso no hay cambio de permisos ni de visibilidad — nadie ve nada que antes no viera; se ve ordenado.
- `correccion_pendiente` (`docentes/views.py:1191`) tiene una tercera copia del enriquecido. No agrupa ni muestra historial, así que queda fuera de alcance a propósito.
- La rama se apila sobre `claude/desbloqueo-configurable` y no se puede mergear antes que ella.

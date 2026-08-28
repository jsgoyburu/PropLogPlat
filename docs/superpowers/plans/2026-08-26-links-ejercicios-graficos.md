# Links al ejercicio desde los gráficos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que los cinco gráficos cuyo eje X son ejercicios permitan abrir cada ejercicio con un click, y muestren el enunciado al pasar el mouse.

**Architecture:** Cada fila que alimenta un gráfico lleva una clave `url` resuelta en Python (`None` si el ejercicio no tiene práctica visible). Un helper JS compartido lee esa clave y engancha `onClick`, `onHover` y el tooltip sobre el chart ya construido.

**Tech Stack:** Django, Chart.js 4.4.4 (vía CDN, ya presente), sin dependencias nuevas.

## Global Constraints

- Python: `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe` (venv en el directorio **padre** del repo).
- Tests: `$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas -v 1`
- **Pasar `timeout: 600000` en cada comando de test.** El default es 2 minutos y el harness manda a background lo que exceda.
- La suite de `analiticas` corre en ~8 s. Correr la app entera, no solo la clase propia.
- URL destino: `ejercicios:ejercicio`, firma `practica/<int:pc_id>/ejercicio/<int:ep_id>/`. **Nunca** reconstruir esa ruta en JavaScript.
- `url` es `None` cuando no hay `PracticaComision` visible. Una barra sin `url` no reacciona: ni cursor, ni click.
- Cuando un ejercicio pertenece a varias comisiones filtradas, se elige el `PracticaComision` de **menor `id`**, de forma determinística.
- Los links abren en pestaña nueva (`target="_blank"` / `window.open(..., '_blank')`), como ya hacen las tablas.
- Sin migraciones. Código y comentarios en español, estilo Google en docstrings.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `analiticas/views.py` | `_url_ejercicio` (arma la ruta) y `_urls_ejercicios` (resuelve en bulk); las tres vistas propagan `url` |
| `templates/analiticas/_chart_links.html` **(nuevo)** | El helper JS `enlazarEjerciciosDelEje`, incluido por las dos páginas que lo usan |
| `templates/analiticas/investigacion.html` | 3 charts enganchados |
| `templates/analiticas/dashboard.html` | 2 charts enganchados |
| `analiticas/tests.py` | Tests |

**Corrección al spec:** dice que el partial lo cargan "las tres páginas". Son **dos** — `encuesta_resumen.html` no tiene gráficos por ejercicio.

Orden: Task 1 (helpers) → Task 2 (investigación) → Task 3 (dashboard) → Task 4 (JS).

---

## Task 1: Helpers de URL en Python

**Files:**
- Modify: `analiticas/views.py` (agregar cerca de `_strip_html`, antes de `_ejercicios_mas_dificiles`)
- Test: `analiticas/tests.py`

**Interfaces:**
- Produces (usado por Tasks 2 y 3):
  - `_url_ejercicio(pc_id, ep_id) -> str | None` — devuelve la ruta, o `None` si `pc_id` es `None`.
  - `_urls_ejercicios(ep_ids, comision_ids) -> dict[int, str | None]` — resuelve en bulk; clave `ep_id`, valor la ruta o `None`.

- [ ] **Step 1: Write the failing tests**

Agregar al final de `analiticas/tests.py`:

```python
# ─── Tests: URLs de ejercicio para los gráficos ──────────────────────────────

from analiticas.views import _url_ejercicio, _urls_ejercicios


class UrlsEjercicioParaGraficosTests(TestCase):
    """Los gráficos necesitan la URL resuelta en el servidor: reconstruir la
    ruta de Django en JavaScript se rompería en silencio ante un cambio de
    ``ejercicios/urls.py`` — el link seguiría existiendo, apuntando a nada."""

    def setUp(self):
        self.com_a, self.practica, self.pc_a, self.ep, _ = _setup_comision('URL-A')
        # La MISMA práctica asignada a una segunda comisión: es el caso que
        # obliga a una regla determinística, porque el ep tiene dos pc.
        self.com_b = Comision.objects.create(nombre='URL-B')
        self.pc_b = PracticaComision.objects.create(
            practica=self.practica, comision=self.com_b, orden=1,
        )

    def test_arma_la_ruta_con_pc_y_ep(self):
        url = _url_ejercicio(self.pc_a.id, self.ep.id)
        self.assertEqual(url, f'/practica/{self.pc_a.id}/ejercicio/{self.ep.id}/')

    def test_sin_pc_devuelve_none(self):
        self.assertIsNone(_url_ejercicio(None, self.ep.id))

    def test_bulk_resuelve_el_ep(self):
        urls = _urls_ejercicios([self.ep.id], [self.com_a.id])
        self.assertEqual(urls[self.ep.id], f'/practica/{self.pc_a.id}/ejercicio/{self.ep.id}/')

    def test_bulk_con_dos_comisiones_elige_el_pc_menor_y_es_estable(self):
        menor = min(self.pc_a.id, self.pc_b.id)
        ids = [self.com_a.id, self.com_b.id]
        primera = _urls_ejercicios([self.ep.id], ids)
        segunda = _urls_ejercicios([self.ep.id], list(reversed(ids)))
        self.assertEqual(primera[self.ep.id], f'/practica/{menor}/ejercicio/{self.ep.id}/')
        # Estable: el orden de comision_ids no puede cambiar el link.
        self.assertEqual(primera, segunda)

    def test_bulk_sin_comision_visible_devuelve_none(self):
        otra = Comision.objects.create(nombre='URL-ajena')
        urls = _urls_ejercicios([self.ep.id], [otra.id])
        self.assertIsNone(urls[self.ep.id])

    def test_bulk_no_hace_una_query_por_ejercicio(self):
        # Estos gráficos traen ~40 filas; resolver de a una sería N+1.
        ep2 = EjercicioPractica.objects.create(
            practica=self.practica,
            ejercicio=Ejercicio.objects.create(
                enunciado='Otro', formula_solucion='q', tipo='formalizacion',
                creado_por=self.com_a.docentes.first(),
            ),
            orden=2,
        )
        with self.assertNumQueries(1):
            _urls_ejercicios([self.ep.id, ep2.id], [self.com_a.id])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.UrlsEjercicioParaGraficosTests -v 2
```

Expected: FAIL — `ImportError: cannot import name '_url_ejercicio' from 'analiticas.views'`

- [ ] **Step 3: Write the implementation**

En `analiticas/views.py`, justo después de `_strip_html` (~línea 50):

```python
def _url_ejercicio(pc_id, ep_id):
    """Ruta al ejercicio dentro de su práctica, o ``None`` si no hay práctica.

    Este es el único lugar del proyecto que conoce el nombre de la ruta para
    los gráficos. La alternativa —reconstruirla en JavaScript— se rompe en
    silencio si ``ejercicios/urls.py`` cambia: el link sigue ahí y no lleva
    a ninguna parte.

    Args:
        pc_id: ID de PracticaComision, o None si el ejercicio no tiene una
            práctica visible para el usuario.
        ep_id: ID de EjercicioPractica.

    Returns:
        La ruta, o ``None``. Una fila con ``None`` deja su barra inerte en el
        gráfico, que es preferible a un link roto o al de otra comisión.
    """
    if pc_id is None:
        return None
    return reverse('ejercicios:ejercicio', args=[pc_id, ep_id])


def _urls_ejercicios(ep_ids, comision_ids):
    """Resuelve en bulk la URL de cada EjercicioPractica dado.

    Los paneles del dashboard agregan varias comisiones, así que una misma
    práctica puede estar asignada a más de una y el ``PracticaComision`` no es
    único. Se elige el de menor ``id``: es determinístico —dos cargas dan el
    mismo link— y el ejercicio que se abre es el mismo en cualquier caso; lo
    único que cambia es la práctica que lo enmarca.

    Args:
        ep_ids: iterable de IDs de EjercicioPractica.
        comision_ids: comisiones visibles para el usuario.

    Returns:
        Dict ``{ep_id: url | None}``, con una entrada por cada ep pedido.
    """
    ep_ids = list(ep_ids)
    if not ep_ids or not comision_ids:
        return {ep_id: None for ep_id in ep_ids}

    # Una sola query: (ep, pc) para todos los ep pedidos. Resolver de a uno
    # sería N+1 sobre gráficos de ~40 barras.
    filas = (
        EjercicioPractica.objects
        .filter(id__in=ep_ids, practica__practicas_comisiones__comision_id__in=comision_ids)
        .values_list('id', 'practica__practicas_comisiones__id')
    )

    mejor_pc = {}
    for ep_id, pc_id in filas:
        if pc_id is None:
            continue
        actual = mejor_pc.get(ep_id)
        if actual is None or pc_id < actual:
            mejor_pc[ep_id] = pc_id

    return {ep_id: _url_ejercicio(mejor_pc.get(ep_id), ep_id) for ep_id in ep_ids}
```

Verificar que `reverse` esté importado al principio del archivo. Si no está, agregar `from django.urls import reverse` junto a los demás imports de Django.

- [ ] **Step 4: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.UrlsEjercicioParaGraficosTests -v 2
```

Expected: PASS — 6 tests.

> Si `test_bulk_no_hace_una_query_por_ejercicio` falla por contar 2 queries en vez de 1, revisar que no haya un `select_related` implícito ni una evaluación temprana del queryset. El conteo exacto importa menos que la propiedad: **no debe crecer con la cantidad de ep**. Si no se puede dejar en 1, ajustar el número esperado y anotar en el reporte por qué.

- [ ] **Step 5: Commit**

```bash
git add analiticas/views.py analiticas/tests.py && git commit -m "feat(analiticas): helpers de URL de ejercicio para los graficos"
```

---

## Task 2: Los tres gráficos de investigación llevan `url`

**Files:**
- Modify: `analiticas/views.py` — función `_enrich` dentro de la vista `investigacion` (~línea 1028-1036)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `_url_ejercicio(pc_id, ep_id)` de Task 1.
- Produces: las filas de `intentos`, `persistencia` y `abandono` en el contexto ganan la clave `url`.

> Investigación **no** usa `_urls_ejercicios`: cada fila ya trae su propio `comision_id`, así que `_enrich` resuelve el `pc_id` exacto de esa comisión. Es más preciso que la regla del menor `id`, que existe solo para el dashboard, donde no hay comisión por fila.

- [ ] **Step 1: Write the failing test**

Agregar al final de `analiticas/tests.py`:

```python
class InvestigacionGraficosLlevanUrlTests(TestCase):
    """Las tablas de C1/B2/D1 ya enlazaban al ejercicio; los gráficos no."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('GRAF-INV', n_estudiantes=1)
        self.est = self.ests[0]
        _crear_encuesta(self.est)
        # Un fallo y luego un acierto: aparece en las tres secciones.
        _intento(self.est, self.ep, False, pc=self.pc)
        _intento(self.est, self.ep, True, pc=self.pc)
        self.admin = _u('admin-graf-inv', is_staff=True, consentimiento_pedagogico=True)
        self.client.force_login(self.admin)

    def test_las_tres_secciones_traen_url(self):
        resp = self.client.get(reverse('analiticas:investigacion'))
        esperada = f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/'
        for clave in ('intentos', 'persistencia', 'abandono'):
            filas = resp.context[clave]
            self.assertTrue(filas, f'{clave} vino vacío: el test no probaría nada')
            self.assertEqual(filas[0]['url'], esperada, f'falla en {clave}')

    def test_la_url_llega_al_html_servido(self):
        # Sobre resp.content, no sobre el contexto: el JSON del gráfico se
        # serializa con json_script y es lo que realmente consume Chart.js.
        resp = self.client.get(reverse('analiticas:investigacion'))
        cuerpo = resp.content.decode('utf-8')
        self.assertIn(f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/', cuerpo)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.InvestigacionGraficosLlevanUrlTests -v 2
```

Expected: FAIL — `KeyError: 'url'`

- [ ] **Step 3: Write the implementation**

En `analiticas/views.py`, reemplazar el cuerpo de `_enrich` (~línea 1028-1032):

```python
        def _enrich(row):
            ep_id = row['ep_id']
            practica_id = _ep_practica.get(ep_id)
            pc_id = _pc_lookup.get((practica_id, row['comision_id'])) if practica_id else None
            return {
                **row,
                'pc_id': pc_id,
                'enunciado_corto': _ep_enunciado.get(ep_id, ''),
                # Los gráficos consumen esto vía json_script; la tabla de la
                # misma sección arma su link con {% url %} y pc_id/ep_id.
                'url': _url_ejercicio(pc_id, ep_id),
            }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.InvestigacionGraficosLlevanUrlTests -v 2
```

Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add analiticas/views.py analiticas/tests.py && git commit -m "feat(analiticas): las filas de C1/B2/D1 llevan la url del ejercicio"
```

---

## Task 3: Los dos gráficos del dashboard llevan `ep_id` y `url`

**Files:**
- Modify: `analiticas/views.py` — `_ejercicios_mas_dificiles` (~línea 52-99) y `_distribucion_intentos` (~línea 200-260)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: `_urls_ejercicios(ep_ids, comision_ids)` de Task 1.
- Produces: las filas de ambos helpers ganan `ep_id` y `url`.

> `_ejercicios_mas_dificiles` ya itera sobre objetos `EjercicioPractica` (`for ep in eps`), así que `ep.id` está disponible; hoy solo emite `ejercicio_id`. `_distribucion_intentos` agrupa por `ejercicio_practica_id`, así que también lo tiene a mano. Ninguno de los dos necesita queries nuevas para el `ep_id`; la única query nueva es la de `_urls_ejercicios`, una sola por helper.

- [ ] **Step 1: Write the failing test**

Agregar al final de `analiticas/tests.py`:

```python
class DashboardGraficosLlevanUrlTests(TestCase):
    """Los dos paneles por ejercicio del dashboard: difíciles y distribución."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('GRAF-DASH', n_estudiantes=1)
        self.est = self.ests[0]
        _intento(self.est, self.ep, False, pc=self.pc)
        _intento(self.est, self.ep, True, pc=self.pc)

    def test_ejercicios_dificiles_trae_ep_id_y_url(self):
        filas = _ejercicios_mas_dificiles([self.com.id], [self.est.id], min_intentos=1)
        self.assertTrue(filas, 'sin filas el test no probaría nada')
        self.assertEqual(filas[0]['ep_id'], self.ep.id)
        self.assertEqual(
            filas[0]['url'], f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/',
        )

    def test_distribucion_intentos_trae_ep_id_y_url(self):
        filas = _distribucion_intentos([self.com.id], [self.est.id])
        self.assertTrue(filas, 'sin filas el test no probaría nada')
        self.assertEqual(filas[0]['ep_id'], self.ep.id)
        self.assertEqual(
            filas[0]['url'], f'/practica/{self.pc.id}/ejercicio/{self.ep.id}/',
        )

    def test_distribucion_elige_un_ep_estable_cuando_el_ejercicio_esta_en_dos(self):
        # _distribucion_intentos agrupa por ejercicio_id, no por ep_id: el mismo
        # ejercicio en dos prácticas es UNA fila que cubre dos EP. El link tiene
        # que ser el mismo entre cargas.
        practica2 = Practica.objects.create(titulo='P-GRAF-DASH-2')
        pc2 = PracticaComision.objects.create(
            practica=practica2, comision=self.com, orden=2,
        )
        ep2 = EjercicioPractica.objects.create(
            practica=practica2, ejercicio=self.ep.ejercicio, orden=1,
        )
        _intento(self.est, ep2, True, pc=pc2)

        filas = _distribucion_intentos([self.com.id], [self.est.id])
        fila = next(f for f in filas if f['ep_id'] in (self.ep.id, ep2.id))
        self.assertEqual(fila['ep_id'], min(self.ep.id, ep2.id))
        self.assertEqual(fila, next(
            f for f in _distribucion_intentos([self.com.id], [self.est.id])
            if f['ep_id'] in (self.ep.id, ep2.id)
        ))

    def test_ejercicio_sin_comision_visible_deja_url_none(self):
        # El helper recibe una comisión que no contiene a este ejercicio.
        otra = Comision.objects.create(nombre='GRAF-DASH-ajena')
        filas = _ejercicios_mas_dificiles([self.com.id], [self.est.id], min_intentos=1)
        urls = _urls_ejercicios([f['ep_id'] for f in filas], [otra.id])
        self.assertIsNone(urls[self.ep.id])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.DashboardGraficosLlevanUrlTests -v 2
```

Expected: FAIL — `KeyError: 'ep_id'`

- [ ] **Step 3: Implementar en `_ejercicios_mas_dificiles`**

Dentro del `for ep in eps:`, agregar `'ep_id': ep.id,` al dict que se apendea (junto a `'ejercicio_id'`). Después del `resultado.sort(...)` y del corte `[:top_n]`, resolver las URLs de las filas que quedan:

```python
    resultado.sort(key=lambda x: x['error_rate'], reverse=True)
    resultado = resultado[:top_n]
    # Se resuelve DESPUÉS del corte: no tiene sentido pedir URLs de filas
    # que el panel no va a mostrar.
    _urls = _urls_ejercicios([r['ep_id'] for r in resultado], comision_ids)
    for r in resultado:
        r['url'] = _urls.get(r['ep_id'])
    return resultado
```

- [ ] **Step 4: Implementar en `_distribucion_intentos`**

**Ojo, esta función no es como la otra.** Agrupa por `ejercicio_id`, no por
`ep_id`: el bucle es `for ejercicio_id, eps_del_ejercicio in ejercicio_grupos.items()`
porque *el mismo ejercicio puede estar en varias prácticas*, y cada fila de
salida agrega todos sus EP. No hay un `ep_id` único por fila.

Se toma el **menor** `ep_id` del grupo como representante. Es la misma clase de
regla determinística que la del `pc_id` menor, y por el mismo motivo: el
ejercicio que se abre es el mismo en cualquiera de sus EP.

Dentro del bucle, junto a `first_m = ep_meta_map[eps_del_ejercicio[0]]`:

```python
        # Representante determinístico: el mismo ejercicio puede estar en
        # varias prácticas y esta fila las agrega todas. Cualquiera de sus EP
        # abre el mismo ejercicio; se fija el menor para que el link no cambie
        # entre cargas.
        ep_representante = min(eps_del_ejercicio)
```

Agregar al dict que se apendea a `resultado`:

```python
            'ep_id': ep_representante,
```

Y después de cerrar el bucle, antes del `return resultado`:

```python
    _urls = _urls_ejercicios([r['ep_id'] for r in resultado], comision_ids)
    for r in resultado:
        r['url'] = _urls.get(r['ep_id'])
    return resultado
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas.tests.DashboardGraficosLlevanUrlTests -v 2
```

Expected: PASS — 4 tests.

- [ ] **Step 6: Correr la app entera**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas -v 1
```

Expected: PASS. Estos dos helpers los consume también `docentes/views.py::comision_detail`; agregar claves a un dict no rompe consumidores, pero la suite lo confirma.

- [ ] **Step 7: Commit**

```bash
git add analiticas/views.py analiticas/tests.py && git commit -m "feat(analiticas): los paneles por ejercicio del dashboard llevan ep_id y url"
```

---

## Task 4: El helper JS y los cinco gráficos enganchados

**Files:**
- Create: `templates/analiticas/_chart_links.html`
- Modify: `templates/analiticas/investigacion.html` (3 charts: ~1195, ~1233, ~1261)
- Modify: `templates/analiticas/dashboard.html` (2 charts: ~824, ~859)
- Test: `analiticas/tests.py`

**Interfaces:**
- Consumes: la clave `url` en las filas (Tasks 2 y 3), y `enunciado_corto`, que ya existía.
- Produces: nada que otra tarea consuma. Es la última.

- [ ] **Step 1: Crear el partial**

`templates/analiticas/_chart_links.html`:

```html
{% comment %}
Helper compartido: hace que las barras y las etiquetas de un gráfico por
ejercicio abran el ejercicio.

Chart.js dibuja el eje dentro de un <canvas>, así que las etiquetas no pueden
ser <a> de verdad. Esto es la aproximación: click sobre la barra o sobre su
etiqueta, cursor de mano donde hay link, y el enunciado en el tooltip.

Lo cargan investigacion.html y dashboard.html. encuesta_resumen.html no, porque
no tiene gráficos por ejercicio.
{% endcomment %}
<script>
  function enlazarEjerciciosDelEje(chart, filas) {
    if (!chart || !filas || !filas.length) return;

    // El eje de categorías es el X en los verticales y el Y en los
    // horizontales (indexAxis: 'y'). Leerlo de la config en vez de asumirlo:
    // los dos gráficos del dashboard son horizontales y los tres de
    // investigación verticales.
    const ejeCat = (chart.options.indexAxis === 'y') ? 'y' : 'x';

    function indiceEn(evt) {
      const els = chart.getElementsAtEventForMode(evt, 'index', { intersect: true }, false);
      if (els.length) return els[0].index;
      // Fuera del área del gráfico: puede ser la etiqueta del eje.
      const escala = chart.scales[ejeCat];
      if (!escala) return null;
      const pos = (ejeCat === 'y') ? evt.y : evt.x;
      const i = escala.getValueForPixel(pos);
      return (Number.isInteger(i) && i >= 0 && i < filas.length) ? i : null;
    }

    function urlDe(i) {
      return (i === null || !filas[i]) ? null : filas[i].url;
    }

    chart.options.onClick = function (evt) {
      const url = urlDe(indiceEn(evt));
      if (url) window.open(url, '_blank', 'noopener');
    };

    chart.options.onHover = function (evt) {
      evt.native.target.style.cursor = urlDe(indiceEn(evt)) ? 'pointer' : 'default';
    };

    const tt = chart.options.plugins.tooltip || (chart.options.plugins.tooltip = {});
    tt.callbacks = tt.callbacks || {};
    tt.callbacks.afterTitle = function (items) {
      const fila = filas[items[0].dataIndex];
      if (!fila) return '';
      const partes = [];
      if (fila.enunciado_corto) partes.push(fila.enunciado_corto);
      if (fila.url) partes.push('(click para abrir el ejercicio)');
      return partes.join('\n');
    };

    chart.update();
  }
</script>
```

- [ ] **Step 2: Incluir el partial en las dos páginas**

En `templates/analiticas/investigacion.html` y en `templates/analiticas/dashboard.html`, agregar inmediatamente después de la línea que carga Chart.js (`<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/...">`):

```html
{% include "analiticas/_chart_links.html" %}
```

- [ ] **Step 3: Enganchar los tres charts de investigación**

En los tres bloques (C1 ~1195, B2 ~1233, D1 ~1261), el patrón hoy es `new Chart(canvas, {...});`. Cambiar a capturar la instancia y enganchar. Para C1:

```js
    const chart = new Chart(canvas, {
      // ... sin cambios ...
    });
    enlazarEjerciciosDelEje(chart, data);
```

Repetir idéntico en B2 y D1: asignar a `const chart` y llamar `enlazarEjerciciosDelEje(chart, data);` justo después del cierre `});`. La variable con las filas ya se llama `data` en los tres.

- [ ] **Step 4: Enganchar los dos charts del dashboard**

Mismo cambio en `chart-dificiles` (~824) y `chart-distribucion` (~859): `const chart = new Chart(canvas, {...});` seguido de `enlazarEjerciciosDelEje(chart, data);`. En estos dos la variable también se llama `data`.

- [ ] **Step 5: Write the test**

Agregar al final de `analiticas/tests.py`:

```python
class ChartLinksPartialTests(TestCase):
    """El partial tiene que llegar a las dos páginas con gráficos por
    ejercicio, y a ninguna otra."""

    def setUp(self):
        self.com, _, self.pc, self.ep, self.ests = _setup_comision('PARTIAL', n_estudiantes=1)
        _intento(self.ests[0], self.ep, True, pc=self.pc)
        self.admin = _u('admin-partial', is_staff=True, consentimiento_pedagogico=True)
        self.client.force_login(self.admin)

    def test_dashboard_e_investigacion_cargan_el_helper(self):
        for nombre in ('analiticas:dashboard', 'analiticas:investigacion'):
            resp = self.client.get(reverse(nombre))
            self.assertContains(resp, 'enlazarEjerciciosDelEje', msg_prefix=nombre)

    def test_encuesta_no_lo_carga(self):
        # No tiene gráficos por ejercicio; cargarlo sería peso muerto.
        resp = self.client.get(reverse('analiticas:encuesta_resumen'))
        self.assertNotContains(resp, 'enlazarEjerciciosDelEje')
```

- [ ] **Step 6: Run tests**

```bash
$env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'; & 'C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe' manage.py test analiticas -v 1
```

Expected: PASS, suite completa de `analiticas`.

- [ ] **Step 7: Verificación manual — obligatoria**

Los tests cubren que la `url` llega al HTML, pero **ningún test ejecuta Chart.js**. Un error de JS acá no rompe nada visible: el gráfico dibuja igual y el click simplemente no hace nada. Hay que mirarlo.

Levantar el server y revisar, en `/analiticas/investigacion/` y `/analiticas/dashboard/`:

- [ ] El cursor cambia a mano al pasar sobre una barra.
- [ ] El tooltip muestra el enunciado.
- [ ] Click en la barra abre el ejercicio en pestaña nueva.
- [ ] Click en la **etiqueta del eje** (fuera del área del gráfico) también lo abre.
- [ ] Probar los dos horizontales del dashboard **y** los tres verticales de investigación: el eje de categorías es distinto y es donde más fácil se rompe.
- [ ] La consola del navegador no tira errores.

Anotar en el reporte qué se verificó y en qué navegador.

- [ ] **Step 8: Commit**

```bash
git add templates/analiticas/_chart_links.html templates/analiticas/investigacion.html templates/analiticas/dashboard.html analiticas/tests.py && git commit -m "feat(analiticas): las barras y etiquetas de los graficos abren el ejercicio"
```

---

## Verificación final

- [ ] Suite global: `manage.py test` → OK.
- [ ] Los 5 gráficos verificados a mano según el checklist de Task 4 Step 7.
- [ ] Un ejercicio sin práctica visible deja su barra inerte, sin error en consola.

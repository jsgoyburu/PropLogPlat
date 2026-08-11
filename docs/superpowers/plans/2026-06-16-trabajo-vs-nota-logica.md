# Métrica "trabajo vs. nota de lógica" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar a las analíticas de investigación una métrica que relacione el trabajo (esfuerzo) del estudiante en la plataforma con la nota de la sección de lógica del primer parcial, visualizada como dispersión con recta de tendencia y correlación.

**Architecture:** Una función pura en `analiticas/research.py` calcula los puntos (un estudiante = un punto) y las correlaciones; la vista `investigacion` la inyecta al contexto; el template la dibuja con Chart.js (scatter + selector de eje X); `descargar_investigacion` la exporta a CSV/XLSX; y `mcp_intentos.py` la expone como tool de solo lectura.

**Tech Stack:** Django, Chart.js 4.4 (ya cargado), FastMCP. Tests con `django.test.TestCase`. Entorno: `SECRET_KEY=x` y ejecutable `C:\Users\Angeles\Documents\IPC-Logica\Scripts\python.exe`.

**Convención de tests:** correr con
`PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test analiticas -v1`

---

### Task 1: Función `trabajo_vs_nota_logica` en research.py

**Files:**
- Modify: `analiticas/research.py` (agregar función al final, antes de `_corr_eta_squared` o al final del archivo)
- Test: `analiticas/tests.py` (nueva clase al final)

- [ ] **Step 1: Write the failing test**

Agregar al final de `analiticas/tests.py`:

```python
class TrabajoVsNotaLogicaTests(TestCase):
    """analiticas.research.trabajo_vs_nota_logica"""

    def setUp(self):
        from datetime import timedelta
        from cursos.models import Parcial, NotaParcial
        self.comision, self.practica, self.pc, self.ep, _ = _setup_comision('TVN', n_estudiantes=0)
        # Parcial con fecha futura para que los intentos "ahora" cuenten como previos
        self.fecha_parcial = timezone.now().date() + timedelta(days=1)
        self.parcial = Parcial.objects.create(
            comision=self.comision, nombre='Parcial 1',
            fecha=self.fecha_parcial, puntaje_total=10,
        )
        # est_con: consentido, trabaja mucho, nota alta
        self.est_con = _u('tvn-con', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_con, comision=self.comision)
        for ok in [True, False, False, True]:
            _intento(self.est_con, self.ep, ok, pc=self.pc)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_con,
                                   nota_logica_parcial=8)
        # est_poco: consentido, trabaja poco, nota baja
        self.est_poco = _u('tvn-poco', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_poco, comision=self.comision)
        _intento(self.est_poco, self.ep, False, pc=self.pc)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_poco,
                                   nota_logica_parcial=2)
        # est_sin: SIN consentimiento → no debe aparecer
        self.est_sin = _u('tvn-sin', consentimiento_investigacion=False)
        Inscripcion.objects.create(estudiante=self.est_sin, comision=self.comision)
        _intento(self.est_sin, self.ep, True, pc=self.pc)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_sin,
                                   nota_logica_parcial=9)
        # est_ausente: consentido pero ausente → excluido
        self.est_aus = _u('tvn-aus', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_aus, comision=self.comision)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_aus,
                                   ausente=True)
        # est_pendiente: consentido pero nota_logica None → excluido
        self.est_pend = _u('tvn-pend', consentimiento_investigacion=True)
        Inscripcion.objects.create(estudiante=self.est_pend, comision=self.comision)
        NotaParcial.objects.create(parcial=self.parcial, estudiante=self.est_pend,
                                   nota_logica_parcial=None)

    def test_filtra_consentimiento_ausente_y_pendiente(self):
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=[self.comision.id], solo_consentimiento=True)
        self.assertEqual(res['n'], 2)
        notas = sorted(p['nota_logica'] for p in res['puntos'])
        self.assertEqual(notas, [2.0, 8.0])

    def test_indice_trabajo_normalizado(self):
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=[self.comision.id], solo_consentimiento=True)
        indices = {p['nota_logica']: p['indice_trabajo'] for p in res['puntos']}
        # est_poco es el mínimo en TODOS los indicadores → índice 0.
        # est_con supera a est_poco (más intentos) → índice mayor.
        # (Solo intentos_totales difiere en esta fixture; los otros 3 indicadores
        #  son iguales, así que su norma es 0 para ambos: índice de est_con = 25.0.)
        self.assertEqual(indices[2.0], 0.0)
        self.assertEqual(indices[8.0], 25.0)
        self.assertGreater(indices[8.0], indices[2.0])

    def test_correlaciones_presentes(self):
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=[self.comision.id], solo_consentimiento=True)
        for ind in ['indice_trabajo', 'intentos_totales', 'dias_activos',
                    'ejercicios_distintos', 'practicas_abiertas']:
            self.assertIn(ind, res['correlaciones'])
            self.assertEqual(res['correlaciones'][ind]['n'], 2)
        # Con N=2 (<3) Pearson devuelve None
        self.assertIsNone(res['correlaciones']['indice_trabajo']['r_pearson'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test analiticas.tests.TrabajoVsNotaLogicaTests -v2`
Expected: FAIL con `ImportError: cannot import name 'trabajo_vs_nota_logica'`.

- [ ] **Step 3: Write minimal implementation**

Agregar al final de `analiticas/research.py`:

```python
# ─── Trabajo en plataforma vs. nota de lógica del parcial ─────────────────────

_TRABAJO_INDICADORES = [
    'intentos_totales', 'dias_activos',
    'ejercicios_distintos', 'practicas_abiertas',
]


def trabajo_vs_nota_logica(comision_ids=None, solo_consentimiento=True):
    """Relaciona el esfuerzo en la plataforma con la nota de lógica del 1er parcial.

    Un punto por estudiante (consentido y con nota de lógica graduada). El eje X
    son indicadores de esfuerzo (no rendimiento) acumulados antes de la fecha del
    primer parcial de cada comisión; el eje Y es ``nota_logica_parcial``.

    Returns:
        dict con ``puntos`` (lista de dicts), ``correlaciones`` (por indicador,
        con ``r_pearson``/``r_spearman``/``n``) y ``n``.
    """
    from cursos.models import Parcial, NotaParcial
    from analiticas.calculos import (
        calcular_uso_plataforma_antes_parcial,
        calcular_desenlace_parcial,
    )

    comision_ids = _resolver_comision_ids(comision_ids)

    # Primer parcial (menor fecha) de cada comisión.
    primer_parcial = {}
    for parcial in Parcial.objects.filter(comision_id__in=comision_ids).order_by('fecha'):
        primer_parcial.setdefault(parcial.comision_id, parcial)

    crudos = []  # (uso_dict, nota_logica, desenlace)
    for parcial in primer_parcial.values():
        notas = NotaParcial.objects.filter(
            parcial=parcial, ausente=False, nota_logica_parcial__isnull=False,
        ).select_related('estudiante', 'parcial')
        if solo_consentimiento:
            notas = notas.filter(estudiante__consentimiento_investigacion=True)
        for nota in notas:
            uso = calcular_uso_plataforma_antes_parcial(nota.estudiante, parcial)
            crudos.append((uso, float(nota.nota_logica_parcial),
                           calcular_desenlace_parcial(nota)))

    # Normalización min-max por indicador sobre la cohorte mostrada.
    mins = {ind: min((u[ind] for u, _, _ in crudos), default=0) for ind in _TRABAJO_INDICADORES}
    maxs = {ind: max((u[ind] for u, _, _ in crudos), default=0) for ind in _TRABAJO_INDICADORES}

    def _norm(ind, val):
        rng = maxs[ind] - mins[ind]
        return 0.0 if rng == 0 else (val - mins[ind]) / rng

    puntos = []
    for uso, nota_logica, desenlace in crudos:
        norms = [_norm(ind, uso[ind]) for ind in _TRABAJO_INDICADORES]
        punto = {ind: uso[ind] for ind in _TRABAJO_INDICADORES}
        punto['indice_trabajo'] = round(sum(norms) / len(norms) * 100, 1)
        punto['nota_logica'] = nota_logica
        punto['desenlace'] = desenlace
        puntos.append(punto)

    # Correlaciones de cada indicador (y del índice) contra la nota de lógica.
    ys = [p['nota_logica'] for p in puntos]
    correlaciones = {}
    for ind in _TRABAJO_INDICADORES + ['indice_trabajo']:
        xs = [p[ind] for p in puntos]
        n = len(xs)
        r_p = _corr_pearson(xs, ys) if n >= 3 else None
        r_s = _corr_pearson(_corr_rankdata(xs), _corr_rankdata(ys)) if n >= 3 else None
        correlaciones[ind] = {
            'r_pearson': round(r_p, 3) if r_p is not None else None,
            'r_spearman': round(r_s, 3) if r_s is not None else None,
            'n': n,
        }

    return {'puntos': puntos, 'correlaciones': correlaciones, 'n': len(puntos)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test analiticas.tests.TrabajoVsNotaLogicaTests -v2`
Expected: PASS (3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add analiticas/research.py analiticas/tests.py
git commit -m "feat(analiticas): trabajo_vs_nota_logica (esfuerzo en plataforma vs nota de logica)"
```

---

### Task 2: Inyectar la métrica en la vista `investigacion`

**Files:**
- Modify: `analiticas/views.py` (import en el bloque de `investigacion`, cálculo y context)

- [ ] **Step 1: Agregar el import en la función `investigacion`**

En `analiticas/views.py`, dentro del `from analiticas.research import (...)` de `investigacion` (empieza en la línea ~801), agregar `trabajo_vs_nota_logica,` a la lista de imports (mantener orden alfabético: va después de `tasa_entrada_efectiva,`).

- [ ] **Step 2: Calcular la métrica**

En `investigacion`, junto a las otras llamadas (después de `nube_palabras_ciencia = nube_ciencia(...)`, ~línea 902), agregar:

```python
    trabajo_nota = trabajo_vs_nota_logica(comision_ids=comision_ids, solo_consentimiento=True)
```

- [ ] **Step 3: Pasar al contexto**

En el `return render(request, 'analiticas/investigacion.html', { ... })`, agregar la clave:

```python
        'trabajo_nota': trabajo_nota,
```

- [ ] **Step 4: Verificar que la vista carga**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 5: Commit**

```bash
git add analiticas/views.py
git commit -m "feat(analiticas): inyectar trabajo_nota en la vista de investigacion"
```

---

### Task 3: Visualización scatter en el template

**Files:**
- Modify: `templates/analiticas/investigacion.html` (serialización JSON, sección HTML, bloque Chart.js)

- [ ] **Step 1: Serializar los datos**

En la zona de `{# ── Serialización de datos para Chart.js ── #}` (después de la línea `data-nube-ciencia`, ~línea 67), agregar:

```django
{% if trabajo_nota %}{{ trabajo_nota|json_script:"data-trabajo-nota" }}{% endif %}
```

- [ ] **Step 2: Agregar la sección HTML**

Insertar una nueva tarjeta antes de la sección de correlaciones (antes de `<canvas id="chart-correlaciones">`). Usar la estructura de tarjeta existente:

```html
  <div class="card" style="margin-bottom:1.5rem; padding:1.25rem 1.5rem;">
    <h3 style="margin:0 0 0.25rem; font-size:1rem; font-weight:600; color:#1a1a2e;">
      Trabajo en la plataforma vs. nota de lógica del parcial
    </h3>
    <p style="margin:0 0 0.75rem; font-size:0.82rem; color:#666;">
      Un punto por estudiante (consentido, con nota de lógica). Eje X: esfuerzo
      antes del 1er parcial. Color: desenlace del parcial.
      <span id="trabajo-r" style="font-weight:600; color:#1a1a2e;"></span>
    </p>
    <label style="font-size:0.84rem; color:#555;">
      Indicador de trabajo:
      <select id="sel-trabajo-x" style="font-size:0.84rem; padding:0.25rem 0.5rem; border:1px solid #ccc; border-radius:4px;">
        <option value="indice_trabajo">Índice de trabajo (compuesto)</option>
        <option value="intentos_totales">Intentos totales</option>
        <option value="dias_activos">Días activos</option>
        <option value="ejercicios_distintos">Ejercicios distintos</option>
        <option value="practicas_abiertas">Prácticas abiertas</option>
      </select>
    </label>
    <div style="position:relative; height:360px; margin-top:0.75rem;">
      <canvas id="chart-trabajo-nota"></canvas>
    </div>
  </div>
```

- [ ] **Step 3: Agregar el bloque Chart.js**

Dentro del IIFE principal de gráficos (después del bloque `// ── E3. Desempeño × Pandemia ──` y antes de `// ── F. Correlaciones`), agregar:

```javascript
  // ── E4. Trabajo en plataforma × nota de lógica ──
  (function() {
    const payload = parseData('data-trabajo-nota');
    const canvas = document.getElementById('chart-trabajo-nota');
    if (!canvas) return;
    if (!payload || !payload.puntos || !payload.puntos.length) { noData(canvas); return; }

    const puntos = payload.puntos;
    const corr = payload.correlaciones || {};
    const sel = document.getElementById('sel-trabajo-x');
    const rLabel = document.getElementById('trabajo-r');
    const COLOR_DESENLACE = { 'Aplazo': C.rojo, 'Final': C.naranja, 'Promoción': C.verde };
    const X_LABEL = {
      indice_trabajo: 'Índice de trabajo (0–100)',
      intentos_totales: 'Intentos totales',
      dias_activos: 'Días activos',
      ejercicios_distintos: 'Ejercicios distintos',
      practicas_abiertas: 'Prácticas abiertas',
    };

    function trendline(pts) {
      const n = pts.length;
      if (n < 2) return null;
      const mx = pts.reduce((s, p) => s + p.x, 0) / n;
      const my = pts.reduce((s, p) => s + p.y, 0) / n;
      let num = 0, den = 0;
      for (const p of pts) { num += (p.x - mx) * (p.y - my); den += (p.x - mx) ** 2; }
      if (den === 0) return null;
      const m = num / den, b = my - m * mx;
      const xs = pts.map(p => p.x);
      const x0 = Math.min(...xs), x1 = Math.max(...xs);
      return [{ x: x0, y: m * x0 + b }, { x: x1, y: m * x1 + b }];
    }

    let chart = null;
    function render(ind) {
      const grupos = { 'Promoción': [], 'Final': [], 'Aplazo': [] };
      for (const p of puntos) {
        (grupos[p.desenlace] || (grupos[p.desenlace] = [])).push({ x: p[ind], y: p.nota_logica });
      }
      const datasets = Object.keys(grupos).filter(k => grupos[k].length).map(k => ({
        label: k, data: grupos[k],
        backgroundColor: COLOR_DESENLACE[k] || C.gris, pointRadius: 5,
      }));
      const linea = trendline(puntos.map(p => ({ x: p[ind], y: p.nota_logica })));
      if (linea) datasets.push({
        label: 'Tendencia', data: linea, type: 'line',
        borderColor: C.gris, borderWidth: 2, pointRadius: 0, fill: false,
      });
      const c = corr[ind] || {};
      const rp = c.r_pearson == null ? '—' : c.r_pearson.toFixed(3);
      const rs = c.r_spearman == null ? '—' : c.r_spearman.toFixed(3);
      rLabel.textContent = `· r = ${rp}  ·  rₛ = ${rs}  ·  N = ${c.n ?? puntos.length}`;
      if (chart) chart.destroy();
      chart = new Chart(canvas, {
        type: 'scatter',
        data: { datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom' } },
          scales: {
            x: { title: { display: true, text: X_LABEL[ind] } },
            y: { title: { display: true, text: 'Nota de lógica' }, beginAtZero: true },
          },
        },
      });
    }

    render('indice_trabajo');
    if (sel) sel.addEventListener('change', () => render(sel.value));
  })();
```

- [ ] **Step 4: Verificar templates/sintaxis**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 5: Commit**

```bash
git add templates/analiticas/investigacion.html
git commit -m "feat(analiticas): scatter trabajo vs nota de logica con selector de eje X"
```

---

### Task 4: Export CSV/XLSX del dataset

**Files:**
- Modify: `analiticas/views.py` (`descargar_investigacion`)

- [ ] **Step 1: Aceptar el nuevo dataset**

En `descargar_investigacion` (~línea 1522), ampliar la validación:

```python
    if dataset not in ('encuesta', 'intentos', 'ejercicios', 'practicas', 'trabajo_nota'):
        dataset = 'encuesta'
```

- [ ] **Step 2: Agregar la rama del dataset**

Antes del `else:  # intentos` final (~línea 1597), agregar:

```python
    elif dataset == 'trabajo_nota':
        from analiticas.research import trabajo_vs_nota_logica
        res = trabajo_vs_nota_logica(comision_ids=comision_ids, solo_consentimiento=True)
        headers = ['intentos_totales', 'dias_activos', 'ejercicios_distintos',
                   'practicas_abiertas', 'indice_trabajo', 'nota_logica', 'desenlace']
        rows = [[p[h] for h in headers] for p in res['puntos']]
        nombre_base = f'ipc-trabajo-nota-{fecha_str}'

        if formato == 'xlsx':
            content = _bytes_xlsx(headers, rows, 'Trabajo vs nota lógica')
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ext = 'xlsx'
        else:
            content = _bytes_csv(headers, rows)
            mime = 'text/csv; charset=utf-8'
            ext = 'csv'
```

- [ ] **Step 3: Agregar botones de descarga en el template**

En la sección "Descargar datos de investigación" de `templates/analiticas/investigacion.html`, junto a los otros botones de descarga (buscar `url('encuesta'`), agregar un par de enlaces análogos:

```html
        <a :href="url('trabajo_nota','csv')" class="btn-descarga">Trabajo vs nota (CSV)</a>
        <a :href="url('trabajo_nota','xlsx')" class="btn-descarga">Trabajo vs nota (XLSX)</a>
```

(Usar exactamente la misma clase/estilo que los `<a>` de descarga vecinos; copiar el atributo `class`/`style` de un botón existente si no usan `.btn-descarga`.)

- [ ] **Step 4: Verificar descarga**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 5: Commit**

```bash
git add analiticas/views.py templates/analiticas/investigacion.html
git commit -m "feat(analiticas): export CSV/XLSX del dataset trabajo vs nota de logica"
```

---

### Task 5: Tool MCP de solo lectura

**Files:**
- Modify: `mcp_intentos.py` (nueva tool + wrapper `_compat`, en la sección de métricas de investigación)

- [ ] **Step 1: Agregar la tool**

En `mcp_intentos.py`, junto a las otras métricas de investigación (después de `red_errores`, ~línea 967), agregar:

```python
@db_tool()
def trabajo_vs_nota_logica(
    comision_ids: list[int] | None = None,
    solo_consentimiento: bool = True,
) -> dict:
    """Relaciona el esfuerzo en la plataforma con la nota de lógica del 1er parcial.

    Un punto por estudiante (consentido, con nota de lógica graduada). El eje X
    son indicadores de esfuerzo (intentos_totales, dias_activos,
    ejercicios_distintos, practicas_abiertas e indice_trabajo compuesto 0–100)
    medidos antes de la fecha del primer parcial; el eje Y es la nota de lógica.

    Args:
        comision_ids: lista de IDs de comisión; None = todas.
        solo_consentimiento: si True, solo consentimiento_investigacion=True.

    Returns:
        Dict con ``puntos``, ``correlaciones`` (r_pearson/r_spearman/n por
        indicador) y ``n``.
    """
    from analiticas.research import trabajo_vs_nota_logica as _f
    return _f(comision_ids=comision_ids, solo_consentimiento=solo_consentimiento)
```

- [ ] **Step 2: Agregar el wrapper de compatibilidad**

En la sección de wrappers `*_compat` (después de `red_errores_compat`, ~línea 1546), agregar:

```python
@mcp.tool()
async def trabajo_vs_nota_logica_compat(args: dict | None = None, kwargs: dict | None = None) -> dict:
    return await trabajo_vs_nota_logica(**_compat_kwargs(args=args, kwargs=kwargs))
```

- [ ] **Step 3: Verificar que el módulo importa sin error**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" -c "import mcp_intentos; print('ok')"`
Expected: imprime `ok` (sin excepción de import).

- [ ] **Step 4: Commit**

```bash
git add mcp_intentos.py
git commit -m "feat(mcp): tool trabajo_vs_nota_logica (solo lectura)"
```

---

### Task 6: Verificación final

- [ ] **Step 1: Correr toda la suite de analiticas**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py test analiticas -v1`
Expected: todos OK (incluida `TrabajoVsNotaLogicaTests`).

- [ ] **Step 2: `manage.py check` global**

Run: `PYTHONIOENCODING=utf-8 SECRET_KEY=x "C:/Users/Angeles/Documents/IPC-Logica/Scripts/python.exe" manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 3 (opcional): dry-check contra prod**

Verificar la métrica sobre datos reales sin escribir (solo lectura):
`railway run --project e520403c-0520-4030-bfc8-769acecd6991 --environment 0e4aa228-39df-4034-967e-de9d2c3c60d8 --service 9e960f45-8ba7-4100-89b4-822c88ea3605 -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" RAILWAY_ENVIRONMENT=production SECRET_KEY=x PYTHONIOENCODING=utf-8 python -c "import django,os; os.environ.setdefault(\"DJANGO_SETTINGS_MODULE\",\"logica_ipc.settings\"); django.setup(); from analiticas.research import trabajo_vs_nota_logica as f; r=f(); print(\"n=\",r[\"n\"]); print(r[\"correlaciones\"])"'`
Expected: imprime `n=` y el dict de correlaciones con datos reales.

---

## Notas de cobertura del spec

- Eje X conmutable + índice compuesto default → Tasks 1 y 3.
- Eje Y = nota_logica graduada (excluye ausente/pendiente) → Task 1 (tests).
- Primer parcial por comisión → Task 1.
- Color por desenlace → Task 3.
- Dashboard + export + MCP → Tasks 2/3, 4, 5.
- Tests → Task 1.

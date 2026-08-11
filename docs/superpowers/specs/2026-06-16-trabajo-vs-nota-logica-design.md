# Métrica de investigación: trabajo en la plataforma vs. nota de lógica del parcial

Fecha: 2026-06-16

## Objetivo

Agregar una métrica a las analíticas de investigación que relacione el **trabajo
del estudiante en la plataforma** (esfuerzo/engagement, *no* rendimiento) con la
**nota obtenida en la parte de lógica del parcial** (`NotaParcial.nota_logica_parcial`).

La pregunta pedagógica que responde: *¿cuánto se asocia el esfuerzo sostenido en
la plataforma con el desempeño en lógica del parcial?* — distinguiendo esfuerzo
de acierto (un estudiante puede trabajar mucho con baja tasa de éxito y aun así
mejorar su nota).

## Definiciones

### Eje X — "trabajo" (esfuerzo)

Indicadores de esfuerzo provistos por `calcular_uso_plataforma_antes_parcial`
(en `analiticas/calculos.py`), medidos con intentos de timestamp anterior a
`parcial.fecha`:

- `intentos_totales` — volumen de envíos.
- `dias_activos` — días distintos con actividad.
- `ejercicios_distintos` — ejercicios distintos intentados.
- `practicas_abiertas` — prácticas distintas en las que trabajó.

Se **excluyen** explícitamente `tasa_exito`, `ejercicios_resueltos` y
`promedio_intentos_hasta_correcto` por ser indicadores de **rendimiento**, no de
trabajo.

**Índice compuesto de trabajo (default):** promedio de los 4 indicadores de
esfuerzo normalizados min-max sobre la cohorte analizada, reescalado a 0–100.
Para cada indicador `v`: `norm = (v - min) / (max - min)` (si `max == min`, `norm = 0`).
`indice_trabajo = mean(norm_intentos, norm_dias, norm_ejercicios, norm_practicas) * 100`.
La normalización se calcula sobre el mismo conjunto de estudiantes que entran al
gráfico (consentidos + con nota de lógica), de modo que el índice es relativo a
la cohorte mostrada.

### Eje Y — nota de lógica

`NotaParcial.nota_logica_parcial` en su escala cruda (puntos de la sección de
lógica). Se incluyen solo notas **graduadas**: se excluyen `ausente=True` y
`nota_logica_parcial is None` (pendiente).

### Unidad de análisis y alcance

- Un punto por **estudiante**.
- Filtro: `consentimiento_investigacion=True` cuando `solo_consentimiento=True`
  (default), igual que el resto de `analiticas/research.py`.
- Se toma el **primer parcial** (menor `fecha`) de cada comisión incluida,
  coherente con el marco "antes del 1er parcial" ya existente en el código.
- Si un estudiante pertenece a varias comisiones incluidas, se considera el
  primer parcial de la comisión donde tiene nota de lógica cargada.

### Color de los puntos

Cada punto se colorea por desenlace del parcial (`calcular_desenlace_parcial`):
`Aplazo` / `Final` / `Promoción`. (`Ausente` no aparece porque no tiene nota de
lógica.) Nota: el desenlace refleja el resultado **global** del parcial
(`puntaje` normalizado), no solo la sección de lógica; se usa únicamente como
contexto visual de color, mientras que el eje Y es específicamente la nota de
lógica.

## Visualización

**Gráfico de dispersión (scatter) con recta de tendencia y coeficiente de
correlación**, en Chart.js 4.4 (ya cargado en `investigacion.html`):

- Eje X: indicador de trabajo seleccionado (índice compuesto por default).
- Eje Y: nota de lógica.
- Un punto por estudiante, coloreado por desenlace.
- Recta de ajuste lineal (mínimos cuadrados) como dataset adicional.
- En el encabezado del panel: `r` de Pearson y de Spearman + `n`.
- Selector (JS/Alpine) para cambiar el eje X entre: índice de trabajo,
  intentos totales, días activos, ejercicios distintos, prácticas abiertas.
  La recta y el `r` se recalculan al cambiar de indicador.

Justificación: con N≈60 el scatter es legible y es la representación más
informativa de una relación entre dos variables continuas (muestra dispersión,
outliers y forma, no solo el promedio).

## Componentes

### 1. `analiticas/research.py` → `trabajo_vs_nota_logica(comision_ids=None, solo_consentimiento=True)`

Devuelve:

```python
{
  "puntos": [
    {
      "intentos_totales": int, "dias_activos": int,
      "ejercicios_distintos": int, "practicas_abiertas": int,
      "indice_trabajo": float,        # 0–100
      "nota_logica": float,
      "desenlace": "Aplazo" | "Final" | "Promoción",
    }, ...
  ],
  "correlaciones": {
    "indice_trabajo": {"r_pearson": float|None, "r_spearman": float|None, "n": int},
    "intentos_totales": {...}, "dias_activos": {...},
    "ejercicios_distintos": {...}, "practicas_abiertas": {...},
  },
  "n": int,
}
```

Reutiliza `_resolver_comision_ids`, `_filtrar_por_consentimiento`,
`_corr_pearson` y `_corr_rankdata` ya existentes en el módulo. Los puntos NO
incluyen identificadores de estudiante (dataset anonimizado, como el resto de
research).

### 2. `analiticas/views.py`

- `investigacion`: importa y agrega `trabajo_vs_nota_logica(...)` al contexto.
- `descargar_investigacion`: nuevo dataset descargable (CSV/XLSX/ODS) con una
  fila por punto (indicadores de trabajo + índice + nota + desenlace).

### 3. `templates/analiticas/investigacion.html`

- Nueva sección con `<canvas id="chart-trabajo-nota">`, selector de eje X y
  encabezado con `r`.
- Serialización de `puntos`/`correlaciones` a JSON (igual que los demás charts)
  y bloque `new Chart(...)` tipo `scatter` con dataset de recta de tendencia.

### 4. `mcp_intentos.py`

- Tool `trabajo_vs_nota_logica` (delegando en `analiticas.research`) + wrapper
  `trabajo_vs_nota_logica_compat`. Solo lectura.

## Tests (`analiticas/tests.py`)

- Filtra correctamente por `consentimiento_investigacion`.
- Excluye notas ausentes y pendientes (None).
- Calcula `indice_trabajo` con normalización min-max esperada (caso `max==min`).
- Devuelve `r_pearson`/`r_spearman` coherentes en un caso construido.
- `n` coincide con la cantidad de puntos.

## Fuera de alcance (YAGNI)

- Normalización de `nota_logica_parcial` entre comisiones con escalas distintas
  (se grafica cruda; se puede agregar después si hace falta comparar cohortes).
- Parciales distintos del primero (recuperatorios, 2º parcial).
- Modelado causal o regresión múltiple; esto es exploratorio/descriptivo.

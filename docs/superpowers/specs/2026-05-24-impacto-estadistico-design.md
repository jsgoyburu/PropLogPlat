# Diseño: Comparabilidad estadística con la serie histórica

**Fecha:** 2026-05-24  
**Objetivo:** Permitir comparar los desenlaces de la cohorte 2026-1 (con plataforma) con las cohortes 2022-2 a 2025-2 (sin plataforma), siguiendo exactamente la misma metodología de la Memoria Profesional.

---

## Contexto

La Memoria Profesional (Goyburu 2026) establece una serie de indicadores calculados a partir del Excel `juntas_con_notas_anon.xlsx` (284 estudiantes, cohortes 2023-1 a 2025-1). El hallazgo central es que el 1er parcial opera como "umbral de presencia": el 99.2% de los ausentes al 1P terminan en deserción, y el 80.6% de las deserciones vienen de no presentarse.

La plataforma entra en uso en 2026-1. Para testear si la práctica estructurada con feedback reduce el ausentismo y mejora los desenlaces, los datos de 2026-1 deben ser directamente apilables sobre la serie histórica.

---

## Sección 1 — Cambios de modelo

### `NotaParcial` (cursos/models.py)

Agregar tres campos:

```python
ausente = models.BooleanField(
    default=False,
    verbose_name='ausente al parcial',
)
puntaje_logica = models.DecimalField(
    max_digits=5, decimal_places=2,
    null=True, blank=True,
    verbose_name='puntaje parte lógica',
)
```

El campo existente `puntaje` pasa a ser la **nota global del parcial** (lo que determina el desenlace y sigue la serie).

Semántica:
- `ausente=True, puntaje=None, puntaje_logica=None` → AU (no se presentó)
- `ausente=False, puntaje=None` → nota pendiente de carga
- `ausente=False, puntaje=Decimal(...)` → tiene nota

### `Parcial` (cursos/models.py)

Agregar umbrales opcionales para la categorización de desenlace:

```python
umbral_aprobacion = models.DecimalField(
    max_digits=4, decimal_places=2,
    default=4.00,
    verbose_name='umbral aprobación (sobre 10)',
)
umbral_promocion = models.DecimalField(
    max_digits=4, decimal_places=2,
    default=7.00,
    verbose_name='umbral promoción (sobre 10)',
)
```

Nota: los umbrales operan sobre la nota **normalizada a escala 0–10** (`puntaje / puntaje_total × 10`), igual que la serie histórica.

---

## Sección 2 — Funciones de cálculo (analiticas/calculos.py)

Todas las funciones replican exactamente la metodología del notebook `analisis.ipynb` de la Memoria.

### `calcular_nse(encuesta: EncuestaEstudiante) → tuple[float, str]`

Réplica exacta de `puntaje_nse()` del notebook. Nueve componentes:

| # | Variable | +1 | 0 | -1 | -0.5/+0.5 |
|---|----------|----|----|-----|-----------|
| 1 | Vivienda (`con_quien_vive`) | "sola" | familiar | "comparto" | — |
| 2 | PC escritorio | individual | — | — | — |
| 2 | Portátil | individual | — | — | — |
| 2 | Tablet | individual | — | — | — |
| 2 | Celular | — | individual | no individual | — |
| 3 | Estudios superiores (`estudios_superiores`, `se_recibio_*`) | recibido | — | — | — |
| 4 | UBA XXI (`hizo_uba_xxi`) | sí | — | — | — |
| 5 | Trayectoria CBC | no primer cuatr. AND materias≥2 | — | — | — |
| 6 | Tiempo de viaje (`tiempo_viaje_puan`) | <30 min | 30-60 min | >1 hora | — |
| 7 | Carga laboral | no trabaja + no busca | otras | busca trabajo | <5d+<4hs→+0.5; >5d+>6hs→-1 |
| 8 | Migración (`mudado_para_trabajar_estudiar`) | — | — | sí | — |
| 9 | Discapacidad (`tiene_cud`) | — | — | sí (CUD) | — |

**Categorías** (mismas que la Memoria):
- `puntaje < -2.5` → "Muy bajo"
- `-2.5 ≤ puntaje < -1` → "Bajo"
- `-1 ≤ puntaje < 1` → "Medio bajo"
- `1 ≤ puntaje < 2.5` → "Medio alto"
- `puntaje ≥ 2.5` → "Alto"

Devuelve `(puntaje_float, categoria_str)`.

### `calcular_puntaje_logicas(encuesta: EncuestaEstudiante) → int`

Réplica exacta de `puntaje_logicas()` del notebook. Tres acertijos (0–3 puntos):

| Acertijo | Campo | Respuesta correcta |
|----------|-------|--------------------|
| Silogismo (María/Carmen/Lola) | `acertijo_silogismo` | `'más bajo'` |
| Cirugía (padre/hijo) | `acertijo_cirugia_correcto` | `True` (evaluado por IA) |
| Hilera de casas | `acertijo_hilera` | `'rodriguez'` |

Nota: el 4° acertijo (perros) no forma parte del `puntaje_logicas` en la Memoria — omitido deliberadamente para mantener compatibilidad.

### `calcular_desenlace_parcial(nota_parcial: NotaParcial) → str`

Réplica de `pd.cut(..., bins=[0,1,4,7,10])` del notebook:

1. Si `nota_parcial.ausente` → `'Ausente'`
2. Si `nota_parcial.puntaje is None` → `None` (pendiente)
3. `nota_norm = (puntaje / parcial.puntaje_total) × 10`
4. `nota_norm < parcial.umbral_aprobacion` → `'Aplazo'`
5. `nota_norm < parcial.umbral_promocion` → `'Final'`
6. `nota_norm ≥ parcial.umbral_promocion` → `'Promoción'`

### `calcular_uso_plataforma_antes_parcial(estudiante, parcial) → dict`

Filtra `Intento` del estudiante en la comisión del parcial con `fecha_hora < parcial.fecha`. Calcula:

**Volumen:**
- `intentos_totales`: count total
- `ejercicios_distintos`: distinct ejercicio IDs
- `practicas_abiertas`: distinct PracticaComision con al menos un intento

**Calidad:**
- `ejercicios_resueltos`: ejercicios con al menos un intento correcto
- `tasa_exito`: % intentos correctos / total (0–1)
- `promedio_intentos_hasta_correcto`: promedio de intentos necesarios para el primer acierto, solo sobre ejercicios resueltos

**Temporal:**
- `dias_activos`: días distintos con al menos un intento
- `dias_primer_uso_hasta_1p`: días desde el primer intento hasta `parcial.fecha`
- `dias_ultimo_uso_hasta_1p`: días desde el último intento hasta `parcial.fecha`

**Perfil de errores (11 categorías del clasificador):**
- `err_tautologia`, `err_contradiccion`, `err_polaridad`, `err_mas_fuerte`, `err_mas_debil`
- `err_equivalente_alt`, `err_parcial_1`, `err_parcial_2`, `err_sistematico`
- `err_variables_extra`, `err_variables_menos`

Cada contador = número de intentos incorrectos con esa categoría de error. Se computa solo sobre intentos con `estado='incorrecto'` y `error_categoria` no nulo.

Si el estudiante no tiene encuesta con consentimiento pedagógico, los campos del bloque de uso quedan en `None`.

---

## Sección 3 — Exportación

### Management command: `exportar_cohorte`

```
python manage.py exportar_cohorte <comision_id> [--parcial-id <id>] --output <archivo.csv>
```

Genera un CSV con una fila por estudiante inscripto en la comisión. Tres bloques de columnas:

**Bloque A — Encuesta** (replica el orden de `juntas_con_notas_anon.xlsx`):
`id_anon` (formato `{anio}-{cuatri}-{N}`, donde N es el índice del estudiante dentro de la comisión — nunca expone `username` ni `pk`), `edad` (calculada desde `fecha_nacimiento` al inicio del cuatrimestre), `facultad`, `carrera`, `origen_caba_gba`, `vive_en`, `mudado_con_familia`, `mudado_para_trabajar_estudiar`, `tiempo_mudado`, `desde_donde`, `provincia_origen`, `pais_origen`, `tiene_cud`, `con_quien_vive`, `tiempo_viaje_puan`, `situacion_laboral`, `dias_trabaja`, `acceso_internet`, `celular`, `tablet`, `pc_escritorio`, `computadora_portatil`, `tiempo_desde_secundaria`, `tipo_escuela`, `estudios_superiores`, `termino_cbc_anterior`, `se_recibio_uba`, `se_recibio_fuera_uba`, `hizo_uba_xxi`, `tiempo_en_cbc`, `interrupcion_cbc`, `ya_curso_ipc`, `motivo_no_termino_ipc`, `materias_aprobadas`, `acertijo_silogismo`, `acertijo_cirugia_respuesta`, `acertijo_hilera`, `puntaje_logicas`, `puntaje_nse`, `categoria_nse`, `anio`, `cuatri`

**Bloque B — Desenlace 1P:**
`ausente_1p`, `nota_global_1p`, `nota_logica_1p`, `desenlace_1p`

**Bloque C — Uso de plataforma** (nuevo; `None` si sin consentimiento):
`intentos_totales`, `ejercicios_distintos`, `practicas_abiertas`, `ejercicios_resueltos`, `tasa_exito`, `promedio_intentos_hasta_correcto`, `dias_activos`, `dias_primer_uso_hasta_1p`, `dias_ultimo_uso_hasta_1p`, `err_tautologia`, `err_contradiccion`, `err_polaridad`, `err_mas_fuerte`, `err_mas_debil`, `err_equivalente_alt`, `err_parcial_1`, `err_parcial_2`, `err_sistematico`, `err_variables_extra`, `err_variables_menos`

El CSV resultante es directamente apilable sobre `juntas_con_notas_anon.xlsx` en las columnas del 1P (Bloques A+B), con el Bloque C como columnas adicionales que permiten el análisis de impacto.

---

## Sección 4 — UI: carga de notas con ausente

### `parcial_notas` (template y vista)

Agregar columna "Ausente" con checkbox en la tabla de carga de notas. Comportamiento:

- Checkbox desmarcado (default): campos `puntaje` y `puntaje_logica` habilitados
- Checkbox marcado: ambos campos se deshabilitan (disabled + valor vacío); al guardar, `ausente=True`, `puntaje=None`, `puntaje_logica=None`
- El chip de estado muestra tres estados: **Pendiente** (sin nota ni ausente) / **Ausente** (ausente=True) / **Cargada** (tiene puntaje)
- El contador "X / N notas cargadas" cuenta como cargada tanto si tiene puntaje como si está marcada como ausente

El formset necesita incluir el campo `ausente` además de `puntaje` y `puntaje_logica`.

---

## Mapeo de campos JSONField para NSE

El campo `dispositivos` en `EncuestaEstudiante` es un JSON dict con claves `celular`, `tablet`, `pc_escritorio`, `computadora_portatil`, cada uno con valor `'individual'`, `'compartido'` o `'no tengo'`. El campo `acceso_internet` es una lista de strings. La función `calcular_nse` extrae estos valores del JSON usando las mismas claves y aplica la misma lógica que el notebook original.

---

## Decisiones de diseño tomadas

1. **Nota global vs. lógica**: `puntaje` = global (para seguir la serie); `puntaje_logica` = opcional (para analítica interna). Sin el global no se puede categorizar el desenlace de forma comparable.
2. **4° acertijo omitido**: el notebook de la Memoria no lo incluye en `puntaje_logicas`. Se mantiene la paridad exacta.
3. **Comparación externa**: la plataforma exporta datos; Angeles hace el análisis en Python/R. No se importan datos históricos a Django.
4. **Umbrales configurables**: el `Parcial` guarda sus umbrales (default 4 y 7) para que la categorización sea reproducible sin depender de constantes hardcodeadas externas.
5. **Bloque C solo con consentimiento**: los datos de uso de plataforma son investigación; solo se exportan si `consentimiento_pedagogico=True`.

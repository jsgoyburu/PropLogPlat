# Reporte: fix I6 + I7 (review final de rama, cohorte)

Rama `claude/desbloqueo-configurable`, base `416cc2e`. Alcance estricto:
`ejercicios/management/commands/corregir_ejercicio_juicio.py`,
`ejercicios/management/commands/reconciliar_V_mayuscula.py`,
`ejercicios/management/commands/recorregir_tabla_verdad.py`,
`analiticas/anonimizador.py`. No se tocó ningún otro archivo (verificado con
`git status --porcelain` antes y después: los siete archivos sucios de otro
arreglo en curso quedaron exactamente como estaban).

## I6 — Los tres management commands ciegos a la cohorte

Referencia de patrón: `60edc47` (`reconciliar_progreso_aprobaciones.py` y
`reevaluar_tablas_verdad.py`), que ya deriva `cohorte_id` del propio `Intento`
que dispara la reconciliación y lo propaga a todas las queries de `Progreso`
e `Intento` involucradas.

### `reconciliar_V_mayuscula.py`

- La clave de `progreso_pendiente` (línea ~135) pasó de
  `(estudiante_id, practica_comision_id, practica_id)` a
  `(estudiante_id, practica_comision_id, cohorte_id, practica_id)`, tomando
  `cohorte_id` de `intento.cohorte_id` (cada `Intento` candidato ya lo trae).
- El loop de avance de progreso (línea ~145) desempaqueta la tupla con
  `cohorte_id` y lo pasa a `_avanzar_progreso`.
- `_avanzar_progreso` (staticmethod, línea ~184) ahora recibe `cohorte_id`
  como parámetro y filtra `Progreso.objects...filter(estudiante_id=...,
  practica_comision_id=..., cohorte_id=...)` en vez de `.filter(estudiante_id,
  practica_comision_id).first()`.
- La clave de caché de analíticas (`comisiones_afectadas`, línea ~138-140) ya
  estaba corregida por un pase anterior (usa `(comision_id, intento.cohorte_id)`);
  no se tocó.

### `corregir_ejercicio_juicio.py`

- `pares_afectados` (línea ~113-119) pasó a incluir `intento.cohorte_id`
  junto a `estudiante_id`, `practica_comision_id` y `practica_id`.
- El loop que llama a `_reconciliar_progreso` (línea ~140) desempaqueta la
  tupla de 4 elementos.
- `_reconciliar_progreso` (línea ~149) recibe `cohorte_id` y lo agrega tanto
  al `.filter()` de `Progreso` (select_for_update) como al `.filter()` de
  `Intento` dentro del `while` que busca el primer EP sin intento aprobado.

### `recorregir_tabla_verdad.py`

- Mismo patrón: `pares_afectados` (línea ~118-122) agrega `intento.cohorte_id`;
  el loop (línea ~132) desempaqueta 4 elementos; `_reconciliar_progreso`
  (línea ~144) recibe y filtra por `cohorte_id` en la query de `Progreso`
  (select_for_update) y en la query de `Intento` dentro del `while`.

En los tres casos la cohorte sale directamente de `intento.cohorte_id` — el
mismo `Intento` que originó la corrección — igual que en `60edc47`. No hace
falta ningún join ni lookup adicional porque `Intento.cohorte` es `NOT NULL`
(FK sin `null=True`, ver `ejercicios/models.py` línea 373-378).

## I7 — Dataset de intentos ignoraba `Intento.cohorte`

`analiticas/anonimizador.py`, función `dataset_intentos` (línea ~298-391).

El filtro `anio`/`cuatri` ya se aplicaba a la query de `Inscripcion` (línea
~332-335) para construir `est_comision` (mapa estudiante→comisión). Pero la
query de `Intento` (línea ~347-361) solo filtraba por
`estudiante_id__in=est_comision` y por comisión — sin cohorte. Un recursante
con inscripciones en 2026-C1 y 2027-C1 en la misma comisión aparecía en
`est_comision` filtrado a 2027-C1, pero sus intentos de 2026-C1 se colaban
igual porque no había filtro de cohorte en la query de `Intento`.

Fix: agregado, después de armar el queryset `qs` de `Intento`, el mismo
patrón que ya usa `dataset_encuesta` (línea ~272-275) y la query de
`Inscripcion` de esta misma función:

```python
if anio is not None:
    qs = qs.filter(cohorte__anio=anio)
    if cuatri is not None:
        qs = qs.filter(cohorte__cuatrimestre=cuatri)
```

Se filtra sobre `cohorte__anio`/`cohorte__cuatrimestre` directamente en
`Intento` (FK propia, `NOT NULL`), tal como pedía el enunciado — no se agregó
ningún join nuevo, `Intento.cohorte` ya está disponible.

## Cómo verifiqué (sin tests)

1. Lectura completa de cada función modificada (no solo la línea tocada),
   comparando contra el patrón ya aplicado en `60edc47` a los dos comandos
   hermanos.
2. `git diff --stat` limitado a los cuatro archivos de alcance — confirmado
   que no se tocó nada más.
3. `git status --porcelain` antes/después — los siete archivos sucios de otro
   arreglo en curso (`analiticas/views.py`, `analiticas/tests.py`,
   `docentes/views.py`, `docentes/tests.py`, `ejercicios/views.py`,
   `ejercicios/tests.py`, `templates/docentes/comision_detail.html`) quedaron
   intactos.
4. Import directo de `analiticas.anonimizador` con `django.setup()`:
   ```
   $env:SECRET_KEY='x'; $env:PYTHONIOENCODING='utf-8'
   python -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','logica_ipc.settings'); django.setup(); import analiticas.anonimizador; print('ok')"
   ```
   → `ok`.
5. `python manage.py help <comando>` para los tres management commands
   (carga el módulo completo, incluyendo el parser de argumentos y los
   imports de nivel de módulo) → los tres cargan sin error y muestran su
   `--help` correctamente.
6. `python manage.py check` sobre el proyecto completo (incluye los archivos
   sucios de terceros, no solo los míos) → "System check identified no
   issues (0 silenced)".

Estas verificaciones cubren sintaxis, imports y carga de Django, pero **no
ejecutan la lógica de negocio** (no hay fixtures de `Intento`/`Progreso`/
`Cohorte` corridos). La corrección del comportamiento se apoya en la lectura
cuidadosa y el paralelismo exacto con el patrón ya probado en `60edc47`.

## Deuda de tests para un pase posterior

En `ejercicios/tests.py` (siguiendo el estilo de los tests que `60edc47` ya
agregó para `reconciliar_progreso_aprobaciones` y `reevaluar_tablas_verdad`):

- `reconciliar_V_mayuscula`: un estudiante recursante (dos `Inscripcion`/dos
  `Progreso` para el mismo `practica_comision`, distinta `cohorte`) con un
  intento de formalización afectado por el bug de "V" mayúscula en la
  cohorte más reciente — verificar que `_avanzar_progreso` toca únicamente el
  `Progreso` de esa cohorte y no el de la otra.
- Caso de regresión explícito: sin el fix, `.filter(estudiante_id,
  practica_comision_id).first()` podía devolver el `Progreso` de la cohorte
  vieja y avanzarlo incorrectamente (o dejar sin avanzar el de la cohorte
  correcta) — un test que falle antes del fix y pase después.
- `corregir_ejercicio_juicio`: mismo escenario de recursante pero con
  ejercicio `tabla_verdad`/`juicio`, usando `--ejercicio-id`.
- `recorregir_tabla_verdad`: mismo escenario de recursante con
  `tabla_verdad` y `tabla_json` guardado (bug de comparación posicional).
- Los tres comandos en modo `--dry-run` con recursantes: confirmar que no
  se guarda nada y que el conteo reportado sigue siendo correcto por
  cohorte (no doble-cuenta ni mezcla camadas).

En `analiticas/tests.py`:

- `dataset_intentos` con un estudiante recursante inscripto en 2026-C1 y
  2027-C1 en la misma comisión, con intentos en ambas cohortes: pedir
  `anio=2027, cuatri=1` y verificar que la lista devuelta **no** incluye los
  intentos de 2026-C1 del mismo estudiante (antes del fix, sí los incluía).
- Caso sin filtro (`anio=None`): verificar que siguen apareciendo los
  intentos de todas las cohortes (no regresionar el caso default).
- Caso de intento histórico con `practica_comision__isnull=True` (dato
  previo a `PracticaComision`) combinado con filtro de cohorte: confirmar
  que el filtro de cohorte sigue aplicando correctamente incluso cuando
  `practica_comision` es NULL (dado que el filtro nuevo es directo sobre
  `Intento.cohorte`, no depende de `practica_comision`).

## Dudas / riesgos

- No corrí ningún test contra una base de datos real (los archivos de test
  correspondientes están fuera de alcance en este pase), así que la
  verificación es por lectura + paralelismo con `60edc47`, no por ejecución.
  El riesgo residual más alto es algún caso borde no cubierto por el patrón
  de referencia (p. ej. algún `Intento` histórico con `cohorte_id` que no
  coincida con lo esperado), que solo un test con fixtures reales
  confirmaría.
- No encontré otros `.filter(estudiante_id=..., practica_comision_id=...)`
  sin cohorte en los cuatro archivos de alcance después del fix — la
  cobertura debería ser completa para estos archivos.
- `Intento.cohorte` es `on_delete=models.PROTECT`, así que no hay riesgo de
  `cohorte_id` nulo por borrado en cascada; el `NOT NULL` de la columna es
  confiable como precondición para todos los filtros agregados.

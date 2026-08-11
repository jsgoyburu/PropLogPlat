# Auditoría QA profunda — módulo `motor`

**Fecha:** 2026-03-29 (UTC)  
**Rol:** QA (sin cambios de código funcional)  
**Objetivo:** auditar flujos del módulo `motor` y detectar fallos o riesgos antes de implementación de fixes.

---

## 1) Resumen ejecutivo

El motor lógico funciona correctamente en su núcleo de parseo/equivalencia para gran parte de los casos cubiertos, pero la auditoría detectó **dos problemas funcionales relevantes en el flujo de argumentos (`tabla_verdad`)** y **varios problemas de calidad/consistencia en tests y tooling**.

### Estado general

- ✅ Parseo y verificación semántica básica (formalización): mayormente consistente.
- ⚠️ Flujo de argumentos: se detectaron bypasses de validación en la corrección de tabla cargada por estudiante.
- ⚠️ Suite `motor/tests`: hay desalineación entre expectativas de tests y comportamiento real/documentado (5 fails).
- ⚠️ Script de auditoría existente `tests/playwright/tests_audit_motor.py` tiene defectos de ejecución/import y de API interna.

### Severidades

- **Crítico (1):** se puede obtener `correcto=True` en argumento enviando `tabla_estudiante=None`.
- **Alto (1):** se puede obtener `correcto=True` enviando solo columnas finales (`P1/P2/.../C`) y omitiendo variables/subcolumnas.
- **Medio (2):** desalineación de tests/documentación del orden de tabla; script de auditoría roto parcialmente.
- **Bajo (1):** asimetría de validación de ambigüedad (se valida estudiante, no siempre solución).

---

## 2) Alcance auditado

### Código revisado

- `motor/parser.py`
- `motor/tabla.py`
- `motor/verificador.py`
- `motor/tests/test_parser.py`
- `motor/tests/test_tabla.py`
- `motor/tests/test_verificador.py`
- `ejercicios/api/views.py`
- `ejercicios/api/serializers.py`
- `tests/playwright/tests_audit_motor.py`

### Flujos auditados

1. **Parseo** (`parsear`, `normalizar_simbolos`, validación de paréntesis mixtos).
2. **Generación de tabla de verdad** (`generar_tabla_desde_expr`, `generar_tabla`).
3. **Verificación de formalización** (`verificar`).
4. **Verificación de argumentos** (`verificar_argumento`) incluyendo chequeo de tabla ingresada.
5. **Integración API** (`POST /api/intentos/`, serializer y ramas por tipo de ejercicio).
6. **Tooling QA existente** (`tests/playwright/tests_audit_motor.py`).

---

## 3) Metodología

Se combinaron:

- **Revisión estática profunda** de implementación y contratos internos.
- **Ejecución de tests existentes** del motor y tests Django específicos de preview de argumento.
- **Pruebas dirigidas ad hoc** con `python - <<'PY' ... PY` para reproducir edge-cases en runtime.

### Comandos ejecutados (trazabilidad)

- `pytest motor/tests -q`
- `SECRET_KEY=test-secret python manage.py test ejercicios.tests.PreviewArgumentoApiTests -v 2`
- `python tests/playwright/tests_audit_motor.py --verbose`
- `PYTHONPATH=. python tests/playwright/tests_audit_motor.py --verbose`
- Snippets ad hoc sobre `verificar()` / `verificar_argumento()` para reproducir bypasses.

---

## 4) Hallazgos detallados

## H-01 (CRÍTICO) — Bypass de corrección: `verificar_argumento` acepta `tabla_estudiante=None`

**Severidad:** Crítico  
**Estado:** Reproducido

### Evidencia

Reproducción directa en runtime:

```python
from motor.verificador import verificar_argumento

ens = [
    {'formula': 'p -> q', 'tipo': 'premisa'},
    {'formula': 'p', 'tipo': 'premisa'},
    {'formula': 'q', 'tipo': 'conclusion'},
]
res = verificar_argumento(ens, ens, True, tabla_estudiante=None)
print(res['correcto'], res['tabla_ok'], res['enunciados_ok'])
# True True True
```

Resultado observado: devuelve `correcto=True` aunque no hay tabla completada.

### Causa técnica

En `verificar_argumento`, `tabla_ok` y `enunciados_ok` inicializan en `True` y el bloque de validación de tabla solo corre si `tabla_estudiante is not None`. Si llega `None`, se preservan en `True` y el `correcto` final puede ser verdadero si coinciden fórmulas + juicio.

### Impacto

- Rompe el flujo pedagógico esperado de ejercicios tipo tabla de verdad.
- Permite bypass desde API (payload manipulado) aunque frontend normal sí envíe tabla.
- Debilita trazabilidad del proceso de razonamiento (principios pedagógicos del proyecto).

### Recomendación para implementación

- En rama `tabla_verdad`, hacer `tabla_estudiante` **obligatoria** (serializer + validación server-side).
- En `verificar_argumento`, si `tabla_estudiante` es `None`, devolver `tabla_ok=False` y mensaje explícito.
- Agregar tests de no-regresión para payload sin tabla.

---

## H-02 (ALTO) — Se aprueba tabla incompleta: solo columnas finales de enunciado

**Severidad:** Alto  
**Estado:** Reproducido

### Evidencia

Se puede construir `tabla_estudiante` con solo `columnas_enunciados` (omitiendo variables y subcolumnas) y obtener `correcto=True`:

```python
from motor.verificador import verificar_argumento

ens=[
  {'formula':'p -> q','tipo':'premisa'},
  {'formula':'p','tipo':'premisa'},
  {'formula':'q','tipo':'conclusion'}
]
base = verificar_argumento(ens, ens, True, tabla_estudiante=None)
cols = base['columnas_enunciados']
tabla_min = [{c: row[c] for c in cols} for row in base['tabla_con_subcolumnas']]
res = verificar_argumento(ens, ens, True, tabla_estudiante=tabla_min)
print(res['correcto'], res['tabla_ok'], res['enunciados_ok'])
# True True True
```

### Causa técnica

- Se valida celda por celda solo sobre columnas **presentes** en `tabla_estudiante`.
- No hay check estricto de esquema contra `columnas_tabla` (que sí se calcula).
- Las variables y subcolumnas omitidas no fuerzan fallo.

### Impacto

- Se puede resolver parcialmente el ejercicio evitando parte del trabajo formativo.
- Se pierde visibilidad del proceso intermedio (subfórmulas), que es objetivo explícito del sistema.

### Recomendación para implementación

- Validar que cada fila tenga exactamente todas las columnas de `columnas_tabla`.
- Validar cantidad exacta de filas (`2^n`).
- Rechazar columnas faltantes/sobrantes con feedback explícito.

---

## H-03 (MEDIO) — Suite `motor/tests` con 5 fallos por desalineación de orden/tablas

**Severidad:** Medio  
**Estado:** Reproducido

### Evidencia

`pytest motor/tests -q` → `5 failed, 99 passed`.

Fallos concentrados en `motor/tests/test_tabla.py` con expectativa de orden de filas/columnas distinto al real. Ejemplo: para `p | q`, el test espera `TT, TF, FT, FF`, pero implementación actual usa orden por primera aparición en expresión (y sympy puede alterar orden estructural interno en expresiones equivalentes).

### Observación técnica

No es necesariamente bug funcional del motor; sí es **inconsistencia de contrato** entre:

- comportamiento implementado,
- docstrings/comentarios en distintas capas,
- expectativas de tests.

### Impacto

- Señal de calidad degradada en CI del módulo.
- Dificulta saber si futuras regresiones son reales o ruido.

### Recomendación para implementación

- Definir contrato único explícito para orden de variables/filas (display vs comparación).
- Alinear `test_tabla.py` y docstrings (`generar_tabla` actualmente menciona alfabético en texto, pero tabla base opera por aparición).
- Separar tests de “orden de presentación” de tests de “equivalencia semántica”.

---

## H-04 (MEDIO) — Script `tests/playwright/tests_audit_motor.py` parcialmente roto

**Severidad:** Medio  
**Estado:** Reproducido

### Evidencia

- Ejecutado sin `PYTHONPATH=.`, falla import `motor`.
- Aún con `PYTHONPATH=.`, sección de tablas falla por importar `generar_tabla` desde `motor.tabla` (función pública está en `motor.verificador` en este repo).
- Depende de servidor live y endpoint opcional; no degrada elegantemente en todos los casos.

### Impacto

- La herramienta de auditoría da falsos negativos y reduce utilidad QA.

### Recomendación para implementación

- Corregir imports y runner path-safe.
- Parametrizar modo “sin servidor” y modo “con servidor”.
- Alinear con API pública real (`from motor.verificador import generar_tabla, verificar`).

---

## H-05 (BAJO) — Asimetría de validación de ambigüedad en solución vs estudiante

**Severidad:** Bajo  
**Estado:** Detectado por revisión estática

### Observación

Se aplica `validar_parentesis_en_operaciones_mixtas()` al input del estudiante en `verificar`/`verificar_argumento`, pero no siempre a fórmulas de solución docente.

### Riesgo

- Puede haber discrepancias pedagógicas si solución cargada usa mezcla sin paréntesis que para estudiantes se rechazaría.

### Recomendación

- Evaluar política uniforme: misma validación para solución en alta/preview.

---

## 5) Cobertura de flujos (matriz)

| Flujo | Estado | Comentario |
|---|---|---|
| Parseo notación Copi/ASCII | ✅ | Funciona en casos principales; mensajes de error adecuados. |
| Equivalencia tabular (formalización) | ✅ | Funciona; contempla tautología/contradicción por diseño. |
| Validación operaciones mixtas en respuesta estudiante | ✅ | Rechaza mezcla binaria sin paréntesis. |
| Generación de tablas (`generar_tabla`) | ⚠️ | Funcional, pero contrato de orden desalineado con tests/docs. |
| Verificación de argumentos (fórmulas + juicio) | ✅ | Matching semántico robusto con renombre de variables. |
| Verificación de tabla completada por estudiante | ❌ | Bypass por `None` y por columnas faltantes. |
| Integración `POST /api/intentos/` tipo `tabla_verdad` | ⚠️ | Hereda bypasses porque serializer no exige tabla estricta. |
| Herramienta `tests_audit_motor.py` | ❌ | Fallos de import/API que afectan la auditoría. |

---

## 6) Plan sugerido de implementación (para Claude Sonnet 4.6)

### Prioridad 1 (bloqueante)

1. Blindar `verificar_argumento` contra `tabla_estudiante=None`.
2. Validación estricta de esquema de tabla:
   - filas exactas,
   - columnas exactas (`columnas_tabla`),
   - tipos booleanos esperados.
3. Tests de no-regresión API (`/api/intentos/`) con payload manipulado.

### Prioridad 2

4. Unificar contrato de orden de tabla (display vs comparación) y actualizar tests/doc.
5. Corregir script de auditoría (`tests/playwright/tests_audit_motor.py`).

### Prioridad 3

6. Revisar política de validación de ambigüedad para fórmulas de solución.

---

## 7) Criterio de cierre QA propuesto

Se recomienda considerar “apto” el módulo cuando:

- `pytest motor/tests -q` queda 100% en verde.
- Existen tests que fallan si `tabla_estudiante` falta o está incompleta.
- `POST /api/intentos/` rechaza payloads manipulados en `tabla_verdad`.
- El script de auditoría corre en limpio (con y sin servidor, según modo elegido) y reporta consistentemente.

---

## 8) Nota final

Esta auditoría fue intencionalmente **sin cambios de código funcional** (rol QA), enfocada en detectar riesgos y dejar evidencia reproducible para implementación posterior.

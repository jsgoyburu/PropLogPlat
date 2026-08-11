# Auditoría QA profunda — módulo `analiticas`

**Fecha:** 2026-03-29 (UTC)  
**Rol ejecutado:** QA (sin cambios funcionales de código)  
**Destinatario de implementación:** Claude Sonnet 4.6  
**Estado general:** ❌ **No apto para cierre sin remediación** (hay defectos de integridad de métricas y deuda de tests críticos)

---

## 1) Alcance auditado

Se auditó de punta a punta el módulo `analiticas` y sus integraciones directas:

- Routing y permisos:
  - `analiticas/urls.py`
  - `analiticas/views.py` (`dashboard`, `investigacion`, `exportar`)
- Cálculo de métricas de investigación:
  - `analiticas/research.py`
- Cobertura QA automatizada existente:
  - `analiticas/tests.py`
- Superficie UI relevante:
  - `templates/analiticas/dashboard.html`
  - `templates/analiticas/investigacion.html`

---

## 2) Metodología de auditoría

1. **Lectura estática profunda** de vistas, funciones analíticas y templates para revisar:
   - consistencia de filtros por comisión,
   - consistencia con consentimiento,
   - integridad de agregaciones,
   - coherencia dashboard operativo vs investigación,
   - robustez de exportaciones.
2. **Ejecución de checks y suite del módulo**:
   - `python manage.py check`
   - `python manage.py test analiticas -v 2`
3. **Trazabilidad de hallazgos** con evidencia reproducible (stack traces + referencias precisas a archivos).

---

## 3) Resultado ejecutivo

Se detectaron **5 hallazgos críticos/altos** y **4 hallazgos medios**, con impacto principal en:

- **Validez pedagógica de métricas** (contaminación cross-comisión).
- **Confiabilidad de QA** (suite de `analiticas` completamente rota).
- **Riesgo de decisiones docentes con datos sesgados** en dashboard operativo.

La implementación actual contradice parcialmente los principios del proyecto de *transparencia* e *interpretabilidad pedagógica* cuando una misma práctica/EP participa en más de una comisión.

---

## 4) Hallazgos priorizados

## H-01 (CRÍTICO) — El dashboard operativo mezcla datos entre comisiones para prácticas compartidas

**Síntoma funcional**
En `dashboard`, los cálculos por práctica dentro de cada comisión no filtran por `PracticaComision`/comisión al contar `Progreso` e `Intento`; filtran solo por `practica`. Esto puede mezclar estudiantes de otras comisiones cuando la práctica está reutilizada/importada.

**Evidencia técnica**
Dentro del loop por `pc` de una comisión:

- `completaron` usa `Progreso.objects.filter(practica=practica, ...)`.
- `total_intentos` usa `Intento.objects.filter(ejercicio_practica__practica=practica)`.
- `intentos_correctos` idem.

No hay restricción por `pc` ni por `practica_comision__comision_id` en esos conteos.  

**Impacto**
- Métricas por comisión pueden inflarse o distorsionarse.
- Docente de comisión A puede ver comportamiento agregado de comisión B en tasas de acierto/completitud.
- Riesgo alto de intervención pedagógica mal dirigida.

**Severidad:** Crítica.

**Sugerencia de implementación**
- Cambiar los filtros de `dashboard` para que sean **siempre por `PracticaComision` de la comisión actual**.
- En `Progreso`, restringir por estudiantes inscriptos en la comisión además de la práctica.
- Agregar tests de regresión con una práctica compartida entre dos comisiones con perfiles de intentos distintos.

---

## H-02 (CRÍTICO) — Suite QA de `analiticas` totalmente quebrada por fixtures legacy

**Síntoma funcional**
La suite `python manage.py test analiticas -v 2` falla en 32/32 tests.

**Evidencia de ejecución**
Errores sistemáticos:
- `TypeError: Practica() got unexpected keyword arguments: 'comision', 'orden'`
- `TypeError: EncuestaEstudiante() got unexpected keyword arguments: 'acertijo_cirugia_no_se'`

Esto revela que los tests siguen modelando un esquema anterior (pre-`PracticaComision` y pre-colapso de `acertijo_cirugia_no_se`).

**Impacto**
- Cobertura automatizada **inutilizable** para prevenir regresiones.
- Cualquier cambio en analíticas queda sin red de seguridad real.
- Bloquea releases confiables de investigación y dashboard.

**Severidad:** Crítica.

**Sugerencia de implementación**
- Refactor completo de fixtures a esquema vigente:
  - Crear `Practica` + `PracticaComision` (sin `comision`/`orden` en `Practica`).
  - Ajustar onboarding research a campo unificado de cirugía.
- Separar tests por capas (`views`, `research`, `exportar`) para aislar fallos.
- Objetivo mínimo: suite verde + 2 tests nuevos de no contaminación entre comisiones.

---

## H-03 (ALTO) — Métricas de research por EP/comisión con asignación ambigua cuando un EP está en múltiples comisiones

**Síntoma funcional**
Funciones como `persistencia_relativa` e `intentos_hasta_correcto_sin_sesgo` construyen `ep_comision` con un `dict()` sobre un queryset que puede devolver múltiples filas por `ep_id` (si la práctica asociada está en múltiples comisiones), quedándose con “la última”.

**Impacto**
- `comision_id` en output puede ser arbitrario/no determinista.
- Gráficos/tablas y exportables pueden atribuir mal resultados.

**Severidad:** Alta.

**Sugerencia de implementación**
- Diseñar salida explícitamente multicomisión por EP (`ep_id`,`comision_id`) o filtrar intentos por `practica_comision__comision_id` antes de agregar.
- Evitar mapeos `dict(ep_id -> comision_id)` cuando la cardinalidad real es 1:N.

---

## H-04 (ALTO) — `tasa_abandono_local` usa mapeo por `practica_id` y puede pisar comisiones

**Síntoma funcional**
`pcs_info` está indexado por `practica_id`; si la práctica existe en varias comisiones, una pisa a otra y el EP hereda un único `comision_id/fecha_cierre` potencialmente incorrecto.

**Impacto**
- `practica_cerrada`, `tasa_abandono` y `comision_id` reportados pueden corresponder a otra comisión.
- Distorsiona análisis de “muro” y abandono local.

**Severidad:** Alta.

**Sugerencia de implementación**
- Elevar la unidad analítica a `(ep_id, comision_id)` desde el origen.
- Filtrar intentos por comisión efectiva y calcular `cerrada` con `PracticaComision` correcto para esa comisión.

---

## H-05 (ALTO) — Ordenamiento defectuoso en `_distribucion_intentos`: `None` puede subir al tope

**Síntoma funcional**
El sort actual usa:
`resultado.sort(key=lambda x: (x['promedio'] is None, x['promedio'] or 0), reverse=True)`

Con `reverse=True`, las filas con `promedio is None == True` tienden a quedar antes que las válidas.

**Impacto**
- Prioriza ejercicios sin promedio (sin resueltos) por encima de ejercicios realmente difíciles con datos válidos.
- Lectura docente confusa.

**Severidad:** Alta.

**Sugerencia de implementación**
- Orden ascendente por tupla invertida (o dos etapas) para dejar `None` al final explícitamente.
- Agregar test unitario para orden esperado con mezcla de `None` y numéricos.

---

## H-06 (MEDIO) — `dashboard` podría mostrar progreso de estudiantes no acotado por comisión

Aun corrigiendo conteos de intentos, el cálculo de `completaron` debería filtrar estudiantes inscriptos en la comisión actual; hoy depende solo de `practica`. Si un estudiante tiene progreso de esa práctica en otra comisión, puede contaminar.

**Severidad:** Media (sube a alta en escenarios multi-comisión).

---

## H-07 (MEDIO) — Riesgo de inconsistencia conceptual en “arranque tardío”

`_velocidad_arranque` toma como “apertura” el primer intento global observado en la práctica (no `fecha_apertura` configurada en `PracticaComision`). Esto puede sesgar el indicador si hay silencio inicial prolongado o carga histórica.

**Severidad:** Media.

**Sugerencia**
Migrar definición a `fecha_apertura` por `PracticaComision` cuando exista; usar fallback actual solo si falta fecha.

---

## H-08 (MEDIO) — Dependencia CDN externa para Chart.js sin fallback robusto

Si falla CDN, hay fallback parcial en algunos gráficos pero no homogéneo en toda la página de investigación (donde hay varios `canvas` y scripts). Riesgo de UI incompleta sin mensaje claro en todos los paneles.

**Severidad:** Media.

---

## H-09 (MEDIO) — Exportación: validación funcional correcta pero sin tests de contrato por dataset/formato

El flujo `exportar` está bien estructurado, pero sin tests específicos por dataset/formato/mimetype/headers, queda expuesto a regresiones silenciosas.

**Severidad:** Media.

---

## 5) Flujos auditados (matriz)

| Flujo | Resultado | Observación QA |
|---|---|---|
| Acceso `dashboard` por docente/admin | ✅ funcional | Permisos correctos, pero métricas pueden contaminarse entre comisiones. |
| Acceso `dashboard` por estudiante | ✅ funcional | Redirección a `ejercicios:home` correcta. |
| KPIs por práctica en dashboard | ❌ defectuoso | Riesgo alto por filtros insuficientes por comisión. |
| Señales de alerta (`en_riesgo`, silencio, concentración) | ⚠️ parcial | Cálculos ejecutan, pero dependen de integridad de filtrado base. |
| Acceso `investigacion` | ✅ funcional | Gate por rol correcto. |
| Filtro de consentimiento en investigación | ✅ mayormente correcto | Aplicado en métricas principales; buena alineación pedagógica. |
| Exportación CSV/XLSX/ODS | ✅ funcional básico | Falta cobertura automática de contrato por formato/dataset. |
| Tests automáticos del módulo | ❌ roto | 32 errores por fixtures/modelos legacy. |

---

## 6) Plan de implementación sugerido (para Claude Sonnet 4.6)

## Fase 1 — Estabilización crítica (bloqueante)
1. Corregir filtros en `dashboard` por comisión/`PracticaComision`.
2. Corregir unidad analítica en research a `(ep_id, comision_id)` donde aplica.
3. Corregir `tasa_abandono_local` para evitar pisado por `practica_id`.
4. Corregir sort de `_distribucion_intentos` (`None` al final).

## Fase 2 — Recuperar red QA
1. Reescribir fixtures de `analiticas/tests.py` al esquema vigente.
2. Añadir tests multi-comisión de no contaminación (mínimo 3 casos):
   - dashboard por práctica,
   - `persistencia_relativa`,
   - `tasa_abandono_local`.
3. Añadir tests de contrato de exportación (`Content-Type`, `Content-Disposition`, columnas).

## Fase 3 — Robustez pedagógica
1. Revisar definición de `_velocidad_arranque` con `fecha_apertura` real.
2. Homogeneizar fallback visual cuando no carga Chart.js.

---

## 7) Criterios de aceptación QA

Se considera resuelto cuando:

- `python manage.py test analiticas -v 2` pasa en verde.
- Existe evidencia testeada de que una práctica compartida entre dos comisiones produce métricas distintas y correctas por comisión.
- `dashboard` no mezcla intentos/progresos cross-comisión.
- `tasa_abandono_local`, `persistencia_relativa` e `intentos_hasta_correcto_sin_sesgo` reportan `comision_id` determinista y correcto.
- Orden de `_distribucion_intentos` deja filas sin promedio al final.

---

## 8) Evidencia de comandos ejecutados

- `SECRET_KEY=test-secret python manage.py check` → OK.
- `SECRET_KEY=test-secret python manage.py test analiticas -v 2` → FAIL (32 errores), principalmente por fixtures legacy incompatibles con modelos actuales.

---

## 9) Conclusión QA

El módulo `analiticas` muestra una intención pedagógica sólida (especialmente en consentimiento y explicabilidad), pero hoy tiene **riesgo alto de integridad de datos por comisión** y **falla total de su suite de tests**. 

Recomiendo tratar H-01 y H-02 como **bloqueantes de release** y ejecutar el plan por fases arriba antes de cualquier ampliación funcional.

# Plan de Implementación Unificado QA — Claude Sonnet 4.6

**Fecha:** 2026-03-29 (UTC)  
**Autor:** Codex (rol QA)  
**Estado:** versión ampliada (incluye principios operativos completos + orden estricto de fases)

---

## 0) Alcance y fuentes obligatorias

Este plan consolida las auditorías de `docs/auditorias/` y define la secuencia de implementación segura.

### Fuentes mínimas a contrastar (lectura obligatoria)
1. `2026-03-29_auditoria_QA_modulo_ejercicios.md`
2. `auditoria_qa_motor_2026-03-29.md`
3. `qa_docentes_auditoria_2026-03-29.md`
4. `2026-03-29-auditoria-modulo-cursos.md`
5. `QA_AUDIT_ACCOUNTS_2026-03-29.md`
6. `2026-03-29_auditoria_QA_modulo_analiticas.md`
7. `QA_AUDITORIA_FLUJOS_2026-03-29.md`
8. `2026-03-29_auditoria_QA_performance_concurrencia_200.md`
9. `2026-03-29_auditoria_ISO_IEC_9126_sistema.md`
10. `2026-03-29_addendum_QA_correcciones_criticas.md`

**Regla de actualización:** antes de ejecutar fases, correr `rg --files docs/auditorias | sort` y registrar toda auditoría nueva en la línea base.

---

## 1) Principios de operación (obligatorios, no negociables)

Estos principios deben guiar cada fix técnico:

1. **Primacía pedagógica:** la plataforma asiste práctica y verificación formal; no reemplaza juicio docente.
2. **Arquitectura híbrida humano-máquina:** máquina verifica y registra; docente interpreta y evalúa.
3. **Error visible y trazable:** evitar “correcciones invisibles”; toda falla relevante debe ser explicable.
4. **Equivalencia semántica > coincidencia literal:** preservar pluralidad de formalizaciones válidas.
5. **Interpretabilidad > sofisticación opaca:** evitar soluciones imposibles de justificar didácticamente.
6. **Aislamiento operativo docente por comisión:** métricas/acciones docentes nunca deben contaminarse con otras comisiones.
7. **Cobertura investigativa global:** investigación/exportación debe preservar dataset total, incluyendo legacy `practica_comision=None`.
8. **QA primero:** sin red de tests estable no se habilitan cambios de negocio/concurrencia/performance.
9. **Cambios incrementales con evidencia:** toda fase exige reproducción, fix mínimo, no-regresión y riesgos residuales.

---

## 2) Correcciones de puntos ciegos incorporadas

### C-01 — Riesgo de pérdida de datos históricos (Data Loss)
- Problema: filtrado estricto universal por `practica_comision` elimina registros legacy.
- Resolución obligatoria: bifurcar por consumidor de datos (docente vs investigación).

### C-02 — Error lógico crítico en dashboard docente
- Problema: contar completados sin filtro de comisión mezcla cohortes.
- Resolución obligatoria: filtros estrictos de comisión en vistas operativas docentes.

### C-03 — N+1 oculto en `docentes/views.py`
- Problema: `comision.practicas_comisiones.count()` dentro de loop.
- Resolución obligatoria: agregación/annotate o precálculo fuera del loop.

### C-04 — Middleware rompe frontend API
- Problema: `/api/*` recibe 302 HTML cuando frontend espera JSON.
- Resolución obligatoria: excluir `/api/` del redirect HTML y devolver HTTP/JSON semántico (401/403 según caso).

---

## 3) Modelo fundacional de doble consumidor de datos

### Consumidor A — Docente (operativo)
- Scope: solo su comisión.
- Objetivo: intervención pedagógica concreta en cohortes propias.
- Regla técnica: filtros estrictos por comisión en dashboards y gestión.

### Consumidor B — Investigador (global)
- Scope: toda la plataforma.
- Objetivo: análisis longitudinal/global y exportación.
- Regla técnica: incluir datos históricos legados, incluso `practica_comision=None`.

### Contrato transversal
Todo endpoint, queryset o export debe declarar explícitamente qué consumidor sirve.

---

## 4) Orden estricto de implementación (obligatorio)

> **No avanzar de fase sin cumplir criterios de salida.**  
> **No tocar optimización pesada/concurrencia antes de estabilizar tests.**

### FASE 0 (Bloqueante Absoluto) — Estabilización de QA

1. Actualizar fixtures obsoletos al modelo `PracticaComision`.
2. Corregir tests rotos por middleware de onboarding/password.
3. Unificar helpers de usuario “listo para cursar” para evitar falsos 302.
4. Ejecutar baseline:
   - `python manage.py check`
   - `python manage.py test -v 1`
   - `pytest motor/tests -q`

**Salida FASE 0**
- suite utilizable como red de seguridad,
- fallos residuales (si existen) clasificados y acotados,
- evidencia de comandos + salida archivada.

---

### FASE 1 — Integridad lógica y aislamiento de vistas

1. Cerrar bypass en API de intentos (fechas + orden progresivo + comisión determinística).
2. Corregir error lógico del dashboard docente (filtro estricto por comisión).
3. Implementar bifurcación por consumidor:
   - docente: aislado por comisión,
   - investigación/exportación: global + legacy null.
4. Excluir `/api/` del middleware de redirect HTML y devolver JSON/HTTP correcto.

**Salida FASE 1**
- bypass API cerrado,
- dashboard docente sin contaminación,
- investigación/export mantiene dataset histórico completo,
- frontend JS sin parseo roto por 302 HTML en API.

---

### FASE 2 — Concurrencia y estabilidad base

1. Locking transaccional (`select_for_update`) en avance de progreso.
2. Integración explícita de Redis en `settings.py` como cache compartido.
3. Política de invalidación de cache en eventos críticos (intentos, aprobaciones, cambios de práctica).

**Salida FASE 2**
- sin carreras reproducibles en avance de progreso,
- cache consistente multi-worker,
- pruebas concurrentes controladas documentadas.

---

### FASE 3 — Optimización de performance pesada

1. Refactor SQL-first para analíticas pesadas.
2. Eliminación de N+1 críticos (incluido `docentes/views.py`).
3. Materialización/estrategia incremental si la carga lo exige.

**Salida FASE 3**
- mejora medible de latencia/queries,
- equivalencia funcional validada,
- sin regresión pedagógica ni de permisos.

---

## 5) Protocolo de auditoría profunda (por fase)

Para cada fase, Claude debe entregar:

1. **Reproducción inicial** del problema (evidencia concreta).
2. **Fix incremental mínimo** (evitar cambios masivos no verificables).
3. **Test de regresión** (falla antes, pasa después).
4. **Prueba negativa/adversarial** (bypass manual/API directa ya no funciona).
5. **Matriz de impacto por consumidor** (docente vs investigador).
6. **Riesgo residual** (severidad, mitigación, owner, fecha objetivo).
7. **Decisión pedagógica explícita** cuando exista trade-off técnico.

---

## 6) Criterios de aceptación y DoD del plan

Se considera cerrado solo si se cumplen todos:

- QA base estabilizado antes de cambios de negocio.
- Vistas docentes estrictamente aisladas por comisión.
- Vistas de investigación/exportación preservan dataset global + legacy nulo.
- API responde JSON/HTTP correcto para clientes frontend.
- Concurrencia controlada y cache compartido operativo.
- N+1 y cuellos críticos mitigados con evidencia cuantitativa.
- Matriz de evidencia por fase completa y audit trail en `MEMORY.md`.

---

## 7) Matriz de ejecución resumida (orden de trabajo)

1. FASE 0 — QA bloqueante.
2. FASE 1 — Integridad lógica + aislamiento de vistas + bifurcación de consumidores.
3. FASE 2 — Concurrencia base + Redis.
4. FASE 3 — Performance pesada SQL-first + eliminación N+1.
5. Cierre — revisión global de riesgos residuales y acta QA final.


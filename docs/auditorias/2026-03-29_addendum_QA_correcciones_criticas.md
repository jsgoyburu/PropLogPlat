# Addendum QA — Correcciones críticas a auditorías previas (2026-03-29)

## Propósito
Registrar los puntos ciegos detectados tras revisión cruzada y su impacto en el plan unificado.

## Correcciones incorporadas

### A-01 — Riesgo de pérdida de datos históricos por filtrado estricto
- **Problema:** aplicar filtro estricto por `practica_comision` en toda vista/reporting elimina datos legacy (`practica_comision=None`).
- **Corrección:** bifurcación de consumo:
  - docente: aislado por comisión,
  - investigación: global + legacy null.

### A-02 — Error lógico en dashboard docente
- **Problema:** métrica de completados sin filtro de comisión mezcla cohortes.
- **Corrección:** filtrar por comisión en vistas operativas docentes.

### A-03 — N+1 oculto en `docentes/views.py`
- **Problema:** `count()` dentro de bucle en `comisiones_list`.
- **Corrección:** reemplazar por agregación/annotate o precálculo fuera del loop.

### A-04 — Middleware rompe frontend API
- **Problema:** `/api/*` recibe `302` HTML por middleware de onboarding/password.
- **Corrección:** excluir rutas API del redirect HTML y responder JSON + HTTP semántico.

## Impacto en priorización
Estas correcciones obligan a:
1. mover estabilización de tests a Fase 0 bloqueante,
2. mover aislamiento por comisión + preservación global legacy a Fase 1,
3. separar concurrencia base (Fase 2) de optimización pesada (Fase 3).


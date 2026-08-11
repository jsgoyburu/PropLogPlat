# Auditoría QA profunda — Módulo Docentes (IPC-Lógica)

**Fecha:** 2026-03-29  
**Rol ejecutado:** QA (sin cambios funcionales de código)  
**Objetivo:** auditar en profundidad los flujos del módulo `docentes`, validar funcionamiento end-to-end y detectar problemas para implementación posterior por Claude Sonnet 4.6.

---

## 1) Alcance de la auditoría

Se auditó el módulo docente en tres capas:

1. **Capa de rutas y permisos** (`docentes/urls.py`, `docentes/views.py`).
2. **Capa de flujos funcionales de panel** (comisiones, estudiantes, prácticas, ejercicios, corrección docente, historial).
3. **Capa de calidad automática** (tests existentes del módulo y suite global, para detectar regresiones que impacten flujos docentes).

No se modificó lógica de aplicación. Solo se relevaron evidencias y se consolidó diagnóstico.

---

## 2) Metodología ejecutada

### 2.1 Lectura estructural (estática)
- Revisión de endpoints del módulo docente.
- Revisión de controles de autorización por rol/comisión.
- Revisión de flujos críticos con mutación de estado (importación, aprobación/rechazo, altas/bajas, reorder).

### 2.2 Verificación automatizada (dinámica)
Se ejecutaron:

1. `SECRET_KEY=test-secret python manage.py check`
2. `SECRET_KEY=test-secret python manage.py test docentes.tests -v 2`
3. `SECRET_KEY=test-secret python manage.py test -v 1`

---

## 3) Resultado ejecutivo (resumen)

## Estado general del módulo docentes

- **Flujo base docente en producción:** razonablemente consistente (permisos por comisión y rol presentes en la mayoría de endpoints críticos).
- **Estado de calidad de tests del módulo docentes:** **degradado** por regresión de fixtures en `IntentoAprobacionUpdateTests` (2 errores).
- **Estado de calidad global del repositorio:** **muy degradado** (34 errores + 5 fallos), con fuerte impacto de migraciones de modelo no reflejadas en tests (`PracticaComision`, onboarding middleware, cambios de encuesta).

### Conclusión QA
El módulo docentes **no está en condición de “sin errores”** desde la perspectiva de aseguramiento de calidad porque:
1. Hay flujos críticos sin cobertura efectiva (o cobertura rota).
2. Parte de la regresión afecta directamente revisión docente de intentos.
3. La suite global no es confiable como red de seguridad para cambios futuros.

---

## 4) Matriz de auditoría por flujo docente

| Flujo | Estado | Evidencia | Comentario QA |
|---|---|---|---|
| Acceso a panel (`comisiones_list`) | ✅ Funcional | tests verdes parciales en `ComisionesListViewTests` | Permisos por rol correctos en vista principal. |
| Detalle de comisión (`comision_detail`) | ✅ Funcional | tests verdes parciales en `ComisionDetailProgressViewTests` | Buen control por docente asignado/admin. |
| Alta individual de estudiante | ✅ Funcional | `GestionEstudiantesTests` en verde | Crea usuario + inscripción correctamente. |
| Importación de estudiantes por Excel | ✅/⚠️ Funcional con observaciones | `GestionEstudiantesTests` en verde + inspección de código | Tolerancia por fila inválida funciona; hay captura genérica en import de prácticas (ver hallazgo H-05). |
| Detalle de estudiante + filtros | ✅ Funcional | `EstudianteDetailIntentosTests` en verde | Filtros por comisión/práctica operativos. |
| Gestión de ejercicios en práctica (agregar/quitar/reordenar) | ✅ Funcional | `EjercicioPracticaOrdenamientoTests` en verde | Reordenamiento robusto con swap temporal. |
| Flujo “volver” en formularios ejercicio | ✅ Funcional | `EjercicioFormVolverTests` en verde | Conserva navegación contextual. |
| Importación/copy-on-write de prácticas | ✅ Funcional | `PracticaOrigenTests` en verde | Semántica actual de `PracticaComision` consistente. |
| Corrección docente (aprobar/rechazar intento) | ❌ Bloqueado en QA automatizado | `IntentoAprobacionUpdateTests` con error de setup | Tests rotos por fixtures obsoletos impiden certificar el flujo. |
| Correcciones pendientes (listado) | ⚠️ Parcial | sin test dedicado de paginación + error en pruebas de aprobación | No hay cobertura integral del ciclo listar → aprobar/rechazar → volver. |
| Gestión de docentes por comisión (add/remove) | ⚠️ Cobertura insuficiente | no se observan tests específicos | Lógica existe, pero falta validación automatizada de casos límite. |
| CRUD de comisión (crear/eliminar) | ⚠️ Cobertura insuficiente | sin tests dedicados de extremos | Riesgo medio por falta de red de seguridad. |

---

## 5) Hallazgos priorizados

## H-01 (CRÍTICO QA) — Regresión en tests del flujo de aprobación/rechazo docente

**Qué pasa:** los tests `IntentoAprobacionUpdateTests` fallan antes de ejecutar aserciones porque crean `Practica` con campos que ya no existen (`comision`, `orden`).  
**Impacto:** el flujo de revisión docente no está certificado; cualquier cambio podría romperlo sin ser detectado.  
**Evidencia:** error `TypeError: Practica() got unexpected keyword arguments: 'comision', 'orden'` al correr `python manage.py test docentes.tests -v 2`.  
**Prioridad:** P0.

**Sugerencia para implementación (Claude):** migrar fixtures de esos tests a modelo actual (`Practica` + `PracticaComision`) y agregar assertions end-to-end para:
1. rechazo sin comentario,
2. rechazo con comentario,
3. aprobación,
4. restaurar pendiente,
5. redirección `next` desde correcciones pendientes y detalle estudiante.

---

## H-02 (CRÍTICO QA transversal) — Suite global rota por desalineación modelo/tests

**Qué pasa:** la suite completa presenta **34 errores + 5 fallos**.  
**Impacto en docentes:** reduce severamente confianza para evolucionar flujos docentes; rompe verificación de regresiones cruzadas (analíticas, intentos, onboarding).  
**Causas observadas:**
- tests legacy que siguen creando `Practica(comision=..., orden=...)`,
- tests legacy con campos removidos de encuesta (`acertijo_cirugia_no_se`),
- tests que no preparan consentimientos y quedan redirigidos (302) por middleware de primer ingreso.

**Prioridad:** P0 (para capacidad de mantenimiento).

---

## H-03 (ALTA) — Cobertura insuficiente en flujos sensibles de gestión docente

**Qué falta cubrir (o se cubre parcialmente):**
- `docente_add` / `docente_remove` (incluyendo “único docente no puede quitarse”).
- `comision_create` / `comision_delete`.
- `correccion_pendiente` (paginación + parseo tabla de verdad + bulk update workflow).
- seguridad del parámetro `next` en endpoints que redirigen por POST (validación de host en todos los casos).

**Impacto:** riesgo de regresión silenciosa en operaciones administrativas centrales.

**Prioridad:** P1.

---

## H-04 (MEDIA) — Gap de seguridad funcional en importación de prácticas por POST manual

**Qué se observa:** `_get_practicas_disponibles()` filtra derivadas (`practica_origen__isnull=True`) en UI, pero `practica_import` no replica explícitamente ese filtro al resolver `practica_origen_id`.  
**Riesgo:** un usuario autorizado podría forzar POST e importar una práctica derivada que no debería actuar como plantilla de banco.  
**Impacto pedagógico/operativo:** puede reintroducir duplicaciones no deseadas en circuitos de importación.

**Prioridad:** P2.

---

## H-05 (MEDIA) — Manejo de errores demasiado genérico en `practica_import`

**Qué pasa:** `except Exception:` engloba cualquier falla y devuelve mensaje genérico.  
**Impacto:** baja trazabilidad operativa y dificultad para soporte/diagnóstico.  
**Riesgo adicional:** puede ocultar errores no esperados (bugs reales) como si fueran colisión de orden.

**Prioridad:** P2.

---

## H-06 (MEDIA) — Cache de analíticas sin invalidación activa

**Qué pasa:** `comision_detail` cachea analíticas 5 minutos por comisión con expiración natural.  
**Impacto:** después de acciones docentes (aprobaciones, nuevos intentos, cambios de práctica) puede verse información stale hasta TTL.  
**Nota:** no es error fatal; es trade-off de rendimiento. Pero convendría invalidación selectiva en eventos críticos.

**Prioridad:** P3.

---

## 6) Riesgos funcionales por severidad

### P0 — Resolver antes de tocar lógica docente
1. Reparar tests rotos de flujo de aprobación docente.
2. Recuperar baseline de suite global (al menos módulos que tocan docente/ejercicios/analíticas).

### P1 — Resolver en el mismo ciclo de hardening
1. Completar cobertura de endpoints administrativos sin tests robustos.
2. Agregar pruebas de integración de correcciones pendientes con paginación.

### P2 — Resolver como deuda técnica próxima
1. Endurecer filtro de prácticas importables en backend (`practica_import`).
2. Reemplazar `except Exception` por manejo específico y logging.

### P3 — Mejora operativa
1. Definir estrategia de invalidación de cache por eventos (aprobación/rechazo/alta intento/cambios de práctica).

---

## 7) Plan sugerido para Claude Sonnet 4.6 (orden recomendado)

1. **Fase 1 — Baseline verde mínima**
   - Corregir fixtures/tests obsoletos en `docentes.tests.IntentoAprobacionUpdateTests`.
   - Ejecutar `python manage.py test docentes.tests -v 2` hasta verde total.

2. **Fase 2 — Hardening de flujos docentes**
   - Agregar tests faltantes: add/remove docentes, create/delete comisión, correcciones pendientes paginadas.
   - Validar redirecciones `next` en todos los endpoints de mutación.

3. **Fase 3 — Endurecimiento backend**
   - Aplicar filtro `practica_origen__isnull=True` dentro de `practica_import`.
   - Reemplazar captura genérica de excepciones por errores tipados + logging.

4. **Fase 4 — Consistencia analítica**
   - Diseñar invalidación de cache por señales de cambio en intentos/progreso/prácticas.

5. **Fase 5 — Regresión transversal**
   - Ejecutar suite global y reducir fallos heredados que impactan estabilidad de releases docentes.

---

## 8) Evidencias de ejecución (comandos)

- `SECRET_KEY=test-secret python manage.py check` → sin issues.
- `SECRET_KEY=test-secret python manage.py test docentes.tests -v 2` → 27 tests, **2 errores** (fixtures obsoletos en `IntentoAprobacionUpdateTests`).
- `SECRET_KEY=test-secret python manage.py test -v 1` → 93 tests, **34 errores + 5 fallos** (desalineaciones legacy en analíticas/ejercicios/docentes).

---

## 9) Cierre

Esta auditoría QA concluye que el módulo docentes tiene estructura funcional sólida en varios flujos operativos, pero **no puede considerarse “verificado sin errores”** hasta restaurar la confiabilidad de la capa de tests y cerrar los gaps de hardening indicados.


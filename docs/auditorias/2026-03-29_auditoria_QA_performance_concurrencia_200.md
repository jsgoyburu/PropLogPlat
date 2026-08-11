# Auditoría QA profunda de performance y concurrencia (escenario ≥200 usuarixs simultáneos)

**Fecha:** 2026-03-29 (UTC)  
**Agente:** Codex (rol QA, sin cambios funcionales)  
**Objetivo:** evaluar riesgos de rendimiento, concurrencia, condiciones de carrera y manejo de base de datos bajo carga simultánea; dejar un informe implementable por Claude Sonnet 4.6.

---

## 1) Resumen ejecutivo

## Veredicto general
El sistema tiene una base correcta para escalar moderadamente (PostgreSQL en Railway, índices críticos en `Intento`, uso de `select_related/prefetch_related` en vistas sensibles y paginación en correcciones pendientes). Sin embargo, **para 200 usuarixs concurrentes** persisten riesgos importantes en tres frentes:

1. **Analíticas CPU/memoria intensivas en Python**, con queries que materializan grandes volúmenes en memoria y procesamiento O(n) por request.
2. **Condiciones de carrera en progreso/desbloqueo** (`_avanzar_progreso`) por ausencia de locking explícito.
3. **Configuración de cache no distribuida explícitamente** (no se define backend de `CACHES` en settings), lo que reduce fuertemente el beneficio real en múltiples workers/instancias.

## Severidad consolidada
- **Crítico:** 2
- **Alto:** 5
- **Medio:** 4
- **Bajo:** 2

---

## 2) Alcance y metodología

## Alcance
- Revisión estática de configuración (`settings`), modelos e índices (`ejercicios/models.py`), flujo de intentos/progreso (`ejercicios/api/views.py`), middleware global (`accounts/middleware.py`) y analíticas (`analiticas/views.py`, `docentes/views.py`).
- Ejecución de checks/tests para validar estado base y detectar fragilidad operativa.

## Comandos ejecutados
- `SECRET_KEY=test-secret python manage.py check`
- `SECRET_KEY=test-secret python manage.py test ejercicios.tests.DesbloqueoProgresivoTests docentes.tests.IntentoAprobacionUpdateTests --verbosity 1`
- Lectura dirigida con `nl -ba` y `rg -n`.

## Nota metodológica
No se ejecutó benchmark de carga sintética (Locust/k6/JMeter) en este turno porque el pedido fue de auditoría QA sin cambios de implementación ni setup de infraestructura de stress-test. Este informe prioriza hallazgos estructurales y un plan de pruebas reproducible para que Claude implemente y valide.

---

## 3) Hallazgos detallados (priorizados)

## H-01 — [CRÍTICO] Analíticas con materialización masiva en memoria por request

### Evidencia
Funciones como `_estudiantes_en_riesgo`, `_distribucion_intentos`, `_concentracion_practica` y `_velocidad_arranque` hacen `values(...).order_by(...)` sobre `Intento` y luego agrupan en estructuras Python (`defaultdict`, listas, sets), recorriendo todos los intentos relevantes en RAM. Esto escala mal con cohortes grandes y simultaneidad.  
Referencia: `analiticas/views.py` líneas 103-149, 179-281, 429-475, 494-536.

### Riesgo bajo 200 concurrentes
- Saturación de CPU del worker por loops Python largos.
- Picos de memoria por listas/diccionarios de intentos.
- Latencias altas y variabilidad (p95/p99) en paneles docentes.

### Recomendación implementable
1. Migrar agregaciones principales a SQL (`annotate`, subqueries, `Window`, `TruncWeek` cuando aplique).
2. Introducir materialización incremental (tabla de métricas por comisión/práctica diaria u horaria).
3. Aplicar cache de resultados ya agregados (Redis) con invalidación por eventos de nuevos intentos.

---

## H-02 — [CRÍTICO] Posible condición de carrera en avance de progreso

### Evidencia
`IntentoCreateView` guarda intento en `transaction.atomic()`, pero `_avanzar_progreso` usa `get_or_create` y luego `save` sin `select_for_update` sobre la fila de `Progreso`.  
Referencia: `ejercicios/api/views.py` líneas 194-207 y 238-259; `Progreso.unique_together` en `ejercicios/models.py` líneas 500-504.

### Riesgo bajo 200 concurrentes
Si el mismo estudiante dispara requests concurrentes (doble click, reconexión, reintentos rápidos), puede haber:
- lost update del `ejercicio_practica_actual`,
- avance duplicado o inconsistente,
- estado final no determinista.

### Recomendación implementable
1. Envolver lectura/escritura de `Progreso` con `select_for_update()` (fila por estudiante+práctica).
2. Hacer la transición idempotente (guardas por versión/estado previo esperado).
3. Agregar tests concurrentes de integración (dos POST simultáneos sobre mismo EP).

---

## H-03 — [ALTO] Cache de analíticas sin backend compartido explícito

### Evidencia
Se usa `cache.get/set` con TTL 300 en `comision_detail`, pero en `settings.py` no hay bloque explícito `CACHES` con Redis/Memcached. Django cae en `LocMemCache` por proceso.  
Referencia: `docentes/views.py` líneas 535-565; `logica_ipc/settings.py` líneas 120-145 (sin definición de `CACHES`).

### Riesgo bajo 200 concurrentes
- Cada worker recalcula lo mismo (cache no compartida entre procesos/instancias).
- Efecto “cache stampede” al expirar TTL.
- Uso de CPU desparejo y latencia innecesaria.

### Recomendación implementable
1. Configurar `CACHES` con Redis compartido.
2. Agregar lock anti-stampede (dogpile lock) al recomputar métricas caras.
3. Separar TTL por panel (rápido/lento) para suavizar recomputaciones simultáneas.

---

## H-04 — [ALTO] N+1 / multi-count en dashboard global de analíticas

### Evidencia
En `dashboard`, por cada práctica se ejecutan múltiples `count()` sobre `Progreso` e `Intento`. Con varias comisiones/prácticas esto multiplica queries en cascada.  
Referencia: `analiticas/views.py` líneas 653-677.

### Riesgo bajo 200 concurrentes
- Aumento fuerte de round-trips DB.
- Bloqueo del pool de conexiones y cola en workers.

### Recomendación implementable
- Reescribir con agregaciones batch por comisión/práctica (`values(...).annotate(...)`) y mapear en memoria resultados ya consolidados (1-3 queries grandes en lugar de decenas/centenas).

---

## H-05 — [ALTO] Selección ambigua de `PracticaComision` en API de intentos

### Evidencia
`IntentoCreateView` resuelve `PracticaComision` con `.first()` entre coincidencias de práctica e inscripción.  
Referencia: `ejercicios/api/views.py` líneas 109-114.

### Riesgo bajo concurrencia/multi-comisión
- Asignación no determinista del intento a comisión cuando hay múltiples matches.
- Distorsión analítica por comisión y posible inconsistencia pedagógica.

### Recomendación implementable
- Exigir `practica_comision_id` explícito en el payload/contexto y validarlo server-side.

---

## H-06 — [ALTO] Índices insuficientes para patrones analíticos actuales

### Evidencia
Hay índices en `Intento(estudiante, ejercicio_practica)`, `(es_correcto, aprobado_docente)` y `(aprobado_docente)`, más `practica_origen`. Faltan índices compuestos alineados a filtros/order usados en analíticas (ej. `practica_comision_id`, `timestamp`, `ejercicio_practica_id`).  
Referencia: `ejercicios/models.py` líneas 426-439; queries analíticas en `analiticas/views.py` líneas 103-113, 179-191, 429-440, 494-505.

### Riesgo
- Scan costoso sobre `Intento` al crecer histórico.
- Degradación progresiva de p95/p99.

### Recomendación implementable
Diseñar índices con `EXPLAIN ANALYZE` real en PostgreSQL productivo, proponiendo al menos candidatos:
- `(practica_comision_id, timestamp)`
- `(practica_comision_id, ejercicio_practica_id, estudiante_id, timestamp)`
- `(practica_comision_id, es_correcto)`

---

## H-07 — [MEDIO] Middleware global con redirecciones adicionales por request autenticada

### Evidencia
`ForzarCambioPasswordMiddleware` evalúa condiciones y potenciales redirects en cada request autenticada.  
Referencia: `accounts/middleware.py` líneas 33-63.

### Riesgo bajo 200 concurrentes
No es el mayor cuello de botella, pero suma overhead y ramas de control en todos los endpoints autenticados.

### Recomendación implementable
- Reducir costo con flags de sesión estables post-onboarding.
- Evitar comprobaciones redundantes en endpoints API hot-path.

---

## H-08 — [MEDIO] Paginación correcta en correcciones, pero `count()` sigue costando en tablas grandes

### Evidencia
`correccion_pendiente` pagina (25) y usa `select_related`, pero además pide `total = intentos_qs.count()`.  
Referencia: `docentes/views.py` líneas 944-983.

### Riesgo
En volúmenes altos, el `count()` puede seguir siendo costoso, aunque menor que cargar todos los objetos.

### Recomendación implementable
- Mantener paginación (ya correcto).
- Evaluar `estimated_count` o cache de conteo para vistas de alto tráfico docente.

---

## H-09 — [MEDIO] Configuración DB local puede inducir pruebas no realistas

### Evidencia
Si no se detecta `RAILWAY_ENVIRONMENT`, se fuerza SQLite incluso con `DATABASE_URL` definida.  
Referencia: `logica_ipc/settings.py` líneas 126-145.

### Riesgo
- Benchmarks locales no representan locks/planes de PostgreSQL.
- Falsa sensación de performance.

### Recomendación implementable
- Permitir activar PostgreSQL fuera de Railway para QA de carga (`USE_POSTGRES=true` o similar).

---

## H-10 — [MEDIO] Suite de tests relevante con fallos actuales (fragilidad de regresión)

### Evidencia
Ejecución de tests indicada arriba devuelve `FAIL/ERROR`: redirects 302 inesperados en desbloqueo y fixtures legacy inválidos en docentes (`Practica(..., comision=..., orden=...)`).

### Riesgo
- Difícil asegurar no regresiones al implementar optimizaciones concurrentes.

### Recomendación implementable
1. Normalizar fixtures/helpers post-onboarding para tests no orientados a onboarding.
2. Corregir tests legacy a `PracticaComision`.
3. Agregar suite de concurrencia (race tests) y smoke de performance.

---

## H-11 — [BAJO] `CONN_MAX_AGE=600` presente, pero falta gobernanza explícita de pool

### Evidencia
Se define `conn_max_age=600` en Postgres Railway.  
Referencia: `logica_ipc/settings.py` líneas 131-136.

### Recomendación
- Documentar y ajustar número de workers + conexiones máximas por dyno para no sobrepasar límites del plan DB.

---

## H-12 — [BAJO] Falta observabilidad de performance de aplicación/DB

### Evidencia
No se observan en el alcance instrumentaciones explícitas de APM/slow query logging por endpoint.

### Recomendación
- Instrumentar tiempos por vista, query count y p95/p99 (OpenTelemetry/Sentry APM/New Relic o logging estructurado mínimo).

---

## 4) Riesgos de concurrencia y carrera (matriz)

| Riesgo | Probabilidad | Impacto | Prioridad |
|---|---:|---:|---:|
| Race en `Progreso` al recibir intentos simultáneos | Media | Alta | P1 |
| Stampede de cache de analíticas | Alta | Alta | P1 |
| Saturación CPU por analíticas en Python | Alta | Alta | P1 |
| Distorsión por comisión en `.first()` de `PracticaComision` | Media | Media/Alta | P2 |
| N+1 counts en dashboard | Alta | Media | P2 |

---

## 5) Plan de implementación recomendado para Claude Sonnet 4.6

## Fase 1 (bloqueante para 200 concurrentes)
1. **Locking/idempotencia de progreso** en `IntentoCreateView`.
2. **Redis como cache compartida** + anti-stampede en analíticas.
3. **Refactor analíticas más pesadas** a agregación SQL/materialización.

## Fase 2
4. Reescritura de `dashboard` para eliminar multi-count por práctica.
5. Resolución determinística de `practica_comision` en API de intentos.
6. Índices compuestos guiados por `EXPLAIN ANALYZE`.

## Fase 3 (calidad operativa)
7. Reparar tests en rojo y agregar tests concurrentes.
8. Incorporar observabilidad (latencia, query count, error ratio).
9. Ejecutar pruebas de carga reproducibles (Locust/k6) sobre PostgreSQL real.

---

## 6) Propuesta de pruebas de carga (para ejecutar tras implementar)

## Escenario objetivo
- 200 usuarios virtuales concurrentes.
- Mix de tráfico sugerido:
  - 60% endpoints de estudiante (home/práctica/ejercicio + POST intento).
  - 25% panel docente comisiones.
  - 15% analíticas (`comision_detail`, dashboard).

## KPI de aceptación sugeridos
- p95 GET estudiante < 500 ms.
- p95 POST intento < 700 ms.
- p95 analíticas cacheadas < 800 ms.
- error rate total < 1%.
- sin deadlocks ni inconsistencias de `Progreso`.

## Métricas obligatorias
- p50/p95/p99 por endpoint.
- Throughput (req/s).
- Uso CPU/memoria por worker.
- `pg_stat_statements` (top queries por total_time/calls).

---

## 7) Conclusión

El sistema **todavía no está en condición robusta para 200 concurrentes sostenidos** sin riesgo de degradación, principalmente por el costo de analíticas en Python, race conditions potenciales en progreso y una estrategia de cache posiblemente no distribuida. La arquitectura actual es recuperable con cambios incrementales (sin rediseño radical), y el orden propuesto permite mejorar estabilidad y legibilidad pedagógica manteniendo los principios del proyecto.

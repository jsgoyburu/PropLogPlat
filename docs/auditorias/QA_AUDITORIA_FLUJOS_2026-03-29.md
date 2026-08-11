# Informe QA exhaustivo — auditoría de flujos inter-módulo

**Proyecto:** IPC-Lógica  
**Fecha:** 2026-03-29 (UTC)  
**Rol ejecutado:** QA (sin cambios de código funcional)  
**Objetivo:** auditar en profundidad la interrelación entre módulos, verificar funcionamiento end-to-end y detectar problemas en los flujos.

---

## 1) Alcance y metodología

Se auditó la interacción entre los módulos:

- `accounts` (auth, onboarding, consentimiento, perfil, acceso por comisión)
- `cursos` (comisiones e inscripciones)
- `ejercicios` (prácticas, ejercicios, intentos, progreso)
- `docentes` (gestión operativa y corrección)
- `analiticas` (dashboard y métricas)
- `motor` (verificación formal)
- `logica_ipc` (enrutamiento global)

### Metodología aplicada

1. **Revisión estructural** de rutas y dependencias entre apps.
2. **Ejecución de checks automáticos** (`manage.py check`, suite de tests).
3. **Inspección de código** en puntos de integración críticos (middleware, API de intentos, cache analítica, onboarding, asignación a comisión).
4. **Análisis de fallas** con foco en impacto funcional, pedagógico y operativo.

---

## 2) Comandos ejecutados y resultado

```bash
SECRET_KEY=test-secret python manage.py check
SECRET_KEY=test-secret python manage.py test --verbosity 1
```

### Resultado consolidado

- `manage.py check`: **OK** (sin issues de configuración declarativos).
- `manage.py test`: **FAIL global**.
  - **93 tests ejecutados**.
  - **34 errores + 5 fallos**.
  - Total de casos no verdes: **39/93 (41,9%)**.

---

## 3) Mapa de flujos inter-módulo auditados

## Flujo A — Acceso y onboarding (accounts ↔ middleware ↔ ejercicios/docentes)

1. Login (`accounts:login`) y autenticación.
2. `ForzarCambioPasswordMiddleware` fuerza secuencia:
   - cambio de contraseña,
   - consentimientos,
   - encuesta onboarding (si aplica).
3. Recién luego deriva a home estudiante (`ejercicios:home`) o panel docente.

**Estado QA:** funcionalmente coherente, pero con acoplamiento fuerte por redirección universal (incluyendo APIs, ver Hallazgo H-02).

## Flujo B — Estudiante resuelve ejercicio (ejercicios UI ↔ API intentos ↔ motor ↔ progreso)

1. Estudiante entra a práctica y ejercicio habilitado.
2. Front llama `POST /api/intentos/`.
3. API verifica inscripción, ejecuta motor (`verificar`/`verificar_argumento`), guarda intento, avanza progreso.
4. Docente revisa lo pendiente.

**Estado QA:** hay un riesgo de trazabilidad cruzada de comisión cuando la práctica está asignada a más de una comisión para el mismo estudiante (Hallazgo H-03).

## Flujo C — Corrección docente (docentes ↔ intentos)

1. Intentos correctos sin revisión se listan como pendientes.
2. Docente aprueba/rechaza; rechazo exige devolución.
3. Estado final impacta visualización y avance interpretado.

**Estado QA:** flujo estable en diseño; sin embargo, hay deuda de invalidación de cache analítica posterior a correcciones (Hallazgo H-04).

## Flujo D — Analíticas (analiticas ↔ intentos/progreso/inscripciones)

1. `docentes/comision_detail` consume helpers analíticos.
2. Métricas cacheadas 5 minutos.
3. Dashboard cruza intentos, progreso y datos de onboarding con filtros por consentimiento.

**Estado QA:** lógica analítica significativa, pero con doble señal de riesgo:
- suite de tests de analíticas rota por desalineación de fixtures/modelo (Hallazgo H-01),
- posible desfasaje temporal por cache sin invalidación activa (Hallazgo H-04).

---

## 4) Hallazgos (priorizados)

## H-01 — **CRÍTICO** — La suite de integración está severamente degradada

**Severidad:** Crítica  
**Tipo:** Calidad/Regresión/Confiabilidad de release  
**Impacto:** Alto para operación de cambios y prevención de regresiones.

### Evidencia

En la corrida integral aparecen dos patrones graves:

1. **Fixtures desactualizadas respecto del modelo actual**:
   - tests crean `Practica(..., comision=..., orden=...)`, pero `Practica` ya no tiene esos campos (existen en `PracticaComision`).
   - tests intentan usar `EncuestaEstudiante(acertijo_cirugia_no_se=...)` con campo inexistente.

2. **Tests que esperan códigos API/HTML, pero reciben redirección 302**:
   - múltiples casos en `ejercicios.tests` y `docentes.tests` esperan `200/403` y reciben `302` por middleware de onboarding.

### Diagnóstico

Hay una **desincronización fuerte entre contratos de datos y tests**. Esto impide usar la suite como garantía de no-regresión en flujos inter-módulo.

### Recomendación para implementación (Claude)

1. Normalizar fixtures a modelo vigente (`PracticaComision`).
2. Actualizar tests de onboarding/research a esquema actual de encuesta.
3. Establecer helper único de usuarios de test con estado onboarding explícito (docente/estudiante).
4. Separar en CI suites “core crítico” y “analíticas” para recuperar señal incremental mientras se sanea el total.

---

## H-02 — **ALTO** — Middleware de onboarding intercepta también endpoints API y rompe semántica HTTP esperada

**Severidad:** Alta  
**Tipo:** Flujo UX/API  
**Impacto:** Medio/Alto (clientes JS reciben HTML 302 cuando esperan JSON 401/403/422).

### Evidencia

`ForzarCambioPasswordMiddleware` aplica redirección por `request.path` sin excepción para `/api/`.  
En la práctica, durante estado onboarding pendiente, un `POST /api/intentos/` puede retornar redirect a pantallas HTML.

### Riesgo funcional

- Front que espera JSON puede quedar en estado inconsistente.
- Se enmascaran errores semánticos reales (p.ej., autorización) detrás de redirecciones.

### Recomendación para implementación (Claude)

- Excluir rutas API del middleware de redirección HTML.
- Para API, devolver códigos JSON consistentes (`401/403`) con payload explícito (`onboarding_required`, `step`).
- Mantener redirección sólo para navegación HTML tradicional.

---

## H-03 — **ALTO** — Ambigüedad de comisión en `IntentoCreateView` cuando una práctica está en más de una comisión

**Severidad:** Alta  
**Tipo:** Integridad de datos / Analítica  
**Impacto:** Alto (atribución de intentos potencialmente incorrecta).

### Evidencia

En `IntentoCreateView`, la `practica_comision` se resuelve así:

- se busca por `practica=ep.practica` y `comision__estudiantes=request.user`,
- luego se toma `.first()`.

Si el/la estudiante está en **más de una comisión** que comparte la misma práctica, la atribución queda no determinística (dependiente del orden de query), afectando:

- panel docente por comisión,
- métricas de analíticas por comisión,
- trazabilidad del proceso.

### Recomendación para implementación (Claude)

1. Exigir contexto explícito de comisión o `practica_comision_id` en el request de intento.
2. Validar pertenencia `ep -> practica -> practica_comision` de forma determinística.
3. Bloquear persistencia si no hay una única correspondencia.

---

## H-04 — **MEDIO** — Cache de analíticas sin invalidación por eventos relevantes

**Severidad:** Media  
**Tipo:** Consistencia temporal  
**Impacto:** Medio (dashboard desactualizado hasta 5 min).

### Evidencia

En `docentes/comision_detail` se cachean analíticas 300s por clave `analiticas_{comision_id}`, pero no se invalida cuando:

- entra un nuevo intento,
- se aprueba/rechaza un intento,
- cambia inscripción.

### Recomendación para implementación (Claude)

Agregar invalidación por señales/eventos de escritura (intentos, aprobaciones, inscripciones), manteniendo TTL como fallback.

---

## H-05 — **MEDIO** — Señal mixta entre “check de sistema OK” y suite funcional rota

**Severidad:** Media  
**Tipo:** Gobernanza QA/CI  
**Impacto:** Medio/Alto (falsa sensación de estabilidad en despliegue).

### Evidencia

`manage.py check` da verde, pero la suite end-to-end de apps falla masivamente. Esto sugiere que el check de configuración no refleja salud funcional real de flujos.

### Recomendación para implementación (Claude)

- Formalizar criterio de release: `check + subset crítico de tests + smoke flujos principales`.
- Agregar smoke tests para onboarding completo + intento API + corrección docente + dashboard comisión.

---

## 5) Evaluación por flujo (semáforo)

- **Auth + onboarding base:** 🟡 (funciona, pero API sufre redirecciones HTML).
- **Resolución de ejercicios estudiante:** 🟡 (core funcional, riesgo de atribución de comisión).
- **Gestión/corrección docente:** 🟢 (flujo principal estable en diseño).
- **Analíticas docentes:** 🟡 (valor alto, pero con riesgo de desactualización temporal y deuda de test).
- **Confiabilidad de regresión (tests):** 🔴 (estado crítico actual).

---

## 6) Priorización sugerida de implementación

### Sprint 1 (bloqueante)
1. Resolver H-01 (sanear suite para recuperar señal de calidad).
2. Resolver H-03 (determinismo de comisión en intentos).
3. Resolver H-02 (semántica API sin redirects HTML).

### Sprint 2 (estabilización)
4. Resolver H-04 (invalidación de cache analítica por evento).
5. Resolver H-05 (pipeline QA mínimo obligatorio para release).

---

## 7) Notas para Claude Sonnet 4.6

- Este informe **no modifica lógica de negocio**, solo documenta riesgos reales detectados en flujos inter-módulo.
- La prioridad técnica recomendada está alineada con continuidad pedagógica: preservar trazabilidad de intentos, legibilidad del proceso y confiabilidad operativa.
- Se sugiere implementar primero lo que evita distorsión de datos de comisión y lo que devuelve señal confiable en tests.

---

## 8) Conclusión ejecutiva

El sistema presenta una base funcional sólida en su arquitectura pedagógica híbrida, pero actualmente tiene una **brecha crítica de aseguramiento de calidad**: la suite integrada no está confiable y hay dos riesgos inter-módulo de alto impacto (redirecciones API por middleware y atribución ambigua de comisión en intentos).  

Antes de nuevas features, conviene ejecutar una **fase de estabilización QA** para recuperar trazabilidad, consistencia analítica y confianza en releases.

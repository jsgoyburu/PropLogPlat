# Auditoría QA profunda — Módulo Ejercicios

**Fecha:** 2026-03-29 (UTC)  
**Agente:** Codex (rol QA, sin cambios funcionales)  
**Repositorio:** `IPC-Logica`  
**Objetivo:** auditar flujos end-to-end del módulo ejercicios para detectar errores/fragilidades y dejar un informe implementable por Claude Sonnet 4.6.

---

## 1) Resumen ejecutivo

### Estado general
- El módulo **tiene buena cobertura funcional de base** (home, práctica, ejercicio, API de intentos, historial, preview docente), con arquitectura coherente con la pedagogía del proyecto.
- Sin embargo, la auditoría encontró **4 problemas críticos/altos** que afectan confiabilidad y/o integridad de flujo.

### Hallazgos principales (priorizados)
1. **[CRÍTICO]** `POST /api/intentos/` valida inscripción pero **no valida desbloqueo secuencial ni ventana temporal** (apertura/cierre) al registrar intentos por API. Esto permite bypass del flujo pedagógico desde cliente/API directo.  
2. **[ALTO]** `mi_historial` agrupa por `ejercicio_practica_id` solamente, mezclando intentos de distintas comisiones cuando comparten la misma práctica.  
3. **[ALTO]** Suite de tests de `ejercicios`/`docentes` actualmente en rojo por **desalineación con middleware de onboarding** y por tests que siguen creando `Practica(comision=..., orden=...)` (campos inexistentes desde `PracticaComision`).
4. **[MEDIO]** Ambigüedad de comisión en `IntentoCreateView` cuando una práctica está asignada a múltiples comisiones del mismo estudiante (`first()` sin criterio explícito de `pc_id`).

---

## 2) Alcance y metodología

### Alcance auditado
- Flujos estudiante:
  - Home de prácticas
  - Listado de ejercicios por práctica
  - Resolución de ejercicio (formalización y tabla de verdad)
  - Registro de intento por API
  - Historial propio (`mi_historial`)
- Flujos de soporte docente vinculados al módulo ejercicios:
  - Preview de verificación
  - Preview de argumento
  - Comentarios por intento
  - Tests del panel docente que ejercitan aprobación/rechazo

### Método aplicado
1. Revisión estática de vistas, serializers, modelos, URLs y templates involucrados.
2. Ejecución de checks/test suite relevante.
3. Trazabilidad de fallos con evidencia concreta de salida de test y lectura de código.

### Comandos ejecutados
- `SECRET_KEY=test-secret python manage.py check`
- `SECRET_KEY=test-secret python manage.py test ejercicios docentes --verbosity 2`
- Lectura dirigida de archivos con `nl -ba ... | sed -n ...`.

---

## 3) Resultado por flujo (matriz)

| Flujo | Estado | Observación QA |
|---|---|---|
| Home estudiante (`ejercicios:home`) | ✅ Funcional | Lista comisiones/prácticas con estado y badges de disponibilidad. |
| Práctica (`ejercicios:practica`) | ✅ Funcional | Respeta inscripción y fechas desde vista HTML; modela estados (`actual`, `pendiente`, etc.). |
| Ejercicio HTML (`ejercicios:ejercicio`) | ✅ Funcional con riesgo de bypass | La vista sí respeta inscripción, disponibilidad y secuencia; riesgo aparece por endpoint API no alineado. |
| Registro intento API (`ejercicios_api:intento-create`) | ❌ Crítico | Falta bloqueo por secuencia y por fechas en API; posible bypass desde cliente manual. |
| Historial estudiante (`ejercicios:mi_historial`) | ⚠️ Parcial | Agrupación por `ep_id` mezcla contextos de comisión para una misma práctica compartida. |
| Preview verificación (`preview-verificacion`) | ✅ Funcional | OK en tests; valida fórmula de solución. |
| Preview argumento (`preview-argumento`) | ✅ Funcional | OK en tests; captura error por operaciones mixtas sin paréntesis. |
| Comentario intento API | ✅ Funcional | Control de permisos por docente de comisión/admin presente. |
| Integridad de suite de tests | ❌ Alto | Fallas estructurales actuales impiden confiar plenamente en regresión automática. |

---

## 4) Hallazgos detallados

## H-01 — Bypass del flujo pedagógico en `POST /api/intentos/` (CRÍTICO)

### Evidencia
En `IntentoCreateView.post` se valida:
- input,
- existencia de `EjercicioPractica`,
- inscripción en *alguna* comisión que tenga esa práctica.

Pero **no se valida**:
- si el ejercicio está desbloqueado según `Progreso`,
- si la práctica está abierta/cerrada según `PracticaComision.estado_disponibilidad()`.

### Impacto
Un estudiante inscripto podría, por API directa:
- enviar intentos de ejercicios bloqueados,
- enviar intentos fuera de ventana temporal (antes de apertura/después de cierre),
- contaminar trazas de progreso y analítica.

Esto rompe la consistencia entre frontend (que sí restringe) y backend (que debería ser la autoridad).

### Referencias técnicas
- La vista HTML sí controla acceso por fechas y secuencia: `ejercicios/views.py` (`practica_detail`, `ejercicio_detail`).
- La API de intentos no lo hace: `ejercicios/api/views.py`.

### Recomendación de implementación
1. En `IntentoCreateView`, resolver `PracticaComision` de forma explícita y validar:
   - `estado_disponibilidad() == 'abierta'`.
2. Validar desbloqueo con lógica equivalente a `ejercicio_detail`:
   - primer EP si no hay `Progreso`,
   - EP actual si hay `Progreso`,
   - rechazar envíos a EP futuro.
3. Devolver `403` con mensaje pedagógico claro si no corresponde enviar.
4. Agregar tests de API específicos para:
   - práctica no iniciada,
   - práctica cerrada,
   - EP bloqueado,
   - EP actual permitido.

---

## H-02 — Agrupación incorrecta en `mi_historial` cuando hay práctica compartida entre comisiones (ALTO)

### Evidencia
En `mi_historial`, el agrupamiento se indexa por `ejercicio_practica_id` solamente.

### Impacto
Si una práctica canónica está asignada a dos comisiones y el/la estudiante participa en ambas, los intentos de ambas comisiones quedan mezclados en un mismo bloque. Esto distorsiona:
- lectura del proceso de aprendizaje por contexto de comisión,
- interpretación docente,
- trazabilidad pedagógica.

### Recomendación
Agrupar por clave compuesta, por ejemplo:
- `(practica_comision_id, ejercicio_practica_id)` (recomendado), o
- `(comision_id, practica_id, ejercicio_practica_id)`.

Agregar test de regresión que cree dos `PracticaComision` con misma práctica y verifique separación de grupos.

---

## H-03 — Suite de tests del módulo ejercicios/docentes en estado rojo (ALTO)

### Evidencia de ejecución
`python manage.py test ejercicios docentes --verbosity 2` arrojó:
- **5 FAIL + 2 ERROR**.
- Fallos recurrentes `302` donde los tests esperaban `200/403`.
- Errores por creación inválida de `Practica` con argumentos `comision` y `orden`.

### Diagnóstico
1. **Desalineación con middleware de onboarding** (`ForzarCambioPasswordMiddleware`):
   - helper `_u()` de tests setea consentimientos, pero no garantiza campos de gating (p. ej., `debe_cambiar_password=False`, `encuesta_completada=True`), provocando redirects 302 en requests autenticadas.
2. **Tests obsoletos respecto al modelo actual**:
   - `IntentoAprobacionUpdateTests` aún crea `Practica(..., comision=..., orden=...)`, pero `comision/orden` están en `PracticaComision`.

### Impacto
- Baja confiabilidad del semáforo de CI para el módulo auditado.
- Riesgo de introducir regresiones reales sin detección o de normalizar fallas “ruidosas”.

### Recomendación
- Unificar helper de usuarios de tests para dejarlos “post-onboarding completo” cuando el caso no testea onboarding.
- Corregir tests legacy para usar `PracticaComision`.
- Exigir verde para `ejercicios + docentes` antes de merges que toquen estos flujos.

---

## H-04 — Ambigüedad de `PracticaComision` en creación de intentos (MEDIO)

### Evidencia
`IntentoCreateView` obtiene `pc` con `.filter(...).first()` sobre “alguna comisión del estudiante que tenga esa práctica”.

### Impacto
- Si un estudiante pertenece a más de una comisión con la misma práctica, el intento puede asociarse a una `practica_comision` no esperada.
- Distorsión de analíticas por comisión y del historial contextual.

### Recomendación
- Incorporar `practica_comision_id` en payload de intento (o resolverlo por URL contextual).
- Validar que `ep.practica == pc.practica` e inscripción del estudiante en `pc.comision`.
- Hacer determinístico y explícito el contexto de comisión para cada envío.

---

## 5) Hallazgos menores / observaciones de calidad

1. **Riesgo de divergencia HTML vs API**: la UI contiene validaciones pedagógicas que no deben vivir solo en frontend/vistas HTML. Consolidar en backend API reduce bypasses.
2. **Acople de `mi_historial` a template docente**: funcional, pero convendría separar parcial o template específico para evitar deuda de condiciones `vista_propia_estudiante` en muchos bloques.
3. **Cobertura faltante de escenarios multi-comisión**: caso relevante por diseño `Practica` canónica + `PracticaComision` contextual.

---

## 6) Plan sugerido para implementación (orden recomendado)

1. **Bloquear bypass API de intentos** (H-01).
2. **Resolver contexto de comisión explícito y determinístico** en intentos (H-04).
3. **Arreglar agrupación de historial por contexto** (H-02).
4. **Dejar suite `ejercicios/docentes` en verde** con helpers y fixtures alineados (H-03).
5. Agregar tests de regresión de los puntos anteriores.

---

## 7) Criterios de aceptación QA propuestos para cierre

- [ ] `POST /api/intentos/` rechaza EP bloqueado y prácticas fuera de ventana (403).
- [ ] `POST /api/intentos/` persiste intento con `practica_comision` correcta y explícita.
- [ ] `mi_historial` separa intentos por contexto de comisión.
- [ ] `python manage.py test ejercicios docentes` en verde.
- [ ] Sin regresión en flujos de preview y comentarios docentes.

---

## 8) Conclusión

El módulo ejercicios está conceptualmente sólido y alineado con la arquitectura pedagógica del proyecto, pero hoy presenta inconsistencias backend críticas en el flujo de intentos (autoridad de negocio) y una base de tests desactualizada que reduce la seguridad de cambios. Recomiendo tratar H-01 y H-03 como bloque de prioridad inmediata, luego completar H-02/H-04 para cerrar trazabilidad contextual en escenarios multi-comisión.

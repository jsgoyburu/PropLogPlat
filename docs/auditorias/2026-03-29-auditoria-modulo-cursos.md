# Auditoría QA profunda — Módulo **Cursos**

**Fecha:** 2026-03-29 (UTC)  
**Rol:** QA (sin cambios de lógica/código de producto)  
**Objetivo:** auditar integralmente los flujos del módulo cursos/comisiones/inscripciones y su integración con onboarding, panel docente y ejercicios.

---

## 1) Alcance auditado

Aunque la app `cursos/` contiene principalmente modelos, el comportamiento funcional del módulo se distribuye en:

- `cursos.models` (entidades `Comision` e `Inscripcion`).
- Flujos docentes de comisiones/estudiantes en `docentes.views` + `docentes.forms` + templates.
- Acceso público por comisión y autoinscripción en `accounts.views`.
- Consumo de inscripciones por los flujos estudiante/API en `ejercicios.views` y `ejercicios.api.views`.

> **Criterio QA aplicado:** cobertura funcional real del “módulo cursos” como conjunto de flujos de negocio, no solo del paquete Python `cursos/`.

---

## 2) Metodología

### 2.1 Revisión estática
- Lectura detallada de modelos, vistas, formularios, rutas y templates involucrados.
- Verificación de permisos, consistencia de mensajes, integridad de flujo y deuda de testeo.

### 2.2 Verificación dinámica (tests)
Se ejecutaron checks y suites relevantes:

1. `SECRET_KEY=test-secret python manage.py check`
2. `SECRET_KEY=test-secret python manage.py test accounts.tests.AccesoComisionTests accounts.tests.TipoEncuestaResolucionTests docentes.tests.ComisionesListViewTests`
3. `SECRET_KEY=test-secret python manage.py test cursos accounts docentes ejercicios`
4. `SECRET_KEY=test-secret python manage.py test docentes.tests.IntentoAprobacionUpdateTests ejercicios.tests.IntentoCreateViewTests ejercicios.tests.DesbloqueoProgresivoTests ejercicios.tests.MiHistorialViewTests`

---

## 3) Resultado ejecutivo

## Estado general
- **Arquitectura del dominio cursos: sólida** (modelo de comisión/inscripción correcto, restricción de unicidad estudiante-comisión presente).
- **Flujos principales operativos:** crear comisión, alta de docentes en comisión, alta/importación de estudiantes, autoinscripción por link público.
- **Problemas QA relevantes detectados:**
  1. Cobertura directa de `cursos/` prácticamente inexistente (tests y views vacíos).
  2. Suite actual con regresiones de tests (errores reales de mantenimiento de suite).
  3. Inconsistencia UX en confirmación de borrado de comisión vs comportamiento real de cascadas.

---

## 4) Hallazgos detallados

## H-01 — **Cobertura nula en la app `cursos/` (tests vacíos)**
**Severidad:** Alta (riesgo de regresión silenciosa)

### Evidencia
- `cursos/tests.py` está vacío (solo boilerplate).
- `cursos/views.py` también es boilerplate sin lógica cubierta.

### Impacto
- No existe “contrato de comportamiento” automatizado del núcleo del módulo (`Comision`, `Inscripcion`) en su propia app.
- Cualquier cambio de permisos, inscripciones o constraints depende de tests indirectos en otras apps.

### Recomendación para implementación
- Crear suite dedicada `cursos/tests.py` con mínimo:
  - creación de comisión con `tipo_encuesta`;
  - unicidad de inscripción (`estudiante`, `comision`);
  - alta/baja de inscripción;
  - permisos básicos en operaciones de comisión expuestas por panel docente.

---

## H-02 — **Regresión en tests docentes por desalineación de modelo `Practica`**
**Severidad:** Alta (la suite falla)

### Evidencia
- `docentes.tests.IntentoAprobacionUpdateTests` intenta crear `Practica` con kwargs `comision` y `orden`, campos que ya no pertenecen al modelo canónico de práctica (hoy viven en `PracticaComision`).
- Resultado: `TypeError: Practica() got unexpected keyword arguments: 'comision', 'orden'`.

### Impacto
- La suite no puede validar el flujo de aprobación/rechazo docente asociado a comisión.
- Reduce confiabilidad del pipeline QA.

### Recomendación para implementación
- Refactor del setup de esos tests para crear:
  1) `Practica` canónica;  
  2) `PracticaComision(practica, comision, orden)`;  
  3) `Intento` con `practica_comision` explícita.

---

## H-03 — **Regresión de tests por redirecciones del middleware de onboarding**
**Severidad:** Media-Alta

### Evidencia
- Varias pruebas esperaban 200/403 pero reciben 302.
- El middleware fuerza redirección si faltan consentimientos o encuesta (`ForzarCambioPasswordMiddleware`).
- Helpers de test `_u()` setean consentimientos pero no garantizan estado final de onboarding para estudiantes (por ejemplo, `encuesta_completada=True` cuando aplica), provocando redirecciones inesperadas.

### Impacto
- Falsos negativos masivos en suites de API/historial/desbloqueo.
- Dificulta detectar fallos reales del flujo cursos porque el fallo se produce “antes” por gating de onboarding.

### Recomendación para implementación
- Estándar de fixtures de test para estudiantes “operativos”:
  - `debe_cambiar_password=False`
  - `consentimiento_pedagogico=True`
  - `consentimiento_investigacion=True`
  - `encuesta_completada=True` (si corresponde al flujo esperado)
- Alternativa: helper explícito `crear_estudiante_listo_para_cursar()` compartido entre apps.

---

## H-04 — **Inconsistencia UX: mensaje de borrado de comisión potencialmente engañoso**
**Severidad:** Media

### Evidencia
- En diálogo de confirmación se indica: “Se borrarán todas sus prácticas, ejercicios e intentos.”
- A nivel modelo, al borrar comisión se borra `PracticaComision` (y sus intentos por cascade), pero **no necesariamente** se eliminan prácticas/ejercicios canónicos si están asociados a otras comisiones.

### Impacto
- Riesgo de comunicar al docente un impacto más destructivo que el real.
- Puede generar temor innecesario o decisiones operativas incorrectas.

### Recomendación para implementación
- Ajustar copy del diálogo para reflejar semántica real de borrado:
  - “Se eliminarán las asignaciones de prácticas de esta comisión y sus intentos asociados; las prácticas/ejercicios compartidos en otras comisiones no se eliminan.”

---

## H-05 — **Manejo de errores demasiado genérico en importación de práctica**
**Severidad:** Media

### Evidencia
- En `practica_import`, bloque `except Exception:` devuelve un mensaje genérico de orden repetido.

### Impacto
- Oculta causa raíz real (integridad, permisos, datos inválidos, etc.).
- Dificulta soporte docente y depuración.

### Recomendación para implementación
- Capturar excepciones específicas (`IntegrityError`, `ValidationError`) y registrar (`logger.exception`) las inesperadas.
- Mantener mensaje pedagógico al docente, pero con trazabilidad técnica en logs.

---

## 5) Flujos auditados (checklist funcional)

## 5.1 Gestión de comisión (docente)
- Crear comisión con `tipo_encuesta`: **OK**.
- Autoasignación del docente creador + co-docentes opcionales: **OK**.
- Permisos por comisión en detalle/acciones: **OK**.

## 5.2 Gestión de docentes en comisión
- Agregar/quitar co-docente con validación de pertenencia: **OK**.
- Protección de “último docente no puede autoquitarse”: **OK**.

## 5.3 Gestión de estudiantes en comisión
- Alta manual + inscripción atómica: **OK**.
- Importación Excel tolerante por fila: **OK** (con hallazgo de error handling genérico).
- Edición/baja de estudiante en comisión: **OK**.

## 5.4 Acceso público por link de comisión
- Registro + autoinscripción + login: **OK**.
- Estudiante ya autenticado entra por link y se inscribe: **OK**.
- Docente/admin autenticado por link: redirección al panel docente: **OK**.

## 5.5 Consumo de inscripciones por flujos de ejercicios
- API de intentos valida inscripción en comisión con esa práctica: lógica **correcta**, pero pruebas afectadas por middleware (H-03).
- Vistas de práctica/ejercicio validan pertenencia de estudiante a comisión: **OK**.

---

## 6) Riesgo residual y priorización sugerida

### Prioridad P0 (inmediata)
1. Corregir regresión de tests en `IntentoAprobacionUpdateTests` (H-02).
2. Normalizar fixtures de usuarios para no romper por middleware en tests funcionales (H-03).

### Prioridad P1
3. Crear suite dedicada para `cursos/` (H-01).
4. Ajustar mensaje de borrado de comisión (H-04).

### Prioridad P2
5. Mejorar granularidad de errores y logging en importación de prácticas (H-05).

---

## 7) Conclusión QA

El módulo cursos está **funcionalmente bien orientado** y con buen enfoque de permisos por comisión, pero hoy presenta un problema de **aseguramiento de calidad**: la cobertura propia de `cursos/` es mínima y hay regresiones de tests que reducen la capacidad de detectar problemas reales a tiempo.

La recomendación global es priorizar estabilización de suite y cobertura explícita del dominio cursos antes de incorporar nuevas features.

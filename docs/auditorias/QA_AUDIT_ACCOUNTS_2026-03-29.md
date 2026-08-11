# Auditoría QA exhaustiva — Módulo `accounts`

**Proyecto:** IPC-Lógica  
**Fecha:** 2026-03-29 (UTC)  
**Rol ejecutado:** QA (sin cambios de código funcional)  
**Objetivo:** auditar en profundidad los flujos de `accounts`, verificar funcionamiento, detectar problemas y dejar un informe accionable para implementación posterior.

---

## 1) Alcance auditado

Se auditó el módulo `accounts` en sus flujos principales:

1. Acceso por link de comisión + auto-registro de estudiante.
2. Login/Logout.
3. Primer ingreso con cambio forzado de contraseña.
4. Consentimientos informados (vista separada para cuentas preexistentes).
5. Encuesta de onboarding (básica/completa).
6. Middleware de enforcement de onboarding.
7. Mi perfil (datos personales + cambio de contraseña voluntario).
8. Integración de estados con `cursos.Inscripcion` y tipo de encuesta por comisión.

---

## 2) Metodología

### 2.1 Revisión estática
- Lectura de rutas, vistas, formularios, middleware, modelos y templates de `accounts`.
- Verificación de consistencia entre docstrings/comportamiento real.
- Revisión de condiciones de redirección y estados de onboarding.

### 2.2 Verificación automatizada existente
Se ejecutó la suite de tests de `accounts` existente en el repositorio.

### 2.3 Verificaciones de entorno
- Migraciones y chequeo general para poder validar flujos en contexto de app.

### 2.4 Limitaciones de ejecución
- No se ejecutó auditoría E2E real en navegador contra servidor levantado para este informe puntual (aunque hay scripts Playwright disponibles en repo).
- No se modificó código (cumpliendo pedido explícito de QA únicamente).

---

## 3) Resultado ejecutivo

### Estado general
- **Resultado global:** `PARCIALMENTE CONFORME`.
- **Fortalezas:** arquitectura clara de onboarding escalonado (password → consentimientos → encuesta), buen set de tests unitarios de `accounts`, cobertura de casos relevantes de persistencia de encuesta.
- **Riesgos principales detectados:**
  1. **Validación incompleta de consentimientos Q9/Q10 en encuesta completa** (se aceptan faltantes por POST manual).
  2. **Inconsistencia potencial con `consentimiento_contacto_seguimiento=None`** no contemplada en middleware ni gate de vista.
  3. **Errores de formulario de consentimientos no visibles en UI** (degradación UX y trazabilidad pedagógica del error).

---

## 4) Hallazgos detallados

## H-01 — Consentimientos Q9/Q10 no obligatorios en tipo completa cuando Q8=Sí

- **Severidad:** Alta (lógica de consentimiento / integridad de dato).
- **Tipo:** Validación server-side incompleta.
- **Dónde:** `accounts/forms.py` + `accounts/views.py` (`ConsentimientosForm`, `_guardar_consentimientos`, `cambiar_password_forzado`, `dar_consentimiento`).

### Descripción
Aunque el texto funcional/documental del formulario sugiere respuesta activa de consentimientos, para `tipo='completa'` los campos `consentimiento_investigacion` y `consentimiento_contacto_seguimiento` están declarados como `required=False`; además no hay validación condicional que exija ambos cuando `consentimiento_pedagogico='true'`.  
Si se omiten por manipulación de POST (o por edge de frontend), el backend guarda ambos en `False` silenciosamente.

### Impacto
- Se transforma “falta de respuesta explícita” en “respuesta negativa” sin confirmación activa.
- Riesgo de calidad/integridad de datos de consentimiento.
- Riesgo ético/legal si se interpreta como consentimiento informado estrictamente activo para cada ítem.

### Recomendación
- Implementar validación condicional en `ConsentimientosForm.clean()` con parámetro de contexto `tipo`.
- Regla sugerida:
  - Si `tipo='completa'` y `consentimiento_pedagogico='true'` → exigir presencia explícita de Q9 y Q10.
- En caso de error, mostrar mensajes visibles por campo en template.

---

## H-02 — Estado inconsistente no contemplado: `consentimiento_contacto_seguimiento is None`

- **Severidad:** Media-Alta.
- **Tipo:** Inconsistencia de estado / bypass de reparación de datos.
- **Dónde:** `accounts/middleware.py` y `accounts/views.py` (`dar_consentimiento`).

### Descripción
El middleware y la vista de consentimientos consideran incompleto solo cuando `consentimiento_pedagogico` o `consentimiento_investigacion` son `None`.  
`consentimiento_contacto_seguimiento` no participa de la condición de incompletitud.

### Escenario de falla
Si existe usuario histórico con:
- `consentimiento_pedagogico=True`
- `consentimiento_investigacion=True`
- `consentimiento_contacto_seguimiento=None`

el usuario no sería redirigido a consentimientos ni tendría camino estándar para completar ese dato.

### Impacto
- Estados “semi-completos” persistentes.
- Inconsistencia analítica y semántica del onboarding.

### Recomendación
- Definir explícitamente modelo de completitud:
  - Para tipo básica: contacto puede forzarse a `False`.
  - Para tipo completa con Q8=Sí: contacto debe ser no-`None`.
- Ajustar condiciones en middleware y vista de consentimientos para contemplar ese criterio.
- Opcional: script/data migration correctiva para cuentas históricas.

---

## H-03 — Errores de `ConsentimientosForm` no se muestran en templates

- **Severidad:** Media (UX + trazabilidad pedagógica del error).
- **Tipo:** Defecto de presentación de errores.
- **Dónde:** `templates/registration/cambiar_password.html`, `templates/registration/consentimientos.html`.

### Descripción
Si el form de consentimientos falla validación (p.ej. no selecciona Q8), la plantilla no imprime `field.errors` ni `non_field_errors` para ese formulario.

### Impacto
- Usuario recibe solo recarga sin guía clara sobre qué faltó.
- Aumenta fricción y potencial abandono del flujo.
- Contradice principio pedagógico de “error visible”.

### Recomendación
- Renderizar errores por campo y errores globales del `consent_form`.
- Mantener mensajes claros y breves junto a cada pregunta.

---

## H-04 — Riesgo menor de preservación semántica en teléfono WhatsApp

- **Severidad:** Baja.
- **Tipo:** Calidad de dato.
- **Dónde:** `_crear_encuesta_estudiante` en `accounts/views.py`.

### Descripción
El valor `whatsapp` se transforma a `int` si es dígito. Esto elimina ceros a la izquierda.

### Impacto
- Potencial pérdida de fidelidad del dato ingresado.
- Puede no ser problema si el diseño asume formato sin 0 ni 15 (actualmente lo sugiere el label).

### Recomendación
- Evaluar almacenar como string normalizado y validar formato explícito.
- Si se mantiene int, documentar fuertemente la normalización.

---

## 5) Flujos verificados y estado

| Flujo | Estado | Evidencia | Observaciones |
|---|---|---|---|
| Acceso por comisión (GET/registro) | ✅ OK | tests `AccesoComisionTests` | Cubre creación de usuario + inscripción y validación de contraseña débil. |
| Login estándar | ✅ OK | template + URL + tests indirectos | Flujo básico funcional. |
| Cambio forzado de contraseña | ✅/⚠️ | vista + middleware | Funciona; depende de mejoras en validación/errores de consentimientos. |
| Consentimientos para cuentas preexistentes | ✅/⚠️ | vista + middleware | Funciona en casos comunes; ver H-01/H-02/H-03. |
| Encuesta onboarding básica/completa | ✅ OK | tests `EncuestaOnboardingPersistenciaTests` | Persistencia verificada en múltiples campos y casos condicionales. |
| Resolución tipo de encuesta por múltiples comisiones | ✅ OK | `TipoEncuestaResolucionTests` | Prioriza completa correctamente. |
| Mi Perfil (datos + password voluntario) | ✅ OK (estático) | vista/template | No se detectan fallas críticas en revisión estática. |
| Enforcements del middleware | ✅/⚠️ | código + tests indirectos | Secuencia principal sólida; edge inconsistente en `contacto=None` (H-02). |

---

## 6) Priorización para implementación (Claude Sonnet 4.6)

## Prioridad P1 (hacer primero)
1. **Corregir H-01**: validación condicional estricta de Q9/Q10 para `tipo='completa'` con Q8=Sí.
2. **Corregir H-03**: mostrar errores de `consent_form` en templates.

## Prioridad P2
3. **Corregir H-02**: unificar criterio de “consentimientos completos” incluyendo `contacto` según tipo.
4. Agregar tests de regresión de casos edge (`POST` sin Q9/Q10; usuario con `contacto=None`).

## Prioridad P3
5. Evaluar normalización de `whatsapp` (H-04) y documentar decisión final.

---

## 7) Casos de prueba recomendados (nuevos)

1. `test_consentimientos_completa_requiere_q9_q10_si_pedagogico_true`.
2. `test_cambiar_password_completa_rechaza_post_sin_q9_q10`.
3. `test_template_consentimientos_muestra_error_required_q8`.
4. `test_middleware_redirige_si_contacto_none_en_estado_completa`.
5. `test_dar_consentimiento_no_bypassea_usuario_incompleto_por_contacto_none`.

---

## 8) Comandos ejecutados en esta auditoría

```bash
python manage.py test accounts -v 2
python manage.py migrate
```

---

## 9) Conclusión

El módulo `accounts` presenta una base funcional robusta para los flujos troncales de autenticación y onboarding, con buena cobertura de tests en casos frecuentes.  
Sin embargo, hay **3 mejoras importantes** para cerrar brechas de integridad/UX en consentimientos (especialmente para tipo completa), y **1 mejora menor** de calidad de dato.  

Este informe deja priorización y casos de regresión concretos para que Claude Sonnet 4.6 implemente cambios con bajo riesgo de regresión.

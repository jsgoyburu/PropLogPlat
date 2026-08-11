# Auditoría integral del sistema según ISO/IEC 9126

**Proyecto:** IPC-Lógica  
**Fecha:** 2026-03-29 (UTC)  
**Auditoría:** funcional + técnica (sin cambios de código funcional)  
**Norma de referencia:** ISO/IEC 9126 (modelo de calidad de producto)

---

## 1) Alcance y metodología

### Alcance
Se auditó el sistema completo con foco en las seis características de ISO/IEC 9126:

1. **Funcionalidad**
2. **Fiabilidad**
3. **Usabilidad**
4. **Eficiencia**
5. **Mantenibilidad**
6. **Portabilidad**

Se consolidó evidencia de módulos centrales y transversales:

- `accounts` (auth, onboarding, consentimientos)
- `cursos` (comisiones/inscripciones)
- `ejercicios` + `motor` (resolución y verificación formal)
- `docentes` (gestión/corrección)
- `analiticas` (dashboard operativo e investigación)

### Método aplicado
- Revisión estática de documentación y arquitectura (`README.md`, auditorías previas en `docs/auditorias/`).
- Ejecución de checks automáticos de plataforma.
- Ejecución de suite global para medir confiabilidad de regresión.
- Mapeo de hallazgos a subcaracterísticas ISO/IEC 9126.

### Evidencia ejecutada

```bash
SECRET_KEY=test-secret python manage.py check
SECRET_KEY=test-secret python manage.py test --verbosity 1
```

Resultado resumido:
- `check`: **OK** (0 issues).
- `test`: **FAIL** (93 tests corridos, 34 errores y 5 fallos), con concentraciones en fixtures legacy de analíticas y desalineaciones de tests que esperan códigos 200/403 y reciben 302 por middleware/flujos actuales.

---

## 2) Evaluación por característica ISO/IEC 9126

## 2.1 Funcionalidad

### Fortalezas
- El sistema sostiene el objetivo pedagógico central: verificación formal automática con separación explícita del juicio docente (arquitectura híbrida humano–máquina).
- Existe cobertura funcional amplia en flujos de onboarding, gestión docente, resolución de ejercicios, historial y analíticas.
- La corrección por equivalencia semántica (vs coincidencia literal) está alineada con los principios pedagógicos del proyecto.

### Hallazgos
- **Riesgo alto en exactitud de métricas operativas/analíticas** cuando hay reutilización de prácticas entre comisiones: pueden darse mezclas cross-comisión en ciertos cálculos históricos reportados en auditorías previas.
- **Tests de analíticas desfasados respecto del modelo vigente** (ej., uso de kwargs legacy como `comision` en `Practica` o campos removidos de onboarding), lo que reduce confianza funcional sobre esa capa.

### Veredicto funcionalidad
**Parcialmente conforme**: el núcleo pedagógico opera, pero la capa analítica necesita normalización prioritaria para garantizar exactitud de datos de intervención docente.

---

## 2.2 Fiabilidad

### Fortalezas
- `python manage.py check` no reporta inconsistencias de configuración estructural.
- Existen suites por módulo y antecedentes de auditorías QA recurrentes.

### Hallazgos
- La suite global actual no está estable (34 errores + 5 fallos), por lo que el sistema tiene **debilidad de detección temprana de regresiones**.
- Parte de los errores son de infraestructura de tests/fixtures legacy, no necesariamente defectos productivos directos, pero impactan severamente la confiabilidad del ciclo de cambios.

### Veredicto fiabilidad
**No conforme para nivel de release robusto** hasta estabilizar la suite base y fijar contratos de test de módulos críticos (analíticas, intentos, progreso, middleware).

---

## 2.3 Usabilidad

### Fortalezas
- Flujo docente dedicado (no admin-first) y foco en legibilidad pedagógica.
- Términos pedagógicos recientes (verificación formal, señales de acompañamiento) mejoran claridad conceptual.
- Flujos de onboarding y consentimientos están explicitados.

### Hallazgos
- En analíticas, cuando los datos de base se contaminan entre comisiones, la interfaz puede ser clara visualmente pero **engañosa semánticamente** para la toma de decisiones docentes.
- Parte de la UX de error/feedback depende de validaciones distribuidas entre cliente/servidor y tests con desalineación histórica.

### Veredicto usabilidad
**Conforme con observaciones**: buena UX general, pero la usabilidad pedagógica depende de corregir integridad de métricas.

---

## 2.4 Eficiencia

### Fortalezas
- Hay optimizaciones incorporadas en iteraciones previas (paginación, cache de analíticas, índices).
- Arquitectura Django + consultas focalizadas permite escalamiento incremental.

### Hallazgos
- Riesgos de eficiencia vinculados a consultas analíticas complejas y potencial sobrecosto en agregaciones no totalmente desacopladas por comisión.
- La falta de suite estable dificulta medir regresiones de performance de forma continua.

### Veredicto eficiencia
**Conforme parcial**: base razonable, pero requiere observabilidad de performance y contratos de test/benchmark en analíticas para consolidar.

---

## 2.5 Mantenibilidad

### Fortalezas
- Alto nivel de documentación operativa (`README.md`, `MEMORY.md`, auditorías por módulo).
- Separación del motor lógico como app Python pura testeable fuera de Django.
- Trazabilidad histórica de decisiones pedagógicas y técnicas.

### Hallazgos
- Hay **deuda técnica en tests legacy** que no acompañaron ciertos cambios de modelo.
- Existen múltiples reportes QA previos con hallazgos repetidos, indicador de cierre parcial de remediaciones.

### Veredicto mantenibilidad
**Conforme con deuda relevante**: mantenible por documentación/estructura, pero urge saneamiento sistemático de tests y cierres de hallazgos para evitar deriva.

---

## 2.6 Portabilidad

### Fortalezas
- Configuración documentada para local y Railway.
- Separación SQLite local / PostgreSQL deploy contemplada.
- Variables de entorno y comandos de arranque claros.

### Hallazgos
- Algunas inconsistencias históricas en migraciones/tests sugieren fragilidad en entornos heterogéneos si no se mantiene disciplina de migración + test en CI.

### Veredicto portabilidad
**Conforme parcial**: buena base, mejorar garantía de portabilidad con pipeline CI consistente y suites verdes obligatorias.

---

## 3) Matriz resumida ISO/IEC 9126

| Característica | Estado | Riesgo principal | Prioridad |
|---|---|---|---|
| Funcionalidad | Parcialmente conforme | Exactitud analítica cross-comisión | Alta |
| Fiabilidad | No conforme | Suite global inestable (errores/fallos) | Crítica |
| Usabilidad | Conforme con observaciones | Lectura pedagógica sesgada por datos contaminados | Alta |
| Eficiencia | Conforme parcial | Falta de contratos de performance en analíticas | Media |
| Mantenibilidad | Conforme con deuda | Tests legacy + remediaciones incompletas | Alta |
| Portabilidad | Conforme parcial | Riesgo en consistencia entre entornos sin CI estricto | Media |

---

## 4) Hallazgos críticos priorizados (plan de cierre)

1. **Estabilizar suite global como gate de calidad (Crítico).**
   - Objetivo mínimo: 0 errores de infraestructura en tests.
   - Refactorizar fixtures legacy en `analiticas/tests.py` y tests que dependen de contratos antiguos de modelos/middleware.

2. **Blindar integridad de métricas por comisión (Crítico/Alto).**
   - Revisar y reforzar filtros por `PracticaComision`/comisión efectiva en agregaciones de dashboard e investigación.
   - Agregar tests de no contaminación cross-comisión.

3. **Definir contrato QA por capa (Alto).**
   - Unitario: cálculos puros (research/indicadores).
   - Integración: vistas y permisos.
   - E2E focal: onboarding, intento, corrección docente, analíticas.

4. **Institucionalizar calidad continua (Alto).**
   - CI obligatorio con `manage.py check` + subset crítico de tests + suite completa nocturna.
   - Política “no merge con suite roja”.

---

## 5) Conclusión ejecutiva

Bajo ISO/IEC 9126, el sistema **presenta una base sólida y pedagógicamente consistente en funcionalidad central**, pero **no alcanza un nivel de conformidad robusto en fiabilidad** por la inestabilidad actual de la suite global y por riesgos de exactitud en métricas analíticas cuando hay escenarios multi-comisión.

En términos de priorización, el orden recomendado es:

1) fiabilidad de tests,  
2) exactitud analítica por comisión,  
3) consolidación de contratos de performance y portabilidad en CI.

Con ese cierre, el sistema quedaría en condiciones de una conformidad ISO/IEC 9126 sustancialmente más alta sin sacrificar los principios pedagógicos del proyecto.

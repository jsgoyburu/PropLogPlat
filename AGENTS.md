# AGENTS.md — Guía de trabajo para agentes en IPC-Lógica

Este archivo define las reglas para cualquier agente que trabaje en el repositorio.

---

## Estado funcional de referencia (2026-05)

Antes de proponer cambios, asumir como baseline estas capacidades ya vigentes:

- Arquitectura híbrida: la plataforma hace **verificación formal** y el/la docente conserva evaluación e interpretación pedagógica.
- Motor lógico semántico por equivalencia tabular, con notación Copi primaria y variantes ASCII (`&`, `.`, `->`, `<->`).
- Validación didáctica de paréntesis explícitos cuando se mezclan conectivos binarios en el mismo nivel.
- **Clasificador de errores** (`motor/clasificador.py`): 11 categorías semánticas para intentos de formalización incorrectos (tautologia, contradiccion, polaridad, mas_fuerte, mas_debil, equivalente_alt, error_parcial_1/2, error_sistemico, variables_extra/menos, sin_clasificar).
- Panel docente operativo (comisiones, prácticas, ejercicios, intentos, devoluciones y analíticas).
- Banco de prácticas con importación **copy-on-write** (`practica_origen`) y exclusión de prácticas derivadas del banco.
- **Analíticas M1–M6** orientadas a intervención pedagógica (no ranking), con umbrales configurables en `ConfigSitio`:
  - M1: métricas operativas de comisión/práctica.
  - M2: matriz juicio×cómputo (ejercicios tabla_verdad).
  - M3: curva de convergencia semántica por ejercicio.
  - M4: perfil de error en tabla de verdad.
  - M5: índice de atomización (variables usadas vs. solución).
  - M6: señal de baja variación entre intentos consecutivos.
  - M3–M5 disponibles via drill-down en dashboard y detalle de práctica (endpoint JSON `/analiticas/metricas_ejercicio/`).
- **Pistas pedagógicas** con Gemini (a partir del 5.º intento incorrecto en un mismo ejercicio, `intentos_incorrectos >= 5`) + fallback automático a Groq si Gemini alcanza cuota. Variables: `GEMINI_API_KEY`, `GROQ_API_KEY`.
- Onboarding con cambio obligatorio de contraseña + consentimientos (pedagógico/investigación) en primer ingreso.
- **Recuperación de contraseña por email** (`django.contrib.auth`, sin dependencias nuevas): link firmado, de un solo uso, que vence a las 24 h (`PASSWORD_RESET_TIMEOUT`). El backend se elige en cascada `BREVO_API_KEY` → `EMAIL_HOST` → consola. **En Railway hay que usar la API**: bloquea los puertos SMTP salientes salvo en Pro. El backend de API vive en `logica_ipc/email_backends.py` y usa `urllib`, sin dependencias. **Sin ninguna de las dos variables los mails salen por consola y nadie recibe nada**, así que la funcionalidad no debe anunciarse hasta tener credenciales cargadas y entrega verificada. El formulario público tiene techo de 5 pedidos por dirección y 20 por IP cada hora (leyendo `X-Forwarded-For` desde el proxy de confianza, no desde el primer valor, que lo escribe el cliente), y nunca revela si una dirección está registrada.
- Acceso estudiantil mixto: cuenta creada por docente **o** auto-registro desde link público de comisión (con inscripción automática en esa comisión).

Si una propuesta contradice este estado funcional sin justificación pedagógica explícita, debe descartarse o replantearse.

---

## PRIORIDAD MÁXIMA — PRINCIPIOS, OBJETIVOS Y HEURÍSTICAS DEL PROYECTO

> **Todo agente debe leer y respetar estas secciones antes de tomar cualquier decisión de diseño, implementación o corrección. Tienen precedencia sobre cualquier otra consideración técnica o de conveniencia.**

---

## PRINCIPIOS

Estas reglas tienen máxima prioridad en el proyecto. Cualquier agente que interactúe con este repositorio debe preservarlas incluso si entran en tensión con optimizaciones técnicas o simplificaciones algorítmicas.

### 1. La tecnología es mediación pedagógica, no sustituto del juicio docente

El sistema no reemplaza al docente.
La automatización se utiliza únicamente para:
- verificar condiciones formales mínimas,
- sostener la práctica,
- hacer visibles los procesos de aprendizaje.

Las decisiones de aprobación, interpretación del error y evaluación significativa permanecen en manos humanas.
Agentes de IA no deben diseñar ni proponer sistemas que automaticen la evaluación pedagógica completa.

### 2. La automatización tiene función formativa, no acreditadora

La corrección automática existe para habilitar la continuidad del trabajo, no para emitir juicios definitivos.
Una verificación automática significa:
> "el trabajo es formalmente suficiente para seguir practicando"

No significa:
> "el trabajo está aprobado".

Cualquier agente que modifique el sistema debe preservar esta distinción estructural.

### 3. El error es un objeto pedagógico valioso

El proyecto asume que el error:
- no es simplemente un fallo,
- es una ventana sobre el proceso de modelización.

Las herramientas tecnológicas deben hacer visible el error, no ocultarlo mediante correcciones automáticas opacas.
Agentes de IA deben priorizar:
- trazabilidad de intentos
- visibilidad del proceso
- comprensión de patrones de error

sobre la optimización de resultados correctos.

### 4. La modelización importa más que la coincidencia literal

En lógica aplicada al aprendizaje:
- pueden existir múltiples formalizaciones válidas,
- el objetivo no es reproducir una fórmula exacta.

El sistema utiliza equivalencia semántica (tabular) para reconocer soluciones correctas aunque difieran en:
- elección de variables
- orden de conectivos
- estructura superficial.

Agentes de IA no deben introducir restricciones sintácticas innecesarias que reduzcan esta pluralidad.

### 5. La lógica es una herramienta epistemológica, no un fin en sí misma

La lógica se enseña en este proyecto como propedéutica de la epistemología, no como disciplina autosuficiente.
Su función pedagógica es permitir:
- análisis de argumentos
- clarificación de estructuras de razonamiento
- comprensión de modelos científicos

dentro del marco de la tradición de la filosofía de la ciencia (concepción heredada, Hempel, Popper, etc.).
Las herramientas tecnológicas deben reforzar esta articulación conceptual, no aislar la lógica como técnica autónoma.

### 6. La tecnología debe ampliar oportunidades de aprendizaje

El proyecto parte de un diagnóstico institucional: en cursos masivos, ciertos dispositivos evaluativos funcionan como umbrales de presencia que afectan la continuidad estudiantil.

El objetivo de la plataforma es amortiguar ese umbral, proporcionando:
- práctica estructurada
- visibilidad del proceso
- oportunidades de intervención docente temprana.

Los agentes de IA deben evaluar cualquier modificación del sistema según este criterio: **¿amplía o reduce las oportunidades de aprendizaje?**

### 7. La analítica educativa es herramienta de intervención, no de vigilancia

Los datos de uso de la plataforma se utilizan para:
- identificar patrones de dificultad
- detectar interrupciones de la práctica
- facilitar intervenciones pedagógicas.

No deben utilizarse para:
- clasificar estudiantes
- etiquetar trayectorias como "fracaso"
- generar perfiles normativos rígidos.

Cualquier desarrollo analítico debe priorizar interpretabilidad pedagógica sobre sofisticación técnica.

### 8. Transparencia y legibilidad del sistema

El sistema debe ser comprensible para:
- estudiantes
- docentes
- investigadores.

Las decisiones algorítmicas deben ser:
- explícitas
- documentadas
- auditables.

Agentes de IA deben evitar introducir componentes opacos que dificulten la comprensión del funcionamiento pedagógico del sistema.

### 9. El conocimiento pedagógico es situado

Este proyecto surge de una investigación situada en la Universidad de Buenos Aires, en el contexto específico del CBC y del curso Introducción al Pensamiento Científico.
Las soluciones deben respetar ese contexto institucional.

Los agentes de IA deben evitar generalizaciones abstractas que ignoren las condiciones concretas de:
- cursadas masivas
- diversidad socioeducativa
- estructuras evaluativas existentes.

---

## OBJETIVOS

Los siguientes objetivos orientan el desarrollo del sistema y las contribuciones de cualquier agente de IA.

### 1. Sostener la llegada al primer hito evaluativo

Uno de los problemas centrales identificados en la investigación que origina el proyecto es que el primer examen funciona como umbral crítico de continuidad.

El sistema busca:
- aumentar la práctica previa,
- reducir la distancia entre clase y evaluación,
- mejorar la preparación para ese primer hito.

### 2. Fortalecer la capacidad de modelización

El objetivo pedagógico principal no es memorizar reglas lógicas sino aprender a modelizar problemas.

Esto implica desarrollar habilidades para:
- traducir lenguaje natural a estructuras formales
- identificar restricciones relevantes
- construir representaciones externas claras.

El sistema debe apoyar este proceso.

### 3. Hacer visible el proceso de aprendizaje

El sistema debe permitir observar:
- intentos sucesivos
- tipos de error
- evolución de las soluciones.

Esto sirve tanto para:
- la reflexión del estudiante
- la intervención docente.

### 4. Liberar tiempo docente para la intervención significativa

La automatización debe encargarse de tareas repetitivas de verificación formal.

Esto permite que el tiempo docente se concentre en:
- interpretación de errores
- devolución pedagógica
- acompañamiento de trayectorias.

### 5. Generar conocimiento pedagógico transferible

El proyecto no busca solo mejorar una práctica local. También pretende producir:
- evidencia empírica
- herramientas conceptuales
- recursos pedagógicos

que puedan ser utilizados en otros cursos introductorios con desafíos similares.

### 6. Mantener una arquitectura pedagógica híbrida

El sistema debe conservar una división deliberada de funciones:

**máquina:**
- verificación formal
- registro de procesos
- visibilidad de datos

**docente:**
- interpretación
- evaluación
- devolución pedagógica.

Esta arquitectura híbrida es un principio estructural del proyecto.

### 7. Integrar tecnología, investigación y docencia

El proyecto busca articular tres dimensiones:
- desarrollo tecnológico
- investigación educativa
- práctica docente.

Las herramientas producidas deben servir simultáneamente como:
- dispositivos pedagógicos
- instrumentos de investigación
- recursos didácticos abiertos.

### 8. Construir una cultura de criterios explícitos

El proyecto promueve prácticas de enseñanza donde:
- las consignas sean claras
- los criterios de evaluación sean legibles
- la devolución docente sea argumentada.

La tecnología debe reforzar esa cultura pedagógica.

---

## NON-GOALS

Los siguientes no son objetivos del proyecto. Los agentes de IA no deben orientar el desarrollo hacia estas metas, incluso si parecen mejoras técnicas.

### 1. Automatizar completamente la evaluación

El proyecto no busca reemplazar la evaluación docente.
La corrección automática cumple únicamente una función formativa y habilitante, verificando condiciones mínimas de consistencia lógica.
La aprobación final requiere interpretación pedagógica y permanece bajo responsabilidad docente.
Los agentes de IA no deben introducir sistemas que automaticen la aprobación de ejercicios o trabajos.

### 2. Optimizar la tasa de respuestas correctas

El objetivo del sistema no es maximizar respuestas correctas.
Un sistema que reduce errores simplemente ocultándolos o guiando excesivamente al estudiante empobrece el valor pedagógico del proceso.
Los agentes deben priorizar:
- visibilidad del error
- trazabilidad del proceso
- comprensión de patrones de razonamiento

por sobre métricas superficiales de rendimiento.

### 3. Convertir la lógica en entrenamiento mecánico

El sistema no busca producir entrenamiento repetitivo de reglas formales.
La lógica se enseña como instrumento de modelización conceptual, dentro de un marco epistemológico más amplio.
Los agentes deben evitar introducir dinámicas propias de:
- drill-and-practice automatizado
- gamificación superficial
- ejercicios descontextualizados.

### 4. Construir sistemas de clasificación estudiantil

El sistema no pretende clasificar estudiantes en categorías como: buenos / malos, aptos / no aptos, riesgo / éxito.
Las analíticas existen para apoyar decisiones pedagógicas, no para generar perfiles normativos.
Los agentes de IA deben evitar introducir sistemas de scoring o ranking estudiantil.

### 5. Sustituir la interacción pedagógica por automatización

El proyecto no busca reducir la interacción docente.
Por el contrario, la automatización pretende liberar tiempo docente para intervenciones pedagógicas de mayor calidad.
Cualquier desarrollo que reduzca el espacio de interpretación o devolución docente contradice los objetivos del sistema.

### 6. Maximizar la complejidad tecnológica

El proyecto no busca desarrollar tecnología por sí misma.
Las soluciones deben ser: comprensibles, mantenibles, pedagógicamente justificadas.
Los agentes deben evitar introducir arquitecturas complejas que no aporten valor pedagógico claro.

---

## ANTI-PATTERNS

Los siguientes patrones son errores de diseño conocidos que deben evitarse. Cuando un agente detecte uno de estos patrones, debe priorizar su corrección o prevención.

### 1. "Correct answer engine"

Sistema donde la plataforma se limita a verificar si la respuesta coincide con una solución predeterminada.

**Problemas:**
- penaliza formalizaciones alternativas válidas
- confunde coincidencia sintáctica con corrección conceptual
- desalienta la modelización propia.

El sistema debe privilegiar equivalencia semántica sobre coincidencia literal.

### 2. "Invisible correction"

Sistema donde el algoritmo corrige automáticamente la respuesta sin mostrar el proceso ni el error.

**Problemas:**
- el estudiante no comprende el error
- el proceso de razonamiento se vuelve opaco.

Los errores deben ser explícitos y visibles.

### 3. "Opaque algorithm"

Introducción de modelos algorítmicos cuya lógica de funcionamiento no puede explicarse pedagógicamente.

**Problemas:**
- reduce la transparencia del sistema
- dificulta la reflexión didáctica.

Los agentes deben privilegiar métodos interpretables.

### 4. "Performance fetishism"

Optimización excesiva de métricas como precisión, rapidez, porcentaje de aciertos, sin considerar su significado pedagógico.

Los agentes deben evaluar cualquier métrica preguntando: **¿Qué proceso de aprendizaje representa realmente?**

### 5. "Algorithmic authority"

Situación donde el sistema aparece como autoridad incuestionable.

**Problemas:**
- desalienta la reflexión crítica
- desplaza el rol docente.

La plataforma debe ser entendida como herramienta pedagógica, no como árbitro epistemológico.

### 6. "Student surveillance"

Uso de analítica para monitorizar estudiantes sin propósito pedagógico claro.

**Problemas:**
- transforma el sistema en herramienta de vigilancia
- deteriora la relación pedagógica.

Los datos deben utilizarse únicamente para apoyo a la enseñanza.

### 7. "Pedagogical drift"

Desarrollo tecnológico que gradualmente se aleja del marco pedagógico original.

**Síntomas típicos:**
- nuevas funciones sin justificación didáctica
- decisiones guiadas exclusivamente por facilidad técnica.

Los agentes deben verificar que cada modificación sea consistente con los PRINCIPIOS del proyecto.

**Regla de prioridad:** Cuando exista tensión entre eficiencia técnica, innovación tecnológica y cumplimiento de los PRINCIPIOS pedagógicos, los PRINCIPIOS pedagógicos tienen prioridad absoluta.

---

## DECISION HEURISTICS

Cuando un agente de IA deba tomar decisiones de diseño, implementación o análisis dentro de este proyecto, deberá aplicar las siguientes heurísticas. Estas reglas operan después de los PRINCIPIOS y antes de optimizaciones técnicas.

### 1. Preferir visibilidad del proceso sobre corrección automática

Si una implementación puede:
- A) mostrar el proceso de razonamiento y los errores
- B) ocultarlos pero producir respuestas correctas más rápido

preferir siempre **A**. El objetivo pedagógico es comprender el razonamiento, no solo obtener la respuesta correcta.

### 2. Preferir interpretabilidad sobre sofisticación algorítmica

Si una solución utiliza un método simple y comprensible vs. un modelo más complejo pero opaco, preferir el método simple. Los docentes deben poder explicar cómo funciona el sistema.

### 3. Preferir intervención docente sobre automatización total

Si una funcionalidad puede resolverse automáticamente o puede requerir intervención docente pero preservar interpretación pedagógica, preferir la segunda, salvo que la tarea sea puramente mecánica. El sistema no debe desplazar el juicio pedagógico humano.

### 4. Preferir equivalencia semántica sobre coincidencia sintáctica

Si el sistema puede evaluar respuestas mediante coincidencia literal de fórmulas o equivalencia semántica (por ejemplo, tablas de verdad), preferir la equivalencia semántica. El objetivo es reconocer formalizaciones conceptualmente correctas, no imponer una única expresión válida.

### 5. Preferir pluralidad de soluciones sobre soluciones únicas

Si un ejercicio puede resolverse mediante una única formalización o mediante múltiples formalizaciones equivalentes, preferir la pluralidad. La modelización lógica admite diversas representaciones válidas.

### 6. Preferir simplicidad pedagógica sobre sofisticación tecnológica

Si dos implementaciones tienen el mismo valor pedagógico, elegir siempre la más simple. La complejidad tecnológica solo está justificada cuando aporta valor didáctico claro.

### 7. Preferir herramientas que amplíen oportunidades de aprendizaje

Si una modificación facilita el trabajo del sistema pero no el aprendizaje del estudiante, preferir la que facilita el aprendizaje. La prioridad del proyecto es el aprendizaje, no la eficiencia técnica.

### 8. Preferir datos interpretables sobre métricas agregadas

Si el sistema puede producir métricas agregadas (scores, rankings) o información sobre procesos (intentos, tipos de error), preferir la segunda. Los docentes necesitan comprender trayectorias de aprendizaje, no solo indicadores de rendimiento.

### 9. Preferir evidencia empírica sobre intuición técnica

Cuando una decisión pedagógica o tecnológica sea incierta: buscar evidencia en datos de uso, análisis de errores, resultados de cohortes anteriores. Los cambios importantes deben basarse en observación del proceso real de aprendizaje.

### 10. Preferir coherencia con el marco pedagógico del proyecto

Cuando exista tensión entre facilidad de implementación y alineación con los principios del proyecto, preferir siempre la segunda. Los agentes deben verificar que cualquier cambio sea consistente con PRINCIPIOS, OBJETIVOS, NON-GOALS y ANTI-PATTERNS.

### 11. Preferir mejoras incrementales sobre rediseños radicales

El proyecto sigue una metodología de investigación basada en diseño (design-based research). Cuando sea posible, implementar cambios de forma incremental, observable y evaluable antes de introducir transformaciones estructurales.

### 12. Preferir arquitectura híbrida humano–máquina

El sistema se basa en una división deliberada de funciones:

**máquina:** verificación formal · registro de procesos · visibilidad de datos

**docente:** interpretación · evaluación · devolución pedagógica.

Los agentes deben preservar esta arquitectura híbrida.

**Meta-heurística:** Cuando exista duda sobre cómo proceder, aplicar la siguiente regla: diseñar el sistema de forma que haga más visibles los procesos de razonamiento, más legible la intervención docente y más accesible la práctica para el estudiante.

---

## 0) Objetivo

Permitir continuidad entre agentes y ramas sin pérdida de contexto.

## 1) Regla innegociable: actualizar MEMORY.md

**Siempre** que un agente haga una intervención (con o sin cambios de código), debe:

1. Editar `MEMORY.md`.
2. Agregar/actualizar una entrada en la **Bitácora de trabajo de agentes**.
3. Reflejar estado real (tests, commit y PR en estado pendiente o final).

Esto aplica en `master` y en cualquier rama de trabajo.

## 2) Antes de tocar código

- Revisar `MEMORY.md` para entender contexto reciente.
- Revisar `README.md` para mantener consistencia de documentación pública.
- Si la tarea cambia comportamiento funcional, actualizar también la sección “Estado actual” de `MEMORY.md`.

## 3) Después de tocar código

- Ejecutar checks/tests relevantes.
- Actualizar `README.md` si cambia instalación, funcionalidad, variables o flujos.
- Registrar en `MEMORY.md`: pedido, cambios, checks, commit y PR.

## 4) Criterios de documentación mínima

Si el cambio afecta alguno de estos puntos, documentar explícitamente:

- Motor lógico (sintaxis, validaciones, equivalencia, errores).
- Flujos de onboarding/auth (primer login, consentimientos).
- Gestión docente (comisiones, prácticas, ejercicios, intentos).
- Deploy/configuración (Railway, variables de entorno, migraciones).

## 5) Formato de bitácora (obligatorio)

Usar este template en `MEMORY.md`:

```md
### YYYY-MM-DD HH:MM (TZ) — agente:<nombre> — rama:<branch>
- Pedido: ...
- Cambios: ...
- Tests/checks: ...
- Commit: <hash corto> (<mensaje>)
- PR: <título o N/A>
```

Si algo no existe todavía, marcar `pendiente`.

## 6) Principio operativo

**ATENCIÓN**: "GOYBURU - Memoria Profesional v2.pdf" Es la memoria profesional de docencia del desarrollador, y otorga contexto para comprender los principios y objetivos del sistema.

| Fecha | Decisión                                  | Alternativa descartada                               | Razón                                                                                                                                                      |
| ----- | ------------------------------------------ | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2025  | Corrección por equivalencia tabular       | Corrección sintáctica                              | Acepta formalizaciones equivalentes válidas                                                                                                                |
| 2026  | Alta de cuentas estudiantiles mixta (docente o link de comisión) | Auto-registro abierto sin contexto de comisión       | Mantiene control de acceso por comisión y, a la vez, reduce fricción de ingreso en cursos masivos.                                                       |
| 2025  | SQLite solo para desarrollo local; PostgreSQL en producción | SQLite en producción                                 | Railway usa filesystem efímero; producción requiere persistencia robusta en base administrada.                                                             |
| 2025  | Alpine.js en lugar de React/Vue            | React                                                | Mantenedor único con perfil Python; sin build step                                                                                                         |
| 2025  | Motor como app Python pura                 | Integrado en views                                   | Testeable sin Django; reemplazable sin tocar vistas                                                                                                         |
| 2025  | es_publico en Ejercicio                    | Tabla separada para banco                            | Simplicidad; la distinción es binaria                                                                                                                      |
| 2025  | Progreso como tabla explícita             | Calcular desde Intento                               | Evita recorrer todos los intentos en cada request                                                                                                           |
| 2025  | Documentación con Sphinx + Napoleon       | Markdown / sin doc                                   | Autodoc desde docstrings; Google style legible en código y en HTML                                                                                         |
| 2025  | Notación Copi como primaria               | ASCII puro (`&`, `->`)                           | Alineación con el libro de texto usado en IPC/CBC-UBA (Copi, *Introduction to Logic*); `->` se mantiene como alternativa teclado-amigable para `⊃` |
| 2026  | Aceptar `.` como conjunción alternativa  | Requerir solo `·` y `&`                          | Reduce fricción de tipeo en teclados donde el punto medio `·` no está disponible y mantiene compatibilidad con material que usa notación ASCII simple. |
| 2025  | Panel docente en frontend (no admin-first) | Gestión exclusiva por Django admin                  | Mejora adopción por docentes no técnicos y reduce dependencia del admin                                                                                   |
| 2025  | Comentarios ligados a `Intento`          | Comentarios por ejercicio sin intento                | Preserva contexto temporal y trazabilidad del historial                                                                                                     |
| 2026  | Paréntesis explícitos para mezclar conectivos binarios | Aceptar precedencia implícita (`A · B ∨ C`, `p · q ⊃ r`) | Pedagógicamente se evita ambigüedad: cuando conviven conectivos binarios distintos en el mismo nivel, la estructura debe explicitarse con paréntesis para evitar correcciones automáticas por precedencia sintáctica. |
| 2025  | Importación Excel tolerante a errores     | Fallar importación completa ante una fila inválida | Prioriza robustez operativa y evita bloquear altas masivas                                                                                                  |
| 2026  | `practica_origen` FK en Practica (copy-on-write) | Siempre duplicar al importar; no duplicar nunca (M2M) | Importar una práctica marca la copia como "derivada" (`practica_origen`). El banco de prácticas excluye derivadas, evitando duplicados visibles. Si el docente modifica la práctica importada (edita campos o cambia ejercicios), se desancla automáticamente y vuelve a aparecer en el banco como práctica independiente. |
| 2026  | Bancos del panel = propios + públicos, sin excepción `is_staff` | Que el admin vea todas las prácticas y ejercicios en el panel (criterio previo) | El alcance de los bancos de `comisiones_list` se define por autoría y por `es_publica`/`es_publico`, no por rol. Es el mismo principio que 7040945 aplicó a las comisiones: nadie —tampoco el admin— tiene un listado global en el panel docente. Lo que un docente quiere compartir lo marca como público; el admin conserva su permiso de editar/eliminar, pero eso es un permiso, no una vista. Corolario: sobre un ejercicio público ajeno la plantilla no ofrece Editar/Eliminar, porque `ejercicio_edit` exige autoría. |
| 2026  | `Comision` es el aula y persiste; `Cohorte` es la camada que se renueva | Una `Comision` nueva por cuatrimestre; clonar `PracticaComision` por camada | Crear una comisión por cuatrimestre la deja desconectada de la anterior y obliga a reimportar las prácticas. Clonar `PracticaComision` duplicaría filas y desincronizaría la configuración entre camadas. `PracticaComision` no tiene cohorte a propósito: pertenece al aula. Al cambiar de cohorte cambia la lista de estudiantes y **no** la de prácticas. |
| 2026  | La cohorte es la camada de pertenencia, no el período del calendario | Atribuir por fecha del intento (`timestamp`) | Quien cursó en 2026-C1 y practica en septiembre para rendir un final sigue siendo de 2026-C1. Atribuir por calendario le movería el historial a una camada a la que nunca perteneció. La cohorte de un intento sale de la inscripción más reciente del estudiante en esa comisión. |
| 2026  | `Cohorte.activa` no controla acceso | Que la cohorte activa sea también el gate de acceso estudiantil | Estudiantes de camadas anteriores tienen que poder practicar para rendir finales, y lxs docentes corregirles. `activa` solo fija el default del selector y de las altas. Corolario: las fechas de apertura/cierre de `PracticaComision`, que son del aula y se comparten entre camadas, solo frenan a la cohorte activa. |
| 2026  | Crear cohorte exige `is_superuser`, no `is_staff` | El mismo gate `is_staff` que el resto del panel docente | Es la única acción **global** del panel: cambia la cohorte activa de toda la plataforma, no de una comisión. Por eso vive en el home (`comisiones_list`) y no en la vista de comisión, y por eso su gate es más estricto que el de las altas, que son locales a un aula. |
| 2026  | Una camada cerrada no crece ni suma parciales, pero se le sigue trabajando adentro | Solo lectura total en cohortes no activas; o sin restricción alguna | Bloquear todo impediría corregirle a quien rinde final. No bloquear nada dejaría crecer camadas ya cerradas. Se bloquean alta individual, importación masiva y creación de parcial; siguen habilitadas la corrección de intentos y la carga de notas de parciales existentes. Bloqueada significa dos cosas: el formulario no se renderiza **y** el POST rechaza. |
| 2026  | Re-inscripción por búsqueda exacta de username/email | Buscador con coincidencia parcial o autocompletado | Con búsqueda parcial un docente podría tantear el padrón de cuentas de otras comisiones. Lxs recursantes de la propia comisión salen de un `<select>` porque esas cuentas ya son visibles para ese docente; para pases de otra comisión hay que saber el dato de antemano. |
| 2026  | Hasher rápido en tests bajo `_ES_TEST` (`argv[1] == 'test'`) | Dejar el PBKDF2 de producción; o detectar con `'test' in argv` | El default de Django 6 son 1.200.000 iteraciones (~1,9 s por hash): la suite tardaba 32 min derivando claves en vez de ejercitar la aplicación. Detectar con `'test' in argv` matchea un *argumento* igual a 'test': `manage.py changepassword test` guardaba esa contraseña de producción con MD5. Hay que mirar la posición del subcomando. |

# MEMORY.md — Memoria operativa del repositorio

Este archivo existe para que **distintos agentes** (Codex, Claude u otros) puedan retomar contexto sin depender de memoria externa.

## Regla obligatoria

Cada vez que un agente trabaje en este repositorio (en `master` o en cualquier rama):

1. Debe actualizar este archivo.
2. Debe agregar una entrada en la sección **Bitácora de trabajo de agentes**.
3. Debe mantener vigente la sección **Estado actual** si cambió el producto.

> Si no hubo cambios de código, igual registrar la intervención y dejar explícito “sin cambios”.

---

## 1) Resumen del proyecto (estado vigente)

- Plataforma web Django para práctica de lógica proposicional (IPC/CBC-UBA).
- Corrección automática semántica por equivalencia tabular con `sympy`.
- Panel docente frontend como flujo principal (no admin-first).
- Soporta gestión de comisiones, prácticas, ejercicios, intentos y progreso.
- Incluye analíticas docentes, importación Excel, y comentarios por intento.
- Incluye flujo de primer ingreso con cambio de contraseña + consentimientos.

---

## 2) Historia reconstruida del repositorio (por etapas)

### Etapa A — Fundación (2026-02-19)

- Inicialización del proyecto Django y primeras apps.
- Se consolida el objetivo del panel docente.
- Se agregan vistas de gestión para ejercicios, estudiantes y comisiones.
- Se suma preview/sandbox de verificación en formularios docentes.

### Etapa B — Flujo académico núcleo (2026-02-19 a 2026-02-20)

- Se implementa historial de intentos por estudiante.
- Se agregan comentarios docentes asociados a intento.
- Se incorpora gestión de ejercicios dentro de prácticas.
- Se corrigen reglas de progresión y revisión docente.

### Etapa C — Operación y despliegue (2026-02-19 a 2026-02-21)

- Ajustes de Railway/PostgreSQL (`DATABASE_URL`, `railway.toml`, host internos).
- Migraciones y estrategia para datos iniciales/carga.
- Personalización de configuración del sitio y favicon persistente en DB.

### Etapa D — Robustez del motor y ordenamientos (2026-02-19 a 2026-02-25)

- Validación de ambigüedad por conectivos binarios mixtos sin paréntesis.
- Correcciones de colisiones de orden en ejercicios de práctica.
- Evolución hacia ejercicios de tablas de verdad completas.
- Se acepta `.` como conjunción alternativa.

### Etapa E — UX docente y analíticas (2026-02-20 a 2026-02-26)

- Mejoras responsive, perfil de usuario y navegación de retorno.
- Métricas avanzadas en dashboard/comisión.
- Métricas de compromiso en el tiempo y errores sistemáticos.
- Descripción enriquecida de prácticas (CKEditor 5).

### Etapa F — Gobernanza y consentimiento (2026-03-07)

- Integración de consentimientos informados en primer ingreso.

---

## 3) Estado actual (snapshot funcional)

- **Auth:** usuario personalizado + middleware de primer ingreso.
- **Onboarding:** cambio de contraseña obligatorio + consentimientos pedagógico/investigación; persistencia alineada de campos socioeducativos del formulario completo (incluye laboral, secundaria y respuestas compuestas como cirugía en un solo campo).
- **Ejercicios/prácticas:** ordenados, con desbloqueo secuencial y ventanas de apertura/cierre; el contenido original en castellano admite traducciones opcionales al inglés, francés y alemán cargadas desde el admin, con fallback explícito al original.
- **Idiomas:** selector visible por persona (castellano, inglés, francés y alemán) e idioma predeterminado configurable por instalación.
- **Intercambio pedagógico:** prácticas y ejercicios se descargan como ZIP con un `package.json` versionado; la instalación crea material privado del docente, sin importar personas, intentos ni analíticas.
- **Instalación y deploy:** asistente inicial protegido por `SETUP_TOKEN`, `railway.toml`, `Dockerfile`, Compose y endpoint `/healthz/`; PostgreSQL obligatorio en producción y SQLite reservado al desarrollo local.
- **Motor lógico:** notación Copi + equivalentes ASCII; comparación tabular.
- **Analíticas M1–M6:** métricas operativas (M1) + avanzadas: M2 (matriz juicio×cómputo en tabla_verdad), M3 (convergencia semántica por ejercicio), M4 (perfil de error en tabla), M5 (índice de atomización), M6 (señal de baja variación/adivinación). M3–M5 expuestos via drill-down con fetch JSON por ejercicio en dashboard y detalle de práctica. M2 y M6 en contexto directo del dashboard. Cacheadas 5 min por comisión.
- **Motor clasificador:** `motor/clasificador.py` clasifica errores de formalización en 11 categorías (tautologia, contradiccion, polaridad, mas_fuerte, mas_debil, equivalente_alt, error_parcial_1/2, error_sistemico, variables_extra/menos, sin_clasificar). Poblar histórico con `python manage.py poblar_error_categoria`.
- **Pistas Gemini+Groq:** `GEMINI_API_KEY` para pistas pedagógicas en intentos no verificados. Si Gemini devuelve 429, fallback automático a Groq (`GROQ_API_KEY`, modelo llama-3.1-8b-instant).
- **Investigación:** módulo con métricas de onboarding (NSE, puntaje lógico, pandemia, cohortes, facultades/carreras y cruces con desempeño en ejercicios), restringidas a consentimiento de investigación.
- **Motor lógico:** `validar_parentesis_en_operaciones_mixtas` aplicado en formalización Y argumentos.
- **Progreso:** clave `(estudiante, practica_comision)` — es **por cursado, no por práctica canónica**: una misma `Practica` en dos comisiones tiene una fila de progreso en cada una, con su propio puntero. Desbloqueo configurable por `PracticaComision.desbloqueo_secuencial` (default `True` = comportamiento histórico). La lógica vive en `ejercicios/progreso.py` (`avanzar_progreso(estudiante, ep, pc)`, `eps_resueltos`, `esta_resuelto`), toda acotada por comisión y compartida por la API de intentos y la aprobación docente. En modo libre el `ejercicio_practica_actual` se recalcula como el primero sin resolver. `practica_origen` FK para copy-on-write de prácticas importadas.
- **Correctitud efectiva:** `ejercicios/correctitud.py` define `Q_CORRECTO`/`Q_INCORRECTO` como única fuente: `aprobado_docente` tiene precedencia y, si el docente no revisó, se usa el resultado del motor. Lo consumen analíticas, el servidor MCP y el panel docente.
- **Panel docente — dos métricas:** el avance se muestra desdoblado en **Resuelto** (correctitud efectiva; no requiere corrección manual, informativa en comisiones masivas) y **Revisado** (`aprobado_docente=True`; alimenta el badge `completa` y el avance promedio, sin cambios de semántica). Los índices `_resueltos_por_estudiante_ep` y `_aprobados_por_estudiante_ep` llevan la comisión en la clave, porque una misma `Practica` canónica puede estar asignada a varias comisiones.
- **Cobertura de tests:** 41 tests Django (ejercicios + docentes) con helper `_u()` que bypasea el middleware.
- **Paginación:** `correccion_pendiente` paginada con Django Paginator (25/página).
- **Documentación:** README y AGENTS orientados a trabajo multiagente.

---

## 4) Convención de actualización para agentes

Al finalizar cualquier tarea, agregar entrada con este formato:

```md
### YYYY-MM-DD HH:MM (TZ) — agente:<nombre> — rama:<branch>
- Pedido: ...
- Cambios: ...
- Tests/checks: ...
- Commit: 499adce (Agregar pista pedagógica opcional con Gemini en intentos incorrectos)
- PR: <título o N/A>
```

Si todavía no se hizo commit al momento de editar MEMORY, usar `Commit: e39dc5a (Mostrar pregunta de recibido solo si terminó CBC)`.

---

## 5) Bitácora de trabajo de agentes

### 2026-03-07 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright
- Pedido: auditoría profunda del proyecto + implementar fixes críticos de seguridad.
- Auditoría: revisión completa de modelos, vistas, API, motor, tests y configuración.
- Hallazgos principales: (1) `IntentoCreateView` sin check de inscripción — cualquier usuario autenticado podía enviar intentos a comisiones ajenas; (2) `intento_comentario_update` e `intento_aprobacion_update` en `docentes/views.py` ya tenían check correcto (falso positivo en auditoría); (3) 5 índices faltantes en Intento y Practica; (4) cobertura de tests Django ~0% en vistas.
- Cambios: `ejercicios/api/views.py` — `IntentoCreateView.post()`: se agrega check `comision.estudiantes.filter(pk=user.pk).exists()` + `select_related('practica__comision', 'ejercicio')` en `get_object_or_404`.
- Tests/checks: 25 tests Django corrieron; 23 errores preexistentes por `SECRET_KEY` vacía en worktree; 0 fallos nuevos relacionados con el cambio.
- Commit: 0c8d7d1 (Seguridad: verificar inscripción en IntentoCreateView)
- PR: #27 — https://github.com/jsgoyburu/IPC-Logica/pull/27

### 2026-03-07 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright (índices)
- Pedido: implementar índices de rendimiento (alta prioridad de auditoría).
- Cambios: `ejercicios/models.py` + `ejercicios/migrations/0014_indices_rendimiento.py`. Tres índices: `practica_origen_idx` en Practica; `intento_correcto_aprobado_idx` e `intento_aprobado_idx` en Intento.
- Tests/checks: 25 tests corridos con SECRET_KEY provista. 3 OK. 22 FAIL pre-existentes: `ForzarCambioPasswordMiddleware` redirige usuarios de test sin `debe_cambiar_password=False`. Migración 0014 aplicada OK en test DB.
- Commit: 8878b0b (Performance: índices en Intento y Practica)
- PR: Refuerza rechazo con devolución obligatoria en correcciones pendientes

### 2026-03-07 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright
- Pedido: fix comparación tabular en verificador + tests de infraestructura.
- Cambios: `motor/tabla.py` revertido a preorder_traversal (orden pedagógico B⊃A). `motor/verificador.py`: comparación con orden canónico de filas cuando las variables son las mismas; helper `_u()` con consentimientos en tests. `docentes/tests.py`: cobertura completa de vistas (22 tests → 0 fallos con `_u()`). Correcciones de 3 tests que fallaban por redirect 302, formato template y `aprobado_docente`.
- Tests/checks: 28 tests OK (ejercicios + docentes).
- Commit: 1108085 (Motor: fix comparación tabular cuando sympy reordena variables)
- PR: #28 (infraestructura tests, cerrado) + #29 (fix verificador.py) — https://github.com/jsgoyburu/IPC-Logica/pull/29

### 2026-03-07 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright
- Pedido: (1) tests para `practica_origen` y desbloqueo progresivo; (2) aplicar `validar_parentesis_en_operaciones_mixtas` en `verificar_argumento()`.
- Cambios: `motor/verificador.py`: agrega `validar_parentesis_en_operaciones_mixtas(formula)` en el loop de parseo de fórmulas del estudiante en `verificar_argumento()`. `docentes/tests.py`: nueva clase `PracticaOrigenTests` (7 tests) cubre import, copia de ejercicios, banco, desanclado. `ejercicios/tests.py`: `DesbloqueoProgresivoTests` (4 tests) cubre `_avanzar_progreso()` e2e; `PreviewArgumentoApiTests` (2 tests) cubre el endpoint y la validación de paréntesis mixtos. Corrección: answer incorrecto debe ser `~p` no `q` (misma forma proposicional); `PracticaForm` requiere `comision` en el POST.
- Tests/checks: 41 tests OK.
- Commit: 21ac136 (Tests y fix: practica_origen, desbloqueo progresivo, validar_parentesis en argumentos)
- PR: #30 — https://github.com/jsgoyburu/IPC-Logica/pull/30

### 2026-03-07 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright
- Pedido: (1) paginación en listas docente; (2) cache 5 min en analíticas de `comision_detail`.
- Cambios: `docentes/views.py`: agrega imports `Paginator/EmptyPage/PageNotAnInteger` y `cache`; `correccion_pendiente` usa `Paginator(qs, 25)` + itera solo sobre `page_obj` (evita procesar todos los intentos en Python); `comision_detail` cachea bloque de 9 funciones analíticas bajo `analiticas_{comision_id}` con TTL 300 s. `templates/docentes/correccion_pendiente.html`: itera sobre `page_obj`, agrega controles `← / N/M / →` con clase `.paginacion-ctrl`.
- Tests/checks: 41 tests OK.
- Commit: 1bb3deb (Paginación en correccion_pendiente + cache 5 min en analíticas de comision_detail)
- PR: #31 — https://github.com/jsgoyburu/IPC-Logica/pull/31

### 2026-03-07 00:00 (ART) — agente:codex — rama:work
- Pedido: reconstruir `README.md`, crear `MEMORY.md`, reconstruir `AGENTS.md` con obligación de actualizar memoria.
- Cambios: redacción integral de documentación operativa multiagente y resumen histórico del repo.
- Tests/checks: `pytest motor/tests/` (8 fallos preexistentes en motor/tests/test_tabla.py y motor/tests/test_verificador.py).
- Commit: 8b07e9e (Reconstruir documentación base y memoria operativa multiagente).
- PR: Reconstruir README y establecer memoria operativa multiagente.

### 2026-03-07 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright
- Pedido: sincronizar `AGENTS.md` del worktree con la versión completa de `master` (worktree tenía versión vieja sin la primera mitad).
- Cambios: `AGENTS.md` actualizado con las secciones PRINCIPIOS (9), OBJETIVOS (8), NON-GOALS (6), ANTI-PATTERNS (7) y DECISION HEURISTICS (12) que faltaban. El contenido de §0-§6 no cambió.
- Tests/checks: sin cambios de código; no aplica.
- Commit: 8e2610b (Docs: sincronizar AGENTS.md con versión completa de master)
- PR: N/A

### 2026-03-08 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright (banco)
- Pedido: bug — prácticas importadas (copiadas) aparecían en el Banco de Prácticas del panel docente.
- Root cause: `comisiones_list` en `docentes/views.py` construía `mis_practicas_qs` sin filtrar `practica_origen__isnull=True`. Solo `_get_practicas_disponibles` (selector de importación) lo filtraba, pero el banco del panel principal no.
- Cambios: `docentes/views.py` — `mis_practicas_qs` ahora incluye `.filter(practica_origen__isnull=True)` en ambas ramas (docente y staff).
- Tests/checks: 41/41 OK.
- Commit: c86c3e0 (Fix: excluir prácticas derivadas del Banco de Prácticas en comisiones_list)
- PR: #33 — https://github.com/jsgoyburu/IPC-Logica/pull/33

### 2026-03-08 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright (distribucion)
- Pedido: panel "Distribución de intentos hasta resolver" mostraba el mismo ejercicio N veces (una por práctica que lo contiene). Rediseñar para mostrar agregado por ejercicio con desplegable por comisión/práctica.
- Root cause: `_distribucion_intentos` agrupaba por `ejercicio_practica_id` (la fila intermedia), no por `ejercicio_id`. El modelo de datos es correcto (practica_import no duplica ejercicios), solo era un bug de agrupación en la analítica.
- Cambios:
  - `analiticas/views.py`: `_distribucion_intentos` refactorizada — agrupa por `ejercicio_id`, calcula estadísticas agregadas + lista `detalle` (por comisión/práctica) para el desplegable.
  - `templates/analiticas/dashboard.html`: panel usa `<tbody x-data="{ abierto: false }">` por ejercicio; botón ▼ visible solo si `detalle|length > 1`; fila expandible con subtabla "Comisión · Práctica".
  - `templates/docentes/comision_detail.html`: igual pero detalle muestra solo "Práctica" (comisión ya es fija).
- Tests/checks: 41/41 OK.
- Commit: f291d0f (Fix: agrupar distribucion_intentos por ejercicio con desplegable por comisión/práctica)
- PR: #34 — https://github.com/jsgoyburu/IPC-Logica/pull/34

### 2026-03-08 (ART) — agente:claude-sonnet-4-6 — rama:claude/adoring-wright
- Pedido: implementar mejoras pedagógicas identificadas en auditoría según AGENTS.md (excepto resaltado de diferencias en tablas, que es intencional).
- Cambios:
  - **A** `accounts/models.py` + migración `0007`: 5 nuevos campos en `ConfigSitio` (`umbral_min_intentos`, `umbral_riesgo`, `umbral_silencio_dias`, `umbral_maraton`, `umbral_arranque_dias`). Ya no son constantes hardcodeadas.
  - **A** `analiticas/views.py`: eliminadas constantes `_MIN_INTENTOS`, `_RIESGO_UMBRAL`, `_SILENCIO_UMBRAL`, `_MARATON_UMBRAL`, `_ARRANQUE_DIAS`, `_ERROR_CONSENSO_MIN`. Reemplazadas por parámetros en cada función; vistas leen de `ConfigSitio.get()`. Umbrales visibles en contexto de template como `cfg_umbral_*`.
  - **A** `docentes/views.py` (`comision_detail`): actualizado para usar `cfg.*` en lugar de constantes.
  - **B** `templates/ejercicios/ejercicio.html`: párrafo pedagógico junto a las tablas comparadas ("Encontrá la fila donde tu tabla difiere de la esperada…").
  - **C+F** `templates/analiticas/dashboard.html` + `templates/docentes/comision_detail.html`: criterios de cada panel documentados con valores reales de `cfg_*`; "Estudiantes en riesgo" renombrado a "Señales de alerta — estudiantes que podrían necesitar acompañamiento"; "fallos seguidos" sin etiqueta clasificatoria.
  - **D** `docentes/views.py` (`intento_aprobacion_update`): comentario obligatorio al rechazar (server-side); JS `onclick` en botones de rechazo (client-side); placeholder actualizado a "Devolución (obligatoria al rechazar)…".
  - **E** `templates/docentes/estudiante_detail.html` + `templates/ejercicios/ejercicio.html`: "Corrección automática" → "Verificación formal"; badges "Correcto"/"Incorrecto" → "Formalmente válido"/"No verificado" con nota "(automático)".
- Tests/checks: 41/41 OK.
- Commit: 6b4269b (Mejoras pedagógicas según auditoría AGENTS.md)
- PR: #32 — https://github.com/jsgoyburu/IPC-Logica/pull/32


### 2026-03-08 22:43 (UTC) — agente:codex — rama:work
- Pedido: reforzar flujo de rechazo en correcciones pendientes (etiqueta/placeholder explícitos, validación client-side y tests de vista para rechazo sin comentario).
- Cambios: `templates/docentes/correccion_pendiente.html` ahora muestra “Devolución docente (obligatoria al rechazar)”, placeholder alineado y validación JS en botón de rechazo para evitar envío sin comentario; `docentes/tests.py` agrega cobertura de `intento_aprobacion_update` verificando rechazo sin comentario desde corrección pendiente (sin mutar estado) y consistencia del mensaje de error.
- Tests/checks: `python manage.py test docentes.tests.IntentoAprobacionUpdateTests` (falla inicial por `SECRET_KEY` vacía); `SECRET_KEY=test-secret python manage.py test docentes.tests.IntentoAprobacionUpdateTests` (OK, 2 tests).
- Commit: 91c1986 (Refuerza rechazo con devolución obligatoria en correcciones pendientes)
- PR: Refuerza rechazo con devolución obligatoria en correcciones pendientes

### 2026-03-08 23:49 (UTC) — agente:codex — rama:work
- Pedido: actualizar `README.md` para reflejar el estado actual del sitio.
- Cambios: reescritura de README con estado funcional vigente (onboarding con consentimientos, verificación formal por equivalencia, copy-on-write de prácticas, analíticas actuales, checks/instalación/estructura).
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK).
- Commit: bb7774f (Fix NameError en encuesta onboarding para facultad/carrera)
- PR: Fix NameError en encuesta onboarding para facultad/carrera

### 2026-03-10 10:33 (UTC) — agente:codex — rama:work
- Pedido: resolver error de arranque por conflicto de migraciones en `accounts` (dos nodos hoja `0007_*`).
- Cambios: creada migración de merge `accounts/migrations/0008_merge_20260310_0732.py` para unificar las ramas `0007_configsitio_umbrales_analiticos` y `0007_encuesta_onboarding` sin operaciones adicionales.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py migrate --plan` (OK, grafo lineal con `accounts.0008_merge_20260310_0732`).
- Commit: c4f9ad1 (Docs: registrar PR en bitácora)
- PR: Fix conflicto de migraciones en accounts al iniciar el contenedor

### 2026-03-10 10:42 (UTC) — agente:codex — rama:work
- Pedido: habilitar ingreso por link de comisión para no logueadxs, con opción de iniciar sesión o registrarse (onboarding), inscribiendo automáticamente al registradx en esa comisión.
- Cambios: se agregó `accounts:acceso_comision` (vista + URL + template) con auto-registro de estudiante y alta automática de `Inscripcion`; se añadió `RegistroEstudianteComisionForm`; se mostró el link público en el detalle de comisión docente; se ajustó copy en login y README para reflejar registro desde link de comisión; se sumaron tests de la nueva vista.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests.AccesoComisionTests` (OK); `SECRET_KEY=test-secret python manage.py check` (OK); screenshot de UI de acceso por comisión generado.
- Commit: 7647404 (Agregar acceso público por comisión con auto-registro estudiantil)
- PR: Agregar acceso por link de comisión con opción de login o registro

### 2026-03-10 11:15 (UTC) — agente:codex — rama:work
- Pedido: usar `facultades_carreras.json` para que el campo carrera se autopopule al elegir facultad en encuesta de onboarding.
- Cambios: se agregó carga cacheada de `facultades_carreras.json` en `accounts/views.py` para construir un mapa facultad→carreras (claves compatibles con choices existentes), se envió ese mapa al template de encuesta, y se implementó JS en `templates/registration/encuesta_onboarding.html` para reconstruir dinámicamente el select de carrera según la facultad elegida preservando valor previo válido; se agregó test de mapeo en `accounts/tests.py`.

### 2026-04-14 05:01 (UTC) — agente:codex — rama:work
- Pedido: explicar por qué una respuesta literal tipo `JvM` no era aceptada como equivalente en sandbox/formulario.
- Cambios: se corrigió la normalización de `v` minúscula para que funcione también en forma infija sin espacios (ej. `JvM`, `)v(`) en backend (`motor/parser.py`) y en frontend (`templates/docentes/ejercicio_form.html`, `templates/ejercicios/ejercicio.html`); se agregaron tests de normalización/parsing asociado en `motor/tests/test_parser.py`.
- Tests/checks: `pytest motor/tests/test_parser.py` (OK, 50 passed); `SECRET_KEY=test-secret python manage.py check` (OK).
- Commit: 0b574ef (Fix normalización de disyunción 'v' sin espacios)
- PR: Fix normalización de disyunción `v` en fórmulas sin espacios

### 2026-04-14 05:08 (UTC) — agente:codex — rama:work
- Pedido: atender impacto histórico del bug (`JvM`) en respuestas ya enviadas y en métricas.
- Cambios: nuevo comando `reconciliar_disyuncion_v` para reconciliar datos históricos: normaliza fórmulas solución de formalización afectadas y recalcula intentos asociados (actualizando `respuesta_raw`/`es_correcto`); se agregaron tests de comando (modo normal y `--dry-run`) en `ejercicios/tests.py`.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test ejercicios.tests.ReconciliarDisyuncionVCommandTests ejercicios.tests.DesbloqueoProgresivoTests --verbosity 1` (OK, 6 tests).
- Commit: 6664e7f (Agregar reconciliación histórica por bug de disyunción v)
- PR: Agregar reconciliación histórica para intentos afectados por `JvM`

### 2026-04-14 05:13 (UTC) — agente:codex — rama:work
- Pedido: aclarar/garantizar que la reconciliación no deje intentos “autoaprobados” por docente.
- Cambios: `reconciliar_disyuncion_v` ahora, si un intento cambia a correcto y estaba `aprobado_docente=False`, lo pasa a `aprobado_docente=None` (pendiente de revisión); se agregó test específico en `ejercicios/tests.py`.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test ejercicios.tests.ReconciliarDisyuncionVCommandTests --verbosity 1` (OK, 3 tests).
- Commit: 8ece114 (Evitar autoaprobación docente en reconciliación histórica)
- PR: Evitar autoaprobación docente en la reconciliación de intentos
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); `SECRET_KEY=test-secret python manage.py check` (OK); intento de screenshot con browser tool (falló por crash de Chromium en el contenedor, SIGSEGV).
- Commit: d290f11 (Autopoblar carreras según facultad desde JSON)
- PR: Autopoblar carreras según facultad desde JSON

### 2026-03-10 11:34 (UTC) — agente:codex — rama:work
- Pedido: corregir el error `NameError: _facultades_carreras_por_clave` en `/accounts/encuesta/` reportado sobre el PR anterior.
- Cambios: se extrajo el mapeo facultad→carreras a un módulo dedicado `accounts/facultades.py` con función pública `get_facultades_carreras_por_clave()` y cache; `accounts/views.py` ahora importa y usa esa función en `encuesta_onboarding`; `accounts/tests.py` se actualizó para testear el helper desde su nuevo módulo.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); `SECRET_KEY=test-secret python manage.py check` (OK).
- Commit: 3ead2e4 (Actualizar hash de commit en MEMORY)
- PR: Fix NameError en encuesta onboarding para facultad/carrera

### 2026-03-10 11:40 (UTC) — agente:codex — rama:work
- Pedido: asegurar que la pregunta de carrera estudiada previamente en UBA (`carrera_uba_anterior`) mantenga todas las carreras, sin depender de la facultad elegida.
- Cambios: en `templates/registration/encuesta_onboarding.html` se agregó aclaración pedagógica en el bloque de `carrera_uba_anterior` y se ajustó el JS de autopoblado para apuntar explícitamente al select principal `form.carrera` por id; en `accounts/tests.py` se añadió `EncuestaFormCarreraAnteriorTests` para verificar que `carrera_uba_anterior` conserva todas las opciones de `CARRERA_CHOICES`.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); `SECRET_KEY=test-secret python manage.py check` (OK).
- Commit: 68d1dde (Mantener carrera previa UBA independiente de facultad)
- PR: Mantener carrera previa UBA independiente de facultad

### 2026-03-10 23:46 (UTC) — agente:codex — rama:work
- Pedido: restaurar la encuesta de onboarding en `accounts` con el texto literal indicado (preguntas, opciones y bifurcaciones clave).
- Cambios: se ajustaron labels y opciones de `EncuestaForm` para alinearlos al cuestionario solicitado (incluyendo internet, laboral, secundaria, estudios previos, CBC, acertijos y polémica), se agregó `email_tipo`, se actualizó obligatoriedad de datos básicos y validación de facultad/carrera para encuesta completa, se corrigió literal en provincia “Buenos Aires (Interior)”, y se reescribieron los templates de consentimientos/primer ingreso y onboarding para mostrar textos y enunciados requeridos.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 1` (OK); screenshot tomado de frontend.
- Commit: c506f26 (Restaurar texto literal de encuesta onboarding en accounts)
- PR: Restaurar texto literal de encuesta onboarding en accounts

### 2026-03-10 23:52 (UTC) — agente:codex — rama:work
- Pedido: verificar si la encuesta de onboarding quedó con la totalidad de preguntas y texto literal solicitado.
- Cambios: auditoría puntual de `accounts/forms.py` y templates de onboarding/consentimientos para contrastar cobertura literal y bifurcaciones contra el requerimiento; sin cambios funcionales de código.
- Tests/checks: `rg -n "No sé|xatakaciencia|LA RESPUESTA A ESTA PREGUNTA ES ESTRICTAMENTE OPCIONAL|Área de Discapacidad|Sección 19" templates/registration/encuesta_onboarding.html accounts/forms.py templates/registration/consentimientos.html templates/registration/cambiar_password.html`; `rg -n "Sección 1|Sección 2|Sección 3|Sección 4|Sección 5|Sección 6|Sección 7|Sección 8|Sección 9|Sección 10|Sección 11|Sección 12|Sección 13|Sección 14|Sección 15|Sección 16|Sección 17|Sección 18|Sección 19" templates/registration/encuesta_onboarding.html`.
- Commit: a32b27b (Registrar auditoría de cobertura literal de encuesta)
- PR: Auditoría de cobertura literal de encuesta de onboarding

### 2026-03-11 00:02 (UTC) — agente:codex — rama:work
- Pedido: corregir crash en `/accounts/encuesta/` (`DataError: value too long for type character varying(10)`) reportado al crear `EncuestaEstudiante`.
- Cambios: se amplió `max_length` y se alinearon choices de `tipo_escuela` en `EncuestaEstudiante` con los valores actuales del formulario; se generó migración `accounts/migrations/0009_alter_encuestaestudiante_provincia_origen_and_more.py`; se agregó test de persistencia de onboarding que postea `tipo_escuela='bachillerato'` y verifica que no rompe y guarda correctamente.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); `SECRET_KEY=test-secret python manage.py check` (OK).
- Commit: 82e978f (Corregir DataError de onboarding por tipo_escuela)
- PR: Corregir DataError de onboarding por tipo_escuela

### 2026-03-11 00:06 (UTC) — agente:codex — rama:work
- Pedido: corregir inconsistencia de hash en la bitácora tras commits de ajuste.
- Cambios: actualización de referencia de commit en MEMORY para mantener trazabilidad exacta.
- Tests/checks: N/A (cambio documental).
- Commit: f663e0d (Actualizar hash de commit en MEMORY)
- PR: Corregir DataError en onboarding por longitud de tipo_escuela

### 2026-03-11 00:16 (UTC) — agente:codex — rama:work
- Pedido: asegurar literalidad integral de encuesta y reflejo de todas las preguntas en modelo/forms/views/template, usando la especificación de encuesta IPC como referencia.
- Cambios: se añadieron campos faltantes de persistencia (`email_tipo`, `tipo_inst_fuera_uba_otras`, `motivo_no_termino_ipc_otras`, `acertijo_cirugia_no_se`) en `EncuestaEstudiante`; se alinearon choices de institución fuera UBA y motivo de no finalización IPC; se actualizó `_crear_encuesta_estudiante` para mapear los nuevos campos; se extendió `EncuestaForm` para capturar opciones “Otras” y “No sé”; se reforzó lógica `clean()` condicional; se ajustó template de onboarding con textos literales adicionales (incluye sección 19, link de Xataka, textos opcionales Q21/Q22, y ramas de campos “Otras”).
- Tests/checks: `SECRET_KEY=test-secret python manage.py makemigrations accounts` (OK); `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); intento de screenshot con browser tool (falló por crash SIGSEGV de Chromium en contenedor).
- Commit: df8763e (Completar literalidad y persistencia de encuesta onboarding)
- PR: Completar literalidad y persistencia de encuesta onboarding

### 2026-03-11 00:17 (UTC) — agente:codex — rama:work
- Pedido: actualizar referencia de hash final en bitácora tras commit documental.
- Cambios: ajuste documental en `MEMORY.md` para reflejar el estado final de commits del ciclo.
- Tests/checks: N/A (cambio documental).
- Commit: e419aef (Actualizar hash de commit en MEMORY)
- PR: Completar literalidad y persistencia de encuesta onboarding

### 2026-03-11 00:36 (UTC) — agente:codex — rama:work
- Pedido: corregir que no se guardaban campos como “situación laboral” y “días que trabaja”.
- Cambios: `_get_tipo_encuesta` ahora prioriza `completa` cuando un estudiante tiene inscripciones mixtas (evita que onboarding quede en modo básico y descarte campos extendidos); se agregó test de regresión que verifica persistencia de `situacion_laboral` y `dias_trabaja` con inscripciones `basica+completa`.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); `SECRET_KEY=test-secret python manage.py check` (OK).
- Commit: 62314ea (Priorizar encuesta completa para guardar campos extendidos)
- PR: Priorizar encuesta completa para guardar campos extendidos

### 2026-03-11 00:37 (UTC) — agente:codex — rama:work
- Pedido: actualizar hash final en bitácora tras commit de ajuste.
- Cambios: corrección documental de referencia de commit en MEMORY.
- Tests/checks: N/A (cambio documental).
- Commit: 0792e33 (Corregir hash de commit en MEMORY)
- PR: Corregir persistencia de campos extendidos en encuesta onboarding

### 2026-03-11 03:45 (UTC) — agente:codex — rama:work
- Pedido: al responder “Sí” en “¿Terminaste el CBC de esa carrera?” desplegar la pregunta “¿Te recibiste de esa carrera?” con opciones Sí/No.
- Cambios: en encuesta onboarding se cambió el literal del campo `se_recibio_uba` a “¿Te recibiste de esa carrera?”; en template se ocultó ese bloque por defecto y se agregó lógica JS para mostrarlo solo cuando `termino_cbc_anterior=true`; en `EncuestaForm.clean()` se limpia `se_recibio_uba` cuando no terminó CBC; se agregaron tests de formulario para validar el comportamiento condicional.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests.EncuestaFormRecibidoUBAConditionalTests accounts.tests.EncuestaOnboardingPersistenciaTests --verbosity 2` (OK). Intento de screenshot con browser tool: fallo por navegación a endpoint no encontrado en el contenedor de browser.
- Commit: e39dc5a (Mostrar pregunta de recibido solo si terminó CBC)
- PR: Mostrar pregunta de recibido solo si terminó CBC
### 2026-03-11 03:41 (UTC) — agente:codex — rama:work
- Pedido: hacer que el dropdown de “¿Qué carrera cursaste en la UBA?” se alimente con carreras unificadas desde `facultades_carreras.json` (sin separar por facultad).
- Cambios: se agregó helper cacheado `get_carreras_unificadas_por_clave()` en `accounts/facultades.py`; `EncuestaForm` ahora arma las opciones de `carrera_uba_anterior` con esa lista unificada en orden del JSON; se actualizó test para validar el origen de esas opciones.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); `SECRET_KEY=test-secret python manage.py check` (OK); intento de screenshot con browser tool (falló por crash SIGSEGV de Chromium en el contenedor).
- Commit: 2987d19 (Onboarding: unificar carreras UBA desde JSON)
### 2026-03-11 03:36 (UTC) — agente:codex — rama:work
- Pedido: quitar el desplegable “Correo electrónico” de la encuesta de onboarding si no tiene utilidad práctica.
- Cambios: se eliminó el campo `email_tipo` del `EncuestaForm`, su renderizado en la plantilla de onboarding y su persistencia en `_crear_encuesta_estudiante`; se agregó test de vista para verificar que el desplegable ya no se muestre.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK).
- Commit: 12510d8 (Quitar desplegable de correo en onboarding)
- PR: Quitar desplegable de correo en onboarding
### 2026-03-11 03:42 (UTC) — agente:codex — rama:work
- Pedido: aclarar para qué sirve `email_tipo` y resolver observaciones posteriores al PR previo.
- Cambios: se eliminó definitivamente `email_tipo` del modelo `EncuestaEstudiante` y se generó migración `0011_remove_encuestaestudiante_email_tipo`, para dejar consistente backend/DB con la UI donde ese desplegable ya no existe.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK).
- Commit: 520e0d5 (Eliminar email_tipo residual de encuesta onboarding)
- PR: Eliminar email_tipo residual de encuesta onboarding
### 2026-03-11 03:43 (UTC) — agente:codex — rama:work
- Pedido: sincronizar bitácora tras corrección de hash y registro de PR.
- Cambios: se corrigió referencia de hash en la bitácora y se dejó asentado el PR "Eliminar email_tipo residual de encuesta onboarding".
- Tests/checks: N/A (ajuste documental).
- Commit: f9410ee (Registrar ajuste final de bitácora en MEMORY)
- PR: Eliminar email_tipo residual de encuesta onboarding
### 2026-03-11 03:44 (UTC) — agente:codex — rama:work
- Pedido: dejar bitácora consistente tras último ajuste documental.
- Cambios: se actualizaron hash/estado de PR en entradas previas para reflejar el estado real.
- Tests/checks: N/A (ajuste documental).
- Commit: 51a8469 (Agregar entrada final de trazabilidad en MEMORY)
- PR: Eliminar email_tipo residual de encuesta onboarding
- Pedido: ocultar/eliminar los radio buttons de la elección vacía en la encuesta de onboarding.
- Cambios: se eliminaron opciones vacías (`('', '')`) de los `ChoiceField` con `RadioSelect` en `EncuestaForm`; se agregó test que verifica que ningún campo con `RadioSelect` incluya opción vacía.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test accounts.tests --verbosity 2` (OK); intento de screenshot con Playwright falló por crash del navegador en este entorno (SIGSEGV).
- Commit: cdd1e98 (Agregar auditoría QA exhaustiva del módulo accounts)
- PR: Agregar auditoría QA exhaustiva del módulo accounts

### 2026-03-11 04:10 (ART) — agente:codex — rama:master
- Pedido: analizar las métricas de la Memoria Profesional y los scripts externos para implementarlas en el módulo de investigación de `analiticas`, excluyendo dependencias de notas de examen y cruzándolas con desempeño en ejercicios.
- Cambios: `analiticas/research.py` ahora calcula índices de onboarding (puntaje NSE, categoría NSE, puntaje de acertijos lógicos, clasificación pandemia, cohortes, facultades/carreras) y cruces agregados con desempeño en ejercicios (intentos, ejercicios resueltos, prácticas completadas); `analiticas/views.py` expone esos datasets y agrega exportación CSV/XLSX/ODS; `templates/analiticas/investigacion.html` muestra los nuevos paneles y aclara que no se usan notas de examen; `analiticas/tests.py` suma cobertura puntual de estas métricas.
- Tests/checks: `wsl.exe bash -lc "cd /mnt/c/Users/Angeles/Documents/IPC-Logica/IPC-Logica && python3 -m py_compile analiticas/research.py analiticas/views.py analiticas/tests.py"` (OK). `wsl.exe bash -lc "cd /mnt/c/Users/Angeles/Documents/IPC-Logica/IPC-Logica && SECRET_KEY=test-secret python3 manage.py test analiticas.tests.EncuestaOnboardingResearchTests --verbosity 2"` (pendiente: el Python disponible en este entorno no tiene Django instalado). `wsl.exe bash -lc "cd /mnt/c/Users/Angeles/Documents/IPC-Logica/IPC-Logica && SECRET_KEY=test-secret python3 manage.py check"` (pendiente por la misma falta de Django).
- Commit: 7a3ce22 (QA: auditar flujos docentes y documentar hallazgos)
- Commit: cdd1e98 (Agregar auditoría QA exhaustiva del módulo accounts)
- PR: Ajustar correlaciones de onboarding para incluir ausentismo

### 2026-03-11 01:47 (ART) — agente:codex — rama:master
- Pedido: corregir que la encuesta de onboarding no guardaba consistentemente Situación laboral y Días que trabaja.
- Cambios: se alinearon los choices de EncuestaEstudiante.situacion_laboral y EncuestaEstudiante.dias_trabaja con los valores reales del formulario de onboarding; se agregó migración `accounts/migrations/0012_alter_encuestaestudiante_situacion_laboral_and_more.py`; se sumó test de regresión para verificar que ambos valores quedan persistidos y siguen siendo válidos para el modelo.
- Tests/checks: pendiente; en este entorno no hay intérprete python/py disponible en PATH para correr manage.py.
- Commit: b0c94da (Ajustar correlaciones de onboarding para incluir ausentismo)
- PR: N/A
### 2026-03-11 02:05 (ART) — agente:codex — rama:beb3
- Pedido: corregir que en onboarding tampoco se guardaba consistentemente “Tiempo desde secundaria”.
- Cambios: se alinearon los choices de EncuestaEstudiante.tiempo_desde_secundaria con los valores reales del formulario (menos_1, 1_3, mas_3); se agregó migración `accounts/migrations/0013_alter_encuestaestudiante_tiempo_desde_secundaria.py`; se sumó test de regresión para verificar que el valor queda persistido y sigue siendo válido para el modelo.
- Tests/checks: pendiente; en este entorno no hay intérprete python/py disponible en PATH para correr manage.py.
- Commit: pendiente
- PR: N/A
### 2026-03-11 02:16 (ART) — agente:codex — rama:beb3
- Pedido: corregir que la opción mostrada para certijo_silogismo quedaba desfasada respecto del enunciado de onboarding.
- Cambios: se alinearon los choices de EncuestaEstudiante.acertijo_silogismo con las opciones reales del formulario (Más alto / Más bajo); se agregó migración ccounts/migrations/0014_alter_encuestaestudiante_acertijo_silogismo.py; se sumó test de regresión para verificar persistencia y label correcto del valor guardado.
- Tests/checks: pendiente; en este entorno no hay intérprete python/py disponible en PATH para correr manage.py.
- Commit: pendiente
- PR: N/A
### 2026-03-11 02:32 (ART) — agente:codex — rama:beb3
- Pedido: unificar certijo_cirugia_no_se y certijo_cirugia para que la respuesta de cirugía se persista en un solo campo.
- Cambios: EncuestaForm.clean() ahora colapsa la opción “No sé” dentro de certijo_cirugia; _crear_encuesta_estudiante dejó de persistir el booleano separado; EncuestaEstudiante eliminó certijo_cirugia_no_se y renombró el label del campo restante; se agregó migración de datos ccounts/migrations/0015_colapsar_acertijo_cirugia_en_un_campo.py para convertir respuestas previas con “No sé” y luego borrar el campo antiguo; se ajustaron tests de persistencia para reflejar el almacenamiento en un único campo.
- Tests/checks: pendiente; en este entorno no hay intérprete python/py disponible en PATH para correr manage.py.
- Commit: pendiente
- PR: N/A
### 2026-03-11 02:50 (ART) — agente:codex — rama:beb3
- Pedido: unificar también 	ipo_inst_fuera_uba/	ipo_inst_fuera_uba_otras y motivo_no_termino_ipc/motivo_no_termino_ipc_otras para persistir una sola respuesta por pregunta.
- Cambios: EncuestaForm.clean() ahora colapsa ambas ramas en texto único legible dentro del campo principal; _crear_encuesta_estudiante dejó de persistir los campos auxiliares *_otras; EncuestaEstudiante eliminó 	ipo_inst_fuera_uba_otras y motivo_no_termino_ipc_otras, y amplió 	ipo_inst_fuera_uba/motivo_no_termino_ipc a texto libre; se agregó migración de datos ccounts/migrations/0016_colapsar_respuestas_otras_en_un_solo_campo.py para convertir claves viejas y respuestas “Otras” al formato unificado; se sumaron tests de persistencia para institución fuera UBA y motivo de no finalización de IPC.
- Tests/checks: pendiente; en este entorno no hay intérprete python/py disponible en PATH para correr manage.py.
- Commit: pendiente
- PR: N/A
### 2026-03-11 03:30 (ART) — agente:codex — rama:beb3
- PR: pendiente
### 2026-03-29 08:59 (UTC) — agente:codex — rama:work
- Pedido: auditoría QA profunda de todos los flujos del módulo ejercicios, sin tocar código funcional; generar informe markdown para implementación posterior por Claude Sonnet 4.6.
- Cambios: se creó informe exhaustivo `docs/auditorias/2026-03-29_auditoria_QA_modulo_ejercicios.md` con alcance, metodología, matriz de flujos, hallazgos priorizados (H-01 a H-04), plan de implementación y criterios de aceptación QA.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test ejercicios docentes --verbosity 2` (FAIL: 5 failures, 2 errors; evidencia documentada en informe).
- Commit: 81a77b5 (QA: auditar flujos del modulo ejercicios y documentar hallazgos)
- PR: QA: Auditoría integral del módulo ejercicios (reporte para implementación)
- PR: pendiente### 2026-03-29 08:57 (UTC) — agente:codex — rama:work
- Pedido: auditar en profundidad todos los flujos del módulo motor sin tocar código funcional, documentar hallazgos y dejar informe listo para PR.
- Cambios: se realizó auditoría QA técnica de `motor` + integración API (`ejercicios/api`) y se creó `docs/auditoria_qa_motor_2026-03-29.md` con hallazgos priorizados, evidencia reproducible y plan de implementación sugerido para Claude Sonnet 4.6.
- Tests/checks: `pytest motor/tests -q` (5 fallos en `motor/tests/test_tabla.py` por desalineación de expectativas de orden); `SECRET_KEY=test-secret python manage.py test ejercicios.tests.PreviewArgumentoApiTests -v 2` (OK, 2 tests); `python tests/playwright/tests_audit_motor.py --verbose` (fallos por servidor no levantado + problemas de import/path); `PYTHONPATH=. python tests/playwright/tests_audit_motor.py --verbose` (parcial: 11/14).
- Commit: 767fa23 (QA: auditar flujos del motor y documentar hallazgos)
- PR: QA: auditar en profundidad flujos del módulo motor
alue too long for type character varying(20)).
- Cambios: se reordenó ccounts/migrations/0016_colapsar_respuestas_otras_en_un_solo_campo.py para ampliar primero 	ipo_inst_fuera_uba y motivo_no_termino_ipc, luego migrar los datos unificados y recién después eliminar los campos auxiliares *_otras.
- Tests/checks: sin ejecución local; el error quedó diagnosticado a partir del log de migración en Railway y corregido en el orden de operaciones.
- Commit: pendiente
- PR: N/A
### 2026-03-11 08:41 (ART) - agente:codex - rama:codex/implementar-mtricas-de-memoria
- Pedido: corregir crash en /analiticas/investigacion/ por AttributeError al procesar encuestas sin acertijo_cirugia_no_se.
- Cambios: analiticas/research.py ahora usa getattr(..., None) para acertijo_cirugia_no_se, endurece el puntaje logico para encuestas legacy y hace tolerante la lectura de fecha_nacimiento, facultad y carrera en el dataset de investigacion.
- Tests/checks: wsl.exe bash -lc "cd /mnt/c/Users/Angeles/.codex/worktrees/3121/IPC-Logica && python3 -m py_compile analiticas/research.py" OK.
- Commit: 7a3ce22 (QA: auditar flujos docentes y documentar hallazgos)
- Commit: cdd1e98 (Agregar auditoría QA exhaustiva del módulo accounts)
- PR: pendiente
### 2026-03-11 09:08 (ART) - agente:codex - rama:codex/implementar-mtricas-de-memoria
- Pedido: endurecer todo el bloque de investigacion para encuestas legacy con campos opcionales faltantes y verificar que el dashboard/export solo considere consentimiento de investigacion.
- Cambios: analiticas/research.py agrega helpers de lectura segura para encuesta, vuelve tolerante puntaje_nse_encuesta(), puntaje_logicas_encuesta(), clasificacion_pandemia_encuesta() y labels de facultad/carrera; ademas alinea el filtro por consentimiento en _metricas_desempeno_por_estudiante() tambien para Progreso. analiticas/tests.py agrega cobertura para encuestas legacy y para el filtrado de consentimiento en desempeno.
- Tests/checks: wsl.exe bash -lc "cd /mnt/c/Users/Angeles/.codex/worktrees/3121/IPC-Logica && python3 -m py_compile analiticas/research.py analiticas/tests.py" OK. wsl.exe bash -lc "cd /mnt/c/Users/Angeles/.codex/worktrees/3121/IPC-Logica && SECRET_KEY=test-secret python3 manage.py test analiticas.tests.EncuestaOnboardingResearchTests --verbosity 2" pendiente en este entorno (ModuleNotFoundError: django).
- Commit: 7a3ce22 (QA: auditar flujos docentes y documentar hallazgos)
- PR: pendiente
### 2026-03-29 01:10 (UTC) — agente:codex — rama:work
- Pedido: auditoría QA profunda de todos los flujos del módulo docentes, sin tocar código funcional; generar informe .md para implementación posterior.
- Cambios: se auditó `docentes/urls.py`, `docentes/views.py`, `docentes/tests.py` y se creó `docs/qa_docentes_auditoria_2026-03-29.md` con diagnóstico por flujo, hallazgos priorizados y plan de remediación para Claude Sonnet 4.6.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test docentes.tests -v 2` (27 tests, 2 errores en fixtures legacy); `SECRET_KEY=test-secret python manage.py test -v 1` (93 tests, 34 errores y 5 fallos por desalineaciones legacy de tests/modelos y middleware).
- Commit: b1f37c1 (QA: auditar flujos docentes y documentar hallazgos)
- PR: pendiente
- Commit: cdd1e98 (Agregar auditoría QA exhaustiva del módulo accounts)
- PR: pendiente
### 2026-03-29 09:04 (UTC) — agente:codex — rama:work
- Pedido: auditoría QA profunda de todos los flujos del módulo `accounts`, sin tocar código funcional, y dejar informe exhaustivo en `.md` listo para PR.
- Cambios: se realizó auditoría estática y de flujos del módulo `accounts`; se creó `QA_AUDIT_ACCOUNTS_2026-03-29.md` con hallazgos, severidad, priorización y casos de prueba sugeridos para implementación posterior.
- Tests/checks: `python manage.py test accounts -v 2` (OK, 18 tests); `python manage.py migrate` (OK, migraciones aplicadas en entorno local).
- Commit: b267844 / d56ab99 (Agregar auditoría QA exhaustiva del módulo accounts; Actualizar bitácora con estado de PR de auditoría accounts)
- PR: Agregar auditoría QA exhaustiva del módulo accounts

### 2026-03-29 09:40 (UTC) — agente:codex — rama:work
- Pedido: auditar en profundidad todos los flujos del módulo `analiticas` sin tocar código funcional; generar informe exhaustivo en markdown para implementación posterior por Claude Sonnet 4.6.
- Cambios: se auditó el módulo `analiticas` (views, research, urls, templates y tests), se ejecutaron checks/suite y se creó `docs/auditorias/2026-03-29_auditoria_QA_modulo_analiticas.md` con hallazgos priorizados (H-01..H-09), plan de implementación por fases y criterios de aceptación QA.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test analiticas -v 2` (FAIL, 32 errores por fixtures legacy desalineados con modelos actuales; evidencia en informe).
- Commit: 8ecd021 (QA: auditar flujos del modulo analiticas y documentar hallazgos)
- PR: QA: auditar flujos del módulo analíticas y documentar hallazgos

### 2026-03-29 09:48 (UTC) — agente:codex — rama:work
- Pedido: dejar la bitácora consistente con el hash final del commit de auditoría de analíticas.
- Cambios: ajuste documental de la entrada 2026-03-29 09:40 para reflejar el hash correcto del commit de auditoría.
- Tests/checks: N/A (ajuste documental).
- Commit: pendiente
- PR: QA: auditar flujos del módulo analíticas y documentar hallazgos
### 2026-03-29 09:19 (UTC) — agente:codex — rama:work
- Pedido: auditoría QA profunda de todos los flujos del módulo cursos, sin tocar código de producto, y dejar informe listo para PR.
- Cambios: se realizó auditoría estática + dinámica de flujos cursos/comisiones/inscripciones y se creó informe exhaustivo en `docs/auditorias/2026-03-29-auditoria-modulo-cursos.md` con hallazgos, severidad, evidencia y priorización.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test accounts.tests.AccesoComisionTests accounts.tests.TipoEncuestaResolucionTests docentes.tests.ComisionesListViewTests` (OK, 8 tests); `SECRET_KEY=test-secret python manage.py test cursos accounts docentes ejercicios` (FAIL: 5 failures + 2 errors preexistentes); `SECRET_KEY=test-secret python manage.py test docentes.tests.IntentoAprobacionUpdateTests ejercicios.tests.IntentoCreateViewTests ejercicios.tests.DesbloqueoProgresivoTests ejercicios.tests.MiHistorialViewTests` (FAIL reproducible: mismos 5 failures + 2 errors).
- Commit: 502ce2a (QA: auditar flujos del modulo cursos y documentar hallazgos)
- PR: QA: auditoría exhaustiva del módulo cursos y reporte de hallazgos

### 2026-03-29 10:01 (UTC) — agente:codex — rama:work
- Pedido: auditoría QA profunda de flujos inter-módulo (sin tocar código funcional), con informe markdown listo para implementación posterior por Claude Sonnet 4.6.
- Cambios: se ejecutó auditoría integral de rutas, middleware, vistas API/HTML, flujo de onboarding, resolución de intentos, corrección docente y analíticas; se creó `QA_AUDITORIA_FLUJOS_2026-03-29.md` con hallazgos priorizados (crítico/alto/medio), evidencias, riesgos y plan sugerido por sprint.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test --verbosity 1` (FAIL: 93 tests, 34 errores + 5 fallos; desalineaciones de fixtures/modelos y redirects 302 por middleware en tests).
- Commit: pendiente
- PR: Auditoría QA de performance/concurrencia para 200 usuarixs simultáneos

### 2026-03-29 10:03 (UTC) — agente:codex — rama:work
- Pedido: actualizar bitácora con estado final de commit/PR para la auditoría QA.
- Cambios: actualización administrativa de `MEMORY.md` para reflejar hash real del informe QA y dejar PR en estado pendiente.
- Tests/checks: sin checks adicionales (sin cambios funcionales).
- Commit: 3dafc0f (QA: auditar flujos intermodulo y documentar hallazgos)
- PR: Informe QA exhaustivo de flujos inter-módulo

### 2026-03-29 03:25 (UTC) — agente:codex — rama:work
- Pedido: auditoría QA profunda de performance/concurrencia para escenario de 200 usuarixs simultáneos, sin tocar código funcional.
- Cambios: se realizó auditoría estática/técnica y se creó informe exhaustivo en `docs/auditorias/2026-03-29_auditoria_QA_performance_concurrencia_200.md` con hallazgos priorizados, riesgos de carrera/DB y plan de implementación para Claude Sonnet 4.6.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test ejercicios.tests.DesbloqueoProgresivoTests docentes.tests.IntentoAprobacionUpdateTests --verbosity 1` (FAIL/ERROR preexistentes documentados en el informe).
- Commit: pendiente
- PR: Auditoría QA de performance/concurrencia para 200 usuarixs simultáneos
### 2026-03-29 11:00 (UTC) — agente:codex — rama:work
- Pedido: actuar en rol QA sin tocar código funcional; leer todos los informes en `docs/auditorias/` y diseñar un plan de implementación para Claude Sonnet 4.6, dejándolo registrado en un archivo markdown.
- Cambios: lectura y consolidación de los 8 informes de auditoría existentes; creación de `docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md` con plan unificado por fases (baseline, P0 funcional, motor, analíticas, estabilización de tests, onboarding y performance), protocolo de verificación + auditoría propia y DoD de cierre.
- Tests/checks: `rg --files docs/auditorias`; `sed -n '1,220p' docs/auditorias/*.md` (lectura QA); `rg -n "^## |^# |^\\*\\*|^### " docs/auditorias/*.md`.
- Commit: pendiente
- PR: QA: plan unificado de implementación para Claude Sonnet 4.6
### 2026-03-29 11:05 (UTC) — agente:codex — rama:work
- Pedido: atender feedback del PR previo: exigir que la auditoría propia de Claude sea profunda, no breve.
- Cambios: actualización del plan en `docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; en el protocolo se reemplaza “auditoría propia breve” por “auditoría propia profunda (obligatoria)” y se agregan requisitos mínimos de profundidad + entregables obligatorios por fase (matriz de evidencia, riesgos residuales, pruebas negativas, trazabilidad de comandos y decisión pedagógica explícita).
- Tests/checks: `sed -n '150,270p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `rg -n "Auditoría propia profunda|Requisitos mínimos de profundidad|Entregables obligatorios por fase" docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`.
- Commit: pendiente
- PR: QA: plan unificado de implementación para Claude Sonnet 4.6
### 2026-03-29 11:17 (UTC) — agente:codex — rama:work
- Pedido: reformular el plan para incorporar una nueva auditoría agregada y ajustar el orden/alcance donde corresponda.
- Cambios: actualización de `docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md` para contemplar explícitamente la nueva auditoría docente; se cambió la sección de fuentes a lectura dinámica de todas las auditorías del directorio, se agregó el hallazgo consolidado B2 (hardening docente/comisiones), se incorporó una Fase 4 específica para endurecimiento docente/comisiones, y se renumeraron fases/orden de ejecución en consecuencia.
- Tests/checks: `rg --files docs/auditorias`; `rg -n "Fuentes auditadas|Regla de actualización|B2|Fase 4|Fase 5|Fase 6|Fase 7|Orden concreto" docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `sed -n '1,170p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `sed -n '170,250p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`.
- Commit: pendiente
- PR: QA: fortalecer plan para exigir auditoría profunda de Claude
### 2026-03-29 11:23 (UTC) — agente:codex — rama:work
- Pedido: corregir omisión del informe `2026-03-29_auditoria_ISO_IEC_9126_sistema.md` y reformular el plan para contemplarlo explícitamente.
- Cambios: actualización de `docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md` para incluir la auditoría ISO/IEC 9126 en fuentes obligatorias; agregado del Bloque D (calidad de producto), extensión de Fase 0 con matriz ISO/IEC 9126, nueva Fase 8 de verificación integral por atributos de calidad y actualización de checklist/DoD para exigir evidencia por los 6 atributos.
- Tests/checks: `rg --files docs/auditorias | sort`; `rg -n "ISO|9126|son estas|Fase 8|matriz ISO|DoD|Orden concreto" docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `sed -n '1,120p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `nl -ba docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md | sed -n '96,190p'`.
- Commit: pendiente
- PR: QA: reformular plan incorporando nueva auditoría
### 2026-03-29 11:47 (UTC) — agente:codex — rama:work
- Pedido: incorporar feedback crítico sobre el orden de ejecución QA (Gemini): mover estabilización de tests al inicio bloqueante antes de cambios de lógica/concurrencia/optimización.
- Cambios: reformulación integral de la sección de fases en `docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; nuevo orden seguro: Fase 0 tests bloqueante, Fase 1 seguridad/lógica de ejercicios, Fase 2 concurrencia base (locking + cache compartido), Fase 3 optimización pesada SQL-first, luego hardening docente, onboarding, performance bajo carga e ISO/IEC 9126 de cierre; actualización del checklist de ejecución y limpieza de duplicado en DoD.
- Tests/checks: `rg -n "## 3\)|Fase 0 \(Bloqueante|Fase 1 \(Seguridad|Fase 2 \(Concurrencia|Fase 3 \(Optimización|## 5\)|DoD" docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `sed -n '78,250p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `sed -n '250,310p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`.
- Commit: pendiente
- PR: QA: incorporar auditoría ISO/IEC 9126 al plan unificado
### 2026-03-29 11:54 (UTC) — agente:codex — rama:work
- Pedido: corregir plan previo por orden riesgoso y puntos ciegos críticos; incorporar requerimiento fundacional de doble consumidor (docente por comisión vs investigación global con legacy null).
- Cambios: reemplazo integral de `docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md` con nuevo plan unificado en orden estricto Fase 0..3 solicitado; creación de `docs/auditorias/2026-03-29_addendum_QA_correcciones_criticas.md` con correcciones de análisis (data loss legacy, error lógico dashboard, N+1 oculto, rotura frontend por middleware API).
- Tests/checks: `sed -n '1,220p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `sed -n '1,220p' docs/auditorias/2026-03-29_addendum_QA_correcciones_criticas.md`; `rg -n "FASE 0|FASE 1|FASE 2|FASE 3|practica_comision=None|/api/" docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md docs/auditorias/2026-03-29_addendum_QA_correcciones_criticas.md`.
- Commit: pendiente
- PR: QA: reordenar plan con tests como bloqueante absoluto
### 2026-03-29 12:00 (UTC) — agente:codex — rama:work
- Pedido: ampliar el plan porque quedó demasiado corto y no recogía todos los principios de operación definidos previamente.
- Cambios: reescritura ampliada de `docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md` incorporando: fuentes obligatorias completas, principios operativos no negociables, correcciones de puntos ciegos, modelo de doble consumidor, orden estricto FASE 0..3, protocolo de auditoría profunda por fase, DoD y matriz de ejecución resumida.
- Tests/checks: `sed -n '1,260p' docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`; `rg -n "Principios de operación|doble consumidor|FASE 0|FASE 1|FASE 2|FASE 3|Protocolo de auditoría profunda|DoD" docs/auditorias/2026-03-29_plan_implementacion_para_claude_sonnet_4_6.md`.
- Commit: pendiente
- PR: QA: reemplazar plan unificado con orden estricto y doble consumidor

### 2026-03-29 11:11 (UTC) — agente:codex — rama:work
- Pedido: realizar una auditoría completa del sistema de acuerdo a ISO/IEC 9126.
- Cambios: se creó `docs/auditorias/2026-03-29_auditoria_ISO_IEC_9126_sistema.md` con evaluación integral por características ISO/IEC 9126 (funcionalidad, fiabilidad, usabilidad, eficiencia, mantenibilidad, portabilidad), matriz de estado y plan de remediación priorizado.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test --verbosity 1` (FAIL: 93 tests, 34 errores y 5 fallos; desalineaciones legacy documentadas en auditoría).
- Commit: 4e2dd49 (QA: auditoria integral del sistema segun ISO/IEC 9126)
- PR: Auditoría integral del sistema según ISO/IEC 9126 (pendiente)

### 2026-04-17 05:58 (UTC) — agente:codex — rama:work
- Pedido: actualizar `AGENTS.md` en base al estado y capacidades actuales del sistema.
- Cambios: se agregó en `AGENTS.md` una sección de estado funcional de referencia (2026-04) con capacidades vigentes (arquitectura híbrida, motor semántico, onboarding/consentimientos, copy-on-write, analíticas pedagógicas y acceso mixto por link de comisión); además se actualizó la tabla de decisiones para reflejar el alta de cuentas mixta y el uso de SQLite solo en desarrollo local (PostgreSQL en producción).
- Tests/checks: `python manage.py check`.
- Commit: pendiente
- PR: Docs: actualizar AGENTS según estado funcional vigente

### 2026-04-29 12:27 (UTC) — agente:codex — rama:work
- Pedido: corregir crash del servidor MCP de intentos en modo `streamable-http` por `TypeError` al pasar `host`/`port` a `FastMCP.run()`.
- Cambios: `mcp_intentos.py` ahora configura `mcp.settings.host` y `mcp.settings.port` antes de ejecutar `mcp.run(transport="streamable-http")`, alineado con la firma actual de FastMCP.
- Tests/checks: `python -m py_compile mcp_intentos.py`; `python - <<'PY' ... inspect.signature(FastMCP.run) ... PY`.
- Commit: ece1cc6 (Fix FastMCP streamable-http startup host/port config)
- PR: Fix FastMCP streamable-http startup host/port config

### 2026-04-29 12:32 (UTC) — agente:codex — rama:work
- Pedido: corregir error `Invalid Host header: mcp-intentos-production.up.railway.app` en despliegue HTTP de MCP.
- Cambios: `mcp_intentos.py` ahora agrega `RAILWAY_PUBLIC_DOMAIN` a `mcp.settings.transport_security.allowed_hosts` y a `allowed_origins` (http/https) cuando `MCP_TRANSPORT=http`.
- Tests/checks: `python -m py_compile mcp_intentos.py`; `python - <<'PY' ... FastMCP('x').settings.transport_security ... PY`.
- Commit: e74539d (Fix Railway host header allowlist for MCP HTTP transport)
- PR: Fix Railway host header allowlist for MCP HTTP transport

### 2026-04-29 12:37 (UTC) — agente:codex — rama:work
- Pedido: corregir respuesta `421 Misdirected Request` en endpoint MCP sobre Railway (`POST /mcp`).
- Cambios: en `mcp_intentos.py` se amplió allowlist de orígenes con variantes `: *` y, si existe `RAILWAY_ENVIRONMENT`, se desactiva `enable_dns_rebinding_protection` de FastMCP para evitar falsos positivos por proxy/rewrite de host/origin en Railway.
- Tests/checks: `python -m py_compile mcp_intentos.py`.
- Commit: e298a32 (Fix db_tool NameError by removing duplicate compat wrappers)
- PR: Fix db_tool NameError by removing duplicate compat wrappers

### 2026-04-29 13:00 (UTC) — agente:codex — rama:work
- Pedido: corregir error al usar herramientas MCP: `You cannot call this from an async context - use a thread or sync_to_async`.
- Cambios: en `mcp_intentos.py` se incorporó el decorador `db_tool()` que registra tools MCP ejecutando cada función síncrona en un thread vía `sync_to_async(..., thread_sensitive=True)`, y se migraron todas las herramientas de `@mcp.tool()` a `@db_tool()` para evitar acceso ORM directo en contexto async.
- Tests/checks: `python -m py_compile mcp_intentos.py` (OK).
- Commit: 15d9b8c (Fix async context error in MCP tools with sync_to_async wrapper)
- PR: Fix async context error in MCP tools by wrapping ORM access in threads
### 2026-04-29 13:11 (UTC) — agente:codex — rama:work
- Pedido: agregar wrappers MCP de compatibilidad para clientes que envían `{ "args": {}, "kwargs": {...} }` sin romper firmas actuales usadas por Claude Desktop/MCP estándar.
- Cambios: en `mcp_intentos.py` se agregó `_compat_kwargs(args, kwargs)` y 12 herramientas nuevas `*_compat` (una por tool existente) que aceptan explícitamente `args: dict | None` y `kwargs: dict | None`, normalizan payload y delegan en la tool original sin modificar sus firmas.
- Tests/checks: `python -m py_compile mcp_intentos.py`.
- Commit: 7d0b17f (Add MCP compat tool wrappers for args/kwargs payloads)
- PR: Add MCP compat tool wrappers for args/kwargs payloads
### 2026-04-29 13:17 (UTC) — agente:codex — rama:work
- Pedido: corregir regresión en `mcp_intentos.py` (`NameError: db_tool`) reportada tras PR de wrappers `_compat`.
- Cambios: se eliminó el bloque duplicado de wrappers `_compat` que había quedado antes de definir `db_tool()`, dejando una única definición de wrappers en la sección final del archivo para mantener orden de carga y compatibilidad.
- Tests/checks: `rg -n "def db_tool|Wrappers de compatibilidad|_compat" mcp_intentos.py`; `python -m py_compile mcp_intentos.py`.
- Commit: c9c79c8 (Fix db_tool NameError by removing duplicate compat wrappers)
- PR: Fix db_tool NameError by removing duplicate compat wrappers
### 2026-04-29 13:25 (UTC) — agente:codex — rama:work
- Pedido: corregir que los endpoints `*_compat` devolvían coroutines sin resolver al delegar en tools ya decoradas con `@db_tool()`.
- Cambios: los wrappers `*_compat` pasaron de `@db_tool()` + funciones sync a `@mcp.tool()` + funciones `async` que hacen `await` explícito sobre la tool delegada, evitando respuestas con coroutine object y warnings de runtime.
- Tests/checks: `python -m py_compile mcp_intentos.py`; `python - <<'PY' ... inspect.iscoroutinefunction(...) ... PY`.
- Commit: fc77c16 (Fix compat MCP wrappers to await delegated tool calls)
- PR: Fix compat MCP wrappers to await delegated tool calls
### 2026-04-29 13:34 (UTC) — agente:codex — rama:work
- Pedido: corregir publicación de firmas MCP (evitar esquema `args/kwargs` en tools originales) y garantizar registro utilizable de tools `_compat` sin romper compatibilidad con Claude Desktop.
- Cambios: `db_tool()` ahora usa `@wraps`; además se aplicó refactor incremental robusto con funciones sync `_impl` + tools async explícitas para `listar_comisiones`, `listar_intentos`, `obtener_intento` y `obtener_ejercicio`; sus wrappers `_compat` ahora llaman directamente a esos `_impl` vía `sync_to_async(..., thread_sensitive=True)` con firma explícita `args/kwargs`.
- Tests/checks: `python -m py_compile mcp_intentos.py`; `python - <<'PY' ... inspect.signature(...) ... PY`.
- Commit: b3ccb7c (Fix MCP tool signatures and compat registration for key endpoints)
- PR: Fix MCP tool signatures and compat registration for key endpoints

### 2026-04-30 04:49 (UTC) — agente:codex — rama:work
- Pedido: permitir exportar desde la página de comisión un Excel con la lista de estudiantes (DNI, Apellido, Nombre y Correo electrónico).
- Cambios: se agregó endpoint docente `estudiantes_exportar` con validación de permisos por comisión y generación XLSX; se añadió botón de exportación en la sección “Estudiantes” de `comision_detail`; se incorporó test de integración para validar encabezados/filas exportadas y se actualizó README con la nueva capacidad.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test docentes.tests.GestionEstudiantesTests --verbosity 1` (OK).
- Commit: c528b78 (Agregar exportación XLSX de estudiantes por comisión)
- PR: pendiente

### 2026-04-30 04:51 (UTC) — agente:codex — rama:work
- Pedido: actualizar bitácora para reflejar hash final posterior al ajuste documental.
- Cambios: ajuste menor en `MEMORY.md` para mantener trazabilidad de commit real en la rama.
- Tests/checks: N/A (cambio documental).
- Commit: 46232f0 (Actualizar bitácora con hash final de exportación XLSX)
- PR: Agregar exportación Excel de estudiantes por comisión

### 2026-04-30 00:00 (UTC) — agente:codex — rama:work
- Pedido: ante error en un intento, agregar una pista/indicación automática con Gemini evitando efecto Topaze.
- Cambios: se agregó generación opcional de pista pedagógica (`ejercicios/gemini_hints.py`) con fallback silencioso si no hay `GEMINI_API_KEY` o falla la API; `IntentoCreateView` ahora incluye campo `pista` en la respuesta y solo intenta generarla cuando `correcto=False`; se agregaron tests de API para cubrir casos incorrecto/correcto con mock; se actualizó README con la variable opcional y el comportamiento.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test ejercicios.tests.IntentoCreatePistaGeminiTests --verbosity 1` (OK).
- Commit: e99c94c (Agregar pista pedagógica opcional con Gemini en intentos incorrectos)
- PR: Agregar pista pedagógica opcional con Gemini en intentos incorrectos

### 2026-04-30 12:32 (ART) — agente:codex — rama:master
- Pedido: analizar con el MCP de IPC-Logica intentos de ejercicios 8, 9, 11, 12 y 33 marcados incorrectos pese a fórmulas idénticas o de igual forma lógica.
- Cambios: sin cambios funcionales; análisis con MCP y lectura de `motor/verificador.py`, `ejercicios/api/views.py` y `templates/ejercicios/ejercicio.html`. Diagnóstico: en ejercicios 8/9 los intentos literal-identicos fallan por celdas incorrectas en `tabla_json`, no por el matcher de fórmulas; el caso 1625/1626 no es no determinístico porque la tabla guardada difiere. Hallazgo separado real: en tabla de verdad, `verificar_argumento()` acepta renombramiento de variables en `formulas_ok`, pero luego compara `tabla_estudiante` contra columnas/variables de la solución, lo que rompe respuestas equivalentes con letras distintas (ej. 11/12/33).
- Tests/checks: consultas MCP `_obtener_ejercicio`, `_obtener_intento`, `_listar_intentos`, `_buscar_respuesta`; snippet local de `verificar_argumento()` con casos 8, 9 y 12 (OK, reproduce diagnóstico). No se ejecutó suite Django.
- Commit: 3555247 (Fix tablas de verdad con renombramiento)
- PR: #142 — https://github.com/jsgoyburu/IPC-Logica/pull/142

### 2026-04-30 12:39 (ART) — agente:codex — rama:master
- Pedido: corregir tabla de verdad para que la comparación use el mismo criterio que el matcher de fórmulas; agregar comando de management para reevaluar intentos históricos de tabla de verdad, actualizar verificación automática y habilitar progreso sin retroceder estudiantes ya avanzados.
- Cambios: `motor/verificador.py` ahora busca un renombramiento global de variables para todo el argumento y, cuando `formulas_ok=True`, corrige/compara la tabla contra las letras y fórmulas efectivamente usadas por lx estudiante; se agregó `reevaluar_tablas_verdad` para recalcular `es_correcto`, limpiar `error_categoria` en intentos ahora verificados, reconciliar `Progreso` y no tocar `aprobado_docente`; `README.md` documenta el comando; tests cubren renombramiento consistente/inconsistente y que el comando avanza sin retroceder.
- Tests/checks: `python -m py_compile motor\verificador.py motor\tests\test_verificador.py ejercicios\management\commands\reevaluar_tablas_verdad.py ejercicios\tests.py` (OK); `SECRET_KEY=test-secret python manage.py test ejercicios.tests.ReevaluarTablasVerdadCommandTests ejercicios.tests.PreviewArgumentoApiTests --verbosity 1` (OK, 4 tests); `SECRET_KEY=test-secret python manage.py check` (OK); snippet local de `verificar_argumento()` para ejercicio 12 renombrado (OK). `pytest` no disponible en el Python activo.
- Commit: pendiente
- PR: N/A

### 2026-05-01 (ART) — agente:claude-sonnet-4-6 — rama:claude/competent-lovelace-08a471
- Pedido: actualizar todos los archivos .md existentes con el estado actual de la plataforma, actualizar documentación Sphinx, y generar ARCHITECTURE.md y WHITE_PAPER.md.
- Cambios:
  - `ARCHITECTURE.md` (nuevo): arquitectura técnica exhaustiva — modelos, flujos, apps, motor, API, frontend, analíticas, configuración, testing, decisiones de diseño, dependencias.
  - `WHITE_PAPER.md` (nuevo): marco pedagógico, didáctico, filosófico y político — Brousseau (TSD, contrato didáctico, devolución, obstáculos epistemológicos), Palau-Couló (errores sistemáticos, lenguaje natural como obstáculo, didáctica de la lógica), principios políticos del diseño, lógica como propedéutica epistemológica.
  - `README.md`: agrega referencias a los nuevos documentos y tabla de documentación.
  - `docs/index.rst`: expandido para cubrir la plataforma completa (no solo el motor); tabla de contenidos actualizada.
  - `docs/plataforma.rst` (nuevo): referencia técnica de apps Django, flujos, API, y comandos de gestión en Sphinx.
  - `docs/conf.py`: actualiza `project` a 'IPC-Lógica', `copyright` a 2025-2026, `release` a '0.3.0'.
- Tests/checks: sin cambios de código funcional; solo documentación y configuración de Sphinx.
- Commit: 0cd081a (Docs: agregar ARCHITECTURE.md, WHITE_PAPER.md y actualizar Sphinx)
- PR: #143

### 2026-05-01 (ART) — agente:codex — rama:claude/sad-bartik-9a15ca
- Pedido: agregar fallback a Groq cuando Gemini alcanza el límite de cuota.
- Cambios:
  - `ejercicios/gemini_hints.py`: agrega `_llamar_groq()` con llamada a Groq Cloud (`llama-3.1-8b-instant`); `generar_pista_gemini()` hace `return _llamar_groq(prompt)` cuando Gemini responde 429. Nueva variable de entorno `GROQ_API_KEY` (opcional).
- Tests/checks: no reportado.
- Commit: 82b952a (feat: agregar fallback a Groq cuando Gemini alcanza el límite de cuota)
- PR: #144

### 2026-05-01 (ART) — agente:claude-sonnet-4-6 — rama:claude/elegant-stonebraker-9e78a2
- Pedido: implementar métricas analíticas avanzadas M1–M6.
- Cambios:
  - `motor/clasificador.py` (nuevo): clasificador automático de errores lógicos (11 categorías: tautologia, contradiccion, polaridad, mas_fuerte, mas_debil, equivalente_alt, error_parcial_1, error_parcial_2, error_sistemico, variables_extra, variables_menos, sin_clasificar). Python puro, sin Django.
  - `motor/tests/test_clasificador.py` (nuevo): tests del clasificador.
  - `motor/verificador.py`: integra clasificador para poblar `error_categoria` en intentos incorrectos de formalización.
  - `analiticas/calculos.py` (nuevo): M2 `_matriz_juicio_computo`, M3 `_convergencia_por_ejercicio`, M4 `_perfil_error_tabla`, M5 `_indice_atomizacion`, M6 `_patron_adivinacion`.
  - `analiticas/views.py`: expone M2 y M6 en el contexto del dashboard; endpoint JSON `/analiticas/metricas_ejercicio/<comision_id>/<ejercicio_id>/` para M3+M4+M5 on-demand.
  - `accounts/models.py` + migración `0017_configsitio_metricas_analiticas`: campos `umbral_adivinacion_intentos` (default 5) y `umbral_adivinacion_segundos` (default 30) en `ConfigSitio`.
  - `ejercicios/models.py`: actualiza choices de `error_categoria` con las 11 categorías del clasificador.
  - `ejercicios/management/commands/poblar_error_categoria.py` (nuevo): comando para poblar `error_categoria` en intentos históricos de formalización.
  - `ejercicios/migrations/0019_update_error_categoria_choices.py` (nueva migración).
- Tests/checks: no reportado.
- Commit: 8e721ef (feat: métricas analíticas avanzadas (M1–M6))
- PR: #146

### 2026-05-01 (ART) — agente:claude-sonnet-4-6 — rama:claude/elegant-stonebraker-9e78a2
- Pedido: exponer M3/M4/M5 con drill-down en dashboard y detalle de práctica.
- Cambios:
  - `templates/analiticas/dashboard.html`: sección expandible por ejercicio que carga M3 (convergencia), M4 (perfil de error en tabla) y M5 (atomización) via fetch JSON al nuevo endpoint.
  - `templates/docentes/practica_detail.html`: igual, con drill-down por ejercicio dentro del contexto de práctica.
  - `analiticas/urls.py`: ruta `metricas_ejercicio/<int:comision_id>/<int:ejercicio_id>/` registrada.
- Tests/checks: no reportado.
- Commit: 4ef10a5 (feat: exponer M3/M4/M5 con drill-down en dashboard y detalle de práctica)
- PR: #147

### 2026-05-01 (ART) — agente:claude-sonnet-4-6 — rama:claude/bold-bohr-d29247
- Pedido: actualizar todos los documentos .md con las novedades.
- Cambios: MEMORY.md, README.md, AGENTS.md y ARCHITECTURE.md actualizados para reflejar M2–M6, motor/clasificador.py, fallback Groq y drill-down de métricas.
- Tests/checks: sin cambios de código funcional.
- Commit: e7ed95a (docs: actualizar documentación con métricas M2–M6, clasificador y fallback Groq)
- PR: #149 — https://github.com/jsgoyburu/IPC-Logica/pull/149

### 2026-05-03 02:46 (UTC) — agente:codex — rama:work
- Pedido: ajustar “Factores del onboarding y rendimiento” para incorporar ausentismo en la métrica de rendimiento previa a correlación.
- Cambios: en `analiticas/research.py` se reemplazó la variable objetivo de correlación por `rendimiento_con_ausentismo` (0–1), ponderando por estado de avance por ejercicio (sin intento < error/rechazo docente < verificación formal automática < aprobación docente) y se actualizó la documentación de la función; en `templates/analiticas/investigacion.html` se actualizó el texto explicativo del panel para reflejar la nueva métrica.
- Tests/checks: `SECRET_KEY=test-secret python manage.py check` (OK); `SECRET_KEY=test-secret python manage.py test analiticas.tests --keepdb` (OK, 42 tests).
- Commit: 3c1ba0c (Ajustar correlaciones de onboarding para incluir ausentismo)
- PR: Ajustar correlaciones de onboarding para incluir ausentismo

### 2026-05-23 15:34 (UTC) — agente:codex — rama:work
- Pedido: agregar paginación por offset en la tool MCP `listar_intentos` manteniendo compatibilidad y cobertura mínima de tests.
- Cambios: `mcp_intentos.py` ahora acepta `offset` en `_listar_intentos_impl`, `listar_intentos` y `listar_intentos_compat`; valida `limit > 0` y `offset >= 0`, limita `limit` a 500, ordena de forma estable por `-timestamp, -id` y pagina con slice `qs[offset:offset+limit]`. Se actualizó `skill-analizar-intentos/SKILL.md` para documentar `offset`. Se agregaron tests en `ejercicios/tests.py` para primera/segunda página, no solapamiento, filtros con offset y compatibilidad por default.
- Tests/checks: `SECRET_KEY=test-secret python manage.py test ejercicios.tests.MCPPaginacionListarIntentosTests` (OK, 4 tests).
- Commit: 5487019 (Agregar paginación offset a listar_intentos MCP)
- PR: Agregar paginación por offset en listar_intentos (MCP)

### 2026-08-07 (ART) — agente:claude-fable-5 — rama:claude/panel-resuelto-vs-revisado
- Pedido: hacer customizable el desbloqueo de ejercicios por práctica. Al diseñarlo apareció un problema previo y más urgente: en cursos masivos el panel docente mostraba 0% de avance porque las métricas dependían de la corrección manual. Se separó ese arreglo en este PR, previo a la feature.
- Cambios: nuevo `ejercicios/correctitud.py` con `Q_CORRECTO`/`Q_INCORRECTO` como definición única de correctitud efectiva; `analiticas/views.py` y cuatro funciones de `mcp_intentos.py` pasan a importarla (había cinco copias literales). Nuevo `_resueltos_por_estudiante_ep` en `docentes/views.py`; `_build_progreso_estudiantes` expone `porcentaje_resuelto` y `resueltos_count`/`total_ejercicios`; `_calcular_avance_promedio` se parametriza por índice de pares. Columna **Resuelto** junto a **Revisado** en `comision_detail.html` y `comisiones_list.html`. Fix adicional tras review: ambos índices de avance llevan ahora la comisión en la clave — una misma `Practica` canónica puede estar en varias comisiones y lo resuelto en una inflaba el avance de la otra al 100% (defecto preexistente en `_aprobados_por_estudiante_ep`).
- Tests/checks: 9 tests nuevos (5 del predicado en `ejercicios`, 4 en `docentes` incluidos 2 de fuga entre comisiones). Suite completa: 189 tests, 15 failures + 4 errors, **todos preexistentes en master** (verificado contra árbol limpio en `origin/master` 8762a97 antes de empezar; la descomposición coincide app por app). Cero regresiones. `docentes` completo: 54 tests, 1 fallo preexistente.
- Pendiente: revisión visual en navegador (no se hizo: el `.env` local apunta a la base de Railway). Suite de `analiticas` rota en master (15 tests), a atacar por separado.
- Commit: a92d98d (fix(docentes): acotar avance por comisión, no solo por ejercicio)
- PR: #181 — https://github.com/jsgoyburu/IPC-Logica/pull/181

### 2026-08-07 (ART) — agente:claude-fable-5 — rama:claude/pinear-dependencias
- Pedido: diagnosticar por qué falló el deploy en Railway tras mergear el PR #181.
- Diagnóstico: el merge no causó el fallo, sólo disparó el primer rebuild en un mes. `requirements.txt` no tenía ninguna versión fijada (15 líneas con `>=` o sin restricción) y pip resolvió dos majors nuevos. `django` 6.0.6 → 6.1 quitó `cc_delim_re` de `django.utils.cache`, que DRF 3.17.2 todavía importa → servicio IPC-Logica FAILED al construir el URLconf. `mcp` 1.28.1 → 2.0.0 renombró `FastMCP` a `MCPServer` y movió `mcp.server.fastmcp.*` a `mcp.server.mcpserver.*` → servicio mcp-intentos CRASHED en el import de `mcp_intentos.py:82`. Verificado comparando el "Successfully installed" del build verde (2026-07-07, deploy 5b75c9e9) contra el fallido (2026-08-07, deploys 4abab6f0 y a456c0cf).
- Cambios: `requirements.txt` con las 15 dependencias directas fijadas con `==` a las versiones del build verde, más comentarios explicando por qué no subir `django` ni `mcp`.
- Tests/checks: los 15 pins verificados uno a uno contra el "Successfully installed" del build verde (15/15 coinciden).
- Pendiente: (a) migrar el servidor MCP a la SDK v2 en un PR aparte — los 49 `@mcp.tool()` no cambian, pero sí la construcción del servidor, `mcp_auth.py` y los cuatro usos de `mcp.settings.transport_security`, que en v2 se pasan a `run()`; no hay codemod. (b) Subir a Django 6.1 recién cuando DRF publique un release con el shim `split_header_value` (ya está en su rama main).
- Commit: (este)
- PR: pendiente

### 2026-08-07 (ART) — agente:claude-opus-5 — rama:claude/lucid-chaplygin-912a6a
- Pedido: decidir y aplicar el criterio de lectura de `practica_detail` en el panel docente. El único camino de acceso para un no-admin era tener la práctica asignada a una comisión propia, así que el autor de una práctica sin comisión recibía 403 sobre su propia práctica, y el "Ver" del banco de prácticas rompía para las públicas de otros docentes.
- Cambios: dos helpers en `docentes/views.py` fijan el criterio. `_puede_ver_practica` (lectura) = staff, autor, práctica pública, o docente de una comisión donde está asignada; `_puede_editar_practica` (escritura) = staff, docente de una comisión donde está asignada, o el autor **mientras ninguna comisión use la práctica**. Ser del banco común no habilita a modificar la práctica de otro. La restricción del autor entró tras el review de Codex en el PR: la `Practica` es canónica y `practica_import` la comparte sin copiar, así que si el autor no enseña en ninguna de las comisiones que la usan, dejarlo escribir le permitía quitar un `EjercicioPractica` y borrar en cascada (`Intento.ejercicio_practica` es CASCADE) los intentos de estudiantes ajenos. El caso que motivó el PR —autor de una práctica que ninguna comisión usa— sigue cubierto. `practica_detail` pasa `puede_editar` al contexto y `practica_detail.html` esconde flechas de reorden, "Quitar", el bloque "Agregar ejercicio existente" y "+ Crear nuevo ejercicio" en modo lectura (más un aviso de solo lectura); el link "Editar" de cada ejercicio se muestra sólo al autor del ejercicio, que es lo que exige `ejercicio_edit` (era un link roto preexistente para ejercicios importados). `ejercicio_practica_add/remove/reorder` y las asignaciones inline de `ejercicio_create`/`ejercicio_edit` pasan a usar `_puede_editar_practica`; `practicas_disponibles` usa el nuevo `_practicas_editables`. El queryset de `practica` en `EjercicioPracticaForm` suma `Q(creada_por=usuario)` para que el autor pueda efectivamente agregar ejercicios a su práctica sin comisión (si no, el form rechazaba la opción). `practica_edit`/`practica_delete` no cambian: operan sobre `PracticaComision`, no sobre la práctica canónica.
- Tests/checks: nueva clase `PracticaDetailPermisosTests` en `docentes/tests.py`, 12 tests (lectura de autor sin comisión, lectura pública ajena en modo lectura, 403 sobre privada ajena, docente de la comisión, staff, ausencia/presencia de acciones en el HTML, 403 en add/remove/reorder para el lector público, alta de ejercicio del autor sobre práctica sin comisión, y los tres del límite del autor: pierde escritura si una comisión ajena usa la práctica, la sigue leyendo, y la conserva si él enseña ahí). `manage.py test docentes`: 67 tests, 1 fallo — `ComisionesListViewTests.test_admin_ve_todas_las_comisiones`, preexistente en master y ajeno a este cambio.
- Nota: no es un fix de fuga de información. Cualquier docente ya podía importar cualquier práctica pública vía `_get_practicas_disponibles`, así que el contenido ya le era accesible; lo que se corrige es la coherencia de permisos y los links rotos.
- Commit: (este)
- PR: pendiente

### 2026-08-07 (ART) — agente:claude-opus-5 — rama:claude/zealous-poincare-60b0f2
- Pedido: determinar si la rama `is_staff` que sobrevivía en `comisiones_list` para el banco de prácticas era deliberada o un descuido, y resolverla en un sentido u otro sin cambiar comportamiento a ciegas. Es el punto que `fda5001` dejó explícitamente pendiente.
- Diagnóstico: descuido. La evidencia inicial apuntaba a lo contrario —`accounts/models.py` documenta el rol Admin como quien "edita/elimina cualquier ejercicio del banco común", la misma asimetría aparecía en tres lugares (`mis_practicas_qs`, `mis_ejercicios`, `_get_practicas_disponibles`) y ningún test la cubría— pero el criterio de alcance de un banco ya estaba definido en el código por autoría más `es_publica`/`es_publico`: así filtran `_get_practicas_disponibles` (`Q(creada_por) | Q(es_publica=True)`) y `EjercicioPracticaForm` (`Q(creado_por) | Q(es_publico=True)`). Los dos bancos del panel eran la única superficie que decidía por rol. Ser admin es un permiso de escritura, no una vista.
- Cambios: `docentes/views.py` — los dos bancos de `comisiones_list` pasan a `Q(propio) | Q(público)` sin rama `is_staff`; las prácticas mantienen el filtro de derivadas (`practica_origen__isnull=True`). `templates/docentes/comisiones_list.html` — sobre un ejercicio público ajeno no se ofrecen Editar/Eliminar ni su diálogo de confirmación (lo exige `ejercicio_edit`) y se muestra el autor en su lugar; sobre una práctica ajena no se ofrece "+ Ejercicio", que tras el review de Codex resultó ser un link roto equivalente: `ejercicio_create` descarta la preselección con `_puede_editar_practica` y el ejercicio quedaba creado sin asignar. El permiso por fila se resuelve con una consulta a `_practicas_editables` para toda la lista, no llamando a `_puede_editar_practica` por práctica. `AGENTS.md` — la decisión queda en la tabla de decisiones.
- Composición con el PR #183: se necesitan las dos mitades. Este cambio hace que el banco liste las públicas ajenas; `_puede_ver_practica` es lo que evita el 403 al abrirlas. `origin/master` mergeado en la rama sin conflictos.
- Tests/checks: 7 tests nuevos en `ComisionesListViewTests` (propio/público ajeno/privado ajeno en cada banco, el caso admin, exclusión de derivadas, botones Editar/Eliminar ocultos y "+ Ejercicio" oculto). `manage.py test docentes ejercicios`: 105 tests en verde. Los 3 errores de `ReconciliarDisyuncionVCommandTests` que aparecen con consola cp1252 son de entorno —`reconciliar_disyuncion_v.py:130` escribe `→`— y pasan con `PYTHONIOENCODING=utf-8`; previos y ajenos a esta rama, que no toca `ejercicios`.
- Pendiente: `_get_practicas_disponibles` (`docentes/views.py`), el selector de importación, conserva su propia rama `is_staff`. La decisión registrada se acotó a los bancos del panel; unificar el selector es un cambio aparte.
- Commit: (este)
- PR: #185

### 2026-08-07 (ART) — agente:claude-opus-5 — rama:claude/zen-brahmagupta-14d5bd
- Pedido: resolver el drift entre `cursos/models.py` y las migraciones, preexistente en master: `makemigrations --check --dry-run` reclamaba una `0006` con `AlterField` sobre `ausente` y `nota_logica_parcial` de `NotaParcial`. Se pedía además determinar si el cambio tocaba el esquema o era sólo de metadatos, y dejarlo dicho en el commit.
- Diagnóstico: sólo metadatos. La migración `0005_rename_puntaje_logica_nota_logica_parcial` renombró el campo `puntaje_logica` → `nota_logica_parcial`, pero `RenameField` cambia únicamente el nombre: los textos que mencionaban el nombre viejo quedaron congelados en el estado de migraciones mientras el modelo seguía evolucionando. Las dos diferencias son el `help_text` de `ausente` (decía "puntaje y puntaje_logica deben ser null", el modelo dice "nota_logica_parcial") y el `verbose_name` de `nota_logica_parcial` ("puntaje parte lógica" → "nota sección lógica"). Los tipos de columna son idénticos en ambos lados: `BooleanField(default=False)` y `DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)`.
- Cambios: nueva `cursos/migrations/0006_sincronizar_metadatos_notaparcial.py`, con las dos `AlterField`. Ningún cambio de código.
- Tests/checks: `sqlmigrate cursos 0006` devuelve las dos operaciones como `-- (no-op)` — cero DDL, así que aplicarla en producción es instantáneo y sin riesgo de bloqueo. `makemigrations cursos --check --dry-run` → `No changes detected in app 'cursos'`. `manage.py test cursos`: 6 tests, OK.
- Pendiente: el `--check` a nivel proyecto sigue sin quedar limpio, pero por otra app: `ejercicios` reclama `0021_alter_intento_error_categoria` (drift en los choices de `Intento.error_categoria`). Ese archivo ya existe, en el commit `d636d66` de otra rama todavía sin mergear a master. Deliberadamente no se generó acá: hacerlo crearía una migración duplicada que choca cuando esa rama se integre. Se cierra mergeando esa rama, no regenerando la migración.
- Criterio: la sincronización de drift va en su propio commit, sin mezclarse con ninguna feature — el mismo criterio que se usó para el drift de choices de `Intento.error_categoria`.
- Commit: cf86522 (chore(cursos): sincronizar migraciones con metadatos de NotaParcial)
- PR: #186 — https://github.com/jsgoyburu/IPC-Logica/pull/186

### 2026-08-07 (ART) — agente:claude-fable-5 — rama:claude/desbloqueo-configurable
- Pedido: que el desbloqueo de ejercicios sea customizable por práctica (hasta ahora era siempre secuencial y estaba cableado en el código).
- Cambios: `PracticaComision.desbloqueo_secuencial` (BooleanField, default True → ninguna práctica existente cambia de comportamiento), migración `0022`. Nuevo módulo `ejercicios/progreso.py` con `avanzar_progreso(estudiante, ep, *, secuencial)`, `eps_resueltos` y `esta_resuelto`; unifica las dos copias casi idénticas que había en `ejercicios/api/views.py` y `docentes/views.py`, que ahora delegan en él. En modo libre el ejercicio actual se recalcula como el primero sin resolver, para que resolver fuera de orden no deje el progreso clavado ni impida marcar la práctica completa. `practica_detail` no bloquea nada y `ejercicio_detail` no redirige en modo libre. Checkbox en `PracticaComisionForm` y `practica_form.html`. El panel docente oculta "Ej. N" en prácticas libres (ahí significaría el primero sin resolver, no hasta dónde llegó) y el cartel al acertar informa cuántos ejercicios quedan en vez de prometer que se avanza al siguiente. La API devuelve `ejercicios_pendientes`.
- Cambio de comportamiento deliberado: `ya_resuelto` en `ejercicio_detail` pasa a usar la correctitud efectiva, así que un intento incorrecto aprobado a mano por el docente ya no admite reenvíos. Antes sí los admitía.
- Migración aparte: `0021_alter_intento_error_categoria` sincroniza drift preexistente de los choices de `Intento.error_categoria` (sólo validación, no toca el esquema). Se separó para no mezclarlo con la feature. El drift equivalente de `cursos.NotaParcial` se resolvió aparte en el PR #186.
- Tests/checks: 16 tests nuevos entre `ejercicios` y `docentes`. Los tests preexistentes de `DesbloqueoProgresivoTests` pasan sin modificarse. Suite completa: 229 tests, OK.
- Commit: b2b4fc8 (docs: registrar el desbloqueo configurable en README y MEMORY)
- PR: #187 — https://github.com/jsgoyburu/IPC-Logica/pull/187

### 2026-08-07 (ART) — agente:claude-opus-5 — rama:claude/charming-bun-071a85
- Pedido: resolver la limitación estructural de `Progreso`, único por `(estudiante, practica)` en vez de por `(estudiante, practica_comision)`. Reportado por Codex en la review del PR #187.
- Problema: importar una práctica no la copia, crea un `PracticaComision` apuntando a la original, así que dos comisiones pueden compartir una `Practica`. Un estudiante inscripto en ambas leía y escribía una sola fila de `Progreso`: un intento en una movía el puntero que leía la otra. El PR #187 lo agravó al dar a cada `PracticaComision` su propio `desbloqueo_secuencial`.
- Cambios de modelo: `Progreso` pasa a `unique_together = ['estudiante', 'practica_comision']`; se elimina `Progreso.practica`; `Intento.practica_comision` pasa a `null=False`. Migraciones `0023` (campo nullable + suelta el unique viejo, necesario porque la rama n≥2 del backfill crea filas con el mismo `(estudiante, practica)`), `0024` (RunPython puro), `0025` (cierra el esquema), `0026` (FK obligatoria).
- Cambio de contrato: `POST /api/intentos/` recibía sólo `ejercicio_practica_id` y adivinaba la comisión con `.first()`. Eso antes elegía sólo el modo de desbloqueo; con la clave nueva elegiría qué fila de progreso avanzar. Ahora exige `practica_comision_id` y valida práctica (400) e inscripción (403). `avanzar_progreso(estudiante, ep, pc)` pierde el kwarg `secuencial`: sale de `pc.desbloqueo_secuencial`.
- Alcance: se scopea por comisión todo el read path (`eps_resueltos`, `esta_resuelto`, el subquery de último intento de `practica_detail`, el historial de `ejercicio_detail`, `home()`), el panel docente, las tres consultas de analíticas/MCP —que además contaban dos veces al estudiante inscripto en varias comisiones— y los cinco management commands que reconcilian progreso. El quinto, `recorregir_tabla_verdad.py`, se detectó tarde: no tiene tests y habría tirado `FieldError`.
- Reglas de backfill en `ejercicios/backfill.py`, como funciones puras que reciben las clases de modelo por parámetro, para que la migración las llame con `apps.get_model(...)` y los tests con los modelos reales sin duplicar la regla ni agregar dependencias.
- Verificación contra producción: 3140 intentos, 0 con `practica_comision` NULL; 0 de 67 estudiantes inscriptos en más de una comisión; 0 pares `(estudiante, práctica)` ambiguos. De 133 filas de `Progreso`, 132 caen en n=1 (puntero verbatim), 0 en n≥2 y 1 en n=0 (`id=29`, estudiante 62, desinscripto de toda comisión) que el backfill borra. La rama n≥2 no se ejecuta en producción; su cobertura es unitaria a propósito.
- Reatribución (P1 de Codex en este PR): la `0015` pobló `Intento.practica_comision` con un mapa global `practica_id -> pc`, quedándose con un pc arbitrario y sin mirar la inscripción, y corrió después de `deduplicar_practicas`. La `0024` ahora reconcilia también las filas no nulas vía `reatribuir_intento()`, que sólo corrige cuando la inscripción identifica un candidato único y nunca anula una FK existente. En producción cambia 0 filas: los 5 intentos incoherentes son todos del estudiante 62, sin inscripción alguna.
- Decisión deliberada: `Intento.practica_comision = null=False` es un tripwire. Si quedara un intento genuinamente ambiguo, la `0026` falla ruidosamente dentro de su transacción en vez de adivinar una comisión y corromper datos en silencio.
- Riesgo operativo pendiente: `Procfile` corre `release: migrate` con el deploy viejo sirviendo tráfico. Entre la `0023` y la `0025` no hay unicidad sobre `Progreso`, así que un envío en esa ventana puede insertar una fila con `practica_comision` NULL y dejar la migración trabada. Requiere ventana corta de mantenimiento o escalar web a cero. Backup obligatorio: la `0024` tiene reversa `noop` y la `0025` borra una columna.
- Tests/checks: 265 tests, OK (`ejercicios` 78, `docentes` 81, `analiticas` 84, `accounts`+`cursos`+`motor`+`tests` 24). Los tests de caracterización que la base agregó en `30ec59c` afirmaban el comportamiento viejo con la firma vieja; se reemplazaron por los que afirman el nuevo, que es lo que el pedido pedía.
- Diseño: `docs/superpowers/specs/2026-08-07-progreso-por-comision-design.md`. Plan: `docs/superpowers/plans/2026-08-07-progreso-por-comision.md`.
- Commit: pendiente de push en esta rama.
- PR: #188 — https://github.com/jsgoyburu/IPC-Logica/pull/188 (apilado sobre #187, no mergeable hasta que ése entre)

### 2026-08-11 02:07 (ART) — agente:codex — rama:codex/public-multilingual-sharing
- Pedido: preparar una continuación pública llamada PropLogPlat, multilingüe (castellano original + inglés, francés y alemán), con contenidos compartibles, instalación de un clic y documentación suficiente para futuros forks humanos o agénticos.
- Cambios: selector de idioma por cookie y default desde `ConfigSitio`; traducciones opcionales de prácticas/ejercicios editables en admin con fallback al castellano; paquetes ZIP/JSON v1 sin datos personales e instalados como copias privadas; asistente inicial protegido, con contacto responsable de privacidad configurable para que cada fork asuma sus propios consentimientos; salud, Railway, Docker y Compose; licencias AGPL-3.0/CC BY-SA 4.0; guías de contribución, forks, despliegue, referencias y contrato de paquetes; CI separado para Django y el motor. La copia pública excluye PDFs académicos de terceros sin licencia acreditada, configuraciones/artefactos locales y `data_utf8.json` (volcado histórico con cuentas), manteniendo referencias y documentos pedagógicos propios. Los scripts locales ahora conducen al asistente en vez de crear credenciales conocidas de ejemplo.
- Tests/checks: `manage.py check` y `makemigrations --check --dry-run` OK; JSON Schema y `railway.toml` parsean; 7 tests nuevos de instalador/idiomas/paquetes OK; `accounts.tests` 26/26 OK; motor 151/151 OK; `docker compose config` OK; atributos `export-ignore` verificados para todas las rutas sensibles/no redistribuibles. La suite completa agotó 5 min y `docentes.tests` agotó 15 min sin resultado final ni fallo emitido. El build de la imagen quedó pendiente porque Docker Desktop no tenía iniciado su servicio.
- Commit: f500ba2 (feat: preparar PropLogPlat multilingue y portable)
- PR: N/A — publicación independiente `jsgoyburu/PropLogPlat` pendiente

# ARCHITECTURE.md — Arquitectura de PropLogPlat

> Documento de referencia exhaustivo. Describe la arquitectura completa, flujos funcionales y decisiones de diseño del sistema.
> Estado: Mayo 2026.

---

## Índice

1. [Visión general](#1-visión-general)
2. [Stack técnico](#2-stack-técnico)
3. [Estructura del repositorio](#3-estructura-del-repositorio)
4. [Modelo de datos](#4-modelo-de-datos)
5. [Apps Django](#5-apps-django)
6. [Motor lógico](#6-motor-lógico)
7. [API REST](#7-api-rest)
8. [Flujos funcionales](#8-flujos-funcionales)
9. [Frontend](#9-frontend)
10. [Analíticas y módulo de investigación](#10-analíticas-y-módulo-de-investigación)
11. [Configuración y despliegue](#11-configuración-y-despliegue)
12. [Testing](#12-testing)
13. [Decisiones de diseño](#13-decisiones-de-diseño)
14. [Dependencias externas](#14-dependencias-externas)

---

## 1. Visión general

PropLogPlat es una plataforma web para práctica de lógica proposicional,
nacida como IPC-Lógica en el curso Introducción al Pensamiento Científico
(IPC) del Ciclo Básico Común de la Universidad de Buenos Aires (CBC-UBA).

### Principio arquitectónico central: hibridez humano–máquina

La arquitectura no es la de un sistema de corrección automática convencional. Está deliberadamente diseñada como una **división de funciones** entre dos agentes:

| Agente | Función |
|--------|---------|
| Máquina | Verificación formal, registro de intentos, visibilidad de datos |
| Docente | Interpretación del error, evaluación pedagógica, devolución |

Esta división no es una limitación técnica: es un **principio pedagógico estructural**. La verificación automática determina si una respuesta es formalmente suficiente para habilitar la continuidad del trabajo. La evaluación pedagógica —decidir si el proceso de aprendizaje fue significativo— permanece en manos humanas.

### Contexto institucional

- **Curso:** IPC/CBC-UBA
- **Escala:** cursos masivos con múltiples comisiones paralelas
- **Libro de texto:** Irving Copi, *Introduction to Logic* (notación Copi)
- **Objetivo pedagógico:** la lógica como propedéutica epistemológica, no como disciplina técnica autónoma

---

## 2. Stack técnico

| Capa | Tecnología |
|------|-----------|
| Backend | Django 5 + Django REST Framework |
| Base de datos | SQLite (local) / PostgreSQL (producción, Railway) |
| Motor lógico | Python puro + SymPy (`sympy.logic`) |
| Frontend | Templates Django + Alpine.js |
| Editor de texto | django-ckeditor-5 (descripciones de prácticas) |
| Servidor estático | WhiteNoise |
| Despliegue | Railway + Gunicorn |
| Tests unitarios | pytest (motor) + Django test runner |
| Tests E2E | Playwright |
| Documentación | Sphinx + Napoleon (Google-style docstrings) |
| Pistas automáticas | Google Gemini API (opcional) + fallback Groq (`llama-3.1-8b-instant`) cuando Gemini alcanza cuota |

---

## 3. Estructura del repositorio

```
IPC-Logica/
├── AGENTS.md                  # Principios, objetivos y reglas para agentes
├── MEMORY.md                  # Bitácora operativa multiagente
├── ARCHITECTURE.md            # Este documento
├── WHITE_PAPER.md             # Principios pedagógicos y marco teórico
├── README.md                  # Documentación pública
├── requirements.txt
├── manage.py
├── railway.toml
│
├── logica_ipc/                # Proyecto Django (settings, URLs globales)
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── accounts/                  # Usuarios, onboarding, consentimientos
├── cursos/                    # Comisiones e inscripciones
├── ejercicios/                # Ejercicios, prácticas, intentos, progreso
│   └── api/                   # API REST (DRF)
├── docentes/                  # Panel docente (vistas, formularios, tests)
├── analiticas/                # Dashboard y módulo de investigación
├── motor/                     # Motor lógico (Python puro, sin Django)
│   └── tests/                 # Tests del motor (pytest)
│
├── templates/                 # Templates HTML
│   ├── base.html
│   ├── registration/          # Auth, onboarding, consentimientos
│   ├── ejercicios/            # Vistas estudiantiles
│   ├── docentes/              # Panel docente
│   └── analiticas/            # Dashboards
│
├── static/                    # Assets estáticos
├── docs/                      # Documentación Sphinx
│   └── auditorias/            # Informes QA históricos
└── tests/                     # Tests E2E (Playwright)
    └── playwright/
```

---

## 4. Modelo de datos

### 4.1 Diagrama de relaciones

```
ConfigSitio (singleton)
└── umbrales analíticos, colores, favicon, nombre del sitio

Usuario (extiende AbstractUser)
├── es_docente: bool
├── debe_cambiar_password: bool
├── consentimiento_pedagogico: bool | null
├── consentimiento_investigacion: bool | null
├── consentimiento_contacto_seguimiento: bool | null
└── encuesta_completada: bool
    └── EncuestaEstudiante (OneToOne, solo si pedagogico=True)

Comision
├── docentes: M:M → Usuario
└── estudiantes: M:M → Usuario (through Inscripcion)

Inscripcion (through-table Comision↔Usuario)
├── estudiante: FK → Usuario
├── comision: FK → Comision
└── fecha_inscripcion: datetime

Practica
├── creada_por: FK → Usuario
├── ejercicios: M:M → Ejercicio (through EjercicioPractica)
└── practica_origen: FK → Practica (self, nullable — copy-on-write)

PracticaComision
├── practica: FK → Practica
├── comision: FK → Comision
├── orden: int
├── fecha_apertura: datetime | null
└── fecha_cierre: datetime | null

Ejercicio
├── creado_por: FK → Usuario
├── tipo: 'tabla_verdad' | 'formalizacion' | 'determinacion_verdad'
├── formula_solucion: str
├── es_publico: bool
└── diccionario_solucion: JSON (variables → lenguaje natural)

EjercicioPractica (through-table Practica↔Ejercicio)
├── practica: FK → Practica
├── ejercicio: FK → Ejercicio
└── orden: int

Intento
├── estudiante: FK → Usuario
├── ejercicio_practica: FK → EjercicioPractica
├── practica_comision: FK → PracticaComision
├── respuesta_raw: str
├── es_correcto: bool            # resultado del motor
├── aprobado_docente: bool | null  # null=pendiente, True=aprobado, False=rechazado
├── comentario_docente: str | null
├── diccionario: JSON
└── timestamp: datetime

Progreso
├── estudiante: FK → Usuario
├── practica_comision: FK → PracticaComision
└── ejercicio_practica_actual: FK → EjercicioPractica | null
```

### 4.2 Invariantes clave

- `Progreso.ejercicio_practica_actual = None` significa que el estudiante completó la práctica.
- `aprobado_docente = None` es el estado "no revisado por docente". La verificación automática (`es_correcto`) y la aprobación docente son independientes.
- `practica_origen IS NOT NULL` identifica prácticas derivadas (importadas). El banco de prácticas solo muestra `practica_origen IS NULL`.
- El rechazo docente (`aprobado_docente = False`) requiere `comentario_docente` no vacío (validado server-side).

### 4.3 Efectividad de la corrección

El sistema distingue dos niveles:
- **Verificación formal** (`es_correcto`): determinada por el motor de forma automática.
- **Aprobación docente** (`aprobado_docente`): decisión humana, puede diferir de `es_correcto`.

El campo `aprobado_docente` permite al docente aprobar una respuesta que el motor rechazó (por ejemplo, formalización semánticamente distinta pero pedagógicamente aceptable) o rechazar una que el motor aprobó (por ejemplo, variables incorrectas en un ejercicio de traducción dirigida).

---

## 5. Apps Django

### 5.1 `accounts` — Usuarios y onboarding

**Responsabilidades:**
- Modelo `Usuario` (extensión de `AbstractUser`)
- Modelo `ConfigSitio` (singleton global de configuración)
- Modelo `EncuestaEstudiante` (survey socioeducativo completo, ~50 campos)
- Flujo de primer ingreso: cambio obligatorio de contraseña + consentimientos informados
- Registro desde link público de comisión (`acceso_comision`)
- Favicon servido desde base de datos (base64)

**Middleware `ForzarCambioPasswordMiddleware`:**
Intercepta todas las requests de usuarios autenticados (excepto logout). Aplica tres checks en orden:
1. Si `debe_cambiar_password=True` → redirige a `cambiar_password`.
2. Si algún consentimiento es `None` → redirige a `dar_consentimiento`.
3. Si es estudiante con `consentimiento_pedagogico=True` y `encuesta_completada=False` → redirige a `encuesta_onboarding`.

**Tipos de encuesta (`Comision.tipo_encuesta`):**
- `'completa'`: 48 preguntas + 3 consentimientos. Para comisiones que participan del proyecto de investigación.
- `'basica'`: preguntas Q2-Q7 + solo Q8. Para comisiones regulares.

**Registro por link de comisión:**
Un docente puede compartir la URL `/accounts/comision/<pk>/acceso/`. Quien accede sin cuenta puede registrarse; la `Inscripcion` en esa comisión se crea automáticamente.

### 5.2 `cursos` — Comisiones

**Responsabilidades:**
- Modelo `Comision`: unidad pedagógica (clase/sección). Tiene N docentes y M estudiantes.
- Modelo `Inscripcion` (through-table explícito): permite enriquecer la relación en el futuro.
- `tipo_encuesta`: elección por comisión.

### 5.3 `ejercicios` — Núcleo académico

**Responsabilidades:**
- Modelos: `Ejercicio`, `Practica`, `PracticaComision`, `EjercicioPractica`, `Intento`, `Progreso`.
- Vistas estudiantiles: lista de prácticas, detalle de práctica (con estados de desbloqueo), formulario de ejercicio individual.
- Lógica de progresión: `_avanzar_progreso()` — actualiza `Progreso` tras intento correcto.
- Comandos de gestión: `reevaluar_tablas_verdad`, `reconciliar_disyuncion_v`.

**Tipos de ejercicio:**
| Tipo | Descripción |
|------|-------------|
| `formalizacion` | Traducir enunciado en lenguaje natural a fórmula proposicional |
| `tabla_verdad` | Construir la tabla de verdad de una fórmula |
| `determinacion_verdad` | Determinar el valor de verdad de una fórmula para una asignación |

**Desbloqueo secuencial:**
Los ejercicios dentro de una práctica se desbloquean uno a uno. `Progreso.ejercicio_practica_actual` apunta al siguiente ejercicio pendiente. Solo ese ejercicio es interactivo; los anteriores están en modo lectura.

**Disponibilidad de práctica:**
`PracticaComision.estado_disponibilidad()` puede retornar:
- `'abierta'`: entre `fecha_apertura` y `fecha_cierre` (o si no hay fechas definidas).
- `'no_iniciada'`: antes de `fecha_apertura`.
- `'cerrada'`: después de `fecha_cierre`.

### 5.4 `docentes` — Panel docente

**Filosofía:** interfaz propia, no admin-first. Optimizada para uso no técnico.

**Vistas principales:**
| Vista | Descripción |
|-------|-------------|
| `comisiones_list` | Dashboard principal del docente |
| `comision_detail` | Detalle de comisión: estudiantes, prácticas, analíticas |
| `ejercicio_form` | CRUD de ejercicios con sandbox de verificación en tiempo real |
| `practica_form` | CRUD de prácticas con CKEditor5 |
| `practica_detail` | Gestión de ejercicios dentro de una práctica (reordenar, agregar, quitar) |
| `estudiante_detail` | Perfil de estudiante con historial completo de intentos |
| `correccion_pendiente` | Cola paginada de intentos pendientes de revisión docente (25/página) |
| `comision_form` | CRUD de comisiones |

**Copy-on-write (`practica_origen`):**
Al importar una práctica del banco, se crea una copia marcada con `practica_origen`. Si el docente edita esa copia (campos o ejercicios), `_desanclar_si_derivada()` limpia `practica_origen` y la copia vuelve a ser independiente. El banco solo muestra prácticas con `practica_origen IS NULL`.

**Importación masiva de estudiantes:**
Desde archivo `.xlsx` con columnas `username`, `email`, `password`. Cada fila se procesa independientemente; las filas inválidas se omiten con reporte. No interrumpe el alta por errores parciales.

### 5.5 `analiticas` — Métricas pedagógicas

**Filosofía:** herramienta de intervención, no de ranking. Los datos existen para facilitar la acción docente, no para clasificar estudiantes.

**Métricas M1 — operativas (en `analiticas/views.py`):**

| Función | Descripción |
|---------|-------------|
| `_ejercicios_mas_dificiles` | Ejercicios por tasa de error (top N) |
| `_distribucion_intentos` | Histograma de intentos hasta resolver (agrupado por ejercicio, desplegable por comisión/práctica) |
| `_estudiantes_en_riesgo` | Estudiantes con N fallos consecutivos sin éxito |
| `_errores_sistematicos` | Respuestas incorrectas compartidas por múltiples estudiantes |
| `_evolucion_temporal` | Intentos por semana ISO (ventana de 8 semanas) |
| `_silencio_resumen` | Estudiantes sin actividad por N días |
| `_silencio_temprano` | Estudiantes que no empezaron en los primeros N días |
| `_velocidad_arranque` | Identificación de práctica concentrada en poco tiempo |
| `_concentracion_practica` | Ratio intentos/día por estudiante |

**Métricas M2–M6 — avanzadas (en `analiticas/calculos.py`):**

| Métrica | Función | Descripción |
|---------|---------|-------------|
| M2 | `_matriz_juicio_computo` | Matriz 2×2 juicio×cómputo en ejercicios `tabla_verdad`. Distingue quién comprende el argumento (juicio) de quién llena la tabla correctamente. Solo disponible cuando hay una comisión seleccionada. |
| M3 | `_convergencia_por_ejercicio` | Curva de intentos acumulados hasta resolver, por ejercicio. Mide la "dificultad efectiva" y la pendiente de aprendizaje. |
| M4 | `_perfil_error_tabla` | Distribución de errores por columna de la tabla de verdad. Identifica qué operador o fila es sistemáticamente incorrecto. |
| M5 | `_indice_atomizacion` | Compara el número de variables usadas por el estudiante con las de la solución. Detecta sobre/sub-atomización. |
| M6 | `_patron_adivinacion` | Señal de baja variación entre intentos consecutivos (intervalo < N seg, respuesta idéntica o muy similar). Sugiere práctica sin reflexión. |

M3, M4 y M5 se cargan **on-demand** via fetch JSON al endpoint `GET /analiticas/detalle-ejercicio/?ejercicio_id=X&comision_id=Y` y se muestran como drill-down expandible en el dashboard y en la vista de detalle de práctica.

**Umbrales:** configurables en `ConfigSitio` (no hardcodeados), incluyendo `umbral_adivinacion_intentos` y `umbral_adivinacion_segundos` para M6. Los valores se muestran en el dashboard para que los criterios sean legibles.

**Cache:** bloque de métricas M1 cacheado 5 minutos por comisión. M3–M5 no se cachean (respuesta JSON directa).

**Módulo de investigación:**
Dashboard separado con métricas de onboarding socioeducativo: NSE estimado, puntaje lógico previo, situación durante pandemia, cohortes, facultades/carreras, cruces con desempeño. Solo visible con `consentimiento_investigacion=True` del estudiante.

### 5.6 `motor` — Motor lógico (Python puro)

Ver sección 6 para documentación detallada.

---

## 6. Motor lógico

El motor es una biblioteca Python pura, completamente desacoplada de Django. Puede testearse e instanciarse sin levantar el stack web.

### 6.1 Módulos

#### `motor/parser.py`

Tokenizador y parser de descenso recursivo.

**Sintaxis aceptada:**

| Conectivo | Notación Copi | Alternativas ASCII |
|-----------|--------------|-------------------|
| Negación | `~` | `~` |
| Conjunción | `·` | `&`, `.` |
| Disyunción | `∨` | `\|`, `v` (en contexto infijo) |
| Condicional | `⊃` | `->` |
| Bicondicional | `≡` | `<->` |

**Símbolos explícitamente rechazados** (con sugerencia de corrección):
`∧` (U+2227), `→` (U+2192), `↔` (U+2194), `¬` (U+00AC).

**Precedencia** (de mayor a menor):
1. `~` (right-associative)
2. `·`
3. `∨`
4. `⊃` (**right-associative**: `p⊃q⊃r` = `p⊃(q⊃r)`)
5. `≡`

**Regla didáctica de paréntesis:**
Cuando se mezclan conectivos binarios distintos al mismo nivel, el parser exige paréntesis explícitos. Ejemplo: `p · q ∨ r` es rechazado; se debe escribir `(p · q) ∨ r` o `p · (q ∨ r)`. Esta regla evita que el estudiante dependa implícitamente de la precedencia sin comprender la estructura.

#### `motor/tabla.py`

Generación de tablas de verdad a partir de expresiones SymPy.

- `generar_tabla_desde_expr(expr)` → `list[dict]` con todas las valuaciones y el resultado.
- `columna_resultado(tabla)` → `list[bool]`, solo la columna de resultado.
- Usa `preorder_traversal` para preservar el orden de primera aparición de variables (orden pedagógico, no alfabético).

#### `motor/clasificador.py`

Clasificador automático de errores lógicos en intentos de formalización incorrectos. Python puro, sin Django.

Función principal: `clasificar_error(respuesta_raw, formula_solucion) → str`.

**11 categorías de error:**

| Categoría | Descripción |
|-----------|-------------|
| `tautologia` | La fórmula del estudiante es siempre verdadera |
| `contradiccion` | La fórmula del estudiante es siempre falsa |
| `polaridad` | Exactamente la negación de la solución (filas invertidas) |
| `mas_fuerte` | La solución implica a la fórmula del estudiante (agregó disyunción) |
| `mas_debil` | La fórmula del estudiante implica a la solución (perdió condición) |
| `equivalente_alt` | Tablas idénticas pero el motor rechazó (variables incorrectas, etc.) |
| `error_parcial_1` | Distancia semántica exactamente 1 fila |
| `error_parcial_2` | Distancia semántica exactamente 2 filas |
| `error_sistemico` | Distancia mayor a la mitad de las filas (error estructural) |
| `variables_extra` | El estudiante usó más variables que la solución |
| `variables_menos` | El estudiante usó menos variables que la solución |
| `sin_clasificar` | Distancias intermedias que no encajan en las anteriores |

Integrado en `IntentoCreateView`: pobla `Intento.error_categoria` para intentos incorrectos de formalización.
Comando para datos históricos: `python manage.py poblar_error_categoria`.

#### `motor/verificador.py`

Interfaz pública del motor. El resto del proyecto solo importa desde aquí.

**`verificar(respuesta_raw, formula_solucion)`**

Flujo:
1. Parsear `respuesta_raw` (error del estudiante si falla → `error_parse`).
2. Parsear `formula_solucion` (bug del sistema si falla → `RuntimeError`).
3. Generar tablas de ambas fórmulas.
4. Comparar columnas de resultado con ordenamiento canónico de filas cuando las variables son las mismas.

Retorna: `{correcto: bool, error_parse: str|None, tabla_estudiante: list|None, tabla_solucion: list|None}`.

**Equivalencia semántica:**
Dos fórmulas son equivalentes si sus columnas de resultado coinciden para todas las valuaciones. Esto permite aceptar `~p | q` como equivalente a `p ⊃ q`, o `~(p & ~q)` como equivalente al mismo condicional.

**Limitaciones conocidas y aceptadas:**
- No verifica que las variables usadas por el estudiante sean las correctas (solo compara la columna de resultado).
- Una tautología es equivalente a cualquier otra tautología (independientemente del número de variables).
- Una contradicción es equivalente a cualquier otra contradicción.
- Si el estudiante agrega variables extra, la tabla tiene más filas → la comparación falla automáticamente por longitud distinta.

**`verificar_argumento(premisas, conclusion, diccionario=None)`**
Verifica si una conclusión se sigue deductivamente de un conjunto de premisas.

**`verificar_determinacion(formula, valores_verdad, diccionario)`**
Verifica asignaciones de valores de verdad específicas para una fórmula.

### 6.2 Flujo de corrección completo

```
Estudiante escribe fórmula en el ejercicio
         ↓
Frontend normaliza símbolos (⊃→->, ∨→|, etc.)
         ↓
POST /api/intentos/ {ejercicio_practica_id, practica_comision_id, respuesta_raw, diccionario}
         ↓
IntentoCreateView.post():
  1. Verifica autenticación
  2. Verifica inscripción del estudiante en la comisión
  3. Verifica disponibilidad de la práctica
  4. Llama motor.verificar(respuesta_raw, formula_solucion)
  5. Crea Intento con resultado
  6. Si correcto: llama _avanzar_progreso()
  7. Retorna {correcto, error_parse, tabla_estudiante, tabla_solucion}
         ↓
Frontend:
  - Si correcto: muestra confirmación, desbloquea siguiente ejercicio
  - Si incorrecto: muestra tablas lado a lado con párrafo pedagógico
    "Encontrá la fila donde tu tabla difiere de la esperada…"
  - Si error_parse: muestra mensaje descriptivo del error de sintaxis
```

---

## 7. API REST

Base URL: `/api/`

### `POST /api/intentos/`

**Autenticación:** requerida (sesión Django).

**Request:**
```json
{
  "ejercicio_practica": 42,
  "practica_comision": 7,
  "respuesta_raw": "~p | q",
  "diccionario": {"p": "Llueve", "q": "Hay tráfico"}
}
```

**Response (correcto):**
```json
{
  "correcto": true,
  "error_parse": null,
  "tabla_estudiante": null,
  "tabla_solucion": null
}
```

**Response (incorrecto):**
```json
{
  "correcto": false,
  "error_parse": null,
  "tabla_estudiante": [{"p": true, "q": true, "resultado": false}, ...],
  "tabla_solucion": [{"p": true, "q": true, "resultado": true}, ...]
}
```

**Response (error de parseo):**
```json
{
  "correcto": false,
  "error_parse": "Carácter no reconocido: '∧' — Usar '·' para la conjunción.",
  "tabla_estudiante": null,
  "tabla_solucion": null
}
```

**Errores HTTP:**
- `403`: estudiante no inscripto en la comisión.
- `403`: práctica no disponible (cerrada o no iniciada).
- `400`: datos de request inválidos.
- `500`: fórmula solución del ejercicio no pudo parsearse (bug del sistema).

### `POST /api/preview/` (sandbox docente)

Endpoint de verificación sin crear `Intento`. Usado en el formulario de ejercicios del panel docente para que el docente verifique su solución antes de guardar.

---

## 8. Flujos funcionales

### 8.1 Primer ingreso de estudiante

```
1. Llega al login (desde link de comisión o por cuenta creada por docente)
2. Si link de comisión (/accounts/comision/<pk>/acceso/):
   a. Puede iniciar sesión (si ya tiene cuenta)
   b. Puede registrarse (username, email, password)
   → Inscripción automática en esa comisión
3. Middleware intercepta post-login:
   a. debe_cambiar_password=True → cambiar_password (obligatorio)
   b. consentimientos None → dar_consentimiento
   c. estudiante + pedagogico=True + encuesta_completada=False → encuesta_onboarding
4. Llega al dashboard estudiantil: lista de prácticas disponibles
```

### 8.2 Resolver un ejercicio

```
1. Estudiante ve lista de prácticas (home)
2. Abre práctica: ve ejercicios con estados (completado / actual / bloqueado)
3. El ejercicio actual muestra:
   - Enunciado
   - Diccionario de variables (si es de formalización)
   - Teclado en pantalla (Alpine.js) con símbolos Copi
   - Campo de texto para la respuesta
4. Envía respuesta → POST /api/intentos/
5. Motor verifica → respuesta aparece en pantalla
6. Si correcto: se desbloquea el siguiente ejercicio
7. Si incorrecto: puede reintentar (sin límite de intentos)
```

### 8.3 Flujo docente — gestión de práctica

```
1. Docente crea o importa práctica
   - Crear: desde cero con título, descripción (CKEditor5), ejercicios del banco
   - Importar: copia una práctica del banco (practica_origen se setea)
2. Asigna la práctica a una comisión (PracticaComision) con orden y fechas opcionales
3. Si edita la práctica importada → _desanclar_si_derivada() limpia practica_origen
4. Estudiantes de esa comisión ven la práctica según disponibilidad
```

### 8.4 Flujo docente — corrección pendiente

```
1. Docente accede a "Correcciones pendientes" (paginado 25/página)
2. Ve intentos con es_correcto determinado por motor pero sin aprobación docente
3. Puede:
   a. Aprobar (aprobado_docente=True, comentario opcional)
   b. Rechazar (aprobado_docente=False, comentario OBLIGATORIO)
4. Puede también revisar el historial completo de intentos de cada estudiante
   en cualquier ejercicio desde estudiante_detail
```

### 8.5 Flujo de analíticas docente

```
1. Docente abre detalle de comisión
2. Dashboard muestra (cacheado 5 min):
   - Ejercicios con mayor dificultad (tasa de error, umbral configurable)
   - Distribución de intentos hasta resolver (histograma, desplegable por comisión)
   - Señales de alerta: estudiantes con N fallos seguidos
   - Errores sistemáticos: respuestas incorrectas compartidas
   - Evolución temporal: intentos por semana (8 semanas)
   - Silencio: estudiantes sin actividad hace N días
   - Arranque tardío: estudiantes sin intentos en primeros N días
3. Criterios visibles en pantalla con valores reales de ConfigSitio
```

---

## 9. Frontend

### Tecnología

- **Templates Django**: Jinja2-style, sin separación de frontend.
- **Alpine.js**: interactividad sin build step (teclado en pantalla, validación de formularios, desplegables en analíticas, formulario de rechazo con comentario obligatorio).
- **CKEditor 5**: editor de texto enriquecido para descripciones de prácticas.
- Sin React, Vue ni bundler. El stack frontend es deliberadamente simple dado el perfil del mantenedor (Python-first) y el objetivo pedagógico (sin sobre-ingeniería).

### Teclado en pantalla

En el formulario de ejercicio (`ejercicio.html`), Alpine.js provee un teclado con los símbolos Copi más usados (`~`, `·`, `∨`, `⊃`, `≡`). El estudiante puede tipear directamente o usar el teclado. El frontend normaliza los equivalentes ASCII antes de enviar al backend.

### Lenguaje de la UI

El sistema usa vocabulario deliberadamente pedagógico:
- "Verificación formal" (no "corrección automática")
- "Formalmente válido" / "No verificado" (no "Correcto" / "Incorrecto")
- "Señales de alerta — estudiantes que podrían necesitar acompañamiento" (no "Estudiantes en riesgo" con connotación evaluativa)

### Idiomas y contenido localizado

`IdiomaSitioMiddleware` activa la preferencia guardada en la cookie estándar
de Django. Si todavía no existe, usa `ConfigSitio.idioma_predeterminado`. La
interfaz propia usa el catálogo explícito y auditable de
`accounts/templatetags/ui_i18n.py`; el administrador de Django usa su soporte
de internacionalización nativo.

El castellano sigue siendo la fuente obligatoria de cada `Practica` y
`Ejercicio`. Los campos `_en`, `_fr` y `_de` son traducciones opcionales
editables desde el admin. Las propiedades `titulo_localizado`,
`descripcion_localizada` y `enunciado_localizado` vuelven al castellano cuando
falta la traducción solicitada: una traducción incompleta nunca oculta material.

### Paquetes de contenido

`ejercicios/paquetes.py` produce y consume un ZIP con un único `package.json`.
El contrato v1 está en `schemas/ipc-logica-package-v1.schema.json`. Sólo viaja
contenido pedagógico y su licencia: quedan fuera usuarios, comisiones, intentos,
progreso, analíticas e identificadores internos. Al instalar, una transacción
valida la fórmula con `EjercicioForm` y crea ejercicios y prácticas privados del
docente importador para que pueda revisarlos antes de compartirlos.

---

## 10. Analíticas y módulo de investigación

### 10.1 Principios de diseño analítico

1. **Intervención, no vigilancia**: los datos sirven para que el docente pueda actuar, no para generar perfiles de estudiantes.
2. **Transparencia de criterios**: los umbrales son visibles en pantalla y configurables.
3. **Consentimiento como prerequisito de investigación**: el módulo de investigación solo accede a datos de estudiantes con `consentimiento_investigacion=True`.
4. **Efectividad pedagógica sobre precisión estadística**: preferir métricas interpretables sobre índices compuestos opacos.

### 10.2 Dashboard de analíticas — vistas y endpoint

**Vistas:**
- `GET /analiticas/dashboard/` — dashboard principal. Selección de comisión(es); renderiza M1 completo y M2/M6 cuando hay una sola comisión seleccionada.
- `GET /analiticas/investigacion/` — módulo de investigación (requiere permiso especial).
- `GET /analiticas/detalle-ejercicio/?ejercicio_id=X&comision_id=Y` — endpoint JSON que devuelve M3 + M4 + M5 para el ejercicio indicado. Cargado por fetch en el drill-down del dashboard y del detalle de práctica.

**Drill-down de M3/M4/M5:**
El dashboard muestra una tabla de ejercicios; cada fila tiene un botón expandible que hace `fetch` al endpoint JSON y renderiza en Alpine.js:
- M3: curva "intentos acumulados vs. porcentaje que resolvió".
- M4: tabla de columnas con errores y conteos.
- M5: comparación de variables usadas vs. esperadas.

### 10.3 Módulo de investigación

Accesible para docentes con permisos especiales. Incluye:
- Distribución socioeducativa de la cohorte (facultad/carrera, NSE estimado, situación laboral)
- Puntaje lógico previo (encuesta de onboarding)
- Situación durante pandemia
- Cruces entre variables socioeducativas y desempeño en ejercicios

Este módulo articula la función de investigación educativa del proyecto: no es solo una herramienta pedagógica sino también un instrumento para producir conocimiento sobre el aprendizaje de la lógica en contextos masivos.

---

## 11. Configuración y despliegue

### 11.1 Variables de entorno

| Variable | Descripción | Requerida |
|----------|-------------|-----------|
| `SECRET_KEY` | Clave secreta Django | Sí |
| `DEBUG` | Modo debug (`True`/`False`) | Sí |
| `ALLOWED_HOSTS` | Hosts habilitados | Sí |
| `DATABASE_URL` | URL de PostgreSQL | En producción |
| `SETUP_TOKEN` | Clave privada del asistente web inicial | En producción |
| `ADMIN_USERNAME` | Usuario admin inicial por variables (alternativa al asistente) | No |
| `ADMIN_EMAIL` | Email admin inicial por variables | No |
| `ADMIN_PASSWORD` | Contraseña admin inicial por variables | No |
| `GEMINI_API_KEY` | Para pistas automáticas (opcional) | No |
| `GROQ_API_KEY` | Fallback a Groq cuando Gemini alcanza cuota (opcional) | No |

### 11.2 Railway

- PostgreSQL administrado, inyectado como `DATABASE_URL`.
- Filesystem efímero → archivos estáticos servidos por WhiteNoise.
- Favicon y configuración persistidos en base de datos (`ConfigSitio`).
- `railway.toml`: migración previa, Gunicorn, `/healthz/` y reinicio ante fallo.
- El template público conecta la aplicación con PostgreSQL y genera los
  secretos necesarios.

### 11.3 Base de datos

- **Local**: SQLite (sin `DATABASE_URL`).
- **Producción**: PostgreSQL con `atomic = False` en migración 0015 (por limitación de PostgreSQL con `ALTER TABLE` en transacciones con FK deferred pendientes).

### 11.4 Inicialización

```bash
python manage.py migrate
python manage.py crear_admin_inicial  # opcional, si se definieron ADMIN_*
```

Sin variables `ADMIN_*`, abrir `/accounts/instalar/` y completar el asistente
con `SETUP_TOKEN`. La operación es transaccional y el asistente queda cerrado
cuando ya existe un superusuario. El asistente también configura
`ConfigSitio.contacto_privacidad`, usado por los consentimientos; si una
instalación no lo completa, la interfaz remite de forma neutra al equipo docente
local y nunca al responsable del proyecto de origen.

### 11.5 Mantenimiento

```bash
# Revalidar intentos históricos con motor actualizado
python manage.py reevaluar_tablas_verdad --dry-run
python manage.py reevaluar_tablas_verdad

# Reconciliar intentos afectados por el bug del parser de 'v' como disyunción
python manage.py reconciliar_disyuncion_v --dry-run
python manage.py reconciliar_disyuncion_v

# Poblar error_categoria en intentos históricos de formalización (clasificador semántico)
python manage.py poblar_error_categoria --dry-run
python manage.py poblar_error_categoria
```

---

## 12. Testing

### 12.1 Motor lógico (pytest)

```bash
pytest motor/tests/
```

Cubre: tokenización, parsing, generación de tablas, verificación semántica, equivalencia tabular, errores conocidos.

### 12.2 Suite Django

```bash
SECRET_KEY=test-secret python manage.py test
```

Apps cubiertas: `accounts`, `ejercicios`, `docentes`.

**Helper `_u(username, password, **kwargs)`**: crea usuario con `debe_cambiar_password=False` y consentimientos completados para bypasear el middleware en tests.

### 12.3 Tests E2E (Playwright)

```bash
# En tests/playwright/
```

Cubre: importación masiva de estudiantes, flujos de UI principales.

### 12.4 Estado actual de la suite (Mayo 2026)

- Motor: 151 tests pasando (agosto de 2026).
- El CI ejecuta el motor y la suite Django en trabajos separados.
- El estado exacto de cada intervención, incluidos timeouts o limitaciones del
  entorno, se registra en `MEMORY.md`.

---

## 13. Decisiones de diseño

| Fecha | Decisión | Alternativa descartada | Razón |
|-------|----------|----------------------|-------|
| 2025 | Corrección por equivalencia tabular | Coincidencia sintáctica | Acepta formalizaciones equivalentes válidas |
| 2025 | Motor como app Python pura | Integrado en views | Testeable sin Django; reemplazable sin tocar vistas |
| 2025 | Panel docente en frontend propio | Solo admin Django | Adopción por docentes no técnicos |
| 2025 | Alpine.js en lugar de React/Vue | React | Perfil Python del mantenedor; sin build step |
| 2025 | SQLite local / PostgreSQL en Railway | SQLite en producción | Railway usa filesystem efímero |
| 2025 | Notación Copi como primaria | ASCII puro | Alineación con el libro de texto IPC/CBC-UBA |
| 2025 | `Progreso` como tabla explícita | Calcular desde `Intento` | Evita recorrer todos los intentos en cada request |
| 2025 | Comentarios ligados a `Intento` | Comentarios por ejercicio | Preserva contexto temporal y trazabilidad |
| 2025 | Importación Excel tolerante a errores | Fallar al primer error | Prioriza robustez en altas masivas |
| 2026 | Paréntesis explícitos para mezclar conectivos | Precedencia implícita | Pedagógico: la estructura debe ser explícita |
| 2026 | `practica_origen` FK (copy-on-write) | Siempre duplicar / nunca duplicar | Evita duplicados visibles; preserva independencia al editar |
| 2026 | `PracticaComision` como tabla intermedia | FK directa `Practica → Comisión` | Porta metadatos contextuales (orden, fechas) |
| 2026 | Alta estudiantil mixta (docente o link) | Auto-registro abierto | Control por comisión + reducción de fricción |
| 2026 | `aprobado_docente` separado de `es_correcto` | Un solo campo | Preserva la distinción formal/pedagógico |
| 2026 | Clasificador de errores semántico (`motor/clasificador.py`) | Solo categoría "incorrecto" | Hace visible el *tipo* de error, no solo la incorrección |
| 2026 | M3–M5 on-demand via endpoint JSON (drill-down) | Calcular todo al cargar el dashboard | Evita sobrecarga en el renderizado; las métricas avanzadas solo se usan cuando el docente las necesita |
| 2026 | Fallback automático Gemini→Groq | Desactivar pistas si Gemini alcanza cuota | Mantiene disponibilidad del servicio sin costo fijo |
| 2026 | Castellano original + traducciones opcionales | Reemplazar el original al traducir | Preserva procedencia, permite traducción incremental y evita material invisible |
| 2026 | Paquetes ZIP/JSON sin datos de uso | Exportar una copia de la base | Hace compartible el material sin exponer trayectorias ni personas |
| 2026 | Instalador web cerrado después del primer uso | Exigir consola para crear el admin | Reduce la barrera técnica sin dejar abierta una superficie de alta privilegiada |

---

## 14. Dependencias externas

| Paquete | Uso |
|---------|-----|
| `django` | Framework web principal |
| `djangorestframework` | API REST (intentos) |
| `sympy` | Motor lógico (tablas de verdad, álgebra booleana) |
| `django-ckeditor-5` | Editor de texto enriquecido para prácticas |
| `openpyxl` | Importación/exportación de estudiantes en Excel |
| `whitenoise` | Archivos estáticos en producción |
| `gunicorn` | Servidor WSGI en Railway |
| `dj-database-url` | Configuración de PostgreSQL desde `DATABASE_URL` |
| `python-dotenv` | Carga de `.env` en desarrollo |
| `sphinx` | Generación de documentación técnica |
| `sphinx-napoleon` | Soporte de Google-style docstrings en Sphinx |
| `sphinx-rtd-theme` | Tema de documentación Read the Docs |
| `google-generativeai` | Pistas automáticas con Gemini (opcional); fallback a Groq vía `urllib` estándar |
| `pytest` | Tests del motor lógico |
| `playwright` | Tests E2E |

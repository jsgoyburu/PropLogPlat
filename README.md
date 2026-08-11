# PropLogPlat

**Propositional Logic Platform** es una plataforma web para práctica de lógica
proposicional, nacida como **IPC-Lógica** en IPC/CBC-UBA y diseñada como apoyo
pedagógico para el trabajo docente en cursos masivos.

El castellano es el idioma original. Cada instalación puede elegir castellano,
inglés, francés o alemán desde el sitio, y el administrador puede definir el
idioma predeterminado y cargar traducciones de prácticas y ejercicios sin
reemplazar los textos originales.

La plataforma implementa una **arquitectura híbrida humano–máquina**:

- **La máquina** realiza verificación formal, registra intentos y visibiliza procesos.
- **El/la docente** interpreta errores, acompaña trayectorias y toma decisiones de evaluación.

Para el marco teórico y los principios pedagógicos que guían el diseño, ver [`WHITE_PAPER.md`](WHITE_PAPER.md).
Para la arquitectura técnica detallada, ver [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Estado actual del sitio

Actualmente el sistema incluye:

- Panel docente operativo (frontend propio, no admin-first) para gestión de comisiones, estudiantes, prácticas, ejercicios e intentos.
- Flujo de primer ingreso con cambio obligatorio de contraseña y consentimientos informados.
- Prácticas con orden explícito de ejercicios, ventanas de apertura/cierre y **desbloqueo configurable**: cada práctica elige, por comisión, si los ejercicios se habilitan de a uno al resolver el anterior (secuencial, el default) o si están todos disponibles desde el inicio (libre).
- Banco de prácticas con importación por **copy-on-write** (`practica_origen`): evita duplicados visibles y desancla copias al editar.
- Verificación formal de respuestas por equivalencia semántica (tablas de verdad), aceptando formalizaciones alternativas válidas.
- Historial de intentos con comentarios docentes por intento.
- Progreso docente desdoblado en **Resuelto** (verificación automática, con precedencia del juicio docente cuando existe) y **Revisado** (corrección manual), para que el avance siga siendo legible en comisiones numerosas sin corrección exhaustiva. La definición de correctitud efectiva vive en `ejercicios/correctitud.py` y la comparten analíticas, MCP y panel docente.
- Analíticas docentes con métricas operativas (M1) y avanzadas M2–M6: matriz juicio×cómputo (tabla_verdad), convergencia semántica, perfil de error, índice de atomización y señal de baja variación; drill-down por ejercicio en el dashboard y en el detalle de práctica.
- Motor de clasificación de errores (`motor/clasificador.py`) con 11 categorías semánticas para intentos de formalización.
- Módulo de investigación con métricas de onboarding socioeducativo (NSE, puntaje lógico, pandemia, cohortes y cruces con desempeño en ejercicios), filtradas por consentimiento.
- Importación masiva de estudiantes por Excel (`.xlsx`) tolerante a errores por fila.
- Configuración del sitio en base de datos (incluyendo favicon y umbrales de analítica pedagógica).
- Selector de idioma castellano/inglés/francés/alemán, con idioma predeterminado y traducciones pedagógicas editables desde el admin.
- Prácticas y ejercicios portables: descarga en ZIP con JSON versionado e instalación como copia privada revisable.
- Asistente web seguro para la primera instalación y despliegue reproducible en Railway o contenedores.

---

## Funcionalidades principales

### Docentes

- Crear/editar ejercicios propios y publicar ejercicios al banco común.
- Crear, editar e importar prácticas.
- Definir descripciones enriquecidas de prácticas con CKEditor 5.
- Programar fechas de apertura y cierre.
- Elegir, por práctica y comisión, si los ejercicios se desbloquean de a uno al resolver el anterior o si están todos disponibles desde el inicio. Útil para distinguir prácticas que construyen dificultad de forma acumulativa de las de repaso, donde trabarse en un ejercicio no debería impedir practicar los demás.
- Revisar progreso por comisión y detalle por estudiante, con dos métricas separadas:
  - **Resuelto**: lo que verificó el sistema. El juicio docente tiene precedencia, así que un intento aprobado a mano cuenta aunque el motor lo haya dado por incorrecto, y uno rechazado no cuenta aunque el motor lo haya dado por correcto. No depende de la corrección manual, así que sigue informando en comisiones numerosas donde revisar todos los intentos no es viable.
  - **Revisado**: lo que el docente aprobó a mano. Es la métrica que alimenta el badge *completa* y el avance promedio por comisión.
- Aprobar/rechazar intentos con devolución pedagógica (obligatoria al rechazar).
- Cargar estudiantes por Excel con reporte de filas inválidas.
- Exportar listado de estudiantes por comisión a Excel (DNI, apellido, nombre y correo).
- Consultar tablero de analíticas para detectar señales de acompañamiento.

### Estudiantes

- Acceder con cuenta creada por su docente o registrarse desde el link público de su comisión.
- Resolver los ejercicios de una práctica: de a uno, desbloqueando el siguiente al resolver el anterior, o en el orden que quieran si la práctica está configurada como libre.
- Recibir verificación formal inmediata de la respuesta.
- A partir del 5.º intento incorrecto en un ejercicio, recibir una pista breve opcional (si `GEMINI_API_KEY` está configurada) orientada al proceso y sin resolver por lx estudiante; con fallback automático a Groq si Gemini alcanza su cuota y `GROQ_API_KEY` está configurada.
- Comparar su tabla con la esperada cuando la respuesta no queda verificada.
- Revisar historial de intentos y devoluciones docentes.
- Completar cambio de contraseña y consentimientos en primer ingreso.

---

## Motor lógico

La app `motor/` está desacoplada de Django (Python puro) y se puede testear en forma aislada.

### Sintaxis aceptada

Notación primaria: **Copi**

- Negación: `~`
- Conjunción: `·` (también `&` y `.`)
- Disyunción: `∨` (también `|`)
- Condicional: `⊃` (también `->`)
- Bicondicional: `≡` (también `<->`)

Regla didáctica vigente: si se mezclan conectivos binarios distintos al mismo nivel, hay que explicitar paréntesis.

### Criterio de verificación

- No se corrige por coincidencia literal de fórmulas.
- Se verifica por equivalencia tabular (semántica).
- Esto permite aceptar múltiples formalizaciones correctas del mismo enunciado.

---

## Stack técnico

- **Backend:** Django 5 + Django REST Framework
- **Base de datos:** SQLite (local) / PostgreSQL (Railway)
- **Motor lógico:** SymPy (`sympy.logic`)
- **Frontend:** templates Django + Alpine.js
- **Rich text:** django-ckeditor-5
- **Deploy:** Railway + Gunicorn + WhiteNoise

Dependencias en `requirements.txt`.

---

## Estructura del repositorio

```text
logica_ipc/      # settings, urls y configuración global
accounts/        # usuarios, onboarding y consentimientos
cursos/          # comisiones e inscripciones
ejercicios/      # ejercicios, prácticas, intentos, progreso
docentes/        # panel docente (vistas/forms/tests)
analiticas/      # dashboard y métricas pedagógicas
motor/           # parser, tablas de verdad y verificador (sin Django)
templates/       # UI HTML
static/          # assets estáticos
docs/            # documentación Sphinx
tests/           # E2E (Playwright)
```

---

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Primera instalación: `http://localhost:8000/accounts/instalar/`

Admin Django después de completar el asistente: `http://localhost:8000/admin/`

### Instalación interactiva

En una base nueva, ejecutar las migraciones y abrir
`http://localhost:8000/accounts/instalar/`. En producción el asistente exige la
clave privada `SETUP_TOKEN`; crea el primer administrador, permite elegir nombre,
idioma y contacto responsable de privacidad del sitio, y luego queda cerrado.

Con contenedores, el recorrido local completo se inicia con:

```bash
docker compose up --build
```

Ver [`docs/DEPLOY.md`](docs/DEPLOY.md) para Railway y otros proveedores.

---

## Variables de entorno

Base (`.env.example`):

- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `ADMIN_USERNAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `SETUP_TOKEN` (protege el asistente de primera instalación)
- `GEMINI_API_KEY` (opcional, para generar pistas automáticas en intentos no verificados)
- `GROQ_API_KEY` (opcional, fallback automático a Groq cuando Gemini alcanza su cuota)

`DATABASE_URL`:

- En local se puede omitir (SQLite por defecto).
- En Railway se inyecta automáticamente para PostgreSQL.

---

## Testing y checks

```bash
# Checks de Django
python manage.py check

# Motor lógico (rápido, sin Django)
pytest motor/tests/

# Suite Django
python manage.py test
```

## Mantenimiento operativo

Para revalidar intentos históricos de ejercicios de tabla de verdad con el motor actual:

```bash
python manage.py reevaluar_tablas_verdad --dry-run
python manage.py reevaluar_tablas_verdad
```

El comando actualiza la verificación formal automática (`es_correcto`) y reconcilia `Progreso` sin modificar `aprobado_docente` ni retroceder estudiantes que ya avanzaron más.

Para poblar `error_categoria` en intentos históricos de formalización (usando el clasificador de errores semántico):

```bash
python manage.py poblar_error_categoria --dry-run
python manage.py poblar_error_categoria
```

---

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Arquitectura técnica completa: modelos, flujos, apps, motor, API, decisiones de diseño |
| [`WHITE_PAPER.md`](WHITE_PAPER.md) | Marco pedagógico: Brousseau, Palau, didáctica de la lógica, principios políticos |
| [`AGENTS.md`](AGENTS.md) | Principios, objetivos, anti-patterns y heurísticas para agentes de IA |
| [`MEMORY.md`](MEMORY.md) | Bitácora operativa multiagente |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Continuidad para docentes, desarrolladorxs y agentes |
| [`FORKING.md`](FORKING.md) | Cómo crear, desplegar y mantener un fork propio |
| [`docs/REFERENCIAS.md`](docs/REFERENCIAS.md) | Procedencia, bibliografía y criterio de publicación de fuentes |
| [`docs/PAQUETES.md`](docs/PAQUETES.md) | Contrato ZIP/JSON para compartir materiales |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Instalación interactiva, Railway y contenedores |
| [`docs/`](docs/) | Documentación Sphinx del motor lógico |

## Licencias

El software se publica bajo AGPL-3.0 (`LICENSE`). La documentación y los
materiales pedagógicos originales se comparten bajo CC BY-SA 4.0
(`CONTENT_LICENSE.md`). Los datos personales y bases de uso real no forman parte
del repositorio ni de esas licencias.

```bash
sphinx-build -b html docs/ docs/_build/html
```

Con warnings como errores:

```bash
sphinx-build -W -b html docs/ docs/_build/html
```

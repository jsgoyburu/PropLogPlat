# PropLogPlat

**Propositional Logic Platform** es una plataforma web para práctica de lógica
proposicional, nacida como **IPC-Lógica** en IPC/CBC-UBA y diseñada como apoyo
pedagógico para el trabajo docente en cursos masivos.

El castellano es el idioma original. Cada instalación puede elegir castellano,
inglés, francés, alemán o chino simplificado desde el sitio, y el administrador puede definir el
idioma predeterminado y cargar traducciones de prácticas y ejercicios sin
reemplazar los textos originales.

La plataforma implementa una **arquitectura híbrida humano–máquina**:

- **La máquina** realiza verificación formal, registra intentos y visibiliza procesos.
- **El/la docente** interpreta errores, acompaña trayectorias y toma decisiones de evaluación.

Para el marco teórico y los principios pedagógicos que guían el diseño, ver [`WHITE_PAPER.md`](WHITE_PAPER.md).
Para la arquitectura técnica detallada, ver [`ARCHITECTURE.md`](ARCHITECTURE.md).

Si la plataforma te resulta útil y querés colaborar voluntariamente con el
sostenimiento de la instancia original, podés
[invitarme un Cafecito](https://cafecito.app/jsgoyburu). Ese apoyo no es un
requisito para instalar, usar, modificar ni compartir PropLogPlat.

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
- Selector de idioma castellano/inglés/francés/alemán/chino simplificado, con idioma predeterminado desde el admin. La interfaz usa catálogos gettext `.po` compilados a `.mo`; las traducciones pedagógicas se editan como contenido desde el admin.
- Prácticas y ejercicios portables: descarga en ZIP con JSON versionado e instalación como copia privada revisable.
- Asistente web de primera entrada, seguro y provider-agnostic: diagnostica el
  despliegue, explica todas las variables, genera un `.env` portable, guía su
  aplicación y configura sitio, cohorte, criterios pedagógicos y administración.

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

#### Cohortes (camadas)

Una **comisión** es el aula y persiste entre cuatrimestres, conservando sus prácticas y ejercicios. Una **cohorte** es la camada que la cursa: año más cuatrimestre.

Para abrir un cuatrimestre nuevo:

1. Un superusuario crea la cohorte desde el home del panel. Es una acción global: cambia la camada en curso para toda la plataforma, por eso no vive dentro de una comisión.
2. Cada docente inscribe a su camada, por alta individual, por Excel, o re-inscribiendo cuentas que ya existen.

El aula aparece con las mismas prácticas y los mismos ejercicios, y todo lo de estudiantes en cero. Las camadas anteriores quedan consultables desde el selector del home.

Algunas propiedades que conviene conocer:

- **La cohorte es la camada de pertenencia, no el período del calendario.** Quien cursó en 2026-C1 y sigue practicando en septiembre para rendir un final sigue perteneciendo a 2026-C1.
- **Una camada cerrada no bloquea a quien la cursó.** Sus estudiantes siguen practicando y avanzando, y se les sigue corrigiendo. Las fechas de apertura y cierre de las prácticas solo frenan a la camada en curso.
- **Una camada cerrada no crece ni suma parciales.** No se pueden dar de alta estudiantes ni crear parciales nuevos en ella; sí cargar notas de los parciales que ya tiene.
- **Quien recursa arranca de cero sin perder su historial.** Su progreso, sus intentos y sus notas de la camada anterior quedan intactos y separados.

Las analíticas, las exportaciones y las herramientas MCP se pueden acotar por camada.

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

- **Backend:** Django 6 + Django REST Framework
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
locale/          # catálogos gettext .po y .mo (es/en/fr/de/zh-Hans)
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

En una base vacía, la primera visita a `http://localhost:8000/` abre el
instalador automáticamente. También puede abrirse directamente en
`http://localhost:8000/accounts/instalar/`.

Admin Django después de completar el asistente: `http://localhost:8000/admin/`

### Instalación interactiva

En una base nueva, ejecutá las migraciones y abrí la URL del sitio. El asistente
está disponible íntegramente en castellano, inglés, francés, alemán y chino
simplificado y recorre tres pasos:

1. **Diagnóstico:** comprueba conexión a la base, migraciones, seguridad,
   dominio, correo, IA y capacidad de escribir un `.env`, sin revelar secretos.
2. **Entorno:** explica y permite completar todas las variables usadas por la
   plataforma. Puede previsualizar o descargar `proplogplat.env`; en un servidor
   propio también puede escribir `.env` si el almacenamiento es persistente.
   Los proveedores administrados no permiten que una aplicación modifique su
   panel: en ese caso el asistente indica exactamente dónde copiar cada valor y
   pide reiniciar antes de continuar.
3. **Sitio:** crea la cuenta administradora, la primera cohorte y la identidad
   local; permite revisar los umbrales pedagógicos con sus valores recomendados.

En producción exige la clave privada `SETUP_TOKEN`. Al crear la primera
administración queda cerrado de manera permanente. Ningún secreto escrito en
el formulario se guarda en la base de datos ni se incluye en logs; las
respuestas del instalador llevan `Cache-Control: no-store`.

Con contenedores, el recorrido local completo se inicia con:

```bash
docker compose up --build
```

Ver [`docs/DEPLOY.md`](docs/DEPLOY.md) para Railway y otros proveedores.
Para agregar o corregir traducciones de interfaz, ver
[`docs/TRADUCCIONES.md`](docs/TRADUCCIONES.md).

---

## Variables de entorno

Base (`.env.example`):

- `SECRET_KEY`
- `SETUP_TOKEN` (protege el asistente de primera instalación)
- `DEBUG`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` y `USE_DATABASE_URL`
- `REDIS_URL` (opcional)
- `PORT` (normalmente lo inyecta el proveedor)
- `ADMIN_USERNAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `GEMINI_API_KEY` (opcional, para generar pistas automáticas en intentos no verificados)
- `GROQ_API_KEY` (opcional, fallback automático a Groq cuando Gemini alcanza su cuota)
- `MCP_TRANSPORT` y `MCP_ISSUER_URL` (opcionales; servidor MCP separado)

Email (recuperación de contraseña):

- `BREVO_API_KEY` (la de producción: manda por la API HTTP de Brevo)
- `EMAIL_HOST` (alternativa por SMTP; sin ninguna de las dos, los mails se imprimen en consola en vez de enviarse)
- `EMAIL_PORT` (default `587`)
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS` (default `True`)
- `EMAIL_USE_SSL` (default `False`; mutuamente excluyente con `EMAIL_USE_TLS`)
- `DEFAULT_FROM_EMAIL` (remitente visible)
- `TRUSTED_PROXY_COUNT` (default `1`; proxies delante de la app, para leer `X-Forwarded-For` al aplicar el techo de pedidos por IP)

La plataforma usa **Brevo** con el dominio propio `practicaslogica.com.ar`
autenticado (SPF + DKIM), y sale por su **API HTTP**, no por SMTP: alcanza con
`BREVO_API_KEY`.

Es API y no SMTP por una razón concreta: **Railway bloquea los puertos SMTP
salientes** (25, 465, 587 y 2525) en los planes Free, Trial y Hobby, y solo los
abre en Pro. Ahí el backend SMTP falla con *Network is unreachable*. El 443 no
se bloquea nunca. El backend vive en `logica_ipc/email_backends.py`, usa
`urllib` de la biblioteca estándar —igual que `ejercicios/gemini_hints.py` con
Gemini y Groq— y no suma dependencias.

El backend SMTP se mantiene como alternativa (`EMAIL_HOST` y compañía) para
desarrollo local, Railway Pro y cualquier otro hosting.

Se eligió sobre Mailgun por una razón operativa, no técnica: Mailgun exige
tarjeta de crédito para mandar a destinatarios no autorizados, aunque nunca se
llegue al límite. Autenticando el mismo dominio, la entregabilidad de los dos
es equivalente. Cambiar de proveedor es editar variables, no código.

`DEFAULT_FROM_EMAIL` tiene que ser una dirección **del dominio autenticado**
(`no-reply@practicaslogica.com.ar`). Con una dirección de otro dominio —un
Gmail, o el subdominio de Railway— SPF y DKIM no alinean, DMARC falla y el mail
se va a spam.

Para probar la configuración sin pasar por la pantalla de recuperación:

```bash
python manage.py sendtestemail vos@ejemplo.com
```

**Si no hay ni `BREVO_API_KEY` ni `EMAIL_HOST`, el sitio no anuncia el enlace
de recuperación de contraseña.** El endpoint sigue disponible para desarrollo
y el correo se imprime en consola; en producción hay que configurar y probar
uno de los dos proveedores antes de ofrecerlo. El setup recomendado en Railway
es `BREVO_API_KEY` sola, sin `EMAIL_HOST`.

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

## Traspaso entre agentes

Si vas a continuar trabajo en curso, empezá por **[`docs/HANDOFF.md`](docs/HANDOFF.md)**:
estado de las ramas y PRs abiertos, verificaciones pendientes contra producción
y trampas del entorno.

Para el modelo de cohortes en particular, **[`docs/bitacora/2026-08-cohortes/README.md`](docs/bitacora/2026-08-cohortes/README.md)**
tiene los invariantes que no hay que romper.

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

---

## Licencia

[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

Se puede usar, estudiar, modificar y redistribuir libremente, incluso con fines comerciales. La condición es la recíproca: cualquier trabajo derivado debe publicarse bajo la misma licencia, y **quien corra una versión modificada como servicio accesible por red está obligado a poner su código fuente a disposición de quienes la usen**. Esa cláusula de red es lo que distingue a la AGPL de la GPL común, y es la razón de elegirla para una plataforma web educativa: impide que el trabajo se convierta en un servicio cerrado sin devolver nada.

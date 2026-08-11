# 🔍 Auditoría Automatizada con Playwright - IPC-Lógica

Suite completa de auditoría del proyecto **IPC-Lógica** según los requerimientos de [AGENTS.md](./AGENTS.md).

---

## 📋 Contenido

Esta auditoría valida los siguientes aspectos según AGENTS.md:

### 1. **tests_audit_playwright.py** - Auditoría General
Verifica fundamentos de la plataforma:
- ✅ Accesibilidad de páginas (home, login)
- ✅ Autenticación y flujo de login/logout
- ✅ Panel docente y analíticas
- ✅ Motor lógico (accesibilidad de API)
- ✅ Seguridad (CSRF protection)
- ✅ Infraestructura (static files, DB connectivity)
- ✅ Diseño responsivo

**Genera:** `audit_report.html` (reporte visual interactivo)

### 2. **tests_audit_motor.py** - Motor Lógico Detallado
Auditoría exhaustiva del motor de lógica proposicional:
- ✅ Parseo de fórmulas en notación Copi (`~`, `·`, `∨`, `⊃`, `≡`)
- ✅ Parseo de ASCII normalizado (`&`, `|`, `->`, `<->`)
- ✅ Generación de tablas de verdad
- ✅ Equivalencia tabular (ley De Morgan, doble negación, condicional, etc.)
- ✅ Casos edge (tautologías, contradicciones, fórmulas complejas)
- ✅ Manejo de errores (símbolos inválidos, paréntesis no balanceados)
- ✅ Normalización Copi vs ASCII

**Genera:** `audit_motor_report.json` (reporte estructurado)

### 3. **tests_audit_docent_panel.py** - Panel Docente
Auditoría de funcionalidades docentes (AGENTS.md §6):
- ✅ Login de docente
- ✅ Gestión de comisiones (CRUD)
- ✅ Gestión de ejercicios (CRUD, banco público)
- ✅ Creación de prácticas y asignación de ejercicios
- ✅ Gestión de estudiantes (creación e importación Excel)
- ✅ Vistas de detalle (comisión, estudiante, progreso)
- ✅ Comentarios de docentes en intentos
- ✅ Exportación de datos como CSV

### 4. **tests_audit_student_flow.py** - Flujo de Estudiante
Auditoría de experiencia del estudiante (AGENTS.md §6):
- ✅ Login de estudiante
- ✅ Visualización de prácticas asignadas
- ✅ Acceso a ejercicios
- ✅ Formulario de respuesta
- ✅ Feedback inmediato (tablas de verdad lado a lado)
- ✅ Seguimiento de progreso
- ✅ Desbloqueo secuencial de ejercicios
- ✅ Historial de intentos y comentarios docentes

---

## 🚀 Instalación y Setup

### 1. Instalar dependencias

```bash
# Ya debería estar instalado, pero confirmar:
pip install playwright

# Instalar navegador Chromium
python -m playwright install chromium
```

### 2. Preparar base de datos de prueba

Ejecutar estos comandos en la raíz del proyecto:

```bash
# Crear migraciones
python manage.py makemigrations
python manage.py migrate

# Crear usuario admin (si no existe)
python manage.py createsuperuser
# Username: admin
# Password: admin123

# Crear usuarios de prueba (docente y estudiante)
python manage.py shell
```

Dentro del shell:

```python
from django.contrib.auth import get_user_model
from cursos.models import Comision
from ejercicios.models import Ejercicio, Practica, EjercicioPractica
from sympy import symbols, And, Or, Implies, Not

Usuario = get_user_model()

# Crear docente de prueba
docent, _ = Usuario.objects.get_or_create(
    username='docent_test',
    defaults={'email': 'docent@test.local', 'es_docente': True}
)
docent.set_password('docent_pass123')
docent.save()

# Crear estudiante de prueba
student, _ = Usuario.objects.get_or_create(
    username='student_test',
    defaults={'email': 'student@test.local', 'es_docente': False}
)
student.set_password('student_pass123')
student.save()

# Crear comisión
comision, _ = Comision.objects.get_or_create(
    nombre='IPC - Turno Test 2025',
)
comision.docentes.add(docent)
comision.estudiantes.add(student)

# Crear ejercicios de prueba
ej1, _ = Ejercicio.objects.get_or_create(
    enunciado='Evalúa la tabla de verdad de p AND q',
    formula_solucion='p · q',
    tipo='tabla_verdad',
    creado_por=docent,
    es_publico=False,
)

ej2, _ = Ejercicio.objects.get_or_create(
    enunciado='Formaliza: "Si llueve entonces la calle está mojada"',
    formula_solucion='p ⊃ q',
    tipo='formalizacion',
    creado_por=docent,
    es_publico=False,
)

# Crear práctica
practica, _ = Practica.objects.get_or_create(
    titulo='Práctica 1 - Tablas de Verdad',
    comision=comision,
    orden=1,
)

# Asignar ejercicios a práctica
EjercicioPractica.objects.get_or_create(
    practica=practica,
    ejercicio=ej1,
    defaults={'orden': 1}
)

EjercicioPractica.objects.get_or_create(
    practica=practica,
    ejercicio=ej2,
    defaults={'orden': 2}
)

print("✓ Base de datos de prueba creada")
exit()
```

### 3. Iniciar servidor Django

Ejecutar en una terminal:

```bash
python manage.py runserver
```

El servidor debe estar en `http://localhost:8000` durante la auditoría.

---

## ▶️ Ejecutar Auditorías

### 🚀 Opción 1: Ejecutar TODO (Recomendado)

```bash
# Ejecuta todas las auditorías y genera reporte consolidado
python audit_all.py
```

**Salida esperada:**
- Ejecución secuencial de 5 auditorías
- Archivo `audit_consolidated_report.html` (reporte visual integrado)
- Reportes individuales adicionales

### Opción 2: Auditorías Individuales

#### Auditoría General

```bash
python tests_audit_playwright.py
```

**Salida esperada:**
- Progreso en consola con ✓/✗
- Archivo `audit_report.html` (abrir en navegador)

#### Motor Lógico

```bash
python tests_audit_motor.py
```

**Salida esperada:**
- Progreso en consola con ✓/✗
- Archivo `audit_motor_report.json` (JSON estructurado)

#### Panel Docente

```bash
python tests_audit_docent_panel.py
```

**Nota:** Requiere credenciales de docente válidas (`docent_test`/`docent_pass123`)

#### Flujo de Estudiante

```bash
python tests_audit_student_flow.py
```

**Nota:** Requiere credenciales de estudiante válidas (`student_test`/`student_pass123`)

#### Importación de Excel

```bash
python tests_audit_excel_import.py
```

**Nota:** Requiere credenciales de docente + datos de prueba en Excel

### Ejecutar Todas las Auditorías en Secuencia (Manual)

```bash
python tests_audit_playwright.py && \
python tests_audit_motor.py && \
python tests_audit_docent_panel.py && \
python tests_audit_student_flow.py && \
python tests_audit_excel_import.py
```

---

## 📊 Interpretación de Resultados

### ✓ PASS
La prueba se ejecutó correctamente y cumple el requerimiento.

### ✗ FAIL  
La prueba falló. Revisar el mensaje para:
- **Servidor no accesible:** Asegurar que `python manage.py runserver` está ejecutándose
- **Usuario no existe:** Crear usuarios de prueba según instrucciones anteriores
- **404 Not Found:** Verificar que las rutas están registradas en `urls.py`
- **Endpoint no implementado:** Completar la implementación de la vista/API

---

## 🔧 Casos Especiales

### Usuario de prueba no autenticado

Si una auditoría muestra "Redirigido a login", significa que:
1. Ese usuario no existe
2. Las credenciales no coinciden

**Solución:**
- Crear el usuario manualmente en `manage.py shell` (ver Setup)
- O modificar las credenciales en los scripts:
  ```python
  auditor = StudentFlowAuditor(
      base_url="http://localhost:8000",
      student_username="tu_usuario",
      student_password="tu_password",
  )
  ```

### Servidor no accesible

Si hay errores de conexión:
```bash
# Asegurar que el servidor está corriendo:
python manage.py runserver
# O en otro puerto:
python manage.py runserver 0.0.0.0:8000
```

### Bases de datos vacía

Si las auditorías no encuentran datos de prueba:
```bash
# Ejecutar setup de datos de prueba (ver sección anterior)
python manage.py shell < setup_test_data.py
```

---

## 📈 Métricas Esperadas

Para una plataforma **completamente implementada**, las tasas de éxito esperadas son:

| Auditoría | Pruebas | Esperado | Tolerancia |
| --- | --- | --- | --- |
| Playwright General | ~15 | 90%+ | Infraestructura |
| Motor Lógico | ~20 | 95%+ | Parseo/Equivalencia |
| Panel Docente | ~10 | 85%+ | CRUD, Importación |
| Flujo Estudiante | ~10 | 85%+ | UX, Desbloqueo |

Si alguna está significativamente por debajo, revisar:
1. Implementación incompleta de esa funcionalidad
2. Configuración incorrecta de URLs o vistas
3. Base de datos vacía o sin datos de prueba

---

## 🛠️ Personalización

### Cambiar URL base

Todos los scripts aceptan un parámetro `base_url`:

```python
auditor = PlaywrightAuditor(base_url="http://tu-servidor.com")
```

### Credenciales personalizadas

```python
auditor = StudentFlowAuditor(
    base_url="http://localhost:8000",
    student_username="mi_usuario",
    student_password="mi_contraseña",
)
```

### Agregar nuevas pruebas

Cada auditor es una clase con métodos `test_*`. Agregar una nueva prueba:

```python
async def test_mi_nueva_prueba(self):
    """Descripción de la prueba."""
    try:
        # Tu lógica aquí
        resultado = await self.page.query_selector("selector")
        passed = bool(resultado)
        self.log_test(
            "Nombre de la prueba",
            "Categoría",
            passed,
            f"Mensaje: {resultado}",
        )
    except Exception as e:
        self.log_test("Nombre de la prueba", "Categoría", False, str(e))
```

---

## 📚 Referencias

- [AGENTS.md](./AGENTS.md) - Documento de arquitectura y decisiones
- [Playwright Documentation](https://playwright.dev/python/) - API de Playwright
- [Django Testing](https://docs.djangoproject.com/en/5.0/topics/testing/) - Testing en Django

---

## 📝 Licencia

Auditoría para **IPC-Lógica** - Plataforma de Lógica Proposicional para IPC-UBA

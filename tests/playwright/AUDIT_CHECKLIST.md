# ✅ Checklist de Auditoría - IPC-Lógica

Referencia rápida de lo que audita cada script según AGENTS.md.

---

## 📋 Checklist Maestro

**Ejecutar:** `python audit_all.py`

Genera reporte consolidado en `audit_consolidated_report.html`.

---

## 1️⃣ Auditoría General (tests_audit_playwright.py)

### Funcionalidades auditadas
- [ ] **Accesibilidad**
  - [ ] Home accesible
  - [ ] Página login funcional
  - [ ] Formulario con username y password
  
- [ ] **Autenticación**
  - [ ] Login funciona (usuario test)
  - [ ] Logout funciona
  - [ ] Redirección post-login correcta
  
- [ ] **Panel Docente**
  - [ ] Accesible en `/docentes/`
  - [ ] Requiere rol docente
  
- [ ] **Analíticas**
  - [ ] Accesibles en `/analiticas/`
  - [ ] Requieren autenticación
  
- [ ] **Motor Lógico (API)**
  - [ ] Endpoint accesible
  - [ ] Responde correctamente
  
- [ ] **Seguridad**
  - [ ] CSRF protection habilitada
  - [ ] Token en formularios
  
- [ ] **Infraestructura**
  - [ ] Archivos estáticos servidos (CSS, JS)
  - [ ] Base de datos conectada
  - [ ] Django admin accesible
  - [ ] Responsive design (viewport meta)

### Reporte generado
- `audit_report.html` - Reporte visual interactivo

---

## 2️⃣ Motor Lógico (tests_audit_motor.py)

### Funcionalidades auditadas
- [ ] **Notación Copi** (parseo)
  - [ ] Negación `~`
  - [ ] Conjunción `·`
  - [ ] Disyunción `∨`
  - [ ] Condicional `⊃`
  - [ ] Bicondicional `≡`
  
- [ ] **Notación ASCII** (parseo)
  - [ ] `&` para conjunción
  - [ ] `|` para disyunción
  - [ ] `->` para condicional
  - [ ] `<->` para bicondicional
  
- [ ] **Generación de Tablas de Verdad**
  - [ ] Variables únicas
  - [ ] Conjunciones/Disyunciones
  - [ ] Fórmulas complejas
  - [ ] Cantidad de filas correcta (2^n)
  
- [ ] **Equivalencia Tabular**
  - [ ] Doble negación: `~~p ≡ p`
  - [ ] De Morgan AND: `~(p·q) ≡ (~p∨~q)`
  - [ ] De Morgan OR: `~(p∨q) ≡ (~p·~q)`
  - [ ] Condicional: `p⊃q ≡ ~p∨q`
  - [ ] Tautologías equivalentes
  
- [ ] **Casos Edge**
  - [ ] Tautologías (p ∨ ~p)
  - [ ] Contradicciones (p · ~p)
  - [ ] Fórmulas complejas con múltiples variables
  
- [ ] **Manejo de Errores**
  - [ ] Fórmula vacía rechazada
  - [ ] Símbolos inválidos detectados
  - [ ] Paréntesis no balanceados rechazados
  - [ ] Mensaje de error legible

### Reporte generado
- `audit_motor_report.json` - Reporte estructurado

---

## 3️⃣ Panel Docente (tests_audit_docent_panel.py)

### Funcionalidades auditadas (AGENTS.md §6)
- [ ] **Autenticación**
  - [ ] Login de docente funciona
  - [ ] Redirige correctamente

- [ ] **Gestión de Comisiones** (CRUD)
  - [ ] Botón crear comisión visible
  - [ ] Listado de comisiones visible
  - [ ] Link a detalle de comisión funciona
  - [ ] Muestra estudiantes inscritos

- [ ] **Gestión de Ejercicios** (CRUD)
  - [ ] Sección de ejercicios accesible
  - [ ] Formulario de creación visible
  - [ ] Opción banco público (es_publico=True)
  - [ ] Vista previa de ejercicio

- [ ] **Prácticas**
  - [ ] Sección de prácticas visible
  - [ ] Crear práctica funciona
  - [ ] Asignar ejercicios a práctica funciona

- [ ] **Gestión de Estudiantes**
  - [ ] Botón crear estudiante visible
  - [ ] Formulario para crear cuenta visible
  - [ ] Botón importar Excel visible
  - [ ] Campo de carga de archivo visible

- [ ] **Vistas de Detalle**
  - [ ] Comisión muestra lista de estudiantes
  - [ ] Estudiante muestra progreso
  - [ ] Progreso es una métrica numérica

- [ ] **Comentarios Docentes**
  - [ ] Campo para comentar intentos visible
  - [ ] Comentarios se guardan y se muestran

- [ ] **Exportación**
  - [ ] Botón exportar datos visible
  - [ ] Formato CSV soportado

### Requisitos previos
- Usuario docente: `docent_test` / `docent_pass123`

---

## 4️⃣ Flujo de Estudiante (tests_audit_student_flow.py)

### Funcionalidades auditadas (AGENTS.md §6)
- [ ] **Autenticación Estudiante**
  - [ ] Login funciona
  - [ ] Sesión iniciada correctamente

- [ ] **Home del Estudiante**
  - [ ] Página home cargada
  - [ ] Título o bienvenida visible

- [ ] **Prácticas Asignadas**
  - [ ] Listado de prácticas visible
  - [ ] Prácticas de su comisión mostradas
  - [ ] Ejercicios dentro de prácticas accesibles

- [ ] **Formulario de Respuesta**
  - [ ] Campo para ingresar fórmula visible
  - [ ] Botón enviar/enviar respuesta visible
  - [ ] Soporta entrada de símbolos Copi

- [ ] **Feedback Inmediato**
  - [ ] Respuesta se evalúa sin recargar
  - [ ] Feedback visible tras envío
  - [ ] Mensaje de error o acierto mostrado

- [ ] **Tablas de Verdad en Feedback**
  - [ ] Si incorrecto, tablas lado-a-lado
  - [ ] Tabla estudiante vs. tabla solución
  - [ ] Filas y columnas visibles

- [ ] **Progreso Personal**
  - [ ] Avance de prácticas visible
  - [ ] Porcentaje o indicador de progreso
  - [ ] Ejercicios realizados contados

- [ ] **Desbloqueo Secuencial**
  - [ ] Primer ejercicio desbloqueado
  - [ ] Siguiente se desbloquea tras responder correctamente
  - [ ] Ejercicios completados permanecen desbloqueados
  - [ ] Indicadores de bloqueado/desbloqueado claros

- [ ] **Historial e Intentos**
  - [ ] Botón historial visible (o similar)
  - [ ] Historial de intentos desplegable
  - [ ] Comentarios docentes visibles
  - [ ] Por defecto muestra último intento

### Requisitos previos
- Usuario estudiante: `student_test` / `student_pass123`
- Prácticas y ejercicios creados en la base de datos

---

## 5️⃣ Importación Excel (tests_audit_excel_import.py)

### Funcionalidades auditadas (AGENTS.md §6)
- [ ] **Botón de Importación**
  - [ ] Botón/link para importar visible
  - [ ] Accesible desde panel docente o comisión

- [ ] **Carga de Archivo**
  - [ ] Campo input file visible
  - [ ] Acepta formato .xlsx
  - [ ] Modal/formulario de importación funciona

- [ ] **Procesamiento de Datos**
  - [ ] Archivo se parsea correctamente
  - [ ] Columnas esperadas: username, email, password
  - [ ] Filas válidas se importan
  - [ ] Se crean usuarios en la BD

- [ ] **Política de Tolerancia a Errores**
  - [ ] Filas con error se saltan (no fallan toda importación)
  - [ ] Usuarios/emails duplicados detectados
  - [ ] Campos incompletos rechazados
  - [ ] El resto se importa normalmente

- [ ] **Reporte de Importación**
  - [ ] Muestra total procesadas
  - [ ] Muestra total importadas
  - [ ] Muestra total fallidas
  - [ ] Detalle por fila fallida (razón del error)
  - [ ] Mensaje legible para docente

- [ ] **Verificación Post-Importación**
  - [ ] Estudiantes importados aparecen en listado
  - [ ] Pueden hacer login con sus credenciales
  - [ ] Están inscritos en la comisión correcta

- [ ] **Manejo de Errores**
  - [ ] Archivo inválido rechazado
  - [ ] Formato incorrecto muestra error
  - [ ] Sin caída del servidor o error 500

### Requisitos previos
- Usuario docente: `docent_test` / `docent_pass123`
- Comisión de prueba creada
- openpyxl instalado (en requirements.txt)

---

## 📊 Resumen de Requerimientos por Rol (AGENTS.md §6)

### Admin
- ✓ Todo lo que hace docente
- ✓ Editar/borrar ejercicios del banco público
- ✓ Gestionar usuarios (crear, desactivar, roles)

### Docente
- ✓ Gestionar comisiones (crear, editar, ver detalle)
- ✓ Crear ejercicios (propios y banco común)
- ✓ Crear prácticas y asignar ejercicios
- ✓ Crear cuentas estudiantes
- ✓ Importar estudiantes masivamente (Excel)
- ✓ Ver vistas de comisión, estudiante y progreso
- ✓ Comentar intentos de estudiantes
- ✓ Exportar datos a CSV
- ✓ Ver analíticas de desempeño

### Estudiante
- ✓ Ver prácticas de su comisión
- ✓ Resolver ejercicios en orden (desbloqueados secuencialmente)
- ✓ Recibir feedback inmediato con tablas de verdad
- ✓ Ver su progreso personal
- ✓ Ver último intento + comentarios docentes
- ✓ Desplegar historial completo de intentos

### Motor Lógico (Todos)
- ✓ Parsear fórmulas en notación Copi
- ✓ Parsear fórmulas en ASCII normalizado
- ✓ Generar tablas de verdad
- ✓ Verificar equivalencia tabular
- ✓ Manejo robusto de errores

---

## 🎯 Métricas de Éxito

| Área | Pruebas | Éxito Mínimo | Real |
|------|---------|--------------|------|
| **General** | ~15 | 90% | ___% |
| **Motor** | ~20 | 95% | ___% |
| **Panel Docente** | ~10 | 85% | ___% |
| **Flujo Estudiante** | ~10 | 85% | ___% |
| **Importación Excel** | ~10 | 85% | ___% |
| **TOTAL** | ~65 | 88% | ___% |

---

## 🔧 Troubleshooting Rápido

| Problema | Solución |
|----------|----------|
| "Servidor no accesible" | `python manage.py runserver` en otra terminal |
| "Usuario no existe" | `python manage.py shell` → crear usuarios de prueba |
| "404 Not Found" | Verificar rutas en `urls.py` |
| "Endpoint no implementado" | Completar vista/serializer corresponiente |
| "Base de datos vacía" | Ejecutar setup de datos de prueba |
| "Motor lógico falla" | Revisar `motor/` + dependencias sympy |

---

## 📚 Referencias Rápidas

- **Documento maestro:** [AGENTS.md](./AGENTS.md)
- **README auditorías:** [AUDIT_README.md](./AUDIT_README.md)
- **Script maestro:** `python audit_all.py`
- **Reportes:** `audit_consolidated_report.html`, `audit_report.html`, `audit_motor_report.json`


# 📑 Índice de Documentación de Auditoría

Referencia completa de la suite de auditoría automatizada Playwright para IPC-Lógica.

---

## ⚡ Comienza Aquí

### Para comenzar rápidamente (3 pasos)
👉 **[QUICK_START.md](./QUICK_START.md)** - Instrucciones ultra-rápidas

### Para entender qué se audita
👉 **[AUDIT_SUMMARY.md](./AUDIT_SUMMARY.md)** - Resumen ejecutivo

---

## 📚 Documentación Completa

### 1. **[QUICK_START.md](./QUICK_START.md)** ⚡
   - **Para:** Usuarios que quieren empezar ahora
   - **Contiene:** 3 pasos + credenciales + troubleshooting rápido
   - **Tiempo de lectura:** 2 minutos

### 2. **[AUDIT_README.md](./AUDIT_README.md)** 📖
   - **Para:** Entender cómo funciona cada auditoría
   - **Contiene:** 
     - Descripción de 5 scripts de auditoría
     - Instalación detallada
     - Setup de base de datos
     - Ejecución paso a paso
     - Troubleshooting completo
     - Personalización de scripts
   - **Tiempo de lectura:** 15 minutos

### 3. **[AUDIT_CHECKLIST.md](./AUDIT_CHECKLIST.md)** ✅
   - **Para:** Verificar qué funcionalidades se auditan
   - **Contiene:**
     - Checklist por cada auditoría
     - Desglose de pruebas por categoría
     - Requerimientos de AGENTS.md por rol
     - Métricas de éxito esperadas
   - **Tiempo de lectura:** 10 minutos

### 4. **[AUDIT_SUMMARY.md](./AUDIT_SUMMARY.md)** 📊
   - **Para:** Resumen ejecutivo
   - **Contiene:**
     - Lista de archivos entregados
     - Cobertura de pruebas (65+ pruebas)
     - Cada auditoría explicada
     - Métricas esperadas
     - Cómo ejecutar
     - Qué verificar manualmente
   - **Tiempo de lectura:** 10 minutos

### 5. **[AGENTS.md](./AGENTS.md)** 📋
   - **Para:** Entender la arquitectura del proyecto y requerimientos
   - **Contiene:**
     - Visión y objetivos (§1)
     - Stack técnico (§2)
     - Arquitectura (§3)
     - Modelos de datos (§4)
     - Motor lógico (§5)
     - Funcionalidades por rol (§6)
     - Desbloqueo de ejercicios (§7)
     - Decisiones de diseño (§10)
   - **Es la FUENTE DE VERDAD**

---

## 🔧 Scripts de Auditoría

| Script | Propósito | Coverage | Reporte |
|--------|-----------|----------|---------|
| [`audit_all.py`](./audit_all.py) | **Ejecuta TODAS las auditorías** | 65+ | HTML consolidado |
| [`tests_audit_playwright.py`](./tests_audit_playwright.py) | General (infra, auth, UX) | 15 pruebas | HTML |
| [`tests_audit_motor.py`](./tests_audit_motor.py) | Motor lógico (parseo, tablas) | 20 pruebas | JSON |
| [`tests_audit_docent_panel.py`](./tests_audit_docent_panel.py) | Panel docente (CRUD) | 10 pruebas | Consola |
| [`tests_audit_student_flow.py`](./tests_audit_student_flow.py) | Flujo estudiante (resolución) | 10 pruebas | Consola |
| [`tests_audit_excel_import.py`](./tests_audit_excel_import.py) | Importación Excel (carga, reporte) | 10 pruebas | Consola |

---

## 🚀 Scripts de Setup

| Script | Plataforma | Hace |
|--------|------------|------|
| [`setup_audit.sh`](./setup_audit.sh) | macOS / Linux / WSL | Instala deps, crea BD, usuarios, datos de prueba |
| [`setup_audit.ps1`](./setup_audit.ps1) | Windows / PowerShell | Instala deps, crea BD, usuarios, datos de prueba |

---

## 📊 Flujo de Trabajo Recomendado

```
1. Leer QUICK_START.md (2 min)
   ↓
2. Ejecutar setup_audit.sh o setup_audit.ps1 (3 min)
   ↓
3. Iniciar Django: python manage.py runserver
   ↓
4. Ejecutar auditorías: python audit_all.py (5 min)
   ↓
5. Abrir audit_consolidated_report.html en navegador
   ↓
6. Si hay fallos:
   - Consultar AUDIT_README.md (troubleshooting)
   - Revisar AUDIT_CHECKLIST.md (qué se audita)
   - Implementar funcionalidad faltante
   - Re-ejecutar auditorías
```

---

## 🎯 Auditorías Explicadas Brevemente

### 1️⃣ **Auditoría General** (15 pruebas)
Verifica que la plataforma existe y funciona básicamente:
- ✓ Páginas accesibles
- ✓ Login/logout funcionan
- ✓ CSRF protection
- ✓ Archivos estáticos se sirven
- ✓ Base de datos conectada
- ✓ Responsive design

### 2️⃣ **Motor Lógico** (20 pruebas)
Verifica el corazón: parseo de fórmulas y cálculo de tablas de verdad:
- ✓ Notación Copi: `~·∨⊃≡`
- ✓ Notación ASCII: `&|->←>`
- ✓ Tablas de verdad correctas
- ✓ Equivalencia tabular (leyes lógicas)
- ✓ Manejo de errores

### 3️⃣ **Panel Docente** (10 pruebas)
Verifica que docentes pueden gestionar:
- ✓ Comisiones (CRUD)
- ✓ Ejercicios (CRUD + banco público)
- ✓ Prácticas (crear + asignar ejercicios)
- ✓ Estudiantes (crear + importar Excel)
- ✓ Comentarios en intentos

### 4️⃣ **Flujo Estudiante** (10 pruebas)
Verifica que estudiantes pueden:
- ✓ Ver prácticas asignadas
- ✓ Resolver ejercicios
- ✓ Recibir feedback inmediato
- ✓ Ver tablas de verdad
- ✓ Seguimiento de progreso
- ✓ Desbloqueo secuencial de ejercicios

### 5️⃣ **Importación Excel** (10 pruebas)
Verifica that teachers can bulk-import students robustly:
- ✓ Carga archivo .xlsx
- ✓ Parsea filas: username, email, password
- ✓ Tolera errores (saltea filas inválidas, continúa)
- ✓ Reporta resultados con detalle
- ✓ Crea usuarios en la BD

---

## ✅ Checklist de Implementación

Antes de ejecutar auditorías, verificar que están implementados:

- [ ] Modelos Django (accounts, cursos, ejercicios): ✓ AGENTS.md §4
- [ ] Motor lógico (sympy): ✓ AGENTS.md §5
- [ ] Vistas de estudiante (resolver, ver progreso)
- [ ] Vistas de docente (CRUD, comisiones, importación)
- [ ] API de intentos (`/api/intentos/`)
- [ ] Modelo `Progreso` (desbloqueo)
- [ ] Templates (ejercicio, feedback, historial)
- [ ] Static files (CSS, JS, Alpine.js)

---

## 🐛 Si Algo Falla

1. **Revisar la sección de troubleshooting en:**
   - QUICK_START.md (rápido)
   - AUDIT_README.md (exhaustivo)

2. **Verificar manualmente:**
   ```bash
   # ¿BD existe?
   ls db.sqlite3
   
   # ¿Usuarios creados?
   python manage.py shell
   >>> from django.contrib.auth import get_user_model
   >>> get_user_model().objects.all()
   
   # ¿Motor funciona?
   >>> from motor.verificador import verificar
   >>> verificar("p · q", "p · q")
   ```

3. **Revisar que el servidor responde:**
   ```bash
   # En otra terminal
   python manage.py runserver
   
   # En otra
   curl http://localhost:8000/
   ```

---

## 📞 Documentación Por Caso de Uso

| Necesito... | Leo... | Tiempo |
|-------------|--------|--------|
| Empezar de inmediato | QUICK_START.md | 2 min |
| Entender qué se audita | AUDIT_SUMMARY.md | 10 min |
| Detalles de cada prueba | AUDIT_CHECKLIST.md | 15 min |
| Instalar y configurar | AUDIT_README.md | 20 min |
| Entender arquitectura | AGENTS.md | 30 min |
| Troubleshooting | AUDIT_README.md (§"Troubleshooting") | 10 min |
| Personalizar auditorías | AUDIT_README.md (§"Personalización") | 15 min |

---

## 🎓 Conceptos Clave

Para entender mejor, revisar en AGENTS.md:

- **Notación Copi** (§5): Símbolos estándar para lógica proposicional
- **Equivalencia Tabular** (§5): Compara fórmulas por tabla de verdad, no sintaxis
- **Desbloqueo Progresivo** (§7): Primer ejercicio abierto, siguiente tras responder bien
- **Tolerancia a Errores** (§6): Importación Excel salta filas inválidas, importa el resto
- **Motor Puro** (§3): `motor/` no importa modelos Django, reutilizable

---

## 🔗 Navegación Rápida

- ⚡ **Quiero empezar ya** → [QUICK_START.md](./QUICK_START.md)
- 📖 **Quiero saber cómo funciona** → [AUDIT_README.md](./AUDIT_README.md)
- ✅ **Quiero ver qué se audita** → [AUDIT_CHECKLIST.md](./AUDIT_CHECKLIST.md)
- 📊 **Quiero resumen ejecutivo** → [AUDIT_SUMMARY.md](./AUDIT_SUMMARY.md)
- 🏗️ **Quiero entender la arquitectura** → [AGENTS.md](./AGENTS.md)

---

**Última actualización:** 2026-02-19  
**Versión:** 1.0  
**Estado:** ✅ Listo para usar


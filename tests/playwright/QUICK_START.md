# ⚡ Quick Start - Auditoría Playwright

Ejecutar auditorías en 3 pasos minimalistas.

---

## Windows (PowerShell)

```powershell
# Paso 1: Setup inicial (instala Chromium, crea usuarios y datos de prueba)
.\setup_audit.ps1

# Paso 2: En otra ventana PowerShell, inicia Django
python manage.py runserver

# Paso 3: Vuelve a la primera ventana y ejecuta auditorías
python audit_all.py
```

Los reportes se generan en:
- `audit_consolidated_report.html` ← **Abre esto en el navegador**

---

## macOS / Linux (Bash)

```bash
# Paso 1: Setup inicial
bash setup_audit.sh

# Paso 2: En otra terminal, inicia Django
python manage.py runserver

# Paso 3: Vuelve a la primera terminal y ejecuta auditorías
python audit_all.py
```

Los reportes se generan en:
- `audit_consolidated_report.html` ← **Abre esto en el navegador**

---

## ¿Qué auditó?

✅ **5 categorías de pruebas:**

1. **General** (15 pruebas)
   - Accesibilidad, autenticación, seguridad, infraestructura

2. **Motor Lógico** (20 pruebas)
   - Parseo Copi/ASCII, tablas de verdad, equivalencia

3. **Panel Docente** (10 pruebas)
   - CRUD comisiones, ejercicios, prácticas, estudiantes

4. **Flujo Estudiante** (10 pruebas)
   - Resolución, feedback, progreso, desbloqueo

5. **Importación Excel** (10 pruebas)
   - Carga de archivo, tolerancia a errores, reporte

---

## Credenciales de Prueba

Se crean automáticamente en step 1:

| Usuario | Password | Rol |
|---------|----------|-----|
| `admin` | `admin123` | Admin |
| `docent_test` | `docent_pass123` | Docente |
| `student_test` | `student_pass123` | Estudiante |

---

## Troubleshooting Rápido

| Error | Solución |
|-------|----------|
| `ModuleNotFoundError: No module named playwright` | La instalación falló; intenta: `pip install playwright` |
| `Servidor no accesible` | Asegúrate de ejecutar `python manage.py runserver` en otra ventana |
| `usuario no existe` | El setup no corrió; vuelve a ejecutar `setup_audit.ps1` o `setup_audit.sh` |
| `ImportError: No module named motor` | Instalar dependencias: `pip install -r requirements.txt` |

---

## Archivos Generados

```
project-root/
├── audit_consolidated_report.html    ← Principal (abre en navegador)
├── audit_report.html                 ← Detalles general
├── audit_motor_report.json           ← Motor lógico (JSON)
└── audit_all.py                      ← Script maestro
```

---

## Para más detalles

📚 Leer [AUDIT_README.md](./AUDIT_README.md) o [AUDIT_CHECKLIST.md](./AUDIT_CHECKLIST.md)

---

## Resumen de lo que verifica

Según **AGENTS.md §6**, audita:

✅ Roles (admin, docente, estudiante)  
✅ Autenticación y autorización  
✅ CRUD de comisiones, ejercicios, prácticas  
✅ Gestión de estudiantes (manual e importación Excel)  
✅ Resolución de ejercicios con feedback  
✅ Desbloqueo progresivo  
✅ Panel de analíticas  
✅ Motor lógico (parseo, tablas, equivalencia)  
✅ Comentarios de docentes  
✅ Exportación de datos  

---

**¿Listo?** Ejecuta `setup_audit.ps1` (Windows) o `setup_audit.sh` (Unix) ahora mismo. 🚀

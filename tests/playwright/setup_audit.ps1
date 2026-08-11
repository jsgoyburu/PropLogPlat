# Script de setup para ejecutar auditorías de Playwright en IPC-Lógica (Windows/PowerShell)
# Uso: .\setup_audit.ps1

Write-Host "=========================================="
Write-Host "Setup de Auditoría Playwright - IPC-Lógica"
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

# Verificar que estamos en el directorio correcto
if (-not (Test-Path "manage.py")) {
    Write-Host "✗ Error: manage.py no encontrado" -ForegroundColor Red
    Write-Host "  Asegúrate de ejecutar este script desde la raíz del proyecto"
    exit 1
}

Write-Host "✓ Directorio correcto" -ForegroundColor Green
Write-Host ""

# 1. Instalar dependencias de Playwright
Write-Host "[1] Instalando Playwright..." -ForegroundColor Cyan
pip install playwright
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Error instalando Playwright" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Playwright instalado" -ForegroundColor Green
Write-Host ""

# 2. Instalar navegador Chromium
Write-Host "[2] Instalando navegador Chromium para Playwright..." -ForegroundColor Cyan
python -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Error instalando Chromium" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Chromium instalado" -ForegroundColor Green
Write-Host ""

# 3. Crear base de datos si no existe
if (-not (Test-Path "db.sqlite3")) {
    Write-Host "[3] Creando base de datos..." -ForegroundColor Cyan
    python manage.py migrate
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Error en migraciones" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Base de datos creada" -ForegroundColor Green
} else {
    Write-Host "[3] Base de datos ya existe" -ForegroundColor Yellow
}
Write-Host ""

# 4. Crear usuarios de prueba
Write-Host "[4] Creando usuarios de prueba..." -ForegroundColor Cyan
python << 'EOF'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'logica_ipc.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
Usuario = get_user_model()

# Admin
admin, created = Usuario.objects.get_or_create(
    username='admin',
    defaults={'email': 'admin@test.local', 'is_staff': True, 'is_superuser': True}
)
if created:
    admin.set_password('admin123')
    admin.save()
    print("✓ Admin creado: admin / admin123")
else:
    print("✓ Admin ya existe")

# Docente
docent, created = Usuario.objects.get_or_create(
    username='docent_test',
    defaults={'email': 'docent@test.local', 'es_docente': True}
)
if created:
    docent.set_password('docent_pass123')
    docent.save()
    print("✓ Docente creado: docent_test / docent_pass123")
else:
    print("✓ Docente ya existe")

# Estudiante
student, created = Usuario.objects.get_or_create(
    username='student_test',
    defaults={'email': 'student@test.local', 'es_docente': False}
)
if created:
    student.set_password('student_pass123')
    student.save()
    print("✓ Estudiante creado: student_test / student_pass123")
else:
    print("✓ Estudiante ya existe")
EOF

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Error creando usuarios de prueba" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 5. Crear datos de prueba
Write-Host "[5] Creando datos de prueba (comisión, prácticas, ejercicios)..." -ForegroundColor Cyan
python << 'EOF'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'logica_ipc.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from cursos.models import Comision, Inscripcion
from ejercicios.models import Ejercicio, Practica, EjercicioPractica

Usuario = get_user_model()

try:
    docent = Usuario.objects.get(username='docent_test')
    student = Usuario.objects.get(username='student_test')

    # Crear comisión
    comision, created = Comision.objects.get_or_create(
        nombre='IPC - Turno Test 2025',
    )
    comision.docentes.add(docent)
    if created:
        print("✓ Comisión creada")
    else:
        print("✓ Comisión ya existe")

    # Inscribir estudiante
    inscripcion, created = Inscripcion.objects.get_or_create(
        estudiante=student,
        comision=comision,
    )
    if created:
        print("✓ Estudiante inscrito en comisión")

    # Crear ejercicios
    ej1, created = Ejercicio.objects.get_or_create(
        enunciado='Evalúa la tabla de verdad de p AND q',
        formula_solucion='p · q',
        tipo='tabla_verdad',
        creado_por=docent,
        es_publico=False,
    )
    if created:
        print("✓ Ejercicio 1 creado (tabla de verdad)")

    ej2, created = Ejercicio.objects.get_or_create(
        enunciado='Formaliza: "Si llueve entonces la calle está mojada"',
        formula_solucion='p ⊃ q',
        tipo='formalizacion',
        creado_por=docent,
        es_publico=False,
    )
    if created:
        print("✓ Ejercicio 2 creado (formalización)")

    # Crear práctica
    practica, created = Practica.objects.get_or_create(
        titulo='Práctica 1 - Tablas de Verdad',
        comision=comision,
        orden=1,
    )
    if created:
        print("✓ Práctica creada")

    # Asignar ejercicios
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
    print("✓ Ejercicios asignados a práctica")

except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)
EOF

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Error creando datos de prueba" -ForegroundColor Red
    exit 1
}
Write-Host ""

Write-Host "=========================================="  -ForegroundColor Green
Write-Host "✓ Setup completado exitosamente" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Próximos pasos:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Inicia el servidor Django en otra terminal/PowerShell:" -ForegroundColor Cyan
Write-Host "   python manage.py runserver" -ForegroundColor White
Write-Host ""
Write-Host "2. En esta terminal, ejecuta las auditorías:" -ForegroundColor Cyan
Write-Host "   python audit_all.py" -ForegroundColor White
Write-Host ""
Write-Host "3. O ejecuta auditorías individuales:" -ForegroundColor Cyan
Write-Host "   python tests_audit_playwright.py" -ForegroundColor White
Write-Host "   python tests_audit_motor.py" -ForegroundColor White
Write-Host "   python tests_audit_docent_panel.py" -ForegroundColor White
Write-Host "   python tests_audit_student_flow.py" -ForegroundColor White
Write-Host "   python tests_audit_excel_import.py" -ForegroundColor White
Write-Host ""
Write-Host "Reportes generados:" -ForegroundColor Yellow
Write-Host "   - audit_consolidated_report.html (reporte maestro)" -ForegroundColor White
Write-Host "   - audit_report.html" -ForegroundColor White
Write-Host "   - audit_motor_report.json" -ForegroundColor White
Write-Host ""

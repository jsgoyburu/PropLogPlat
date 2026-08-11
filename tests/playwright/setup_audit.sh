#!/bin/bash
# Script de setup para ejecutar auditorías de Playwright en IPC-Lógica
# Uso: bash setup_audit.sh

echo "=========================================="
echo "Setup de Auditoría Playwright - IPC-Lógica"
echo "=========================================="
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "manage.py" ]; then
    echo "✗ Error: manage.py no encontrado"
    echo "  Asegúrate de ejecutar este script desde la raíz del proyecto"
    exit 1
fi

echo "✓ Directorio correcto"
echo ""

# 1. Instalar dependencias de Playwright
echo "[1] Instalando Playwright..."
pip install playwright
if [ $? -ne 0 ]; then
    echo "✗ Error instalando Playwright"
    exit 1
fi
echo "✓ Playwright instalado"
echo ""

# 2. Instalar navegador Chromium
echo "[2] Instalando navegador Chromium para Playwright..."
python -m playwright install chromium
if [ $? -ne 0 ]; then
    echo "✗ Error instalando Chromium"
    exit 1
fi
echo "✓ Chromium instalado"
echo ""

# 3. Crear base de datos si no existe
if [ ! -f "db.sqlite3" ]; then
    echo "[3] Creando base de datos..."
    python manage.py migrate
    if [ $? -ne 0 ]; then
        echo "✗ Error en migraciones"
        exit 1
    fi
    echo "✓ Base de datos creada"
else
    echo "[3] Base de datos ya existe"
fi
echo ""

# 4. Crear usuarios de prueba
echo "[4] Creando usuarios de prueba..."
python << EOF
from django.contrib.auth import get_user_model
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'logica_ipc.settings')

import django
django.setup()

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

if [ $? -ne 0 ]; then
    echo "✗ Error creando usuarios de prueba"
    exit 1
fi
echo ""

# 5. Crear datos de prueba (comisión, práctica, ejercicios)
echo "[5] Creando datos de prueba (comisión, prácticas, ejercicios)..."
python << EOF
from django.contrib.auth import get_user_model
from cursos.models import Comision, Inscripcion
from ejercicios.models import Ejercicio, Practica, EjercicioPractica
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'logica_ipc.settings')

import django
django.setup()

Usuario = get_user_model()

try:
    # Obtener usuarios
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

    # Inscribir estudiante en comisión
    inscripcion, created = Inscripcion.objects.get_or_create(
        estudiante=student,
        comision=comision,
    )
    if created:
        print("✓ Estudiante inscrito en comisión")
    else:
        print("✓ Estudiante ya está inscrito")

    # Crear ejercicios de prueba
    ej1, created = Ejercicio.objects.get_or_create(
        enunciado='Evalúa la tabla de verdad de p AND q',
        formula_solucion='p · q',
        tipo='tabla_verdad',
        creado_por=docent,
        es_publico=False,
    )
    if created:
        print("✓ Ejercicio 1 creado (tabla de verdad)")
    else:
        print("✓ Ejercicio 1 ya existe")

    ej2, created = Ejercicio.objects.get_or_create(
        enunciado='Formaliza: "Si llueve entonces la calle está mojada"',
        formula_solucion='p ⊃ q',
        tipo='formalizacion',
        creado_por=docent,
        es_publico=False,
    )
    if created:
        print("✓ Ejercicio 2 creado (formalización)")
    else:
        print("✓ Ejercicio 2 ya existe")

    # Crear práctica
    practica, created = Practica.objects.get_or_create(
        titulo='Práctica 1 - Tablas de Verdad',
        comision=comision,
        orden=1,
    )
    if created:
        print("✓ Práctica creada")
    else:
        print("✓ Práctica ya existe")

    # Asignar ejercicios a práctica
    ep1, created = EjercicioPractica.objects.get_or_create(
        practica=practica,
        ejercicio=ej1,
        defaults={'orden': 1}
    )
    if created:
        print("✓ Ejercicio 1 asignado a práctica")

    ep2, created = EjercicioPractica.objects.get_or_create(
        practica=practica,
        ejercicio=ej2,
        defaults={'orden': 2}
    )
    if created:
        print("✓ Ejercicio 2 asignado a práctica")

except Exception as e:
    print(f"✗ Error creando datos de prueba: {e}")
    exit(1)
EOF

if [ $? -ne 0 ]; then
    echo "✗ Error creando datos de prueba"
    exit 1
fi
echo ""

echo "=========================================="
echo "✓ Setup completado exitosamente"
echo "=========================================="
echo ""
echo "Próximos pasos:"
echo ""
echo "1. Inicia el servidor Django en otra terminal:"
echo "   python manage.py runserver"
echo ""
echo "2. En esta terminal, ejecuta las auditorías:"
echo "   python audit_all.py"
echo ""
echo "3. O ejecuta auditorías individuales:"
echo "   python tests_audit_playwright.py"
echo "   python tests_audit_motor.py"
echo "   python tests_audit_docent_panel.py"
echo "   python tests_audit_student_flow.py"
echo "   python tests_audit_excel_import.py"
echo ""
echo "Reportes generados:"
echo "   - audit_consolidated_report.html (reporte maestro)"
echo "   - audit_report.html"
echo "   - audit_motor_report.json"
echo ""

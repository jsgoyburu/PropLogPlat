# Reporte de testing de últimas incorporaciones

Fecha: 2026-02-19

## Objetivo

Validar de forma exhaustiva:

1. Suite general del proyecto.
2. Comportamiento del motor lógico.
3. Flujo de importación de estudiantes por Excel con `openpyxl`.
4. Ejecución de prueba E2E con Playwright para la importación masiva.

## Comandos ejecutados

- `python manage.py test`
- `pytest motor/tests/ -q`
- `python manage.py test docentes.tests.GestionEstudiantesTests -v 2`
- `python manage.py migrate --noinput`
- Script auxiliar para preparar datos de Playwright (docente, comisión y archivo `.xlsx`).
- Script Playwright vía herramienta de navegador para validar importación masiva desde UI.

## Resultados

### 1) Suite Django (`python manage.py test`)

- Estado: **OK**
- Resultado: `Ran 7 tests ... OK`

### 2) Suite del motor (`pytest motor/tests/ -q`)

- Estado: **FALLA** (4 tests)
- Resultado: `4 failed, 95 passed`
- Tests con falla:
  - `motor/tests/test_parser.py::TestErrores::test_unicode_wedge_no_es_copi`
  - `motor/tests/test_parser.py::TestErrores::test_unicode_flecha_derecha_no_soportada`
  - `motor/tests/test_parser.py::TestErrores::test_unicode_bicondicional_flecha_no_soportado`
  - `motor/tests/test_verificador.py::TestErrorParseo::test_unicode_no_normalizado_devuelve_error_parse`

Interpretación inicial: el parser/verificador está aceptando símbolos Unicode no-Copi que estos tests esperan rechazar.

### 3) Importación Excel con `openpyxl` (`GestionEstudiantesTests`)

- Estado: **OK**
- Resultado: `Ran 3 tests ... OK`
- Cobertura funcional validada:
  - Alta individual + inscripción.
  - Importación tolerante a errores por fila.
  - Restricción de permisos (docente de comisión/admin).

### 4) Playwright (UI importación masiva)

- Estado: **No concluyente por entorno**.
- Se pudo ejecutar el script de Playwright, pero la navegación desde la herramienta de navegador no alcanzó correctamente las rutas de Django y devolvió vistas "Not Found" en las URL esperadas, impidiendo completar la automatización de login + carga de archivo.
- Se guardó captura diagnóstica del intento (`artifacts/login.png`) mostrando "Not Found".

## Conclusión

- La funcionalidad de importación por Excel está cubierta y pasando en tests Django (incluye `openpyxl`).
- Existe una regresión/inconsistencia en el motor respecto al manejo de símbolos Unicode no-Copi (4 tests fallando).
- La prueba E2E con Playwright fue intentada y ejecutada, pero quedó bloqueada por una limitación de conectividad/ruteo entre la herramienta de navegador y el servidor Django en este entorno.

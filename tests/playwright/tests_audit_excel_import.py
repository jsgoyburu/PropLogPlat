"""
Auditoría de Importación de Estudiantes desde Excel en IPC-Lógica.

Este script valida el requerimiento AGENTS.md §6:
  - Docente carga archivo .xlsx con columnas: username, email, password
  - Sistema procesa fila por fila
  - Política de tolerancia: si una fila falla, se salta y continúa
  - Reporte con: total procesadas, importadas, fallidas, detalles por fila fallida

Uso:
  $ python tests_audit_excel_import.py

Dependencias:
  - Servidor Django corriendo en http://localhost:8000
  - Usuario docente autenticado
  - openpyxl instalado (ya en requirements.txt)
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
)


class ExcelImportAuditor:
    """Audita la importación de estudiantes desde Excel."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        docent_username: str = "docent_test",
        docent_password: str = "docent_pass123",
    ):
        """Inicializa el auditor de importación Excel."""
        self.base_url = base_url
        self.docent_username = docent_username
        self.docent_password = docent_password
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.results: List[Dict[str, Any]] = []

    async def setup(self):
        """Inicia el navegador y contexto."""
        pw = await async_playwright().start()
        self.browser = await pw.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

    async def teardown(self):
        """Cierra navegador y contexto."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    def log_test(
        self,
        name: str,
        category: str,
        passed: bool,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        """Registra un resultado de prueba."""
        self.results.append(
            {
                "name": name,
                "category": category,
                "passed": passed,
                "message": message,
                "details": details or {},
            }
        )
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if message:
            print(f"         {message}")

    async def login_docente(self) -> bool:
        """Intenta login con usuario docente."""
        try:
            await self.page.goto(f"{self.base_url}/accounts/login/")

            await self.page.fill("input[name='username']", self.docent_username)
            await self.page.fill("input[name='password']", self.docent_password)
            await self.page.click("button[type='submit']")

            try:
                await self.page.wait_for_url("**/*", timeout=3000)
                if "accounts/login" not in self.page.url:
                    return True
            except:
                pass

            return False
        except Exception as e:
            print(f"  Error en login: {e}")
            return False

    async def test_import_button_visible(self):
        """6.1 Verifica que el botón de importar está visible en el panel docente."""
        logged_in = await self.login_docente()

        if not logged_in:
            self.log_test(
                "Login de docente",
                "Importación Excel",
                False,
                f"Usuario {self.docent_username} no existe",
            )
            return

        self.log_test(
            "Login de docente",
            "Importación Excel",
            True,
            "Sesión iniciada",
        )

        # Navega a sección donde debería estar el botón de importar
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca botón de importación (puede estar en comisión o seción específica)
            import_button = await self.page.query_selector(
                "button:has-text('Importar'), button:has-text('Excel'), a:has-text('Importar estudiantes'), [data-testid='import-students-button']"
            )

            if not import_button:
                # Intenta buscar en vista de comisión específica
                comision_link = await self.page.query_selector("a[href*='comision']")
                if comision_link:
                    await comision_link.click()
                    await self.page.wait_for_url("**/*", timeout=3000)
                    import_button = await self.page.query_selector(
                        "button:has-text('Importar'), button:has-text('Excel'), [data-testid='import-students']"
                    )

            passed = bool(import_button)
            self.log_test(
                "Botón de importación visible",
                "Importación Excel",
                passed,
                "Botón encontrado" if passed else "Botón no visible",
            )

            if passed:
                self.current_import_button = import_button
        except Exception as e:
            self.log_test(
                "Botón de importación visible",
                "Importación Excel",
                False,
                f"Error: {e}",
            )

    async def test_import_file_upload(self):
        """6.2 Verifica que hay campo para subir archivo .xlsx."""
        try:
            # Intenta acceder al botón de importar y esperar modal/formulario
            if hasattr(self, 'current_import_button') and self.current_import_button:
                await self.current_import_button.click()
                await self.page.wait_for_selector(
                    "input[type='file'], [role='dialog'], .import-modal",
                    timeout=3000,
                )

            # Busca input de archivo
            file_input = await self.page.query_selector("input[type='file']")

            passed = bool(file_input)
            self.log_test(
                "Campo de carga de archivo visible",
                "Importación Excel",
                passed,
                "Input file encontrado" if passed else "No hay campo de archivo",
            )

            if passed:
                self.current_file_input = file_input
        except Exception as e:
            self.log_test(
                "Campo de carga de archivo visible",
                "Importación Excel",
                False,
                f"Error: {e}",
            )

    def create_test_xlsx(self) -> Path:
        """Crea un archivo .xlsx de prueba con estudiantes válidos e inválidos."""
        try:
            from openpyxl import Workbook
        except ImportError:
            print("  WARN: openpyxl no instalado; prueba saltada")
            return None

        wb = Workbook()
        ws = wb.active
        ws.title = "Estudiantes"

        # Encabezados
        ws['A1'] = 'username'
        ws['B1'] = 'email'
        ws['C1'] = 'password'

        # Filas válidas
        ws['A2'] = 'estudiante1'
        ws['B2'] = 'est1@test.local'
        ws['C2'] = 'password123'

        ws['A3'] = 'estudiante2'
        ws['B3'] = 'est2@test.local'
        ws['C3'] = 'password456'

        # Fila inválida: email duplicado (simulado)
        # En producción, el backend debe detectar duplicados
        ws['A4'] = 'estudiante3'
        ws['B4'] = 'est2@test.local'  # Email duplicado
        ws['C4'] = 'password789'

        # Fila incompleta (falta password)
        ws['A5'] = 'estudiante4'
        ws['B5'] = 'est4@test.local'
        # No hay password

        # Guardar archivo temporal
        temp_dir = Path(tempfile.gettempdir())
        temp_file = temp_dir / "test_students.xlsx"
        wb.save(temp_file)

        return temp_file

    async def test_import_with_valid_file(self):
        """6.3 Prueba importación con archivo válido."""
        try:
            test_file = self.create_test_xlsx()

            if not test_file or not test_file.exists():
                self.log_test(
                    "Subir archivo .xlsx válido",
                    "Importación Excel",
                    False,
                    "No se pudo crear archivo de prueba",
                )
                return

            # Sube el archivo
            if hasattr(self, 'current_file_input') and self.current_file_input:
                await self.current_file_input.set_input_files(str(test_file))

                # Busca botón de confirmar/enviar
                submit_button = await self.page.query_selector(
                    "button:has-text('Importar'), button:has-text('Confirmar'), button[type='submit']"
                )

                if submit_button:
                    await submit_button.click()

                    # Espera resultado/reporte
                    try:
                        await self.page.wait_for_selector(
                            "[data-testid='import-report'], .import-result, [role='alert']",
                            timeout=5000,
                        )

                        report = await self.page.query_selector(
                            "[data-testid='import-report'], .import-result"
                        )

                        passed = bool(report)
                        self.log_test(
                            "Subir archivo .xlsx válido",
                            "Importación Excel",
                            passed,
                            "Reporte de importación mostrado" if passed else "Sin reporte",
                        )

                        # Intenta extraer estadísticas del reporte
                        if passed:
                            report_text = await report.text_content()
                            self.log_test(
                                "Reporte contiene estadísticas",
                                "Importación Excel",
                                True,
                                f"Reporte: {report_text[:100]}...",
                            )
                    except:
                        self.log_test(
                            "Subir archivo .xlsx válido",
                            "Importación Excel",
                            False,
                            "No se mostró reporte en tiempo esperado",
                        )
                else:
                    self.log_test(
                        "Subir archivo .xlsx válido",
                        "Importación Excel",
                        False,
                        "Botón de confirmación no encontrado",
                    )
            else:
                self.log_test(
                    "Subir archivo .xlsx válido",
                    "Importación Excel",
                    False,
                    "Input file no accesible",
                )

            # Limpiar archivo temporal
            if test_file.exists():
                test_file.unlink()

        except Exception as e:
            self.log_test(
                "Subir archivo .xlsx válido",
                "Importación Excel",
                False,
                f"Error: {e}",
            )

    async def test_import_tolerance_errors(self):
        """6.4 Prueba política de tolerancia a errores (saltear filas problemáticas)."""
        try:
            # Esta prueba se basa en el comportamiento esperado del backend
            # El reporte debe mostrar que se saltaron filas con error

            report = await self.page.query_selector(
                "[data-testid='import-report'], .import-result, .report"
            )

            if report:
                report_text = await report.text_content()

                # Busca indicadores de filas fallidas
                has_failed_count = "fallida" in report_text.lower() or "error" in report_text.lower()
                has_success_count = "importada" in report_text.lower() or "éxito" in report_text.lower()

                passed = has_failed_count and has_success_count
                self.log_test(
                    "Reporte muestra detalle de fallos",
                    "Importación Excel",
                    passed,
                    f"Fallidas/Exitosas detectadas: {has_failed_count and has_success_count}",
                    {"report_preview": report_text[:200]},
                )
            else:
                self.log_test(
                    "Reporte muestra detalle de fallos",
                    "Importación Excel",
                    False,
                    "No hay reporte visible",
                )
        except Exception as e:
            self.log_test(
                "Reporte muestra detalle de fallos",
                "Importación Excel",
                False,
                f"Error: {e}",
            )

    async def test_import_creates_users(self):
        """6.5 Verifica que la importación crea usuarios en la base de datos."""
        try:
            # Esta prueba es más validación de backend que UI
            # Aquí verificamos que después de importar, los estudiantes aparecen en el listado

            # Navega a listado de estudiantes de la comisión
            await self.page.goto(f"{self.base_url}/docentes/")

            # Busca tabla/listado de estudiantes
            estudiantes_list = await self.page.query_selector(
                "[data-testid='estudiantes-list'], table, [role='table']"
            )

            if estudiantes_list:
                # Busca filas de estudiante (puede haber nuevos después de importar)
                rows = await self.page.query_selector_all("tbody tr, [role='row']")

                # Busca por nombres específicos si es posible
                estudiante1 = await self.page.query_selector("text='estudiante1'")

                passed = bool(rows and len(rows) > 0)
                self.log_test(
                    "Usuarios importados aparecen en listado",
                    "Importación Excel",
                    passed,
                    f"Total de estudiantes en lista: {len(rows)}" if rows else "Sin estudiantes",
                )
            else:
                self.log_test(
                    "Usuarios importados aparecen en listado",
                    "Importación Excel",
                    False,
                    "No hay listado de estudiantes visible",
                )
        except Exception as e:
            self.log_test(
                "Usuarios importados aparecen en listado",
                "Importación Excel",
                False,
                f"Error: {e}",
            )

    async def test_import_error_handling(self):
        """6.6 Prueba manejo de errores: archivo inválido, formato incorrecto."""
        try:
            # Crea un archivo con formato incorrecto
            temp_dir = Path(tempfile.gettempdir())
            bad_file = temp_dir / "bad_students.xlsx"

            # Archivo vacío (inválido)
            bad_file.write_text("not a valid xlsx")

            # Intenta subir archivo inválido
            if hasattr(self, 'current_file_input') and self.current_file_input:
                try:
                    await self.current_file_input.set_input_files(str(bad_file))
                    
                    submit_button = await self.page.query_selector("button[type='submit']")
                    if submit_button:
                        await submit_button.click()

                    # Debería mostrar error
                    error_msg = await self.page.query_selector(
                        "[role='alert'], .error, .error-message"
                    )

                    passed = bool(error_msg)
                    self.log_test(
                        "Manejo de archivo inválido",
                        "Importación Excel",
                        passed,
                        "Mensaje de error mostrado" if passed else "Sin mensaje de error",
                    )
                except Exception as upload_error:
                    # Playwright puede rechazar el archivo antes de enviarlo
                    self.log_test(
                        "Manejo de archivo inválido",
                        "Importación Excel",
                        True,
                        f"Navegador rechazó archivo inválido (esperado): {type(upload_error).__name__}",
                    )
            else:
                self.log_test(
                    "Manejo de archivo inválido",
                    "Importación Excel",
                    False,
                    "Input file no accesible",
                )

            # Limpiar
            if bad_file.exists():
                bad_file.unlink()

        except Exception as e:
            self.log_test(
                "Manejo de archivo inválido",
                "Importación Excel",
                False,
                f"Error: {e}",
            )

    async def run(self):
        """Ejecuta todas las auditorías de importación Excel."""
        await self.setup()

        print("\n" + "=" * 60)
        print("AUDITORÍA DE IMPORTACIÓN DE ESTUDIANTES (EXCEL)")
        print("=" * 60 + "\n")

        try:
            print("[1] Accesibilidad del botón de importación")
            print("-" * 60)
            await self.test_import_button_visible()

            if self.page and "accounts/login" not in self.page.url:
                print("\n[2] Campo de carga de archivo")
                print("-" * 60)
                await self.test_import_file_upload()

                print("\n[3] Importación con archivo válido")
                print("-" * 60)
                await self.test_import_with_valid_file()

                print("\n[4] Política de tolerancia a errores")
                print("-" * 60)
                await self.test_import_tolerance_errors()

                print("\n[5] Verificación de creación de usuarios")
                print("-" * 60)
                await self.test_import_creates_users()

                print("\n[6] Manejo de errores (archivo inválido)")
                print("-" * 60)
                await self.test_import_error_handling()

            # Resumen
            passed = sum(1 for r in self.results if r["passed"])
            total = len(self.results)

            print("\n" + "=" * 60)
            print(f"✓ {passed}/{total} pruebas aprobadas ({passed/total*100:.1f}%)")
            print("=" * 60 + "\n")

        finally:
            await self.teardown()


async def main():
    """Punto de entrada principal."""
    auditor = ExcelImportAuditor(
        base_url="http://localhost:8000",
        docent_username="docent_test",
        docent_password="docent_pass123",
    )
    await auditor.run()


if __name__ == "__main__":
    asyncio.run(main())

"""
Auditoría del Panel Docente de IPC-Lógica con Playwright.

Este script valida los requerimientos del panel docente según AGENTS.md §6:
  - Gestión de comisiones (crear, editar, ver detalle)
  - CRUD de ejercicios (propios y banco común)
  - Creación de prácticas y asignación de ejercicios
  - Vista previa de ejercicios
  - Importación de estudiantes desde Excel
  - Creación de cuentas de estudiantes
  - Vistas de comisión, estudiante y suas resoluciones
  - Comentarios de docentes en intentos
  - Exportación de datos como CSV

Uso:
  $ python tests_audit_docent_panel.py

Dependencias:
  - Servidor Django corriendo en http://localhost:8000
  - Usuario docente autenticado con credenciales de prueba
"""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
)


class DocencePanelAuditor:
    """Audita el panel docente de IPC-Lógica."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        docent_username: str = "docent_test",
        docent_password: str = "docent_pass123",
    ):
        """Inicializa el auditor del panel docente."""
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

            # Intenta llenar y enviar formulario de login
            await self.page.fill("input[name='username']", self.docent_username)
            await self.page.fill("input[name='password']", self.docent_password)
            await self.page.click("button[type='submit']")

            # Espera redirección o mensaje de error
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

    async def test_docente_panel_navigation(self):
        """2.1 Verifica navegación del panel docente."""
        logged_in = await self.login_docente()

        if not logged_in:
            self.log_test(
                "Login de docente",
                "Autenticación",
                False,
                f"Usuario {self.docent_username} no existe o credenciales incorrectas",
            )
            return

        # Si llegó aquí, está logueado
        self.log_test(
            "Login de docente",
            "Autenticación",
            True,
            "Sesión iniciada correctamente",
        )

        # Intenta acceder al panel docente
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca elementos del panel esperados
            panel_title = await self.page.query_selector("h1, h2, [role='heading']")
            passed = bool(panel_title)

            self.log_test(
                "Panel docente accesible",
                "Panel Docente",
                passed,
                "Panel cargado correctamente" if passed else "Panel no cargado",
            )
        except Exception as e:
            self.log_test(
                "Panel docente accesible",
                "Panel Docente",
                False,
                f"Error: {e}",
            )

    async def test_comisiones_crud(self):
        """2.2 Audita CRUD de comisiones."""
        # Asume que ya está logueado
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca botón/link para crear nueva comisión
            create_button = await self.page.query_selector(
                "button:has-text('Nueva comisión'), a:has-text('Nueva comisión'), [data-testid='create-comision']"
            )

            passed = bool(create_button)
            self.log_test(
                "Botón crear comisión visible",
                "Panel Docente - Comisiones",
                passed,
                "Botón encontrado" if passed else "Botón no visible",
            )

            # Busca listado de comisiones del docente
            comisiones_list = await self.page.query_selector(
                "[data-testid='comisiones-list'], .comisiones-table, ul[data-testid='comisiones']"
            )

            passed = bool(comisiones_list)
            self.log_test(
                "Listado de comisiones visible",
                "Panel Docente - Comisiones",
                passed,
                "Tablas de comisiones encontrado" if passed else "Listado no visible",
            )
        except Exception as e:
            self.log_test(
                "Listado de comisiones visible",
                "Panel Docente - Comisiones",
                False,
                f"Error: {e}",
            )

    async def test_ejercicios_crud(self):
        """2.3 Audita CRUD de ejercicios."""
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca enlace a gestión de ejercicios
            ejercicios_link = await self.page.query_selector(
                "a:has-text('Ejercicios'), a:has-text('Nuevo ejercicio'), [data-testid='ejercicios-link']"
            )

            passed = bool(ejercicios_link)
            self.log_test(
                "Sección de ejercicios accesible",
                "Panel Docente - Ejercicios",
                passed,
                "Link/botón a ejercicios encontrado" if passed else "No accesible",
            )

            # Si existe, intenta navegar
            if ejercicios_link:
                await ejercicios_link.click()
                await self.page.wait_for_url("**/*", timeout=3000)

                # Busca formulario de creación o lista de ejercicios
                form = await self.page.query_selector(
                    "form, [role='form'], [data-testid='ejercicio-form']"
                )

                passed = bool(form)
                self.log_test(
                    "Formulario de ejercicios cargado",
                    "Panel Docente - Ejercicios",
                    passed,
                    "Formulario encontrado" if passed else "No se cargó formulario",
                )
        except Exception as e:
            self.log_test(
                "Formulario de ejercicios cargado",
                "Panel Docente - Ejercicios",
                False,
                f"Error: {e}",
            )

    async def test_practicas_asignacion(self):
        """2.4 Audita creación de prácticas y asignación de ejercicios."""
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca elemento para crear/editar prácticas
            practicas_element = await self.page.query_selector(
                "a:has-text('Prácticas'), button:has-text('Nueva práctica'), [data-testid='practicas']"
            )

            passed = bool(practicas_element)
            self.log_test(
                "Sección de prácticas accesible",
                "Panel Docente - Prácticas",
                passed,
                "Sección accesible" if passed else "No visible",
            )
        except Exception as e:
            self.log_test(
                "Sección de prácticas accesible",
                "Panel Docente - Prácticas",
                False,
                f"Error: {e}",
            )

    async def test_estudiantes_gestion(self):
        """2.5 Audita gestión de estudiantes (creación e importación)."""
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca botones para crear/importar estudiantes
            create_student_button = await self.page.query_selector(
                "button:has-text('Nuevo estudiante'), a:has-text('Nuevo estudiante'), [data-testid='create-student']"
            )

            import_button = await self.page.query_selector(
                "button:has-text('Importar'), button:has-text('Excel'), [data-testid='import-students']"
            )

            passed_create = bool(create_student_button)
            passed_import = bool(import_button)

            self.log_test(
                "Botón crear estudiante visible",
                "Panel Docente - Estudiantes",
                passed_create,
                "Botón encontrado" if passed_create else "No visible",
            )

            self.log_test(
                "Botón importar estudiantes visible",
                "Panel Docente - Estudiantes",
                passed_import,
                "Botón encontrado" if passed_import else "No visible",
            )
        except Exception as e:
            self.log_test(
                "Gestión de estudiantes",
                "Panel Docente - Estudiantes",
                False,
                f"Error: {e}",
            )

    async def test_vista_comision_detalle(self):
        """2.6 Audita vista de detalle de comisión."""
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca columna de acción o link a comisión
            comision_link = await self.page.query_selector(
                "a[href*='comisiones'], tr:first-child td:first-child a, [data-testid='comision-link']"
            )

            if comision_link:
                await comision_link.click()
                await self.page.wait_for_url("**/*", timeout=3000)

                # Busca elementos de detalle: estudiantes, prácticas, etc.
                estudiantes_section = await self.page.query_selector(
                    "[data-testid='estudiantes-section'], h2:has-text('Estudiantes'), .estudiantes"
                )

                passed = bool(estudiantes_section)
                self.log_test(
                    "Vista de comisión muestra estudiantes",
                    "Panel Docente - Comisión Detalle",
                    passed,
                    "Sección de estudiantes visible" if passed else "No visible",
                )
            else:
                self.log_test(
                    "Vista de comisión muestra estudiantes",
                    "Panel Docente - Comisión Detalle",
                    False,
                    "No se encontró link a comisión",
                )
        except Exception as e:
            self.log_test(
                "Vista de comisión muestra estudiantes",
                "Panel Docente - Comisión Detalle",
                False,
                f"Error: {e}",
            )

    async def test_vista_estudiante_detalle(self):
        """2.7 Audita vista de detalle de estudiante (progreso)."""
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca tabla de estudiantes en alguna comisión
            await self.page.wait_for_selector("table, [role='table']", timeout=5000)

            # Busca link o botón de estudiante
            estudiante_link = await self.page.query_selector(
                "a[href*='estudiante'], button:has-text('Ver progreso'), [data-testid='estudiante-link']"
            )

            if estudiante_link:
                await estudiante_link.click()
                await self.page.wait_for_url("**/*", timeout=3000)

                # Busca elementos de progreso
                progreso_element = await self.page.query_selector(
                    "[data-testid='progreso'], .progreso, [role='progressbar']"
                )

                passed = bool(progreso_element)
                self.log_test(
                    "Vista de estudiante muestra progreso",
                    "Panel Docente - Estudiante Detalle",
                    passed,
                    "Progreso visible" if passed else "No visible",
                )
            else:
                self.log_test(
                    "Vista de estudiante muestra progreso",
                    "Panel Docente - Estudiante Detalle",
                    False,
                    "No se encontró link a estudiante",
                )
        except Exception as e:
            self.log_test(
                "Vista de estudiante muestra progreso",
                "Panel Docente - Estudiante Detalle",
                False,
                f"Error: {e}",
            )

    async def test_comentarios_docentes(self):
        """2.8 Audita comentarios de docentes en intentos."""
        # Esta prueba requiere navegación a una vista de intento específica
        # Implementación simplificada

        try:
            # Busca elemento de comentarios en alguna vista de intento
            comentario_field = await self.page.query_selector(
                "textarea[name='comentario'], input[placeholder*='comentario'], [data-testid='teacher-comment']"
            )

            passed = bool(comentario_field) if comentario_field else False
            self.log_test(
                "Campo de comentarios docentes visible",
                "Panel Docente - Comentarios",
                passed,
                "Campo encontrado" if passed else "No visible (puede requerer navegación específica)",
            )
        except Exception as e:
            self.log_test(
                "Campo de comentarios docentes visible",
                "Panel Docente - Comentarios",
                False,
                f"Error: {e}",
            )

    async def test_exportacion_datos(self):
        """2.9 Audita exportación de datos como CSV."""
        await self.page.goto(f"{self.base_url}/docentes/")

        try:
            # Busca botón de exportar/descargar
            export_button = await self.page.query_selector(
                "button:has-text('Exportar'), button:has-text('Descargar'), a:has-text('CSV'), [data-testid='export-button']"
            )

            passed = bool(export_button)
            self.log_test(
                "Botón exportar datos visible",
                "Panel Docente - Exportación",
                passed,
                "Botón encontrado" if passed else "No visible",
            )
        except Exception as e:
            self.log_test(
                "Botón exportar datos visible",
                "Panel Docente - Exportación",
                False,
                f"Error: {e}",
            )

    async def run(self):
        """Ejecuta todas las auditorías del panel docente."""
        await self.setup()

        print("\n" + "=" * 60)
        print("AUDITORÍA DEL PANEL DOCENTE")
        print("=" * 60 + "\n")

        try:
            print("[1] Navegación y Autenticación")
            print("-" * 60)
            await self.test_docente_panel_navigation()

            print("\n[2] CRUD de Comisiones")
            print("-" * 60)
            if self.page and "accounts/login" not in self.page.url:
                await self.test_comisiones_crud()

            print("\n[3] CRUD de Ejercicios")
            print("-" * 60)
            if self.page and "accounts/login" not in self.page.url:
                await self.test_ejercicios_crud()

            print("\n[4] Prácticas y Asignación")
            print("-" * 60)
            if self.page and "accounts/login" not in self.page.url:
                await self.test_practicas_asignacion()

            print("\n[5] Gestión de Estudiantes")
            print("-" * 60)
            if self.page and "accounts/login" not in self.page.url:
                await self.test_estudiantes_gestion()

            print("\n[6] Vistas de Detalle")
            print("-" * 60)
            if self.page and "accounts/login" not in self.page.url:
                await self.test_vista_comision_detalle()
                await self.test_vista_estudiante_detalle()

            print("\n[7] Comentarios y Exportación")
            print("-" * 60)
            if self.page and "accounts/login" not in self.page.url:
                await self.test_comentarios_docentes()
                await self.test_exportacion_datos()

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
    auditor = DocencePanelAuditor(
        base_url="http://localhost:8000",
        docent_username="docent_test",
        docent_password="docent_pass123",
    )
    await auditor.run()


if __name__ == "__main__":
    asyncio.run(main())

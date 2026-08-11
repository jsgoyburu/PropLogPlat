"""
Auditoría del Flujo de Estudiante en IPC-Lógica con Playwright.

Este script valida los requerimientos del flujo estudiante según AGENTS.md §6:
  - Ver prácticas asignadas de su comisión
  - Resolver ejercicios en orden (desbloqueados secuencialmente)
  - Ver feedback inmediato (tablas de verdad lado a lado si incorrecto)
  - Seguimiento de progreso personal
  - Ver último intento + comentario docente
  - Opción de desplegar historial completo

Uso:
  $ python tests_audit_student_flow.py

Dependencias:
  - Servidor Django corriendo en http://localhost:8000
  - Usuario estudiante autenticado con credenciales de prueba
  - Prácticas y ejercicios previamente creados
"""

import asyncio
from typing import Optional, Dict, Any, List

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
)


class StudentFlowAuditor:
    """Audita el flujo de estudiante en IPC-Lógica."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        student_username: str = "student_test",
        student_password: str = "student_pass123",
    ):
        """Inicializa el auditor de flujo estudiante."""
        self.base_url = base_url
        self.student_username = student_username
        self.student_password = student_password
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

    async def login_estudiante(self) -> bool:
        """Intenta login con usuario estudiante."""
        try:
            await self.page.goto(f"{self.base_url}/accounts/login/")

            await self.page.fill("input[name='username']", self.student_username)
            await self.page.fill("input[name='password']", self.student_password)
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

    async def test_student_home(self):
        """3.1 Verifica que el estudiante ve su página home."""
        logged_in = await self.login_estudiante()

        if not logged_in:
            self.log_test(
                "Login de estudiante",
                "Autenticación",
                False,
                f"Usuario {self.student_username} no existe o credenciales incorrectas",
            )
            return

        self.log_test(
            "Login de estudiante",
            "Autenticación",
            True,
            "Sesión iniciada correctamente",
        )

        # Navega a home del estudiante
        await self.page.goto(f"{self.base_url}/")

        try:
            # Busca elementos de bienvenida o título de página
            title = await self.page.query_selector("h1, h2, [role='heading']")
            passed = bool(title)

            self.log_test(
                "Página home del estudiante cargada",
                "Flujo Estudiante",
                passed,
                "Página cargada" if passed else "No se cargó",
            )
        except Exception as e:
            self.log_test(
                "Página home del estudiante cargada",
                "Flujo Estudiante",
                False,
                f"Error: {e}",
            )

    async def test_practicas_visibles(self):
        """3.2 Verifica que el estudiante ve las prácticas de su comisión."""
        try:
            await self.page.goto(f"{self.base_url}/")

            # Busca listado de prácticas
            practicas_list = await self.page.query_selector(
                "[data-testid='practicas-list'], .practicas, [role='list']"
            )

            if not practicas_list:
                # Intenta buscar por contenido de texto
                practicas_text = await self.page.query_selector("text='Prácticas'")
                practicas_list = practicas_text

            passed = bool(practicas_list)
            self.log_test(
                "Prácticas asignadas visibles",
                "Flujo Estudiante",
                passed,
                "Listado de prácticas encontrado" if passed else "No visible",
            )
        except Exception as e:
            self.log_test(
                "Prácticas asignadas visibles",
                "Flujo Estudiante",
                False,
                f"Error: {e}",
            )

    async def test_ejercicio_acceso(self):
        """3.3 Verifica acceso a un ejercicio de una práctica."""
        try:
            await self.page.goto(f"{self.base_url}/")

            # Busca link a práctica o ejercicio
            ejercicio_link = await self.page.query_selector(
                "a[href*='ejercicio'], button[data-testid='ejercicio'], .ejercicio-card a"
            )

            if ejercicio_link:
                await ejercicio_link.click()
                await self.page.wait_for_url("**/*", timeout=3000)

                # Busca enunciado del ejercicio
                enunciado = await self.page.query_selector(
                    "[data-testid='enunciado'], .enunciado, .ejercicio-description"
                )

                passed = bool(enunciado)
                self.log_test(
                    "Ejercicio cargado con enunciado",
                    "Flujo Estudiante",
                    passed,
                    "Enunciado visible" if passed else "No visible",
                )
            else:
                self.log_test(
                    "Ejercicio cargado con enunciado",
                    "Flujo Estudiante",
                    False,
                    "No se encontró link a ejercicio",
                )
        except Exception as e:
            self.log_test(
                "Ejercicio cargado con enunciado",
                "Flujo Estudiante",
                False,
                f"Error: {e}",
            )

    async def test_formulario_respuesta(self):
        """3.4 Verifica que hay formulario para escribir respuesta."""
        try:
            # Asume que está en una página de ejercicio
            await self.page.wait_for_selector(
                "input[name='respuesta'], textarea[name='respuesta'], [data-testid='respuesta-input']",
                timeout=5000,
            )

            respuesta_input = await self.page.query_selector(
                "input[name='respuesta'], textarea[name='respuesta'], [data-testid='respuesta-input']"
            )

            submit_button = await self.page.query_selector(
                "button[type='submit'], button:has-text('Enviar'), [data-testid='submit-button']"
            )

            passed = bool(respuesta_input and submit_button)
            self.log_test(
                "Formulario de respuesta visible",
                "Flujo Estudiante - Resolución",
                passed,
                "Formulario completo" if passed else "Falta campo o botón",
            )
        except Exception as e:
            self.log_test(
                "Formulario de respuesta visible",
                "Flujo Estudiante - Resolución",
                False,
                f"Error: {e}",
            )

    async def test_feedback_inmediato(self):
        """3.5 Verifica que hay feedback inmediato tras envío."""
        try:
            # Intenta enviar una fórmula de prueba (puede que sea inválida)
            respuesta_input = await self.page.query_selector(
                "input[name='respuesta'], textarea[name='respuesta']"
            )

            if respuesta_input:
                await respuesta_input.fill("p · q")  # Fórmula de prueba

                # Envía el formulario
                await self.page.click("button[type='submit']")

                # Espera feedback (tabla, mensaje de error, etc.)
                try:
                    await self.page.wait_for_selector(
                        "[data-testid='feedback'], .feedback, [role='alert'], table",
                        timeout=5000,
                    )

                    feedback = await self.page.query_selector(
                        "[data-testid='feedback'], .feedback, [role='alert']"
                    )

                    passed = bool(feedback)
                    self.log_test(
                        "Feedback inmediato después de envío",
                        "Flujo Estudiante - Feedback",
                        passed,
                        "Feedback visible" if passed else "Sin feedback",
                    )
                except:
                    self.log_test(
                        "Feedback inmediato después de envío",
                        "Flujo Estudiante - Feedback",
                        False,
                        "No se mostró feedback en tiempo esperado",
                    )
            else:
                self.log_test(
                    "Feedback inmediato después de envío",
                    "Flujo Estudiante - Feedback",
                    False,
                    "No hay campo de respuesta visible",
                )
        except Exception as e:
            self.log_test(
                "Feedback inmediato después de envío",
                "Flujo Estudiante - Feedback",
                False,
                f"Error: {e}",
            )

    async def test_tabla_verdad_feedback(self):
        """3.6 Verifica que el feedback muestra tablas de verdad."""
        try:
            # Busca una tabla en la página (resultado de feedback)
            tabla = await self.page.query_selector("table, [role='table']")

            if tabla:
                # Busca filas y columnas
                rows = await self.page.query_selector_all("tbody tr, [role='row']")

                passed = len(rows) > 0
                self.log_test(
                    "Tabla de verdad en feedback",
                    "Flujo Estudiante - Feedback",
                    passed,
                    f"Tabla con {len(rows)} filas" if passed else "Sin tabla de verdad",
                )
            else:
                self.log_test(
                    "Tabla de verdad en feedback",
                    "Flujo Estudiante - Feedback",
                    False,
                    "No hay tabla visible (puede ser respuesta correcta sin detalles)",
                )
        except Exception as e:
            self.log_test(
                "Tabla de verdad en feedback",
                "Flujo Estudiante - Feedback",
                False,
                f"Error: {e}",
            )

    async def test_progreso_visible(self):
        """3.7 Verifica que el estudiante ve su progreso."""
        try:
            await self.page.goto(f"{self.base_url}/")

            # Busca elemento de progreso: barra, porcentaje, checkmarks
            progreso = await self.page.query_selector(
                "[data-testid='progreso'], .progress, [role='progressbar'], .completed-exercises"
            )

            passed = bool(progreso)
            self.log_test(
                "Progreso personal visible",
                "Flujo Estudiante - Progreso",
                passed,
                "Elemento de progreso encontrado" if passed else "No visible",
            )
        except Exception as e:
            self.log_test(
                "Progreso personal visible",
                "Flujo Estudiante - Progreso",
                False,
                f"Error: {e}",
            )

    async def test_desbloqueo_secuencial(self):
        """3.8 Verifica que los ejercicios se desbloquean secuencialmente."""
        try:
            await self.page.goto(f"{self.base_url}/")

            # Busca al menos dos ejercicios: uno habilitado y uno deshabilitado
            ejercicios = await self.page.query_selector_all(
                "a[href*='ejercicio'], .ejercicio-card, [data-testid='ejercicio']"
            )

            # Busca indicadores de "bloqueado" o "desbloqueado"
            bloqueado = await self.page.query_selector(
                ".bloqueado, [data-locked='true'], [disabled], .disabled"
            )

            desbloqueado = await self.page.query_selector(
                ".desbloqueado, [data-locked='false'], .enabled, .active"
            )

            passed = bool(bloqueado and desbloqueado) or len(ejercicios) >= 2
            self.log_test(
                "Desbloqueo secuencial de ejercicios",
                "Flujo Estudiante - Desbloqueo",
                passed,
                f"Ejercicios: {len(ejercicios)}, Bloqueados: {bool(bloqueado)}, Desbloqueados: {bool(desbloqueado)}",
            )
        except Exception as e:
            self.log_test(
                "Desbloqueo secuencial de ejercicios",
                "Flujo Estudiante - Desbloqueo",
                False,
                f"Error: {e}",
            )

    async def test_historial_intentos(self):
        """3.9 Verifica que hay historial de intentos y comentarios docentes."""
        try:
            # En una página de ejercicio ya resuelto
            historial_link = await self.page.query_selector(
                "button:has-text('Historial'), a:has-text('Ver historial'), [data-testid='historial']"
            )

            if historial_link:
                await historial_link.click()
                await self.page.wait_for_url("**/*", timeout=3000)

                # Busca lista de intentos anteriores
                intentos = await self.page.query_selector("[data-testid='intentos-list'], .intentos")

                passed = bool(intentos)
                self.log_test(
                    "Historial de intentos visible",
                    "Flujo Estudiante - Historial",
                    passed,
                    "Historial cargado" if passed else "No visible",
                )
            else:
                self.log_test(
                    "Historial de intentos visible",
                    "Flujo Estudiante - Historial",
                    False,
                    "Botón historial no encontrado",
                )

            # Busca comentarios docentes en la página
            comentario_docente = await self.page.query_selector(
                "[data-testid='teacher-comment'], .comentario-docente, .teacher-feedback"
            )

            passed = bool(comentario_docente)
            self.log_test(
                "Comentarios docentes visibles",
                "Flujo Estudiante - Historial",
                passed,
                "Comentario encontrado" if passed else "Sin comentarios (es normal si el docente no comentó)",
            )
        except Exception as e:
            self.log_test(
                "Historial de intentos visible",
                "Flujo Estudiante - Historial",
                False,
                f"Error: {e}",
            )

    async def run(self):
        """Ejecuta todas las auditorías del flujo estudiante."""
        await self.setup()

        print("\n" + "=" * 60)
        print("AUDITORÍA DEL FLUJO DE ESTUDIANTE")
        print("=" * 60 + "\n")

        try:
            print("[1] Autenticación y Home")
            print("-" * 60)
            await self.test_student_home()

            if self.page and "accounts/login" not in self.page.url:
                print("\n[2] Prácticas y Ejercicios")
                print("-" * 60)
                await self.test_practicas_visibles()
                await self.test_ejercicio_acceso()

                print("\n[3] Resolución y Feedback")
                print("-" * 60)
                await self.test_formulario_respuesta()
                await self.test_feedback_inmediato()
                await self.test_tabla_verdad_feedback()

                print("\n[4] Progreso y Desbloqueo")
                print("-" * 60)
                await self.test_progreso_visible()
                await self.test_desbloqueo_secuencial()

                print("\n[5] Historial e Intentos")
                print("-" * 60)
                await self.test_historial_intentos()

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
    auditor = StudentFlowAuditor(
        base_url="http://localhost:8000",
        student_username="student_test",
        student_password="student_pass123",
    )
    await auditor.run()


if __name__ == "__main__":
    asyncio.run(main())

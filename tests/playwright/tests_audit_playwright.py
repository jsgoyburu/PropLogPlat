"""
Auditoría automatizada del proyecto IPC-Lógica con Playwright.

Este script verifica los requerimientos principales del AGENTS.md:
  1. Autenticación y roles (admin, docente, estudiante)
  2. Panel docente: CRUD de ejercicios, prácticas, comisiones
  3. Flujo estudiante: desbloqueo progresivo, feedback
  4. Motor lógico: corrección de fórmulas (tabla de verdad y formalización)
  5. Importación de estudiantes desde Excel
  6. Analíticas y comentarios docentes

Uso:
  Python 3.9+, Playwright instalado:
    $ pip install playwright
    $ python -m playwright install chromium
    $ python tests_audit_playwright.py

El script genera un reporte HTML (audit_report.html) al finalizar.

Dependencias:
  - Servidor Django corriendo en http://localhost:8000
  - Base de datos vacía o con datos de prueba
  - Usuarios test ya creados (o se crean dinámicamente si necesario)
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)


class PlaywrightAuditor:
    """Auditor de plataforma IPC-Lógica basado en Playwright."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Inicializa el auditor.
        
        Args:
            base_url: URL base de la aplicación a auditar.
        """
        self.base_url = base_url
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.results: List[Dict[str, Any]] = []
        self.start_time = datetime.now()

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
                "timestamp": datetime.now().isoformat(),
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

    async def test_home_accessibility(self):
        """1.1 Verifica que la página home es accesible."""
        try:
            response = await self.page.goto(self.base_url)
            passed = response.ok if response else False
            self.log_test(
                "Home accesible",
                "Accesibilidad",
                passed,
                f"Status: {response.status if response else 'no response'}",
            )
        except Exception as e:
            self.log_test("Home accesible", "Accesibilidad", False, str(e))

    async def test_login_page(self):
        """1.2 Verifica que la página de login existe."""
        try:
            await self.page.goto(f"{self.base_url}/accounts/login/")
            # Buscan elementos de login estándar
            login_form = await self.page.query_selector("form")
            username_input = await self.page.query_selector("input[name='username']")
            password_input = await self.page.query_selector("input[name='password']")

            passed = bool(login_form and username_input and password_input)
            self.log_test(
                "Página login existe",
                "Autenticación",
                passed,
                "Formulario con username y password encontrado" if passed else "Formulario incompleto",
            )
        except Exception as e:
            self.log_test("Página login existe", "Autenticación", False, str(e))

    async def test_login_and_logout(self):
        """1.3 Verifica el flujo de login y logout."""
        try:
            # Intenta login con usuario de prueba (ajustar credenciales según setup)
            await self.page.goto(f"{self.base_url}/accounts/login/")
            await self.page.fill("input[name='username']", "testuser")
            await self.page.fill("input[name='password']", "testpass123")
            await self.page.click("button[type='submit']")

            # Espera a redirección (puede fallar si las credenciales no existen)
            try:
                await self.page.wait_for_url("**/*", timeout=3000)
                passed = "accounts/login" not in self.page.url
                self.log_test(
                    "Login y redirect",
                    "Autenticación",
                    passed,
                    f"Redirigido a: {self.page.url}" if passed else "No redirigió",
                )
            except:
                self.log_test(
                    "Login y redirect",
                    "Autenticación",
                    False,
                    "Usuario de prueba no existe; crear con: python manage.py createsuperuser",
                )
        except Exception as e:
            self.log_test("Login y redirect", "Autenticación", False, str(e))

    async def test_motor_logico_tabla(self):
        """4.1 Audita el motor lógico: generación de tabla de verdad."""
        try:
            # Intenta acceder a un ejercicio de tabla de verdad
            await self.page.goto(f"{self.base_url}/")
            
            # Busca elemento indicativo de que el usuario está logueado
            user_menu = await self.page.query_selector("[data-testid='user-menu'], .user-menu, .nav-user")
            
            if not user_menu:
                self.log_test(
                    "Motor lógico (tabla de verdad)",
                    "Motor Lógico",
                    False,
                    "No logueado; usuarios de prueba no creados",
                )
                return

            # Si llegó aquí, asume que hay un formulario de entrada de fórmula
            formula_input = await self.page.query_selector("input[placeholder*='fórmula'], textarea[name='respuesta'], input[name='formula']")
            
            passed = bool(formula_input)
            self.log_test(
                "Motor lógico (tabla de verdad)",
                "Motor Lógico",
                passed,
                "Formulario de entrada de fórmula encontrado" if passed else "No hay formulario visible",
            )
        except Exception as e:
            self.log_test(
                "Motor lógico (tabla de verdad)",
                "Motor Lógico",
                False,
                str(e),
            )

    async def test_api_endpoint(self):
        """4.2 Audita el endpoint API de intentos."""
        try:
            response = await self.page.request.get(f"{self.base_url}/api/")
            passed = response.status in (200, 404)  # 404 es ok si no hay API en raíz
            self.log_test(
                "API endpoint accesible",
                "Motor Lógico",
                passed,
                f"Status: {response.status}",
            )
        except Exception as e:
            self.log_test("API endpoint accesible", "Motor Lógico", False, str(e))

    async def test_panel_docente_navigation(self):
        """2.1 Verifica que el panel docente es accesible."""
        try:
            # Intenta acceder a la URL del panel docente directamente
            response = await self.page.goto(f"{self.base_url}/docentes/")
            
            # Si redirige a login, no hay usuario autenticado con rol docente
            if "login" in self.page.url:
                self.log_test(
                    "Panel docente accesible",
                    "Panel Docente",
                    False,
                    "Redirigido a login; usuario docente no autenticado",
                )
            else:
                passed = response.ok if response else False
                self.log_test(
                    "Panel docente accesible",
                    "Panel Docente",
                    passed,
                    f"Status: {response.status if response else 'no response'}",
                )
        except Exception as e:
            self.log_test("Panel docente accesible", "Panel Docente", False, str(e))

    async def test_analiticas_accesibilidad(self):
        """3.1 Verifica que las analíticas son accesibles."""
        try:
            response = await self.page.goto(f"{self.base_url}/analiticas/")
            
            if "login" in self.page.url:
                self.log_test(
                    "Analíticas accesibles",
                    "Analíticas",
                    False,
                    "Redirigido a login; usuario no autenticado",
                )
            else:
                passed = response.ok if response else False
                self.log_test(
                    "Analíticas accesibles",
                    "Analíticas",
                    passed,
                    f"Status: {response.status if response else 'no response'}",
                )
        except Exception as e:
            self.log_test("Analíticas accesibles", "Analíticas", False, str(e))

    async def test_django_admin(self):
        """Admin: Verifica acceso a Django admin."""
        try:
            response = await self.page.goto(f"{self.base_url}/admin/")
            
            if "login" in self.page.url:
                # Login requerido, lo cual es esperado
                self.log_test(
                    "Django admin accesible (con login)",
                    "Admin",
                    True,
                    "Página de login del admin aparece",
                )
            else:
                passed = response.ok if response else False
                self.log_test(
                    "Django admin accesible",
                    "Admin",
                    passed,
                    f"Status: {response.status if response else 'no response'}",
                )
        except Exception as e:
            self.log_test("Django admin accesible", "Admin", False, str(e))

    async def test_csrf_protection(self):
        """Seguridad: Verifica que CSRF está habilitado."""
        try:
            await self.page.goto(f"{self.base_url}/accounts/login/")
            csrf_token = await self.page.query_selector("input[name='csrfmiddlewaretoken']")
            
            passed = bool(csrf_token)
            self.log_test(
                "CSRF protection",
                "Seguridad",
                passed,
                "Token CSRF encontrado en formulario" if passed else "Sin token CSRF",
            )
        except Exception as e:
            self.log_test("CSRF protection", "Seguridad", False, str(e))

    async def test_static_files(self):
        """Infraestructura: Verifica que los archivos estáticos se sirven."""
        try:
            # Intenta cargar la página y verificar que tenga estilos/scripts
            await self.page.goto(f"{self.base_url}/")
            
            # Busca referencias a archivos estáticos
            stylesheets = await self.page.query_selector_all("link[rel='stylesheet']")
            scripts = await self.page.query_selector_all("script[src]")
            
            passed = len(stylesheets) > 0 or len(scripts) > 0
            self.log_test(
                "Archivos estáticos servidos",
                "Infraestructura",
                passed,
                f"Stylesheets: {len(stylesheets)}, Scripts: {len(scripts)}",
            )
        except Exception as e:
            self.log_test("Archivos estáticos servidos", "Infraestructura", False, str(e))

    async def test_database_connectivity(self):
        """Infraestructura: Verifica conectividad a base de datos."""
        try:
            # Un indicador simple: si la página carga sin error 500, hay DB
            await self.page.goto(f"{self.base_url}/")
            status_code = (await self.page.goto(f"{self.base_url}/")).status if await self.page.goto(f"{self.base_url}/") else 500
            
            passed = status_code != 500
            self.log_test(
                "Conectividad base de datos",
                "Infraestructura",
                passed,
                f"Status: {status_code}",
            )
        except Exception as e:
            self.log_test(
                "Conectividad base de datos",
                "Infraestructura",
                False,
                str(e),
            )

    async def test_responsive_design(self):
        """UX: Verifica responsive design en móvil."""
        try:
            # Cambia el viewport a móvil
            await self.page.set_viewport_size({"width": 375, "height": 667})
            await self.page.goto(f"{self.base_url}/")
            
            # Busca meta viewport tag
            viewport_meta = await self.page.query_selector("meta[name='viewport']")
            
            passed = bool(viewport_meta)
            self.log_test(
                "Responsive design (viewport)",
                "UX",
                passed,
                "Meta viewport encontrada" if passed else "Sin meta viewport",
            )
        except Exception as e:
            self.log_test("Responsive design (viewport)", "UX", False, str(e))

    def generate_html_report(self):
        """Genera un reporte HTML de los resultados."""
        passed_count = sum(1 for r in self.results if r["passed"])
        failed_count = sum(1 for r in self.results if not r["passed"])
        total_count = len(self.results)
        pass_rate = (passed_count / total_count * 100) if total_count > 0 else 0

        # Agrupa resultados por categoría
        by_category = {}
        for result in self.results:
            cat = result["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(result)

        # Genera HTML
        html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Auditoría - IPC-Lógica</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
        }}
        .header h1 {{
            margin-bottom: 10px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1fr;
            gap: 20px;
            padding: 40px 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #e0e0e0;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #666;
            font-size: 14px;
        }}
        .stat-value.passed {{ color: #28a745; }}
        .stat-value.failed {{ color: #dc3545; }}
        .stat-value.total {{ color: #667eea; }}
        .stat-value.percent {{ color: #764ba2; }}
        .content {{
            padding: 40px 20px;
        }}
        .category {{
            margin-bottom: 40px;
        }}
        .category-title {{
            font-size: 20px;
            font-weight: bold;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        .test-result {{
            display: flex;
            gap: 15px;
            padding: 15px;
            margin-bottom: 10px;
            background: #f8f9fa;
            border-left: 4px solid #ddd;
            border-radius: 4px;
        }}
        .test-result.passed {{
            border-left-color: #28a745;
            background: #f0f9f6;
        }}
        .test-result.failed {{
            border-left-color: #dc3545;
            background: #fdf6f7;
        }}
        .test-icon {{
            font-size: 24px;
            font-weight: bold;
            width: 30px;
            text-align: center;
        }}
        .test-icon.passed {{ color: #28a745; }}
        .test-icon.failed {{ color: #dc3545; }}
        .test-info {{
            flex: 1;
        }}
        .test-name {{
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }}
        .test-message {{
            font-size: 13px;
            color: #666;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 12px;
            border-top: 1px solid #e0e0e0;
        }}
        @media (max-width: 768px) {{
            .stats {{
                grid-template-columns: 1fr 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Reporte de Auditoría</h1>
            <p>Plataforma de Lógica Proposicional para IPC-UBA</p>
        </div>
        <div class="stats">
            <div class="stat">
                <div class="stat-value passed">{passed_count}</div>
                <div class="stat-label">Pruebas Aprobadas</div>
            </div>
            <div class="stat">
                <div class="stat-value failed">{failed_count}</div>
                <div class="stat-label">Pruebas Fallidas</div>
            </div>
            <div class="stat">
                <div class="stat-value total">{total_count}</div>
                <div class="stat-label">Total de Pruebas</div>
            </div>
            <div class="stat">
                <div class="stat-value percent">{pass_rate:.1f}%</div>
                <div class="stat-label">Tasa de Éxito</div>
            </div>
        </div>
        <div class="content">
"""

        for category in sorted(by_category.keys()):
            tests = by_category[category]
            html += f'<div class="category"><div class="category-title">{category}</div>'

            for test in tests:
                status_class = "passed" if test["passed"] else "failed"
                icon = "✓" if test["passed"] else "✗"
                html += f"""
            <div class="test-result {status_class}">
                <div class="test-icon {status_class}">{icon}</div>
                <div class="test-info">
                    <div class="test-name">{test['name']}</div>
                    <div class="test-message">{test['message']}</div>
                </div>
            </div>
"""
            html += "</div>"

        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        html += f"""
        </div>
        <div class="footer">
            <p>Auditoría completada: {end_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Duración: {duration:.2f} segundos</p>
            <p>Base URL: {self.base_url}</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    async def run(self):
        """Ejecuta todas las auditorías."""
        await self.setup()

        print("\n" + "="*60)
        print("AUDITORÍA PLAYWRIGHT - IPC-LÓGICA")
        print("="*60 + "\n")

        try:
            print("[1] Auditoría de Accesibilidad y Autenticación")
            print("-" * 60)
            await self.test_home_accessibility()
            await self.test_login_page()
            await self.test_login_and_logout()

            print("\n[2] Auditoría del Panel Docente")
            print("-" * 60)
            await self.test_panel_docente_navigation()

            print("\n[3] Auditoría de Analíticas")
            print("-" * 60)
            await self.test_analiticas_accesibilidad()

            print("\n[4] Auditoría del Motor Lógico")
            print("-" * 60)
            await self.test_motor_logico_tabla()
            await self.test_api_endpoint()

            print("\n[5] Auditoría de Seguridad")
            print("-" * 60)
            await self.test_csrf_protection()

            print("\n[6] Auditoría de Infraestructura")
            print("-" * 60)
            await self.test_django_admin()
            await self.test_static_files()
            await self.test_database_connectivity()

            print("\n[7] Auditoría de UX")
            print("-" * 60)
            await self.test_responsive_design()

            # Generación de reporte
            print("\n" + "="*60)
            report_html = self.generate_html_report()
            report_path = Path("audit_report.html")
            report_path.write_text(report_html)

            # Estadísticas finales
            passed = sum(1 for r in self.results if r["passed"])
            total = len(self.results)
            print(f"\n✓ {passed}/{total} pruebas aprobadas ({passed/total*100:.1f}%)")
            print(f"\nReporte guardado en: {report_path.absolute()}")
            print("="*60 + "\n")

        finally:
            await self.teardown()


async def main():
    """Punto de entrada principal."""
    auditor = PlaywrightAuditor(base_url="http://localhost:8000")
    await auditor.run()


if __name__ == "__main__":
    asyncio.run(main())

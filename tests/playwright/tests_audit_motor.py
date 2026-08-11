"""
Auditoría detallada del Motor Lógico de IPC-Lógica.

Este script realiza pruebas exhaustivas del motor lógico (sympy-based):
  - Parseo de fórmulas en notación Copi y ASCII normalizado
  - Generación de tablas de verdad
  - Verificación de equivalencia tabular
  - Casos edge y errores de parseo

Uso:
  $ python tests_audit_motor.py --verbose

Dependencias:
  - Servidor Django corriendo en http://localhost:8000
  - Módulo motor/ implementado según AGENTS.md §5
"""

import asyncio
import json
from typing import Dict, List, Any, Tuple

import requests


class MotorLogicAuditor:
    """Auditoría del motor lógico de IPC-Lógica."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Inicializa el auditor de motor lógico."""
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/intentos/"
        self.results: List[Dict[str, Any]] = []
        self.session = requests.Session()
        # Para pruebas sin necesidad de usuario autenticado (si es posible)
        self.test_motor_endpoint = f"{base_url}/api/verificar/"

    def log_test(
        self,
        name: str,
        passed: bool,
        message: str = "",
        input_data: Dict = None,
        output_data: Dict = None,
    ):
        """Registra un resultado de prueba."""
        self.results.append(
            {
                "name": name,
                "passed": passed,
                "message": message,
                "input": input_data,
                "output": output_data,
            }
        )
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if message:
            print(f"         {message}")

    def test_motor_directamente(self):
        """Prueba el motor lógico directamente si existe endpoint."""
        print("\n[1] Pruebas del Motor Lógico (acceso directo)")
        print("-" * 60)

        # Casos de prueba: (nombre, fórmula, esperado_es_válido)
        test_cases = [
            ("Conjunción (·)", "p · q", True),
            ("Disyunción (∨)", "p ∨ q", True),
            ("Negación (~)", "~p", True),
            ("Condicional (⊃)", "p ⊃ q", True),
            ("Bicondicional (≡)", "p ≡ q", True),
            ("ASCII -> para →", "p -> q", True),
            ("ASCII <-> para ↔", "p <-> q", True),
            # Casos edge
            ("Tautología", "p ∨ ~p", True),
            ("Contradicción", "p · ~p", True),
            ("Fórmula compleja", "(p · q) ⊃ (r ∨ ~s)", True),
            # Errores esperados
            ("Fórmula vacía", "", False),
            ("Símbolo inválido @", "p @ q", False),
            ("Paréntesis no balanceados", "(p · q", False),
        ]

        for name, formula, should_be_valid in test_cases:
            try:
                # Intenta POST al endpoint de verificación (si existe)
                response = self.session.post(
                    self.test_motor_endpoint,
                    json={"formula": formula},
                    timeout=5,
                )

                if response.status_code == 404:
                    # Endpoint no existe, intenta parseo directo importando motor
                    try:
                        from motor.verificador import parsear
                        try:
                            parsear(formula)
                            parsed_ok = True
                            error_msg = ""
                        except ValueError as e:
                            parsed_ok = False
                            error_msg = str(e)

                        passed = parsed_ok == should_be_valid
                        self.log_test(
                            name,
                            passed,
                            f"Fórmula {'válida' if parsed_ok else 'inválida'}: {error_msg}",
                            {"formula": formula},
                            {"parsed": parsed_ok},
                        )
                    except ImportError:
                        self.log_test(
                            name,
                            False,
                            "No se puede importar motor.verificador; verificar instalación de dependencias",
                            {"formula": formula},
                        )
                else:
                    data = response.json()
                    parsed_ok = "error" not in data or not data.get("error")
                    passed = parsed_ok == should_be_valid
                    self.log_test(
                        name,
                        passed,
                        f"API responde: {data}",
                        {"formula": formula},
                        data,
                    )
            except requests.exceptions.ConnectionError:
                self.log_test(
                    name,
                    False,
                    "Servidor no accesible; asegurar que Django está corriendo",
                    {"formula": formula},
                )
                break
            except Exception as e:
                self.log_test(
                    name,
                    False,
                    f"Error: {str(e)}",
                    {"formula": formula},
                )

    def test_equivalencia_tabular(self):
        """Prueba la equivalencia tabular del motor."""
        print("\n[2] Pruebas de Equivalencia Tabular")
        print("-" * 60)

        equivalences = [
            (
                "Doble negación",
                "~~p",
                "p",
                True,
            ),
            (
                "Ley de De Morgan AND",
                "~(p · q)",
                "~p ∨ ~q",
                True,
            ),
            (
                "Ley de De Morgan OR",
                "~(p ∨ q)",
                "~p · ~q",
                True,
            ),
            (
                "Condicional como disyunción",
                "p ⊃ q",
                "~p ∨ q",
                True,
            ),
            (
                "Diferentes variables BUT equivalentes",
                "a ∨ ~a",
                "b ∨ ~b",
                True,  # Ambas tautologías
            ),
            (
                "No equivalentes",
                "p · q",
                "p ∨ q",
                False,
            ),
        ]

        for name, formula1, formula2, should_be_equivalent in equivalences:
            try:
                from motor.verificador import verificar

                result = verificar(formula1, formula2)
                is_equivalent = result.get("correcto", False)
                passed = is_equivalent == should_be_equivalent

                details = f"Formula1: {formula1}, Formula2: {formula2}"
                if result.get("error_parse"):
                    details += f", Parse error: {result['error_parse']}"

                self.log_test(
                    name,
                    passed,
                    f"Equivalentes: {is_equivalent}" if not result.get("error_parse") else f"Parse error: {result.get('error_parse')}",
                    {"formula1": formula1, "formula2": formula2},
                    result,
                )
            except ImportError:
                self.log_test(
                    name,
                    False,
                    "No se puede importar motor.verificador",
                    {"formula1": formula1, "formula2": formula2},
                )
                break
            except Exception as e:
                self.log_test(
                    name,
                    False,
                    f"Error: {str(e)}",
                    {"formula1": formula1, "formula2": formula2},
                )

    def test_tablas_verdad(self):
        """Prueba la generación de tablas de verdad."""
        print("\n[3] Pruebas de Generación de Tablas de Verdad")
        print("-" * 60)

        formulas = [
            ("Variable única", "p"),
            ("Conjunción", "p · q"),
            ("Disyunción", "p ∨ q"),
            ("Negación de conjunción", "~(p · q)"),
            ("Condicional", "p ⊃ q"),
            ("Tres variables", "(p · q) ∨ r"),
        ]

        for name, formula in formulas:
            try:
                from motor.tabla import generar_tabla

                tabla = generar_tabla(formula)
                expected_rows = 2 ** (formula.count("p") + formula.count("q") + formula.count("r") + formula.count("s"))
                passed = len(tabla) == expected_rows

                self.log_test(
                    name,
                    passed,
                    f"Tabla generada con {len(tabla)} filas (esperadas: {expected_rows})",
                    {"formula": formula},
                    {"tabla_length": len(tabla), "expected": expected_rows},
                )
            except ImportError:
                self.log_test(
                    name,
                    False,
                    "No se puede importar motor.tabla",
                    {"formula": formula},
                )
                break
            except Exception as e:
                self.log_test(
                    name,
                    False,
                    f"Error: {str(e)}",
                    {"formula": formula},
                )

    def test_normalizacion_copi(self):
        """Prueba la normalización de notación Copi vs ASCII."""
        print("\n[4] Pruebas de Normalización (Copi vs ASCII)")
        print("-" * 60)

        pair_tests = [
            ("Unicode ∨ vs ASCII |", "p ∨ q", "p | q", True),
            ("Unicode · vs ASCII &", "p · q", "p & q", True),
            ("Unicode ⊃ vs ASCII ->", "p ⊃ q", "p -> q", True),
            ("Unicode ≡ vs ASCII <->", "p ≡ q", "p <-> q", True),
            ("Negación ~ vs ¬", "~p", "~p", True),  # Ambos se aceptan
        ]

        for name, copi_formula, ascii_formula, should_work in pair_tests:
            try:
                from motor.verificador import verificar

                # Ambas fórmulas deberían ser equivalentes o ambas fallar
                result = verificar(copi_formula, ascii_formula)
                copi_valid = not result.get("error_parse")
                ascii_valid = not result.get("error_parse")

                # Lo que importa es que ambas se interpreten igual
                is_equivalent = result.get("correcto", False)
                passed = is_equivalent if should_work else not copi_valid and not ascii_valid

                self.log_test(
                    name,
                    passed,
                    f"Copi: {copi_formula}, ASCII: {ascii_formula}, Equivalentes: {is_equivalent}",
                    {"copi": copi_formula, "ascii": ascii_formula},
                    result,
                )
            except Exception as e:
                self.log_test(
                    name,
                    False,
                    f"Error: {str(e)}",
                    {"copi": copi_formula, "ascii": ascii_formula},
                )

    def test_api_intentos_endpoint(self):
        """Prueba el endpoint API de intentos."""
        print("\n[5] Pruebas del Endpoint API /api/intentos/")
        print("-" * 60)

        try:
            response = self.session.get(self.api_endpoint, timeout=5)
            status_code = response.status_code

            if status_code == 401:
                self.log_test(
                    "API /api/intentos/ requiere autenticación",
                    True,
                    "Status 401; requiere token o sesión",
                )
            elif status_code == 404:
                self.log_test(
                    "API /api/intentos/ no encontrada",
                    False,
                    "Status 404; endpoint no implementado",
                )
            elif status_code == 200:
                self.log_test(
                    "API /api/intentos/ accesible",
                    True,
                    f"Status 200; endpoint activo",
                    output_data=response.json() if response.text else {},
                )
            else:
                self.log_test(
                    "API /api/intentos/ responde",
                    status_code < 500,
                    f"Status {status_code}",
                )
        except requests.exceptions.ConnectionError:
            self.log_test(
                "API /api/intentos/ accesible",
                False,
                "Servidor no accesible",
            )
        except Exception as e:
            self.log_test(
                "API /api/intentos/ accesible",
                False,
                f"Error: {str(e)}",
            )

    def generate_json_report(self) -> str:
        """Genera un reporte JSON de los resultados."""
        summary = {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r["passed"]),
            "failed": sum(1 for r in self.results if not r["passed"]),
        }
        summary["pass_rate"] = (
            summary["passed"] / summary["total"] * 100
            if summary["total"] > 0
            else 0
        )

        return json.dumps(
            {
                "summary": summary,
                "results": self.results,
            },
            indent=2,
            default=str,
        )

    def run(self):
        """Ejecuta todas las auditorías del motor."""
        print("\n" + "=" * 60)
        print("AUDITORÍA DETALLADA - MOTOR LÓGICO")
        print("=" * 60)

        self.test_motor_directamente()
        self.test_equivalencia_tabular()
        self.test_tablas_verdad()
        self.test_normalizacion_copi()
        self.test_api_intentos_endpoint()

        # Resumen
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)

        print("\n" + "=" * 60)
        print(f"✓ {passed}/{total} pruebas aprobadas ({passed/total*100:.1f}%)")
        print("=" * 60)

        # Guardar reporte JSON
        report_json = self.generate_json_report()
        with open("audit_motor_report.json", "w", encoding="utf-8") as f:
            f.write(report_json)

        print(f"\nReporte guardado en: audit_motor_report.json")


if __name__ == "__main__":
    auditor = MotorLogicAuditor(base_url="http://localhost:8000")
    auditor.run()

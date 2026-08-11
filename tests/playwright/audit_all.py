"""
Script maestro de auditoría - Ejecuta todas las auditorías Playwright
e integra resultados en un reporte consolidado.

Uso:
  $ python audit_all.py

O con opciones:
  $ python audit_all.py --headless --server http://localhost:8000
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


class AuditOrchestrator:
    """Orquesta la ejecución de todas las auditorías."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Inicializa el orquestador."""
        self.base_url = base_url
        self.results: Dict[str, Dict[str, Any]] = {}
        self.start_time = datetime.now()

    def run_audit_script(self, script_name: str) -> Dict[str, Any]:
        """Ejecuta un script de auditoría y captura su salida."""
        print(f"\n{'='*70}")
        print(f"  EJECUTANDO: {script_name}")
        print(f"{'='*70}\n")

        try:
            # Ejecuta el script de Python
            result = subprocess.run(
                [sys.executable, script_name],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutos máximo por auditoría
            )

            success = result.returncode == 0

            return {
                "script": script_name,
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "timestamp": datetime.now().isoformat(),
            }

        except subprocess.TimeoutExpired:
            return {
                "script": script_name,
                "success": False,
                "stdout": "",
                "stderr": f"Auditoría excedió tiempo límite (300s)",
                "returncode": -1,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "script": script_name,
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "timestamp": datetime.now().isoformat(),
            }

    def parse_audit_results(self, script_name: str) -> Dict[str, Any]:
        """Intenta parsear resultados JSON si existen."""
        json_files = {
            "tests_audit_motor.py": "audit_motor_report.json",
            "tests_audit_playwright.py": "audit_report.html",  # No es JSON
        }

        json_file = json_files.get(script_name)
        if json_file and Path(json_file).exists():
            try:
                if json_file.endswith('.json'):
                    with open(json_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception as e:
                return {"parse_error": str(e)}

        return {}

    def generate_summary_report(self):
        """Genera un reporte HTML consolidado."""
        total_audits = len(self.results)
        successful_audits = sum(1 for r in self.results.values() if r['success'])
        failed_audits = total_audits - successful_audits

        # Extrae estadísticas de cada auditoría
        stats_by_audit = {}
        for script, result in self.results.items():
            parsed = self.parse_audit_results(script)
            if 'summary' in parsed:
                stats_by_audit[script] = parsed['summary']

        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte Consolidado de Auditoría - IPC-Lógica</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
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
            font-size: 32px;
            margin-bottom: 10px;
        }}
        .header p {{
            font-size: 16px;
            opacity: 0.9;
        }}
        .top-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #e0e0e0;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #667eea;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #666;
            font-size: 13px;
        }}
        .stat-card.success {{
            border-left-color: #28a745;
        }}
        .stat-value.success {{
            color: #28a745;
        }}
        .stat-card.failed {{
            border-left-color: #dc3545;
        }}
        .stat-value.failed {{
            color: #dc3545;
        }}
        .content {{
            padding: 40px 20px;
        }}
        .audit-section {{
            margin-bottom: 40px;
        }}
        .audit-title {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        .audit-result {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ddd;
            margin-bottom: 15px;
        }}
        .audit-result.success {{
            border-left-color: #28a745;
            background: #f0f9f6;
        }}
        .audit-result.failed {{
            border-left-color: #dc3545;
            background: #fdf6f7;
        }}
        .audit-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .audit-name {{
            font-weight: 600;
            color: #333;
        }}
        .audit-status {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }}
        .audit-status.success {{
            background: #d4edda;
            color: #155724;
        }}
        .audit-status.failed {{
            background: #f8d7da;
            color: #721c24;
        }}
        .audit-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 10px;
        }}
        .audit-stat {{
            background: white;
            padding: 10px;
            border-radius: 4px;
            text-align: center;
            font-size: 13px;
        }}
        .audit-stat-value {{
            font-size: 18px;
            font-weight: bold;
            color: #667eea;
        }}
        .audit-stat-label {{
            color: #666;
            font-size: 11px;
            margin-top: 5px;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 30px 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e0e0e0;
        }}
        .footer p {{
            margin: 5px 0;
            font-size: 14px;
        }}
        .timestamp {{
            font-size: 12px;
            color: #999;
        }}
        .details {{
            margin-top: 15px;
            padding: 15px;
            background: white;
            border-radius: 4px;
            border: 1px solid #ddd;
            font-size: 12px;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: 'Courier New', monospace;
        }}
        .warning {{
            color: #ff6b6b;
            font-weight: bold;
        }}
        @media (max-width: 768px) {{
            .top-stats {{
                grid-template-columns: 1fr;
            }}
            .header h1 {{
                font-size: 24px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Auditoría Consolidada</h1>
            <p>Plataforma de Lógica Proposicional para IPC-UBA</p>
        </div>

        <div class="top-stats">
            <div class="stat-card">
                <div class="stat-value">{total_audits}</div>
                <div class="stat-label">Total de Auditorías</div>
            </div>
            <div class="stat-card success">
                <div class="stat-value success">{successful_audits}</div>
                <div class="stat-label">Exitosas</div>
            </div>
            <div class="stat-card failed">
                <div class="stat-value failed">{failed_audits}</div>
                <div class="stat-label">Fallidas</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{duration:.1f}s</div>
                <div class="stat-label">Duración Total</div>
            </div>
        </div>

        <div class="content">
"""

        # Auditorías
        for script, result in self.results.items():
            status_class = "success" if result['success'] else "failed"
            status_text = "✓ Exitosa" if result['success'] else "✗ Fallida"

            html += f"""
            <div class="audit-section">
                <div class="audit-title">{script.replace('tests_audit_', '').replace('.py', '').title()}</div>
                <div class="audit-result {status_class}">
                    <div class="audit-header">
                        <span class="audit-name">{script}</span>
                        <span class="audit-status {status_class}">{status_text}</span>
                    </div>
"""

            # Agrega estadísticas si están disponibles
            if script in stats_by_audit:
                stats = stats_by_audit[script]
                html += f"""
                    <div class="audit-stats">
                        <div class="audit-stat">
                            <div class="audit-stat-value">{stats.get('total', 'N/A')}</div>
                            <div class="audit-stat-label">Pruebas</div>
                        </div>
                        <div class="audit-stat">
                            <div class="audit-stat-value">{stats.get('passed', 'N/A')}</div>
                            <div class="audit-stat-label">Aprobadas</div>
                        </div>
                        <div class="audit-stat">
                            <div class="audit-stat-value">{stats.get('pass_rate', 0):.1f}%</div>
                            <div class="audit-stat-label">Tasa Éxito</div>
                        </div>
                    </div>
"""

            # Muestra detalles de error si falló
            if not result['success'] and result['stderr']:
                error_preview = result['stderr'][:300]
                html += f"""
                    <div class="details">
                        <span class="warning">Error:</span>
                        {error_preview}
                        {'...' if len(result['stderr']) > 300 else ''}
                    </div>
"""

            html += f"""
                    <div style="font-size: 12px; color: #999; margin-top: 10px;">
                        Ejecutado: {result['timestamp']}
                    </div>
                </div>
            </div>
"""

        html += f"""
        </div>

        <div class="footer">
            <p><strong>Auditoría Consolidada completada</strong></p>
            <p>Fecha: {end_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Duración total: {duration:.1f} segundos</p>
            <p class="timestamp">Base URL: {self.base_url}</p>
            <p style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd;">
                Para más detalles, ver los reportes individuales:
                <strong>audit_report.html</strong>, <strong>audit_motor_report.json</strong>, etc.
            </p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def run(self):
        """Ejecuta todas las auditorías."""
        print("\n" + "=" * 70)
        print("AUDITORÍA MAESTRO - IPC-LÓGICA")
        print("=" * 70)
        print(f"\nBase URL: {self.base_url}")
        print(f"Inicio: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Scripts a ejecutar (en orden)
        audit_scripts = [
            "tests_audit_playwright.py",
            "tests_audit_motor.py",
            "tests_audit_docent_panel.py",
            "tests_audit_student_flow.py",
            "tests_audit_excel_import.py",
        ]

        # Ejecuta cada script
        for script in audit_scripts:
            script_path = Path(script)

            if not script_path.exists():
                print(f"\n⚠️  Script no encontrado: {script}")
                self.results[script] = {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Script no encontrado: {script}",
                    "returncode": -1,
                    "timestamp": datetime.now().isoformat(),
                }
                continue

            result = self.run_audit_script(script)
            self.results[script] = result

            # Imprime resumen del resultado
            if result['success']:
                print(f"✓ {script} completada exitosamente")
            else:
                print(f"✗ {script} falló")
                if result['stderr']:
                    print(f"  Error: {result['stderr'][:100]}")

        # Genera reporte consolidado
        print("\n" + "=" * 70)
        print("GENERANDO REPORTE CONSOLIDADO")
        print("=" * 70 + "\n")

        report_html = self.generate_summary_report()
        report_path = Path("audit_consolidated_report.html")
        report_path.write_text(report_html)

        # Resumen final
        successful = sum(1 for r in self.results.values() if r['success'])
        total = len(self.results)

        print(f"\n✓ Auditoría completada")
        print(f"  {successful}/{total} scripts ejecutados exitosamente")
        print(f"  Reporte consolidado: {report_path.absolute()}\n")

        return successful == total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ejecuta todas las auditorías Playwright del proyecto IPC-Lógica"
    )
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="URL base del servidor Django (default: http://localhost:8000)",
    )

    args = parser.parse_args()

    orchestrator = AuditOrchestrator(base_url=args.server)
    success = orchestrator.run()

    sys.exit(0 if success else 1)

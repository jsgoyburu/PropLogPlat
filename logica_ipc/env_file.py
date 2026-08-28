"""Carga mínima y segura de un archivo ``.env`` local.

Los proveedores administrados inyectan variables directamente en el proceso y
siempre tienen precedencia. El archivo existe para instalaciones locales,
contenedores con volumen persistente y servidores autogestionados: el
instalador web puede escribirlo, pero sus valores recién se aplican después de
reiniciar la aplicación.

No se usa una dependencia externa porque el formato que genera PropLogPlat es
deliberadamente pequeño: ``CLAVE="valor JSON"`` y comentarios con ``#``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Carga ``path`` sin sobrescribir variables ya inyectadas por el host.

    Las líneas inválidas se ignoran. Un error de permisos o un archivo ausente
    tampoco debe impedir que Django arranque: la pantalla de diagnóstico del
    instalador explicará después qué falta configurar.
    """

    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, raw_value = line.split('=', 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key or not key.replace('_', '').isalnum() or not key[0].isalpha():
            continue
        if key in os.environ:
            continue

        try:
            value = json.loads(raw_value) if raw_value.startswith('"') else raw_value
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, str):
            os.environ[key] = value

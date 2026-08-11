#!/usr/bin/env bash
# setup.sh — Instalación local en Linux/macOS
# Uso: bash setup.sh

set -e

echo ""
echo "═══════════════════════════════════════════"
echo "  Instalación local — PropLogPlat"
echo "═══════════════════════════════════════════"
echo ""

# 1. Entorno virtual
if [ ! -d ".venv" ]; then
    echo "▶ Creando entorno virtual en .venv/ ..."
    python3 -m venv .venv
else
    echo "✔ Entorno virtual ya existe (.venv/)"
fi

source .venv/bin/activate

# 2. Dependencias
echo "▶ Instalando dependencias de desarrollo ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements-dev.txt
echo "✔ Dependencias instaladas"

# 3. Variables de entorno
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠  Se creó .env a partir de .env.example"
    echo "   Editá SECRET_KEY antes de continuar."
    echo ""
    read -rp "   Presioná Enter para continuar (o Ctrl+C para editar .env primero)..."
fi

export $(grep -v '^#' .env | xargs)

# 4. Migraciones
echo "▶ Ejecutando migraciones ..."
python manage.py migrate --no-input
echo "✔ Migraciones aplicadas"

# 5. Listo
echo ""
echo "═══════════════════════════════════════════"
echo "  ¡Instalación completa!"
echo ""
echo "  Para iniciar el servidor:"
echo "    source .venv/bin/activate"
echo "    python manage.py runserver"
echo ""
echo "  Instalador: http://localhost:8000/accounts/instalar/"
echo "  Usá la SETUP_TOKEN de tu archivo .env."
echo "═══════════════════════════════════════════"
echo ""

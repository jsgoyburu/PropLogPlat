@echo off
REM setup.bat — Instalacion local en Windows
REM Uso: doble click o ejecutar en CMD/PowerShell

echo.
echo ===============================================
echo   Instalacion local -- PropLogPlat
echo ===============================================
echo.

REM 1. Entorno virtual
if not exist ".venv\" (
    echo ^> Creando entorno virtual en .venv\ ...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual.
        echo Asegurate de tener Python 3.10+ instalado y en el PATH.
        pause
        exit /b 1
    )
) else (
    echo [OK] Entorno virtual ya existe ^(.venv^\)
)

call .venv\Scripts\activate.bat

REM 2. Dependencias
echo ^> Instalando dependencias de desarrollo ...
pip install --quiet --upgrade pip
pip install --quiet -r requirements-dev.txt
if errorlevel 1 (
    echo ERROR: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas

REM 3. Variables de entorno
if not exist ".env" (
    copy .env.example .env > nul
    echo.
    echo [!] Se creo .env a partir de .env.example
    echo     Edita SECRET_KEY en el archivo .env antes de continuar.
    echo.
    pause
)

REM Cargar variables de entorno desde .env
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /v "^#" .env`) do (
    if not "%%A"=="" set %%A=%%B
)

REM 4. Migraciones
echo ^> Ejecutando migraciones ...
python manage.py migrate --no-input
if errorlevel 1 (
    echo ERROR: Fallo la migracion.
    pause
    exit /b 1
)
echo [OK] Migraciones aplicadas

REM 5. Listo
echo.
echo ===============================================
echo   ^!Instalacion completa^!
echo.
echo   Para iniciar el servidor:
echo     .venv\Scripts\activate
echo     python manage.py runserver
echo.
echo   Instalador: http://localhost:8000/accounts/instalar/
echo   Usa la SETUP_TOKEN de tu archivo .env.
echo ===============================================
echo.
pause

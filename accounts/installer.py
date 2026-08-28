"""Servicios del instalador web de primera ejecución.

La aplicación no puede modificar de forma universal el panel de variables de
un proveedor externo. Este módulo mantiene esa frontera visible: inspecciona
el proceso actual, genera una configuración portable y solo escribe ``.env``
cuando la persona elige explícitamente el modo autogestionado.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils.translation import gettext


VARIABLES_ENTORNO = (
    ('SECRET_KEY', True, True, 'secret_key'),
    ('SETUP_TOKEN', True, True, 'setup_token'),
    ('DEBUG', True, False, 'debug'),
    ('ALLOWED_HOSTS', True, False, 'allowed_hosts'),
    ('CSRF_TRUSTED_ORIGINS', False, False, 'csrf'),
    ('DATABASE_URL', True, True, 'database_url'),
    ('USE_DATABASE_URL', False, False, 'use_database_url'),
    ('REDIS_URL', False, True, 'redis_url'),
    ('BREVO_API_KEY', False, True, 'brevo'),
    ('EMAIL_HOST', False, False, 'email_host'),
    ('EMAIL_PORT', False, False, 'email_port'),
    ('EMAIL_HOST_USER', False, True, 'email_user'),
    ('EMAIL_HOST_PASSWORD', False, True, 'email_password'),
    ('EMAIL_USE_TLS', False, False, 'email_tls'),
    ('EMAIL_USE_SSL', False, False, 'email_ssl'),
    ('DEFAULT_FROM_EMAIL', False, False, 'from_email'),
    ('TRUSTED_PROXY_COUNT', False, False, 'proxy_count'),
    ('GEMINI_API_KEY', False, True, 'gemini'),
    ('GROQ_API_KEY', False, True, 'groq'),
    ('MCP_TRANSPORT', False, False, 'mcp_transport'),
    ('MCP_ISSUER_URL', False, False, 'mcp_issuer'),
    ('PORT', False, False, 'port'),
    ('ADMIN_USERNAME', False, False, 'admin_username'),
    ('ADMIN_EMAIL', False, False, 'admin_email'),
    ('ADMIN_PASSWORD', False, True, 'admin_password'),
)


def _t(key: str) -> str:
    return gettext(f'installer.{key}')


def _estado(nombre: str, nivel: str, detalle: str, accion: str = '') -> dict:
    return {'nombre': nombre, 'nivel': nivel, 'detalle': detalle, 'accion': accion}


def diagnosticar_entorno(request) -> list[dict]:
    """Devuelve comprobaciones legibles sin exponer valores secretos."""

    resultados = []

    try:
        connection.ensure_connection()
    except Exception as error:  # pragma: no cover - depende del driver/host
        resultados.append(_estado(
            _t('diag.database'), 'error',
            _t('diag.database_error') % {'error': error.__class__.__name__},
            _t('diag.database_action'),
        ))
    else:
        proveedor = 'PostgreSQL' if connection.vendor == 'postgresql' else connection.vendor
        nivel = 'ok' if connection.vendor == 'postgresql' or settings.DEBUG else 'warning'
        detalle = _t('diag.database_ok') % {'vendor': proveedor}
        accion = ''
        if connection.vendor != 'postgresql':
            detalle += ' ' + _t('diag.sqlite_warning')
            accion = _t('diag.sqlite_action')
        resultados.append(_estado(_t('diag.database'), nivel, detalle, accion))

        try:
            executor = MigrationExecutor(connection)
            pendientes = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as error:  # pragma: no cover - corrupción/esquema externo
            resultados.append(_estado(
                _t('diag.migrations'), 'error',
                _t('diag.migrations_error') % {'error': error.__class__.__name__},
                _t('diag.migrations_action'),
            ))
        else:
            if pendientes:
                resultados.append(_estado(
                    _t('diag.migrations'), 'error',
                    _t('diag.migrations_pending') % {'count': len(pendientes)},
                    _t('diag.migrations_reload'),
                ))
            else:
                resultados.append(_estado(_t('diag.migrations'), 'ok', _t('diag.migrations_ok')))

    secret = str(getattr(settings, 'SECRET_KEY', '') or '')
    secret_insegura = (
        len(secret) < 40
        or secret.startswith('cambiar-')
        or secret in {'collectstatic-build-key', 'dev-only-change-me'}
    )
    resultados.append(_estado(
        _t('diag.secret'), 'error' if secret_insegura else 'ok',
        _t('diag.secret_error') if secret_insegura else _t('diag.secret_ok'),
        _t('diag.secret_action') if secret_insegura else '',
    ))

    if settings.DEBUG:
        resultados.append(_estado(
            _t('diag.mode'), 'warning', 'DEBUG=True.', _t('diag.debug_action'),
        ))
    else:
        resultados.append(_estado(_t('diag.mode'), 'ok', _t('diag.production_ok')))

    if settings.SETUP_TOKEN or settings.DEBUG:
        resultados.append(_estado(
            _t('diag.protection'), 'ok',
            _t('diag.token_ok') if settings.SETUP_TOKEN else _t('diag.local_no_token'),
        ))
    else:
        resultados.append(_estado(
            _t('diag.protection'), 'error', _t('diag.token_error'), _t('diag.token_action'),
        ))

    host = request.get_host().split(':', 1)[0]
    host_permitido = '*' in settings.ALLOWED_HOSTS or host in settings.ALLOWED_HOSTS
    resultados.append(_estado(
        _t('diag.domain'), 'ok' if host_permitido else 'error',
        (_t('diag.domain_ok') if host_permitido else _t('diag.domain_error')) % {'host': host},
        '' if host_permitido else _t('diag.domain_action'),
    ))

    if settings.BREVO_API_KEY:
        resultados.append(_estado(_t('diag.email'), 'ok', _t('diag.email_brevo')))
    elif settings.EMAIL_HOST:
        resultados.append(_estado(_t('diag.email'), 'ok', _t('diag.email_smtp')))
    else:
        resultados.append(_estado(
            _t('diag.email'), 'warning', _t('diag.email_warning'), _t('diag.email_action'),
        ))

    if os.environ.get('GEMINI_API_KEY') or os.environ.get('GROQ_API_KEY'):
        resultados.append(_estado(_t('diag.ai'), 'ok', _t('diag.ai_ok')))
    else:
        resultados.append(_estado(
            _t('diag.ai'), 'warning', _t('diag.ai_warning'), _t('diag.ai_action'),
        ))

    env_path = Path(settings.BASE_DIR) / '.env'
    parent = env_path.parent
    escribible = (env_path.exists() and os.access(env_path, os.W_OK)) or (
        not env_path.exists() and os.access(parent, os.W_OK)
    )
    resultados.append(_estado(
        _t('diag.env_file'), 'ok' if escribible else 'warning',
        _t('diag.env_writable') if escribible else _t('diag.env_not_writable'),
        '' if escribible else _t('diag.env_action'),
    ))

    return resultados


def estado_variables() -> list[dict]:
    """Lista completa de variables y si el proceso recibió cada una."""

    estados = []
    for nombre, requerida, secreta, explanation_key in VARIABLES_ENTORNO:
        estados.append({
            'nombre': nombre,
            'requerida': requerida,
            'secreta': secreta,
            'configurada': bool(os.environ.get(nombre)),
            'explicacion': _t(f'var.{explanation_key}'),
        })
    return estados


def valores_entorno(cleaned_data: dict) -> dict[str, str]:
    """Convierte el formulario validado en variables, omitiendo opcionales vacías."""

    values = {
        'SECRET_KEY': cleaned_data['secret_key'],
        'SETUP_TOKEN': cleaned_data['setup_token'],
        'DEBUG': cleaned_data['debug'],
        'ALLOWED_HOSTS': cleaned_data['allowed_hosts'],
        'CSRF_TRUSTED_ORIGINS': cleaned_data.get('csrf_trusted_origins', ''),
        'DATABASE_URL': cleaned_data.get('database_url', ''),
        'USE_DATABASE_URL': cleaned_data.get('use_database_url', 'True'),
        'REDIS_URL': cleaned_data.get('redis_url', ''),
        'DEFAULT_FROM_EMAIL': cleaned_data.get('default_from_email', ''),
        'TRUSTED_PROXY_COUNT': str(cleaned_data.get('trusted_proxy_count', 1)),
        'GEMINI_API_KEY': cleaned_data.get('gemini_api_key', ''),
        'GROQ_API_KEY': cleaned_data.get('groq_api_key', ''),
        'MCP_TRANSPORT': cleaned_data.get('mcp_transport', ''),
        'MCP_ISSUER_URL': cleaned_data.get('mcp_issuer_url', ''),
        'PORT': str(cleaned_data.get('port', 8000)),
        'ADMIN_USERNAME': cleaned_data.get('admin_username', ''),
        'ADMIN_EMAIL': cleaned_data.get('admin_email', ''),
        'ADMIN_PASSWORD': cleaned_data.get('admin_password', ''),
    }

    email_provider = cleaned_data.get('email_provider')
    if email_provider == 'brevo':
        values['BREVO_API_KEY'] = cleaned_data.get('brevo_api_key', '')
    elif email_provider == 'smtp':
        values.update({
            'EMAIL_HOST': cleaned_data.get('email_host', ''),
            'EMAIL_PORT': str(cleaned_data.get('email_port', 587)),
            'EMAIL_HOST_USER': cleaned_data.get('email_host_user', ''),
            'EMAIL_HOST_PASSWORD': cleaned_data.get('email_host_password', ''),
            'EMAIL_USE_TLS': cleaned_data.get('email_use_tls', 'True'),
            'EMAIL_USE_SSL': cleaned_data.get('email_use_ssl', 'False'),
        })

    # El archivo no necesita ruido ni asignaciones vacías. Una variable ya
    # inyectada por el proveedor seguirá teniendo precedencia al reiniciar.
    return {key: str(value) for key, value in values.items() if value not in ('', None)}


def render_env_file(values: dict[str, str], deployment_kind: str) -> str:
    """Genera un ``.env`` portable, sin interpolación accidental del shell."""

    header = [
        '# ' + _t('env_header.generated'),
        '# ' + _t('env_header.profile') % {'profile': deployment_kind},
        '# ' + _t('env_header.secret_warning'),
        '# ' + _t('env_header.managed'),
        '',
    ]
    # Sin comillas exteriores: Docker --env-file conserva comillas en algunas
    # versiones, mientras que nuestro lector, Compose y los paneles aceptan
    # este formato literal. El formulario ya rechaza CR/LF para que cada valor
    # permanezca confinado a una sola asignación.
    lines = [f'{key}={value}' for key, value in values.items()]
    return '\n'.join(header + lines) + '\n'


def write_env_file(content: str) -> Path:
    """Escribe ``.env`` atómicamente y limita permisos cuando el SO lo permite."""

    destination = Path(settings.BASE_DIR) / '.env'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', newline='\n',
            dir=destination.parent, prefix='.env.', suffix='.tmp', delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_name = temporary.name
        try:
            os.chmod(temporary_name, 0o600)
        except OSError:
            pass
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
    return destination

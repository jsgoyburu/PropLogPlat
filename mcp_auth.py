"""OAuth 2.0 Authorization Code + PKCE provider para el servidor MCP de IPC-Lógica.

Flujo:
  1. Claude.ai redirige al usuario a /login con los parámetros OAuth.
  2. El usuario ingresa usuario y contraseña.
  3. Se genera un código de autorización (en memoria, TTL 5 min) y se redirige al cliente.
  4. FastMCP intercambia el código por un access token firmado con HMAC-SHA256.

Los access tokens son auto-verificables (no requieren almacenamiento): sobreviven
reinicios del servicio. Solo los códigos de autorización temporales van a memoria.
"""

import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import time
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

ADMIN_USERNAME = os.environ.get("MCP_ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.environ.get("MCP_ADMIN_PASSWORD", "").strip()

_CLIENT_ID = os.environ.get("MCP_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("MCP_CLIENT_SECRET", "")

# Clave para firmar tokens: usar variable dedicada o caer en la contraseña de admin.
_TOKEN_SECRET = (
    os.environ.get("MCP_TOKEN_SECRET") or ADMIN_PASSWORD or "insecure-fallback"
).encode()

_clients: dict[str, OAuthClientInformationFull] = {}
_auth_codes: dict[str, dict] = {}

# Pre-registrar el cliente al iniciar (no registro dinámico)
if _CLIENT_ID:
    _clients[_CLIENT_ID] = OAuthClientInformationFull(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET or None,
        redirect_uris=["https://claude.ai/api/mcp/auth_callback","https://chatgpt.com/connector/oauth/16PDHNBRP7vM"],
        token_endpoint_auth_method="client_secret_post",
    )

_TOKEN_TTL = 86400 * 30   # 30 días
_CODE_TTL = 300           # 5 minutos


def _make_token(client_id: str, scopes: list[str], expires_at: float) -> str:
    """Crea un token firmado con HMAC-SHA256. No requiere almacenamiento."""
    payload = {"c": client_id, "s": scopes, "e": math.ceil(expires_at)}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.digest(_TOKEN_SECRET, body.encode(), "sha256")
    ).rstrip(b"=").decode()
    return f"{body}.{sig}"


def _parse_token(token: str) -> dict | None:
    """Verifica firma y devuelve el payload, o None si es inválido/expirado."""
    parts = token.split(".")
    if len(parts) != 2:
        return None
    body, sig_str = parts
    expected = base64.urlsafe_b64encode(
        hmac.digest(_TOKEN_SECRET, body.encode(), "sha256")
    ).rstrip(b"=").decode()
    if not hmac.compare_digest(expected, sig_str):
        return None
    try:
        padding = "=" * (-len(body) % 4)
        return json.loads(base64.urlsafe_b64decode(body + padding))
    except Exception:
        return None


class IPCOAuthProvider(OAuthAuthorizationServerProvider):

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return _clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise NotImplementedError("Registro dinámico deshabilitado")

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        qs = urlencode({
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri or ""),
            "state": params.state or "",
            "code_challenge": params.code_challenge or "",
            "code_challenge_method": getattr(params, "code_challenge_method", None) or "S256",
        })
        return f"/login?{qs}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        data = _auth_codes.get(authorization_code)
        if not data or data["expires_at"] < time.time():
            return None
        return AuthorizationCode(
            code=authorization_code,
            client_id=data["client_id"],
            redirect_uri=data["redirect_uri"],
            redirect_uri_provided_explicitly=True,
            expires_at=math.ceil(data["expires_at"]),
            scopes=data.get("scopes", []),
            code_challenge=data.get("code_challenge"),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        _auth_codes.pop(authorization_code.code, None)
        expires_at = time.time() + _TOKEN_TTL
        token = _make_token(client.client_id, authorization_code.scopes or [], expires_at)
        return OAuthToken(
            access_token=token,
            token_type="bearer",
            expires_in=_TOKEN_TTL,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        data = _parse_token(token)
        if not data:
            return None
        expires_at = data.get("e", 0)
        if expires_at < time.time():
            return None
        return AccessToken(
            token=token,
            client_id=data["c"],
            scopes=data.get("s", []),
            expires_at=expires_at,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        raise ValueError("Refresh tokens no soportados")

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
        # Los tokens firmados no necesitan limpieza de almacenamiento.
        _auth_codes.pop(token, None)


async def login_handler(request: Request) -> HTMLResponse | RedirectResponse:
    params = dict(request.query_params)
    error = ""

    if request.method == "POST":
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", "")).strip()

        user_ok = bool(ADMIN_USERNAME) and hmac.compare_digest(username, ADMIN_USERNAME)
        pass_ok = bool(ADMIN_PASSWORD) and hmac.compare_digest(password, ADMIN_PASSWORD)

        if user_ok and pass_ok:
            code = secrets.token_urlsafe(32)
            redirect_uri = params.get("redirect_uri", "")
            _auth_codes[code] = {
                "client_id": params.get("client_id", ""),
                "redirect_uri": redirect_uri,
                "expires_at": time.time() + _CODE_TTL,
                "scopes": ["read"],
                "code_challenge": params.get("code_challenge", ""),
                "code_challenge_method": params.get("code_challenge_method", "S256"),
            }
            sep = "&" if "?" in redirect_uri else "?"
            location = f"{redirect_uri}{sep}code={code}"
            if params.get("state"):
                location += f"&state={params['state']}"
            return RedirectResponse(location, status_code=302)

        error = "Usuario o contraseña incorrectos."

    qs = urlencode(params)
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IPC-Lógica — Acceso MCP</title>
  <style>
    body{{font-family:sans-serif;max-width:360px;margin:80px auto;padding:0 20px;color:#333}}
    h1{{font-size:1.1em;margin-bottom:.4em}}
    p.sub{{font-size:.85em;color:#666;margin-bottom:1.5em}}
    input[type=text],input[type=password]{{width:100%;padding:8px;box-sizing:border-box;margin-bottom:12px;
      border:1px solid #ccc;border-radius:4px;font-size:1em}}
    button{{width:100%;padding:10px;background:#0066cc;color:#fff;border:none;
      border-radius:4px;cursor:pointer;font-size:1em}}
    button:hover{{background:#0052a3}}
    .err{{color:#c00;margin-bottom:12px;font-size:.9em}}
  </style>
</head>
<body>
  <h1>IPC-Lógica · Servidor MCP</h1>
  <p class="sub">Acceso restringido a docentes autorizados.</p>
  {"<p class='err'>" + error + "</p>" if error else ""}
  <form method="post" action="/login?{qs}">
    <input type="text" name="username" placeholder="Usuario" autofocus autocomplete="username">
    <input type="password" name="password" placeholder="Contraseña" autocomplete="current-password">
    <button type="submit">Ingresar</button>
  </form>
</body>
</html>"""
    return HTMLResponse(html)

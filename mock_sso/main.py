"""
MindBridge Mock SSO Server
==========================
Implements OAuth 2.0 authorization_code flow for local development.
Provides test users for every platform role.

Endpoints:
  GET  /health           → Health check
  GET  /authorize        → Show login form (HTML)
  POST /authorize        → Validate credentials, redirect with code
  POST /token            → Exchange code for access_token
  GET  /userinfo         → Return user claims from Bearer token
  GET  /.well-known/openid-configuration → OIDC discovery document
"""

import os
import secrets
import time
import hashlib
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode, urlparse, parse_qs

from fastapi import FastAPI, Form, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MindBridge Mock SSO",
    description="OAuth 2.0 mock for local development",
    version="1.0.0",
)

SSO_CLIENT_ID = os.getenv("SSO_CLIENT_ID", "mental-health-platform")
SSO_CLIENT_SECRET = os.getenv("SSO_CLIENT_SECRET", "dev-secret")
BASE_URL = os.getenv("SSO_BASE_URL", "http://localhost:8080")

# ---------------------------------------------------------------------------
# Test Users
# Each entry: username → {password, role, sub, name, email, ...}
# ---------------------------------------------------------------------------
TEST_USERS: Dict[str, Dict[str, Any]] = {
    "student1": {
        "password": "password",
        "role": "student",
        "sub": "stu-001",
        "name": "Ana García",
        "email": "ana.garcia@udistrital.edu.co",
        "student_id": "20231020001",
        "university": "Universidad Distrital Francisco José de Caldas",
        "faculty": "Ingeniería",
        "program": "Ingeniería de Sistemas",
        "semester": 6,
    },
    "student2": {
        "password": "password",
        "role": "student",
        "sub": "stu-002",
        "name": "Carlos Martínez",
        "email": "carlos.martinez@udistrital.edu.co",
        "student_id": "20231020002",
        "university": "Universidad Distrital Francisco José de Caldas",
        "faculty": "Ciencias y Educación",
        "program": "Licenciatura en Matemáticas",
        "semester": 4,
    },
    "peer1": {
        "password": "password",
        "role": "peer_counselor",
        "sub": "peer-001",
        "name": "Sofía Ramírez",
        "email": "sofia.ramirez@udistrital.edu.co",
        "student_id": "20201020050",
        "university": "Universidad Distrital Francisco José de Caldas",
        "faculty": "Psicología",
        "program": "Psicología",
        "semester": 9,
    },
    "professional1": {
        "password": "password",
        "role": "professional_counselor",
        "sub": "prof-001",
        "name": "Dr. Juliana Torres",
        "email": "juliana.torres@udistrital.edu.co",
        "employee_id": "EMP-1001",
        "university": "Universidad Distrital Francisco José de Caldas",
        "department": "Bienestar Universitario",
        "license_number": "COL-PSY-12345",
    },
    "uniadmin1": {
        "password": "password",
        "role": "university_admin",
        "sub": "uadm-001",
        "name": "Roberto Vargas",
        "email": "roberto.vargas@udistrital.edu.co",
        "employee_id": "EMP-2001",
        "university": "Universidad Distrital Francisco José de Caldas",
        "department": "Vicerrectoría Académica",
    },
    "platadmin1": {
        "password": "password",
        "role": "platform_admin",
        "sub": "padm-001",
        "name": "Lucía Hernández",
        "email": "lucia.hernandez@mindbridge.io",
        "employee_id": "PLAT-001",
    },
}

# ---------------------------------------------------------------------------
# In-memory stores (dev only — resets on restart)
# ---------------------------------------------------------------------------
# auth_code → {user_sub, redirect_uri, scope, expires_at, code_challenge}
_auth_codes: Dict[str, Dict[str, Any]] = {}
# access_token → {user_sub, scope, expires_at}
_access_tokens: Dict[str, Dict[str, Any]] = {}

CODE_TTL = 600       # 10 minutes
TOKEN_TTL = 28800    # 8 hours


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _get_user_by_sub(sub: str) -> Optional[Dict[str, Any]]:
    for udata in TEST_USERS.values():
        if udata["sub"] == sub:
            return udata
    return None


def _build_userinfo(user: Dict[str, Any]) -> Dict[str, Any]:
    """Return OIDC-compatible userinfo claims."""
    info: Dict[str, Any] = {
        "sub": user["sub"],
        "name": user["name"],
        "email": user["email"],
        "email_verified": True,
        "role": user["role"],
    }
    # Include non-sensitive extra claims
    for key in ("student_id", "employee_id", "university", "faculty", "program", "semester", "department"):
        if key in user:
            info[key] = user[key]
    return info


# ---------------------------------------------------------------------------
# HTML Template helpers
# ---------------------------------------------------------------------------
def _login_page(redirect_uri: str, state: str, client_id: str, scope: str, error: str = "") -> str:
    error_html = f'<div class="error">⚠️ {error}</div>' if error else ""
    user_rows = ""
    for username, udata in TEST_USERS.items():
        badge_colors = {
            "student": "#4A90D9",
            "peer_counselor": "#7B68EE",
            "professional_counselor": "#2E8B57",
            "university_admin": "#D4A017",
            "platform_admin": "#C0392B",
        }
        color = badge_colors.get(udata["role"], "#888")
        role_label = udata["role"].replace("_", " ").title()
        user_rows += f"""
        <tr>
          <td><code class="clickable" onclick="setUser('{username}')">{username}</code></td>
          <td><code>password</code></td>
          <td><span class="badge" style="background:{color}">{role_label}</span></td>
          <td>{udata['name']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MindBridge SSO — Sign In</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
           min-height: 100vh; display: flex; align-items: center; justify-content: center;
           padding: 20px; }}
    .container {{ max-width: 860px; width: 100%; }}
    .card {{ background: #fff; border-radius: 16px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.4); }}
    .logo {{ text-align: center; margin-bottom: 24px; }}
    .logo h1 {{ font-size: 2rem; color: #1a1a2e; font-weight: 700; }}
    .logo p {{ color: #666; font-size: 0.9rem; margin-top: 4px; }}
    .dev-banner {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px;
                  padding: 10px 16px; margin-bottom: 24px; font-size: 0.85rem; color: #856404; }}
    .error {{ background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px;
             padding: 10px 16px; margin-bottom: 16px; color: #721c24; font-size: 0.9rem; }}
    .form-group {{ margin-bottom: 16px; }}
    label {{ display: block; font-weight: 600; color: #333; margin-bottom: 6px; font-size: 0.9rem; }}
    input[type=text], input[type=password] {{
      width: 100%; padding: 12px 16px; border: 2px solid #e0e0e0;
      border-radius: 8px; font-size: 1rem; transition: border-color 0.2s;
    }}
    input:focus {{ outline: none; border-color: #4A90D9; }}
    button[type=submit] {{
      width: 100%; padding: 14px; background: #1a1a2e; color: #fff;
      border: none; border-radius: 8px; font-size: 1rem; font-weight: 600;
      cursor: pointer; transition: background 0.2s;
    }}
    button[type=submit]:hover {{ background: #0f3460; }}
    .divider {{ border: none; border-top: 1px solid #eee; margin: 28px 0; }}
    .test-users h3 {{ font-size: 1rem; color: #333; margin-bottom: 12px; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
    th {{ background: #f5f5f5; padding: 10px 12px; text-align: left; color: #666;
         font-weight: 600; border-bottom: 2px solid #e0e0e0; }}
    td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; color: #333; vertical-align: middle; }}
    tr:last-child td {{ border-bottom: none; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px;
             color: #fff; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }}
    code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; }}
    .clickable {{ cursor: pointer; color: #4A90D9; text-decoration: underline; }}
    .clickable:hover {{ color: #0f3460; }}
    .scope-info {{ font-size: 0.8rem; color: #888; margin-top: 4px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="logo">
        <h1>🧠 MindBridge</h1>
        <p>Student Mental Health Support Platform</p>
        <p class="scope-info">Development SSO • Client: <strong>{client_id}</strong> • Scope: {scope}</p>
      </div>

      <div class="dev-banner">
        🔧 <strong>Development Mode</strong> — This is a mock SSO server. Click any username below to auto-fill.
      </div>

      {error_html}

      <form method="POST" action="/authorize">
        <input type="hidden" name="redirect_uri" value="{redirect_uri}">
        <input type="hidden" name="state" value="{state}">
        <input type="hidden" name="client_id" value="{client_id}">
        <input type="hidden" name="scope" value="{scope}">

        <div class="form-group">
          <label for="username">Username</label>
          <input type="text" id="username" name="username" placeholder="e.g. student1" autocomplete="username" required>
        </div>

        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" id="password" name="password" placeholder="password" autocomplete="current-password" required>
        </div>

        <button type="submit">Sign In →</button>
      </form>

      <hr class="divider">

      <div class="test-users">
        <h3>📋 Test Credentials — click username to auto-fill</h3>
        <table>
          <thead>
            <tr><th>Username</th><th>Password</th><th>Role</th><th>Name</th></tr>
          </thead>
          <tbody>
            {user_rows}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    function setUser(username) {{
      document.getElementById('username').value = username;
      document.getElementById('password').value = 'password';
      document.getElementById('username').focus();
    }}
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock_sso", "version": "1.0.0"}


@app.get("/.well-known/openid-configuration")
async def oidc_discovery():
    """OIDC Discovery Document."""
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/authorize",
        "token_endpoint": f"{BASE_URL}/token",
        "userinfo_endpoint": f"{BASE_URL}/userinfo",
        "jwks_uri": f"{BASE_URL}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email", "role"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "claims_supported": ["sub", "name", "email", "email_verified", "role"],
    })


@app.get("/authorize", response_class=HTMLResponse)
async def authorize_get(
    request: Request,
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = "openid profile email",
    state: str = "",
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
):
    """Display the login form."""
    if client_id != SSO_CLIENT_ID:
        raise HTTPException(status_code=400, detail=f"Unknown client_id: {client_id}")
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only response_type=code is supported")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri is required")

    return HTMLResponse(_login_page(redirect_uri, state, client_id, scope))


@app.post("/authorize")
async def authorize_post(
    username: str = Form(...),
    password: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(""),
    client_id: str = Form(...),
    scope: str = Form("openid profile email"),
    code_challenge: Optional[str] = Form(None),
    code_challenge_method: Optional[str] = Form(None),
):
    """Validate credentials and redirect with authorization code."""
    # Validate client
    if client_id != SSO_CLIENT_ID:
        raise HTTPException(status_code=400, detail="Invalid client_id")

    # Validate user credentials
    user = TEST_USERS.get(username)
    if not user or user["password"] != password:
        return HTMLResponse(
            _login_page(redirect_uri, state, client_id, scope, error="Invalid username or password. Try again."),
            status_code=401,
        )

    # Generate authorization code
    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "user_sub": user["sub"],
        "redirect_uri": redirect_uri,
        "scope": scope,
        "client_id": client_id,
        "expires_at": time.time() + CODE_TTL,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }

    # Redirect to callback
    params = {"code": code}
    if state:
        params["state"] = state
    redirect_url = f"{redirect_uri}?{urlencode(params)}"
    return RedirectResponse(url=redirect_url, status_code=302)


@app.post("/token")
async def token(
    grant_type: str = Form(...),
    code: str = Form(None),
    redirect_uri: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    code_verifier: str = Form(None),
    # Support Basic auth header via dependency if needed
):
    """Exchange authorization code for access token."""
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")

    # Validate client credentials
    if client_id != SSO_CLIENT_ID or client_secret != SSO_CLIENT_SECRET:
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    # Look up code
    code_data = _auth_codes.pop(code, None)
    if not code_data:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    if time.time() > code_data["expires_at"]:
        raise HTTPException(status_code=400, detail="Authorization code has expired")

    if code_data["redirect_uri"] != redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")

    # PKCE verification (optional in dev)
    if code_data.get("code_challenge") and code_verifier:
        if code_data["code_challenge_method"] == "S256":
            import base64, hashlib as _hl
            digest = base64.urlsafe_b64encode(_hl.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
            if digest != code_data["code_challenge"]:
                raise HTTPException(status_code=400, detail="code_verifier mismatch")

    # Generate tokens
    access_token = secrets.token_urlsafe(48)
    _access_tokens[access_token] = {
        "user_sub": code_data["user_sub"],
        "scope": code_data["scope"],
        "expires_at": time.time() + TOKEN_TTL,
    }

    user = _get_user_by_sub(code_data["user_sub"])
    id_token_payload = {
        "iss": BASE_URL,
        "sub": code_data["user_sub"],
        "aud": client_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL,
        "name": user["name"] if user else "Unknown",
        "email": user["email"] if user else "",
        "role": user["role"] if user else "",
    }

    # Return token response (id_token is simplified for dev — not a real JWT)
    import base64
    def _b64(d): return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    id_token = f"header.{_b64(id_token_payload)}.mock_signature"

    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL,
        "scope": code_data["scope"],
        "id_token": id_token,
    })


@app.get("/userinfo")
async def userinfo(authorization: Optional[str] = Header(None)):
    """Return OIDC user claims from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token_str = authorization[len("Bearer "):]
    token_data = _access_tokens.get(token_str)

    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid access token")

    if time.time() > token_data["expires_at"]:
        _access_tokens.pop(token_str, None)
        raise HTTPException(status_code=401, detail="Access token has expired")

    user = _get_user_by_sub(token_data["user_sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return JSONResponse(_build_userinfo(user))


@app.get("/")
async def root():
    return JSONResponse({
        "service": "MindBridge Mock SSO",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "authorize": "/authorize",
            "token": "/token",
            "userinfo": "/userinfo",
            "discovery": "/.well-known/openid-configuration",
        },
        "test_users": {uname: udata["role"] for uname, udata in TEST_USERS.items()},
    })

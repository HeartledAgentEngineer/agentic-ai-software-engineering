"""Shared FastAPI helpers for the three Azure apps of this portfolio.

Centralises what all three services need identically:

* client → server authentication with **Entra ID** (OAuth 2.0 bearer JWT, validated
  against the tenant's signing keys: signature, issuer, audience, expiry, scope);
* mapping of ``shared_core`` errors onto HTTP status codes;
* the ``/healthz`` payload — booleans and mode names only, never key material.

Configuration (environment):

``ENTRA_TENANT_ID``      Directory (tenant) ID of the app registration.
``ENTRA_API_AUDIENCE``   Expected ``aud`` claim, e.g. ``api://<api-client-id>`` or the
                         API's client ID (v2 tokens carry the client ID).
``ENTRA_REQUIRED_SCOPE`` Delegated scope (``scp``) or app role (``roles``) the caller must
                         hold; default ``Werkzeuge.Nutzen``.
``AUTH_LOKAL_OFFEN``     Only the exact value ``1`` opens the protected endpoints **when no
                         Entra configuration is present** (local development). Default:
                         closed — without Entra configuration the server answers 503.

AI-102/AI-103 mapping: "Plan and manage an Azure AI solution" (secure the service,
Entra ID authentication, no keys in clients).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Mapping

from fastapi import Header, HTTPException

from shared_core import azure_free_core as core

STANDARD_SCOPE = "Werkzeuge.Nutzen"
ENTRA_AUTHORITY = "https://login.microsoftonline.com"


def entra_konfig(env: Mapping[str, str] | None = None) -> dict[str, str] | None:
    """Entra settings from the environment, or ``None`` when not configured."""
    environment = os.environ if env is None else env
    tenant = (environment.get("ENTRA_TENANT_ID") or "").strip()
    audience = (environment.get("ENTRA_API_AUDIENCE") or "").strip()
    if not tenant or not audience:
        return None
    scope = (environment.get("ENTRA_REQUIRED_SCOPE") or "").strip() or STANDARD_SCOPE
    return {"tenant": tenant, "audience": audience, "scope": scope}


def lokal_offen(env: Mapping[str, str] | None = None) -> bool:
    """True only for ``AUTH_LOKAL_OFFEN=1`` exactly — any other value keeps the guard closed."""
    environment = os.environ if env is None else env
    return (environment.get("AUTH_LOKAL_OFFEN") or "").strip() == "1"


def client_auth_modus(env: Mapping[str, str] | None = None) -> str:
    """``entra`` | ``lokal_offen`` | ``nicht_konfiguriert`` (Entra always wins over the switch)."""
    if entra_konfig(env) is not None:
        return "entra"
    return "lokal_offen" if lokal_offen(env) else "nicht_konfiguriert"


@lru_cache(maxsize=4)
def _jwks_client(tenant: str):
    """Cached JWKS client for the tenant's token-signing keys (fetched lazily, cached by PyJWT)."""
    import jwt

    return jwt.PyJWKClient(f"{ENTRA_AUTHORITY}/{tenant}/discovery/v2.0/keys", cache_keys=True)


def pruefe_entra_token(token: str, konfig: Mapping[str, str]) -> dict[str, Any]:
    """Validate an Entra ID access token (v2) and return its claims.

    Raises ``HTTPException`` 401 for an invalid token, 403 for a valid token
    without the required scope/app role, and 503 when the tenant's signing keys
    cannot be fetched (outage is not the caller's fault — no re-login loop).

    Expects **v2 access tokens** (issuer ``…/<tenant>/v2.0``): the API app
    registration needs ``requestedAccessTokenVersion = 2`` in its manifest.
    """
    import jwt

    try:
        signierschluessel = _jwks_client(konfig["tenant"]).get_signing_key_from_jwt(token)
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=503, detail="Signierschlüssel von Entra ID nicht erreichbar — später erneut versuchen."
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Entra-Token ungültig ({type(exc).__name__}).",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    try:
        claims = jwt.decode(
            token,
            signierschluessel.key,
            algorithms=["RS256"],
            audience=konfig["audience"],
            issuer=f"{ENTRA_AUTHORITY}/{konfig['tenant']}/v2.0",
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Entra-Token ungültig ({type(exc).__name__}).",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    scopes = str(claims.get("scp") or "").split()
    rollen = claims.get("roles") or []
    if konfig["scope"] not in scopes and konfig["scope"] not in rollen:
        raise HTTPException(status_code=403, detail=f"Berechtigung {konfig['scope']!r} fehlt im Token.")
    return claims


async def require_entra_user(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    """FastAPI dependency guarding every endpoint that touches Azure.

    * Entra configured  → bearer JWT required and validated (401/403).
    * not configured    → 503, unless ``AUTH_LOKAL_OFFEN=1`` (local development only).
    """
    konfig = entra_konfig()
    if konfig is None:
        if lokal_offen():
            return None
        raise HTTPException(
            status_code=503,
            detail="Anmeldung nicht konfiguriert: ENTRA_TENANT_ID und ENTRA_API_AUDIENCE setzen "
            "(nur lokal: AUTH_LOKAL_OFFEN=1).",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Entra-Token fehlt (Header: Authorization: Bearer …).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return pruefe_entra_token(authorization.split(" ", 1)[1].strip(), konfig)


def azure_fehler(exc: Exception) -> HTTPException:
    """Map ``shared_core`` failures onto HTTP status codes (503 config, 502 upstream)."""
    if isinstance(exc, core.ConfigurationError):
        return HTTPException(status_code=503, detail=f"Azure-Konfiguration unvollständig: {exc}")
    return HTTPException(status_code=502, detail=f"Azure-Aufruf fehlgeschlagen: {exc}")


def health_payload(service: str, version: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Small health/status document for /healthz — never contains secrets."""
    try:
        auth_modus: str = core.choose_auth_mode("speech")
    except Exception:  # noqa: BLE001 - health must never fail because of config
        auth_modus = "unbekannt"
    payload: dict[str, Any] = {
        "status": "ok",
        "service": service,
        "version": version,
        "auth_modus": auth_modus,
        "azure": {
            "speech_schluessel_gesetzt": bool((os.environ.get("AZURE_SPEECH_KEY") or "").strip()),
            "speech_region": (os.environ.get("AZURE_SPEECH_REGION") or "").strip() or None,
            "vision_endpunkt_gesetzt": bool((os.environ.get("AZURE_VISION_ENDPOINT") or "").strip()),
        },
        "llm_wege_verfuegbar": [p for p in core.PROVIDERS if core.provider_available(p)],
        "client_auth": client_auth_modus(),
    }
    if extra:
        payload.update(extra)
    return payload

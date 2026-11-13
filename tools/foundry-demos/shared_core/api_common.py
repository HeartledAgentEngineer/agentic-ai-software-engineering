"""Shared FastAPI helpers for the three Azure apps of this portfolio.

Centralises what all three services need identically:

* optional demo bearer-token guard (client → server). In an enterprise
  deployment this step is replaced by an Entra ID token plus a role check;
* mapping of ``shared_core`` errors onto HTTP status codes;
* the ``/healthz`` payload — booleans and mode names only, never key material.

AI-102 mapping: "Design and implement a solution architecture" (service
boundaries, auth between components).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Header, HTTPException

from shared_core import azure_free_core as core


def erwarteter_token() -> str | None:
    """Client token from ``PORTFOLIO_API_TOKEN``; ``None`` disables the guard."""
    wert = (os.environ.get("PORTFOLIO_API_TOKEN") or "").strip()
    return wert or None


async def require_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: optional demo bearer token (client → server).

    Enterprise replacement: Entra ID token of the calling user/app, validated
    against the tenant (app registration + JWT check). The Azure side of the
    services itself already supports keyless access via ``DefaultAzureCredential``.
    """
    erwartet = erwarteter_token()
    if erwartet is None:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer-Token fehlt (Header: Authorization).")
    if authorization.split(" ", 1)[1].strip() != erwartet:
        raise HTTPException(status_code=403, detail="Token ungültig.")


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
        "client_token_aktiv": erwarteter_token() is not None,
    }
    if extra:
        payload.update(extra)
    return payload

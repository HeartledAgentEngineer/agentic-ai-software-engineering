"""Entra ID sign-in for the three portfolio clients (MSAL, public client).

The clients hold **no secret and no Azure key**. They sign the user in with the
Microsoft Authentication Library (MSAL) and send the resulting access token as
``Authorization: Bearer …`` to their own FastAPI server, which validates it
(see ``api_common.require_entra_user``).

Configuration (environment of the client):

``ENTRA_TENANT_ID``   Directory (tenant) ID.
``ENTRA_CLIENT_ID``   Client ID of the *public client* app registration.
``ENTRA_API_SCOPE``   Full scope of the API, e.g. ``api://<api-client-id>/Werkzeuge.Nutzen``.

Without this configuration the client sends no token (works only against a
server started with ``AUTH_LOKAL_OFFEN=1``).

Flow: silent token from the local MSAL cache first; only when that fails an
interactive sign-in in the browser (``acquire_token_interactive``). The cache
lives in ``%LOCALAPPDATA%\\azure-portfolio\\msal_cache.bin`` and holds tokens,
never a password.

Deliberately only depends on ``msal`` (no Azure SDK), so a client installation
stays small. This module imports nothing from ``azure_free_core``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping

AUTHORITY = "https://login.microsoftonline.com"


class AnmeldungFehlgeschlagen(RuntimeError):
    """MSAL could not obtain a token (cancelled, wrong configuration, …)."""


def client_konfig(env: Mapping[str, str] | None = None) -> dict[str, str] | None:
    """Client settings, or ``None`` when Entra is not configured on the client."""
    environment = os.environ if env is None else env
    werte = {
        "tenant": (environment.get("ENTRA_TENANT_ID") or "").strip(),
        "client_id": (environment.get("ENTRA_CLIENT_ID") or "").strip(),
        "scope": (environment.get("ENTRA_API_SCOPE") or "").strip(),
    }
    return werte if all(werte.values()) else None


def cache_pfad(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    basis = environment.get("LOCALAPPDATA") or str(Path.home())
    return Path(basis) / "azure-portfolio" / "msal_cache.bin"


def _standard_app_fabrik(konfig: Mapping[str, str], cache: Any):
    import msal

    return msal.PublicClientApplication(
        konfig["client_id"],
        authority=f"{AUTHORITY}/{konfig['tenant']}",
        token_cache=cache,
    )


def hole_token(
    env: Mapping[str, str] | None = None,
    *,
    app_fabrik: Callable[[Mapping[str, str], Any], Any] | None = None,
    cache: Any | None = None,
) -> str | None:
    """Return an access token for the API, or ``None`` if Entra is not configured.

    ``app_fabrik`` and ``cache`` exist for tests (MSAL stand-ins, no network).
    """
    konfig = client_konfig(env)
    if konfig is None:
        return None
    pfad = cache_pfad(env)
    if cache is None:
        import msal

        cache = msal.SerializableTokenCache()
        if pfad.is_file():
            cache.deserialize(pfad.read_text(encoding="utf-8"))
    app = (app_fabrik or _standard_app_fabrik)(konfig, cache)
    scopes = [konfig["scope"]]

    ergebnis = None
    konten = app.get_accounts()
    if konten:
        ergebnis = app.acquire_token_silent(scopes, account=konten[0])
    if not ergebnis:
        ergebnis = app.acquire_token_interactive(scopes)

    if getattr(cache, "has_state_changed", False):
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(cache.serialize(), encoding="utf-8")

    if not ergebnis or "access_token" not in ergebnis:
        grund = (ergebnis or {}).get("error_description") or (ergebnis or {}).get("error") or "unbekannt"
        raise AnmeldungFehlgeschlagen(f"Entra-Anmeldung fehlgeschlagen: {grund}")
    return ergebnis["access_token"]


def auth_kopf(env: Mapping[str, str] | None = None, **kwargs: Any) -> dict[str, str]:
    """HTTP header dict with the bearer token, or ``{}`` without Entra configuration."""
    token = hole_token(env, **kwargs)
    return {"Authorization": f"Bearer {token}"} if token else {}

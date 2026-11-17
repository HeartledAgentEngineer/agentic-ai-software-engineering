"""Entra-ID-Anmeldung Client → Server, offline geprüft.

Die Signierschlüssel des Mandanten werden durch einen selbst erzeugten RSA-Schlüssel
ersetzt (JWKS-Attrappe); es gibt keinen Netzaufruf. Geprüft wird die Server-Seite
(``api_common.require_entra_user``) und der Client-Helfer (``client_auth``, MSAL-Attrappe).
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from ReadFree.server import main as readfree
from TypeFree.server import main as typefree
from shotReader.server import main as shotreader
from shared_core import api_common, client_auth
from shared_core import azure_free_core as core

TENANT = "00000000-0000-0000-0000-00000000test"
AUDIENCE = "api://portfolio-werkzeuge-test"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"

SCHLUESSEL = rsa.generate_private_key(public_exponent=65537, key_size=2048)
FREMDER_SCHLUESSEL = rsa.generate_private_key(public_exponent=65537, key_size=2048)

#: Alle geschützten Endpunkte der drei Server (Methode, Pfad, Anfrage-Argumente).
GESCHUETZT = (
    (typefree.app, "/api/v1/transcribe", {"files": {"audio": ("a.wav", b"RIFF", "audio/wav")}}),
    (typefree.app, "/api/v1/dictate", {"files": {"audio": ("a.wav", b"RIFF", "audio/wav")}}),
    (typefree.app, "/api/v1/smooth", {"json": {"text": "Hallo"}}),
    (readfree.app, "/api/v1/speak", {"json": {"text": "Hallo"}}),
    (shotreader.app, "/api/v1/ocr", {"files": {"bild": ("b.png", b"\x89PNG", "image/png")}}),
    (shotreader.app, "/api/v1/ocr-und-vorlesen", {"files": {"bild": ("b.png", b"\x89PNG", "image/png")}}),
)


def _token(*, schluessel=SCHLUESSEL, aud=AUDIENCE, iss=ISSUER, scp="Werkzeuge.Nutzen", roles=None, exp_in=600):
    jetzt = int(time.time())
    claims = {"aud": aud, "iss": iss, "iat": jetzt, "nbf": jetzt, "exp": jetzt + exp_in, "sub": "test-nutzer"}
    if scp is not None:
        claims["scp"] = scp
    if roles is not None:
        claims["roles"] = roles
    return jwt.encode(claims, schluessel, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture
def entra(monkeypatch):
    """Server mit Entra-Konfiguration; JWKS liefert den öffentlichen Testschlüssel."""
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_API_AUDIENCE", AUDIENCE)
    jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=SCHLUESSEL.public_key()))
    monkeypatch.setattr(api_common, "_jwks_client", lambda tenant: jwks)
    monkeypatch.setattr(core, "speak_text_azure_ssml", lambda ssml, play=False, **kw: b"RIFF" + b"\x00" * 4000)


def _sprechen(token: str | None):
    kopf = {"Authorization": f"Bearer {token}"} if token else {}
    with TestClient(readfree.app) as client:
        return client.post("/api/v1/speak", json={"text": "Hallo"}, headers=kopf)


# ── Server: gültig / ungültig ────────────────────────────────────────────────


def test_gueltiges_token_wird_angenommen(entra):
    assert _sprechen(_token()).status_code == 200


def test_app_rolle_statt_scope_wird_angenommen(entra):
    assert _sprechen(_token(scp=None, roles=["Werkzeuge.Nutzen"])).status_code == 200


def test_fehlendes_token_ist_401(entra):
    antwort = _sprechen(None)
    assert antwort.status_code == 401
    assert antwort.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: _token(aud="api://fremde-api"), id="falsche-zielgruppe"),
        pytest.param(lambda: _token(iss="https://login.microsoftonline.com/fremd/v2.0"), id="falscher-aussteller"),
        pytest.param(lambda: _token(exp_in=-60), id="abgelaufen"),
        pytest.param(lambda: _token(schluessel=FREMDER_SCHLUESSEL), id="falsche-signatur"),
        pytest.param(lambda: "kein.jwt.token", id="kaputt"),
    ],
)
def test_ungueltige_tokens_sind_401(entra, token):
    assert _sprechen(token()).status_code == 401


def test_hs256_mit_oeffentlichem_schluessel_wird_abgelehnt(entra):
    """Algorithmus-Verwechslung: nur RS256 ist erlaubt."""
    gefaelscht = jwt.encode({"aud": AUDIENCE, "iss": ISSUER, "exp": int(time.time()) + 600}, "x" * 32, algorithm="HS256")
    assert _sprechen(gefaelscht).status_code == 401


def test_signierschluessel_nicht_erreichbar_ist_503(entra, monkeypatch):
    """Ausfall des JWKS-Abrufs ist ein Dienstproblem (503), kein ungültiges Token (401)."""

    def weg(token):
        raise jwt.PyJWKClientConnectionError("keine Verbindung")

    monkeypatch.setattr(api_common, "_jwks_client", lambda tenant: SimpleNamespace(get_signing_key_from_jwt=weg))
    assert _sprechen(_token()).status_code == 503


def test_unbekannte_schluessel_kennung_ist_401(entra, monkeypatch):
    def unbekannt(token):
        raise jwt.PyJWKClientError("kid unbekannt")

    monkeypatch.setattr(api_common, "_jwks_client", lambda tenant: SimpleNamespace(get_signing_key_from_jwt=unbekannt))
    assert _sprechen(_token()).status_code == 401


def test_fehlender_scope_ist_403(entra):
    assert _sprechen(_token(scp="Anderes.Recht")).status_code == 403


def test_eigener_scope_ueber_umgebung(entra, monkeypatch):
    monkeypatch.setenv("ENTRA_REQUIRED_SCOPE", "Diktat.Nutzen")
    assert _sprechen(_token()).status_code == 403
    assert _sprechen(_token(scp="Diktat.Nutzen")).status_code == 200


# ── Nebeneingang AUTH_LOKAL_OFFEN (Plan R1-2) ────────────────────────────────


@pytest.mark.parametrize("app,pfad,anfrage", GESCHUETZT)
def test_ohne_konfiguration_alle_geschuetzten_endpunkte_503(app, pfad, anfrage):
    with TestClient(app) as client:
        assert client.post(pfad, **anfrage).status_code == 503


@pytest.mark.parametrize("wert", ["", "0", "true", "ja", " 2 "])
def test_schalter_oeffnet_nur_bei_genau_eins(monkeypatch, wert):
    monkeypatch.setenv("AUTH_LOKAL_OFFEN", wert)
    assert _sprechen(None).status_code == 503


def test_schalter_eins_oeffnet_ohne_entra(monkeypatch):
    monkeypatch.setenv("AUTH_LOKAL_OFFEN", "1")
    monkeypatch.setattr(core, "speak_text_azure_ssml", lambda ssml, play=False, **kw: b"RIFF" + b"\x00" * 4000)
    assert _sprechen(None).status_code == 200


def test_entra_schlaegt_den_schalter(entra, monkeypatch):
    monkeypatch.setenv("AUTH_LOKAL_OFFEN", "1")
    assert _sprechen(None).status_code == 401
    assert _sprechen(_token()).status_code == 200


@pytest.mark.parametrize(
    "umgebung,erwartet",
    [
        ({}, "nicht_konfiguriert"),
        ({"AUTH_LOKAL_OFFEN": "1"}, "lokal_offen"),
        ({"ENTRA_TENANT_ID": TENANT, "ENTRA_API_AUDIENCE": AUDIENCE}, "entra"),
        ({"ENTRA_TENANT_ID": TENANT, "ENTRA_API_AUDIENCE": AUDIENCE, "AUTH_LOKAL_OFFEN": "1"}, "entra"),
    ],
)
def test_healthz_zeigt_anmeldemodus(monkeypatch, umgebung, erwartet):
    for name, wert in umgebung.items():
        monkeypatch.setenv(name, wert)
    with TestClient(readfree.app) as client:
        daten = client.get("/healthz").json()
    assert daten["client_auth"] == erwartet
    assert "PORTFOLIO_API_TOKEN" not in str(daten)


# ── Client: MSAL-Helfer ──────────────────────────────────────────────────────

CLIENT_ENV = {
    "ENTRA_TENANT_ID": TENANT,
    "ENTRA_CLIENT_ID": "11111111-1111-1111-1111-111111111111",
    "ENTRA_API_SCOPE": f"{AUDIENCE}/Werkzeuge.Nutzen",
}


class MsalAttrappe:
    def __init__(self, *, konten=(), still=None, interaktiv=None):
        self.konten = list(konten)
        self.still = still
        self.interaktiv = interaktiv
        self.aufrufe: list[tuple] = []

    def get_accounts(self):
        return self.konten

    def acquire_token_silent(self, scopes, account):
        self.aufrufe.append(("still", tuple(scopes)))
        return self.still

    def acquire_token_interactive(self, scopes):
        self.aufrufe.append(("interaktiv", tuple(scopes)))
        return self.interaktiv


class CacheAttrappe:
    has_state_changed = False


def _kopf(attrappe, env=CLIENT_ENV, tmp_path=None):
    umgebung = dict(env)
    if tmp_path is not None:
        umgebung["LOCALAPPDATA"] = str(tmp_path)
    return client_auth.auth_kopf(umgebung, app_fabrik=lambda konfig, cache: attrappe, cache=CacheAttrappe())


def test_client_ohne_konfiguration_sendet_kein_token():
    assert client_auth.auth_kopf({}) == {}


def test_client_nimmt_token_still_aus_dem_cache(tmp_path):
    attrappe = MsalAttrappe(konten=[{"username": "test"}], still={"access_token": "abc"})
    assert _kopf(attrappe, tmp_path=tmp_path) == {"Authorization": "Bearer abc"}
    assert attrappe.aufrufe == [("still", (CLIENT_ENV["ENTRA_API_SCOPE"],))]


def test_client_meldet_interaktiv_an_wenn_cache_leer(tmp_path):
    attrappe = MsalAttrappe(interaktiv={"access_token": "neu"})
    assert _kopf(attrappe, tmp_path=tmp_path) == {"Authorization": "Bearer neu"}
    assert [art for art, _ in attrappe.aufrufe] == ["interaktiv"]


def test_client_fehlgeschlagene_anmeldung_meldet_grund(tmp_path):
    attrappe = MsalAttrappe(interaktiv={"error": "access_denied", "error_description": "abgebrochen"})
    with pytest.raises(client_auth.AnmeldungFehlgeschlagen, match="abgebrochen"):
        _kopf(attrappe, tmp_path=tmp_path)


def test_client_token_wird_vom_server_angenommen(entra, tmp_path):
    """Ende zu Ende offline: Client-Kopf (MSAL-Attrappe) → Server-Prüfung."""
    kopf = _kopf(MsalAttrappe(interaktiv={"access_token": _token()}), tmp_path=tmp_path)
    with TestClient(readfree.app) as client:
        assert client.post("/api/v1/speak", json={"text": "Hallo"}, headers=kopf).status_code == 200

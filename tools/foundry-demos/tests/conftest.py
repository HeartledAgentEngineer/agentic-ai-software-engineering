"""Gemeinsame Test-Fixtures: Anmelde-Umgebung jedes Tests sauber halten."""

from __future__ import annotations

import socket

import pytest

_AUTH_VARS = (
    "ENTRA_TENANT_ID",
    "ENTRA_API_AUDIENCE",
    "ENTRA_REQUIRED_SCOPE",
    "ENTRA_CLIENT_ID",
    "ENTRA_API_SCOPE",
    "AUTH_LOKAL_OFFEN",
    "AZURE_AUTH_MODE",
)


@pytest.fixture(autouse=True)
def saubere_anmeldeumgebung(monkeypatch):
    """Keine Entra-/Auth-Werte aus der echten Umgebung in die Tests durchlassen."""
    for name in _AUTH_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def lokal_offen(monkeypatch):
    """Server ohne Entra-Konfiguration, ausdrücklich für die lokale Entwicklung geöffnet."""
    monkeypatch.setenv("AUTH_LOKAL_OFFEN", "1")


_LOKAL = {"127.0.0.1", "::1", "localhost", "testserver"}
_ECHT_CONNECT = socket.socket.connect
_ECHT_GETADDRINFO = socket.getaddrinfo


def _ist_lokal(adresse) -> bool:
    host = adresse[0] if isinstance(adresse, tuple) else adresse
    return isinstance(host, str) and host in _LOKAL


@pytest.fixture(autouse=True)
def netzsperre(monkeypatch):
    """Kein Test erreicht das Netz: nur Loopback ist erlaubt (Event-Loop-Sockets unter Windows).

    Azure, Entra und LLM-Anbieter sind in allen Tests Attrappen; ein vergessener echter
    Aufruf scheitert hier sofort statt still Kontingent oder Geld zu verbrauchen.
    """

    def connect(self, adresse):
        if not _ist_lokal(adresse):
            raise RuntimeError(f"Netzsperre: Verbindung zu {adresse!r} in Tests verboten")
        return _ECHT_CONNECT(self, adresse)

    def getaddrinfo(host, *args, **kwargs):
        if host is not None and not _ist_lokal(host):
            raise RuntimeError(f"Netzsperre: Namensauflösung für {host!r} in Tests verboten")
        return _ECHT_GETADDRINFO(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

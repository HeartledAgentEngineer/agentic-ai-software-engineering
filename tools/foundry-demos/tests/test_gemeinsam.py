"""Gemeinsame Offline-Tests aller drei Server (Health) und der Netzsperre der Testumgebung.

Getestet wird das HTTP-Verhalten (Statuscodes, Antwortformen, Anmeldemodus),
nicht Azure selbst; die echten Aufrufe belegt der Live-Smoke-Test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ReadFree.server import main as readfree
from shotReader.server import main as shotreader
from TypeFree.server import main as typefree

# Diese Tests prüfen das Fachverhalten; die Anmeldung prüft tests/test_auth.py.
pytestmark = pytest.mark.usefixtures("lokal_offen")


def test_healthz_aller_drei_dienste():
    for app, name in (
        (typefree.app, "typefree-azure"),
        (readfree.app, "readfree-azure"),
        (shotreader.app, "shotreader-azure"),
    ):
        with TestClient(app) as client:
            antwort = client.get("/healthz")
        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["status"] == "ok"
        assert daten["service"] == name
        assert isinstance(daten["llm_wege_verfuegbar"], list)
        assert daten["client_auth"] == "lokal_offen"


def test_netzsperre_der_testumgebung_greift():
    """Kein Test darf ins Netz: echte Verbindungen scheitern sofort (conftest.netzsperre)."""
    import socket

    with pytest.raises(RuntimeError, match="Netzsperre"):
        socket.create_connection(("login.microsoftonline.com", 443), timeout=1)

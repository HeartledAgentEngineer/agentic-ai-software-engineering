"""Der API-Schluessel darf nicht in der URL stehen: URLs landen in Verlauf und Server-Logs."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.router import auth

SCHLUESSEL = "test-schluessel-123"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "api_key", SCHLUESSEL)
    app = FastAPI()

    @app.get("/api/probe", dependencies=[Depends(auth.require_api_key)])
    def probe():
        return {"ok": True}

    return TestClient(app)


@pytest.mark.parametrize("parameter", ["key", "token"])
def test_schluessel_in_der_url_wird_abgelehnt(client, parameter):
    assert client.get("/api/probe", params={parameter: SCHLUESSEL}).status_code == 401


def test_schluessel_im_header_wird_angenommen(client):
    assert client.get("/api/probe", headers={"x-api-key": SCHLUESSEL}).status_code == 200


def test_ohne_schluessel_wird_abgelehnt(client):
    assert client.get("/api/probe").status_code == 401

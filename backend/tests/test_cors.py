"""CORS preflights: local dev accepts localhost/127.0.0.1 and Cloudflare Quick
Tunnel frontends (demo.ps1); a deployment (ALLOWED_ORIGINS set) accepts only
its exact origins; anything else is still rejected."""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import DEV_ORIGIN_REGEX, app

dev_only = pytest.mark.skipif(get_settings().cors_allowed_origins() is not None, reason="ALLOWED_ORIGINS is set: the app runs in deployment CORS mode")


def _preflight(client: TestClient, path: str, origin: str):
    return client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-user-id"})


@dev_only
@pytest.mark.parametrize("path", ["/company", "/business-context"])
@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3001", "https://random-words-for-test.trycloudflare.com"])
def test_dev_preflight_allows_local_and_quick_tunnel_origins(path, origin):
    response = _preflight(TestClient(app), path, origin)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers


@dev_only
@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example.com",
        "http://abc.trycloudflare.com",  # tunnels are https only
        "https://abc.trycloudflare.com.evil.com",  # full match, not prefix
        "https://trycloudflare.com",
        "http://localhost.evil.com:3000",
    ],
)
def test_dev_preflight_still_rejects_other_origins(origin):
    response = _preflight(TestClient(app), "/company", origin)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_deployment_mode_does_not_accept_quick_tunnels():
    """ALLOWED_ORIGINS set -> exact list, same middleware settings as app.main."""

    deployed = FastAPI()
    deployed.add_middleware(CORSMiddleware, allow_origins=["https://ai-business-os.vercel.app"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    @deployed.get("/company")
    def company() -> dict:
        return {}

    client = TestClient(deployed)
    assert _preflight(client, "/company", "https://ai-business-os.vercel.app").status_code == 200
    assert _preflight(client, "/company", "https://abc.trycloudflare.com").status_code == 400
    assert _preflight(client, "/company", "http://localhost:3000").status_code == 400
    assert "trycloudflare" in DEV_ORIGIN_REGEX  # the tunnel rule lives in the dev regex only

"""
Focused, offline tests for the Phase 1 WhatsApp webhook routes in
src/whatsapp_webhook.py: health, GET verification (correct/incorrect
token, missing configuration), and POST acknowledgement.

These tests never touch Supabase or the real .env file - the verify
token is set per-test with monkeypatch, which only changes the test
process's environment variables.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from src.whatsapp_webhook import app


client = TestClient(app)


def test_health_route_reports_running():
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"


def test_verify_webhook_with_correct_token_returns_challenge(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test-verify-token")

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "12345",
        },
    )

    assert response.status_code == 200
    assert response.text == "12345"


def test_verify_webhook_with_incorrect_token_returns_403(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test-verify-token")

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "12345",
        },
    )

    assert response.status_code == 403


def test_verify_webhook_fails_safely_when_token_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "anything",
            "hub.challenge": "12345",
        },
    )

    assert response.status_code == 403


def test_post_webhook_acknowledges_valid_json():
    response = client.post(
        "/webhooks/whatsapp",
        json={
            "object": "whatsapp_business_account",
            "entry": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_post_webhook_rejects_invalid_json():
    response = client.post(
        "/webhooks/whatsapp",
        content=b"not json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400

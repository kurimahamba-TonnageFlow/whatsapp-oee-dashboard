"""
GET /health/ready and the shared server error log line.

The database call is monkeypatched - no real connection is opened.
"""

import io
import logging
from pathlib import Path
import sys

import psycopg
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import api_logging, readiness_api  # noqa: E402
from src.api import app  # noqa: E402

client = TestClient(app)

SECRET = "postgresql://pulse_user:s3cr3t-p4ssw0rd@db.internal:5432/pulse"


def _capture_log():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    api_logging.logger.addHandler(handler)
    return stream, handler


def test_ready_when_the_database_answers_and_every_migration_is_present(monkeypatch):
    monkeypatch.setattr(
        readiness_api,
        "check_schema_readiness",
        lambda: {"0001": True, "0002": True, "0003": True, "0004": True},
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "missing_migrations": []}


def test_not_ready_names_the_missing_migration(monkeypatch):
    monkeypatch.setattr(
        readiness_api,
        "check_schema_readiness",
        lambda: {"0001": True, "0002": True, "0003": True, "0004": False},
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "ok", "missing_migrations": ["0004"]}


def test_not_ready_when_the_database_is_down_and_nothing_secret_leaks(monkeypatch, capsys):
    def down():
        raise psycopg.OperationalError(f"connection to {SECRET} failed")

    monkeypatch.setattr(readiness_api, "check_schema_readiness", down)
    stream, handler = _capture_log()
    try:
        response = client.get("/health/ready")
    finally:
        api_logging.logger.removeHandler(handler)

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    logged = stream.getvalue()
    assert "area=health operation=readiness" in logged
    assert "error_type=psycopg.OperationalError" in logged
    captured = capsys.readouterr()
    for text in (response.text, logged, captured.out, captured.err):
        assert "s3cr3t" not in text
        assert "db.internal" not in text


def test_liveness_stays_static():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_log_line_carries_type_and_sqlstate_but_never_the_message():
    class FakeUniqueViolation(Exception):
        sqlstate = "23505"

    stream, handler = _capture_log()
    try:
        api_logging.log_operation_failure("hmi_capture", "submit_hourly_update", FakeUniqueViolation(SECRET))
    finally:
        api_logging.logger.removeHandler(handler)

    logged = stream.getvalue()
    assert "DATABASE ERROR area=hmi_capture operation=submit_hourly_update" in logged
    assert "FakeUniqueViolation" in logged
    assert "sqlstate=23505" in logged
    assert "s3cr3t" not in logged


def test_readiness_rejects_missing_latest_task_migration(monkeypatch):
    monkeypatch.setattr(readiness_api,'check_schema_readiness',lambda:{'0004':True,'20261006021758':False})
    response=client.get('/health/ready')
    assert response.status_code==503
    assert response.json()['missing_migrations']==['20261006021758']

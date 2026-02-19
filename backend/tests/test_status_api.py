from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes import router


class FakeMongoDBClient:
    shared_doc: Optional[Dict[str, Any]] = None

    def __init__(self, validate_schema: bool = False):
        self.validate_schema = validate_schema

    def get_bill(self, upload_id: str):
        doc = FakeMongoDBClient.shared_doc
        if doc and str(doc.get("_id")) == upload_id:
            return doc
        return None


def _build_client(monkeypatch, doc: Optional[Dict[str, Any]]) -> TestClient:
    import app.db.mongo_client as mongo_client_module

    FakeMongoDBClient.shared_doc = doc
    monkeypatch.setattr(mongo_client_module, "MongoDBClient", FakeMongoDBClient)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_status_pending_has_null_processing_started(monkeypatch):
    upload_id = "9" * 32
    doc = {
        "_id": upload_id,
        "upload_id": upload_id,
        "status": "PENDING",
        "queue_position": 2,
        "upload_date": "2026-02-16T10:00:00",
    }
    client = _build_client(monkeypatch, doc)
    resp = client.get(f"/status/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["queue_position"] == 2
    assert body["processing_started_at"] is None
    assert body["completed_at"] is None


def test_status_processing_exposes_processing_started(monkeypatch):
    upload_id = "a1" * 16
    doc = {
        "_id": upload_id,
        "upload_id": upload_id,
        "status": "PROCESSING",
        "processing_started_at": "2026-02-16T10:05:00",
    }
    client = _build_client(monkeypatch, doc)
    resp = client.get(f"/status/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PROCESSING"
    assert body["processing_started_at"] == "2026-02-16T10:05:00"


def test_status_completed_but_not_ready_reports_processing(monkeypatch):
    upload_id = "b2" * 16
    doc = {
        "_id": upload_id,
        "upload_id": upload_id,
        "status": "completed",
        "verification_status": "completed",
        "details_ready": False,
    }
    client = _build_client(monkeypatch, doc)
    resp = client.get(f"/status/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PROCESSING"
    assert body["details_ready"] is False
    assert body["processing_stage"] == "FORMAT_RESULT"


def test_status_completed_and_ready_reports_completed(monkeypatch):
    upload_id = "c3" * 16
    doc = {
        "_id": upload_id,
        "upload_id": upload_id,
        "status": "completed",
        "verification_status": "completed",
        "details_ready": True,
    }
    client = _build_client(monkeypatch, doc)
    resp = client.get(f"/status/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["details_ready"] is True
    assert body["processing_stage"] == "DONE"


def test_status_string_false_flag_treated_as_false(monkeypatch):
    upload_id = "d4" * 16
    doc = {
        "_id": upload_id,
        "upload_id": upload_id,
        "status": "completed",
        "verification_status": "completed",
        "details_ready": "0",
        "verification_result_text": "Overall Summary\nTotal Items: 1",
    }
    client = _build_client(monkeypatch, doc)
    resp = client.get(f"/status/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["details_ready"] is False
    assert body["status"] == "PROCESSING"

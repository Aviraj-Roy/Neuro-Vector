from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure `app` package (backend/app) is importable in test runs.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes import router


class FakeMongoDBClient:
    shared_doc: Optional[Dict[str, Any]] = None
    saved_payload: Optional[Dict[str, Any]] = None

    def __init__(self, validate_schema: bool = False):
        self.validate_schema = validate_schema

    def get_bill(self, bill_id: str):
        doc = FakeMongoDBClient.shared_doc
        if doc and str(doc.get("_id")) == bill_id:
            return doc
        return None

    def save_verification_result(
        self,
        upload_id: str,
        verification_result: Dict[str, Any],
        verification_result_text: str,
        format_version: str = "v1",
    ) -> bool:
        FakeMongoDBClient.saved_payload = {
            "upload_id": upload_id,
            "verification_result": verification_result,
            "verification_result_text": verification_result_text,
            "format_version": format_version,
        }
        return True


def _build_client(monkeypatch, doc: Optional[Dict[str, Any]] = None) -> TestClient:
    import app.db.mongo_client as mongo_client_module

    FakeMongoDBClient.shared_doc = doc
    FakeMongoDBClient.saved_payload = None
    monkeypatch.setattr(mongo_client_module, "MongoDBClient", FakeMongoDBClient)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_bill_returns_stored_verification_text(monkeypatch):
    bill_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "verification_result_text": "Overall Summary\nTotal Items: 1",
        "verification_format_version": "v1",
    }
    client = _build_client(monkeypatch, doc)

    resp = client.get(f"/bill/{bill_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["billId"] == bill_id
    assert body["upload_id"] == bill_id
    assert body["status"] == "completed"
    assert body["verificationResult"] == "Overall Summary\nTotal Items: 1"
    assert body["formatVersion"] == "v1"


def test_get_bill_formats_from_structured_verification_result(monkeypatch):
    bill_id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "success",
        "verification_result": {
            "green_count": 1,
            "red_count": 0,
            "unclassified_count": 0,
            "mismatch_count": 0,
            "allowed_not_comparable_count": 0,
            "total_bill_amount": 100.0,
            "total_allowed_amount": 100.0,
            "total_extra_amount": 0.0,
            "total_unclassified_amount": 0.0,
            "results": [
                {
                    "category": "medicines",
                    "items": [
                        {
                            "bill_item": "Paracetamol 500mg",
                            "matched_item": "Paracetamol 500mg",
                            "similarity_score": 0.99,
                            "allowed_amount": 100.0,
                            "bill_amount": 100.0,
                            "extra_amount": 0.0,
                            "status": "green",
                            "diagnostics": {},
                        }
                    ],
                }
            ],
        },
    }
    client = _build_client(monkeypatch, doc)

    resp = client.get(f"/bill/{bill_id}")
    assert resp.status_code == 200
    text = resp.json()["verificationResult"]
    assert "Overall Summary" in text
    assert "Financial Summary" in text
    assert "Category: medicines" in text
    assert "Bill Item: Paracetamol 500mg" in text
    assert "Best Match: Paracetamol 500mg" in text
    assert "Similarity: 99.00%" in text
    assert "Allowed: 100.00" in text
    assert "Billed: 100.00" in text
    assert "Extra: 0.00" in text
    assert "Decision: green" in text
    assert "Reason: Match within allowed limit" in text


def test_get_bill_rebuilds_legacy_text_when_format_not_v1(monkeypatch):
    bill_id = "dddddddddddddddddddddddddddddddd"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "verification_result_text": "LEGACY FREEFORM TEXT",
        "verification_format_version": "legacy",
        "verification_result": {
            "green_count": 1,
            "red_count": 0,
            "unclassified_count": 0,
            "mismatch_count": 0,
            "allowed_not_comparable_count": 0,
            "total_bill_amount": 50.0,
            "total_allowed_amount": 50.0,
            "total_extra_amount": 0.0,
            "total_unclassified_amount": 0.0,
            "results": [
                {
                    "category": "diagnostics",
                    "items": [
                        {
                            "bill_item": "CBC",
                            "matched_item": "CBC",
                            "similarity_score": 0.95,
                            "allowed_amount": 50.0,
                            "bill_amount": 50.0,
                            "extra_amount": 0.0,
                            "status": "green",
                            "diagnostics": {},
                        }
                    ],
                }
            ],
        },
    }
    client = _build_client(monkeypatch, doc)

    resp = client.get(f"/bill/{bill_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["formatVersion"] == "v1"
    assert "Category: diagnostics" in body["verificationResult"]
    assert "Bill Item: CBC" in body["verificationResult"]


def test_verify_persists_formatted_verification_text(monkeypatch):
    bill_id = "cccccccccccccccccccccccccccccccc"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "hospital_name_metadata": "Apollo Hospital",
    }
    client = _build_client(monkeypatch, doc)

    import app.verifier.api as verifier_api_module

    def _fake_verify(upload_id: str, hospital_name: Optional[str] = None):
        assert upload_id == bill_id
        assert hospital_name == "Apollo Hospital"
        return {
            "green_count": 1,
            "red_count": 0,
            "unclassified_count": 0,
            "mismatch_count": 0,
            "allowed_not_comparable_count": 0,
            "total_bill_amount": 10.0,
            "total_allowed_amount": 10.0,
            "total_extra_amount": 0.0,
            "total_unclassified_amount": 0.0,
            "results": [],
        }

    monkeypatch.setattr(verifier_api_module, "verify_bill_from_mongodb_sync", _fake_verify)

    resp = client.post(f"/verify/{bill_id}")
    assert resp.status_code == 200
    assert FakeMongoDBClient.saved_payload is not None
    assert FakeMongoDBClient.saved_payload["upload_id"] == bill_id
    assert FakeMongoDBClient.saved_payload["format_version"] == "v1"
    assert "Overall Summary" in FakeMongoDBClient.saved_payload["verification_result_text"]

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

from app.api.routes import _build_line_items_from_verification, router


class FakeMongoDBClient:
    shared_doc: Optional[Dict[str, Any]] = None
    saved_payload: Optional[Dict[str, Any]] = None
    verification_marked = False

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
        line_items: Optional[list[Dict[str, Any]]] = None,
        format_version: str = "v1",
    ) -> bool:
        FakeMongoDBClient.saved_payload = {
            "upload_id": upload_id,
            "verification_result": verification_result,
            "verification_result_text": verification_result_text,
            "line_items": line_items,
            "format_version": format_version,
        }
        return True

    def mark_verification_processing(self, upload_id: str) -> bool:
        if not FakeMongoDBClient.shared_doc:
            return False
        FakeMongoDBClient.shared_doc["verification_status"] = "processing"
        FakeMongoDBClient.verification_marked = True
        return True

    def mark_verification_failed(self, upload_id: str, error_message: str) -> bool:
        if not FakeMongoDBClient.shared_doc:
            return False
        FakeMongoDBClient.shared_doc["verification_status"] = "failed"
        FakeMongoDBClient.shared_doc["verification_error"] = error_message
        return True

    def save_line_item_edits(
        self,
        upload_id: str,
        line_item_edits: list[Dict[str, Any]],
        line_items: list[Dict[str, Any]],
        edited_at: str,
        edited_by: Optional[str] = None,
    ) -> bool:
        if not FakeMongoDBClient.shared_doc:
            return False
        FakeMongoDBClient.shared_doc["line_item_edits"] = line_item_edits
        FakeMongoDBClient.shared_doc["line_items"] = line_items
        FakeMongoDBClient.shared_doc["line_items_last_edited_at"] = edited_at
        FakeMongoDBClient.shared_doc["line_items_last_edited_by"] = edited_by
        return True


def _build_client(monkeypatch, doc: Optional[Dict[str, Any]] = None) -> TestClient:
    import app.db.mongo_client as mongo_client_module

    FakeMongoDBClient.shared_doc = doc
    FakeMongoDBClient.saved_payload = None
    FakeMongoDBClient.verification_marked = False
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
        "items": {
            "medicines": [
                {
                    "description": "Paracetamol 500mg",
                    "qty": 2,
                    "unit_rate": 50,
                    "final_amount": 100,
                }
            ]
        },
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
    line_items = resp.json()["line_items"]
    assert len(line_items) == 1
    assert line_items[0]["item_name"] == "Paracetamol 500mg"
    assert line_items[0]["bill_item"] == "Paracetamol 500mg"
    assert line_items[0]["best_match"] == "Paracetamol 500mg"
    assert line_items[0]["tieup_rate"] == 50.0
    assert line_items[0]["qty"] == 2.0
    assert line_items[0]["rate"] == 50.0
    assert line_items[0]["billed_amount"] == 100.0
    assert line_items[0]["amount_to_be_paid"] == 100.0
    assert line_items[0]["extra_amount"] == 0.0
    assert line_items[0]["decision"] == "green"


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


def test_get_bill_returns_processing_while_on_demand_verification_runs(monkeypatch):
    bill_id = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "hospital_name_metadata": "Apollo Hospital",
        "verification_result_text": "",
    }
    client = _build_client(monkeypatch, doc)

    resp = client.get(f"/bill/{bill_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "processing"
    assert "Verification is processing" in body["verificationResult"]
    assert FakeMongoDBClient.verification_marked is False


def test_get_bill_returns_failed_when_verification_failed(monkeypatch):
    bill_id = "ffffffffffffffffffffffffffffffff"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "verification_status": "failed",
        "verification_result_text": "",
    }
    client = _build_client(monkeypatch, doc)

    resp = client.get(f"/bill/{bill_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "Verification failed" in body["verificationResult"]


def test_build_line_items_maps_all_new_fields():
    doc = {
        "items": {
            "medicines": [
                {
                    "description": "Amoxicillin 500mg",
                    "qty": "3",
                    "unit_rate": "Rs. 12.00",
                    "final_amount": "Rs. 36.00",
                    "amount_to_be_paid": "Rs. 30.00",
                }
            ]
        }
    }
    verification_result = {
        "results": [
            {
                "category": "medicines",
                "items": [
                    {
                        "bill_item": "Amoxicillin 500mg",
                        "matched_item": "Amoxicillin Capsule 500mg",
                        "bill_amount": "Rs. 36.00",
                        "allowed_amount": 33.0,
                        "extra_amount": "Rs. 6.00",
                        "status": "RED",
                    }
                ],
            }
        ]
    }

    line_items = _build_line_items_from_verification(doc, verification_result)
    assert len(line_items) == 1
    item = line_items[0]
    assert item["item_name"] == "Amoxicillin 500mg"
    assert item["bill_item"] == "Amoxicillin 500mg"
    assert item["best_match"] == "Amoxicillin Capsule 500mg"
    assert item["tieup_rate"] == 11.0
    assert item["qty"] == 3.0
    assert item["rate"] == 12.0
    assert item["billed_amount"] == 36.0
    assert item["amount_to_be_paid"] == 30.0
    assert item["extra_amount"] == 6.0
    assert item["decision"] == "red"


def test_get_bill_line_items_missing_qty_rate_tieup_regression(monkeypatch):
    bill_id = "11111111111111111111111111111111"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "verification_result_text": "",
        "verification_format_version": "legacy",
        "verification_result": {
            "green_count": 0,
            "red_count": 0,
            "unclassified_count": 1,
            "mismatch_count": 0,
            "allowed_not_comparable_count": 0,
            "total_bill_amount": 75.0,
            "total_allowed_amount": 0.0,
            "total_extra_amount": 0.0,
            "total_unclassified_amount": 75.0,
            "results": [
                {
                    "category": "tests",
                    "items": [
                        {
                            "bill_item": "Special Test",
                            "matched_item": None,
                            "bill_amount": "75.00",
                            "status": "UNCLASSIFIED",
                        }
                    ],
                }
            ],
        },
    }
    client = _build_client(monkeypatch, doc)

    resp = client.get(f"/bill/{bill_id}")
    assert resp.status_code == 200
    item = resp.json()["line_items"][0]
    assert item["item_name"] == "Special Test"
    assert item["qty"] is None
    assert item["rate"] is None
    assert item["tieup_rate"] is None
    assert item["amount_to_be_paid"] is None
    assert item["billed_amount"] == 75.0


def test_patch_line_items_success_and_get_reflects_edits(monkeypatch):
    bill_id = "22222222222222222222222222222222"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "verification_result_text": "Overall Summary\nTotal Items: 2",
        "verification_format_version": "v1",
        "verification_result": {
            "green_count": 2,
            "red_count": 0,
            "unclassified_count": 0,
            "mismatch_count": 0,
            "allowed_not_comparable_count": 0,
            "total_bill_amount": 200.0,
            "total_allowed_amount": 200.0,
            "total_extra_amount": 0.0,
            "total_unclassified_amount": 0.0,
            "results": [
                {
                    "category": "medicines",
                    "items": [
                        {
                            "bill_item": "Drug A",
                            "matched_item": "Drug A Tieup",
                            "allowed_amount": 100.0,
                            "bill_amount": 100.0,
                            "extra_amount": 0.0,
                            "status": "GREEN",
                        },
                        {
                            "bill_item": "Drug B",
                            "matched_item": "Drug B Tieup",
                            "allowed_amount": 100.0,
                            "bill_amount": 100.0,
                            "extra_amount": 0.0,
                            "status": "GREEN",
                        },
                    ],
                }
            ],
        },
    }
    client = _build_client(monkeypatch, doc)

    patch_resp = client.patch(
        f"/bill/{bill_id}/line-items",
        json={
            "line_items": [
                {
                    "category_name": "medicines",
                    "item_index": 0,
                    "qty": 2,
                    "rate": 150.5,
                }
            ],
            "edited_by": "qa.user",
        },
    )
    assert patch_resp.status_code == 200
    patched_item = patch_resp.json()["line_items"][0]
    assert patched_item["qty"] == 2.0
    assert patched_item["rate"] == 150.5
    assert patched_item["billed_amount"] == 301.0
    assert patched_item["amount_to_be_paid"] == 100.0
    assert FakeMongoDBClient.shared_doc["line_item_edits"][0]["edited_by"] == "qa.user"

    get_resp = client.get(f"/bill/{bill_id}")
    assert get_resp.status_code == 200
    item = get_resp.json()["line_items"][0]
    assert item["qty"] == 2.0
    assert item["rate"] == 150.5
    assert item["billed_amount"] == 301.0
    assert item["amount_to_be_paid"] == 100.0


def test_patch_line_items_rejects_bad_index(monkeypatch):
    bill_id = "33333333333333333333333333333333"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "verification_result": {
            "results": [
                {
                    "category": "services",
                    "items": [{"bill_item": "Consultation", "bill_amount": 50.0, "status": "GREEN"}],
                }
            ]
        },
    }
    client = _build_client(monkeypatch, doc)

    resp = client.patch(
        f"/bill/{bill_id}/line-items",
        json={
            "line_items": [{"category_name": "services", "item_index": 2, "qty": 1, "rate": 50}],
        },
    )
    assert resp.status_code == 400
    assert "Invalid item_index" in resp.json()["detail"]


def test_get_bill_without_edits_keeps_original_values(monkeypatch):
    bill_id = "44444444444444444444444444444444"
    doc = {
        "_id": bill_id,
        "upload_id": bill_id,
        "status": "completed",
        "verification_result_text": "Overall Summary\nTotal Items: 1",
        "verification_format_version": "v1",
        "verification_result": {
            "results": [
                {
                    "category": "tests",
                    "items": [
                        {
                            "bill_item": "CBC",
                            "matched_item": "CBC",
                            "allowed_amount": 80.0,
                            "bill_amount": 80.0,
                            "extra_amount": 0.0,
                            "status": "GREEN",
                        }
                    ],
                }
            ]
        },
    }
    client = _build_client(monkeypatch, doc)
    resp = client.get(f"/bill/{bill_id}")
    assert resp.status_code == 200
    item = resp.json()["line_items"][0]
    assert item["qty"] is None
    assert item["rate"] is None
    assert item["billed_amount"] == 80.0
    assert item["amount_to_be_paid"] == 80.0

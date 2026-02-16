from __future__ import annotations

import asyncio
import io
from pathlib import Path
import sys
from typing import Any, Dict, Optional

from fastapi import UploadFile

# Ensure `app` package (backend/app) is importable in test runs.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.upload_pipeline import handle_pdf_upload


class FakeMongoDBClient:
    docs_by_upload_id: Dict[str, Dict[str, Any]] = {}
    docs_by_request_id: Dict[str, Dict[str, Any]] = {}
    create_calls = 0

    def __init__(self, validate_schema: bool = False):
        self.validate_schema = validate_schema

    def get_bill_by_request_id(self, ingestion_request_id: str) -> Optional[Dict[str, Any]]:
        return FakeMongoDBClient.docs_by_request_id.get(ingestion_request_id)

    def create_upload_record(
        self,
        *,
        upload_id: str,
        original_filename: str,
        file_size_bytes: int,
        hospital_name: str,
        employee_id: str,
        invoice_date: Optional[str] = None,
        source_pdf: Optional[str] = None,
        ingestion_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        FakeMongoDBClient.create_calls += 1
        doc = {
            "_id": upload_id,
            "upload_id": upload_id,
            "status": "PENDING",
            "queue_position": 1,
            "employee_id": employee_id,
            "hospital_name": hospital_name,
            "original_filename": original_filename,
            "file_size_bytes": file_size_bytes,
            "upload_date": "2026-02-14T12:00:00",
        }
        if invoice_date:
            doc["invoice_date"] = invoice_date
        if ingestion_request_id:
            doc["ingestion_request_id"] = ingestion_request_id
            FakeMongoDBClient.docs_by_request_id[ingestion_request_id] = doc
        FakeMongoDBClient.docs_by_upload_id[upload_id] = doc
        return {"upload_id": upload_id, "created": True, "status": "PENDING"}

    def enqueue_upload_job(self, *, upload_id: str, temp_pdf_path: str, hospital_name: str, original_filename: str):
        doc = FakeMongoDBClient.docs_by_upload_id.get(upload_id)
        if not doc:
            return False
        doc["status"] = "PENDING"
        doc["temp_pdf_path"] = temp_pdf_path
        doc["queue_hospital_name"] = hospital_name
        doc["queue_original_filename"] = original_filename
        doc["queue_position"] = doc.get("queue_position") or 1
        return True

    def get_bill(self, upload_id: str) -> Optional[Dict[str, Any]]:
        return FakeMongoDBClient.docs_by_upload_id.get(upload_id)


class FakeThread:
    started = 0

    def __init__(self, target=None, kwargs=None, daemon=None, name=None):
        self.target = target
        self.kwargs = kwargs or {}

    def start(self):
        FakeThread.started += 1


def _make_upload_file() -> UploadFile:
    return UploadFile(filename="bill.pdf", file=io.BytesIO(b"%PDF-1.4 test"))


def test_upload_pipeline_returns_uploaded_and_starts_background(monkeypatch, tmp_path):
    import app.services.upload_pipeline as upload_pipeline_module

    FakeMongoDBClient.docs_by_upload_id = {}
    FakeMongoDBClient.docs_by_request_id = {}
    FakeMongoDBClient.create_calls = 0
    FakeThread.started = 0

    monkeypatch.setattr(upload_pipeline_module, "MongoDBClient", FakeMongoDBClient)
    monkeypatch.setattr(upload_pipeline_module.threading, "Thread", FakeThread)
    monkeypatch.setattr(upload_pipeline_module, "UPLOADS_DIR", tmp_path)

    result = asyncio.run(
        handle_pdf_upload(
            file=_make_upload_file(),
            hospital_name="Apollo Hospital",
            employee_id="12345678",
            invoice_date="2026-02-14",
            client_request_id="req-async-1",
        )
    )

    assert result["status"] == "PENDING"
    assert result["upload_id"]
    assert result["employee_id"] == "12345678"
    assert result["invoice_date"] == "2026-02-14"
    assert FakeMongoDBClient.create_calls == 1
    assert FakeThread.started == 1


def test_upload_pipeline_idempotency_returns_existing_processing(monkeypatch, tmp_path):
    import app.services.upload_pipeline as upload_pipeline_module

    FakeMongoDBClient.docs_by_upload_id = {
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {
            "_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "upload_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "status": "PROCESSING",
            "employee_id": "12345678",
            "original_filename": "bill.pdf",
            "file_size_bytes": 12,
        }
    }
    FakeMongoDBClient.docs_by_request_id = {
        "req-dup-1": FakeMongoDBClient.docs_by_upload_id["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    }
    FakeMongoDBClient.create_calls = 0
    FakeThread.started = 0

    monkeypatch.setattr(upload_pipeline_module, "MongoDBClient", FakeMongoDBClient)
    monkeypatch.setattr(upload_pipeline_module.threading, "Thread", FakeThread)
    monkeypatch.setattr(upload_pipeline_module, "UPLOADS_DIR", tmp_path)

    result = asyncio.run(
        handle_pdf_upload(
            file=_make_upload_file(),
            hospital_name="Apollo Hospital",
            employee_id="12345678",
            client_request_id="req-dup-1",
        )
    )

    assert result["existing"] is True
    assert result["upload_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result["status"] == "PROCESSING"
    assert FakeMongoDBClient.create_calls == 0
    assert FakeThread.started == 0

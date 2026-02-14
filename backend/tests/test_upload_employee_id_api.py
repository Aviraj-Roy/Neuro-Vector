from __future__ import annotations

from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure `app` package (backend/app) is importable in test runs.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes import router


def _build_client(monkeypatch) -> TestClient:
    import app.services.upload_pipeline as upload_pipeline_module

    async def _fake_handle_pdf_upload(
        *,
        file,
        hospital_name,
        employee_id,
        invoice_date=None,
        client_request_id=None,
    ):
        return {
            "upload_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "employee_id": employee_id,
            "hospital_name": hospital_name,
            "status": "completed",
            "message": "Bill uploaded and processed successfully",
            "page_count": 1,
            "original_filename": file.filename,
            "file_size_bytes": 123,
        }

    monkeypatch.setattr(upload_pipeline_module, "handle_pdf_upload", _fake_handle_pdf_upload)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_upload_rejects_missing_employee_id(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.post(
        "/upload",
        files={"file": ("bill.pdf", b"dummy", "application/pdf")},
        data={"hospital_name": "Apollo Hospital"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "employee_id is required"


def test_upload_rejects_non_numeric_employee_id(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.post(
        "/upload",
        files={"file": ("bill.pdf", b"dummy", "application/pdf")},
        data={"hospital_name": "Apollo Hospital", "employee_id": "12AB5678"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "employee_id must be numeric only"


def test_upload_rejects_employee_id_wrong_length(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.post(
        "/upload",
        files={"file": ("bill.pdf", b"dummy", "application/pdf")},
        data={"hospital_name": "Apollo Hospital", "employee_id": "1234567"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "employee_id must contain exactly 8 digits"


def test_upload_accepts_valid_employee_id(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.post(
        "/upload",
        files={"file": ("bill.pdf", b"dummy", "application/pdf")},
        data={"hospital_name": "Apollo Hospital", "employee_id": "12345678"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert body["employee_id"] == "12345678"
    assert body["hospital_name"] == "Apollo Hospital"


def test_upload_rejects_invalid_invoice_date_format(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.post(
        "/upload",
        files={"file": ("bill.pdf", b"dummy", "application/pdf")},
        data={
            "hospital_name": "Apollo Hospital",
            "employee_id": "12345678",
            "invoice_date": "13-02-2026",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invoice_date must be in YYYY-MM-DD format"


def test_upload_accepts_valid_invoice_date_format(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.post(
        "/upload",
        files={"file": ("bill.pdf", b"dummy", "application/pdf")},
        data={
            "hospital_name": "Apollo Hospital",
            "employee_id": "12345678",
            "invoice_date": "2026-02-13",
        },
    )
    assert resp.status_code == 200

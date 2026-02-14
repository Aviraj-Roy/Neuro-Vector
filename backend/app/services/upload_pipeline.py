from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, UploadFile

from app.config import UPLOADS_DIR
from app.db.mongo_client import MongoDBClient
from app.main import process_bill

logger = logging.getLogger(__name__)


def _process_bill_async(
    *,
    pdf_path: Path,
    upload_id: str,
    hospital_name: str,
    original_filename: str,
) -> None:
    """Run extraction + verification out-of-band and clean up temporary PDF."""
    try:
        process_bill(
            pdf_path=str(pdf_path),
            hospital_name=hospital_name,
            upload_id=upload_id,
            original_filename=original_filename,
            auto_cleanup=True,
        )

        # Run verification automatically as part of upload processing lifecycle,
        # so details page does not need to trigger it.
        db = MongoDBClient(validate_schema=False)
        bill_doc = db.get_bill(upload_id) or {}
        effective_hospital_name = str(
            bill_doc.get("hospital_name_metadata")
            or bill_doc.get("hospital_name")
            or hospital_name
            or ""
        ).strip()
        if effective_hospital_name:
            try:
                db.mark_verification_processing(upload_id)
                from app.verifier.api import verify_bill_from_mongodb_sync

                verification_result = verify_bill_from_mongodb_sync(
                    upload_id,
                    hospital_name=effective_hospital_name,
                )
                db.save_verification_result(
                    upload_id=upload_id,
                    verification_result=verification_result or {},
                    verification_result_text="",
                    format_version="legacy",
                )
            except Exception as verify_err:
                db.mark_verification_failed(upload_id, str(verify_err))
                logger.warning(
                    "Auto verification failed for upload_id=%s: %s",
                    upload_id,
                    verify_err,
                )
    except Exception as exc:
        logger.error("Background processing failed for upload_id=%s: %s", upload_id, exc, exc_info=True)
    finally:
        try:
            if pdf_path.exists():
                pdf_path.unlink()
        except Exception as cleanup_err:
            logger.warning("Failed to clean up uploaded PDF %s: %s", pdf_path, cleanup_err)


def _build_ingestion_request_id(
    contents: bytes,
    hospital_name: str,
    filename: str,
    client_request_id: Optional[str],
) -> str:
    if client_request_id and client_request_id.strip():
        return client_request_id.strip()
    digest = hashlib.sha256()
    digest.update(hospital_name.strip().lower().encode("utf-8"))
    digest.update(b"::")
    digest.update(filename.strip().lower().encode("utf-8"))
    digest.update(b"::")
    digest.update(contents)
    return digest.hexdigest()


async def handle_pdf_upload(
    *,
    file: UploadFile,
    hospital_name: str,
    employee_id: str,
    invoice_date: Optional[str] = None,
    client_request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Canonical upload flow for one-PDF-one-document lifecycle."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted.")
    if not hospital_name or not hospital_name.strip():
        raise HTTPException(status_code=400, detail="hospital_name is required and cannot be empty")
    if not employee_id or not employee_id.strip():
        raise HTTPException(status_code=400, detail="employee_id is required")

    clean_hospital = hospital_name.strip()
    clean_employee_id = employee_id.strip()
    if not clean_employee_id.isdigit():
        raise HTTPException(status_code=400, detail="employee_id must be numeric only")
    if len(clean_employee_id) != 8:
        raise HTTPException(status_code=400, detail="employee_id must contain exactly 8 digits")
    clean_invoice_date: Optional[str] = None
    if invoice_date is not None:
        candidate_invoice_date = invoice_date.strip()
        if candidate_invoice_date:
            try:
                clean_invoice_date = datetime.strptime(candidate_invoice_date, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invoice_date must be in YYYY-MM-DD format") from exc
    original_filename = Path(file.filename).name or "uploaded_bill.pdf"
    contents = await file.read()
    file_size_bytes = len(contents or b"")
    if file_size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

    ingestion_request_id = _build_ingestion_request_id(
        contents=contents,
        hospital_name=clean_hospital,
        filename=original_filename,
        client_request_id=client_request_id,
    )

    db = MongoDBClient(validate_schema=False)
    existing = db.get_bill_by_request_id(ingestion_request_id)
    existing_upload_id = str(existing.get("upload_id") or existing.get("_id")) if existing else None
    existing_status = str(existing.get("status") or "").lower() if existing else ""
    if existing and existing_status in {"processing", "completed"}:
        return {
            "upload_id": existing_upload_id,
            "employee_id": str(existing.get("employee_id") or clean_employee_id),
            "hospital_name": clean_hospital,
            "status": existing_status or "uploaded",
            "page_count": existing.get("page_count"),
            "file_size_bytes": int(existing.get("file_size_bytes") or file_size_bytes),
            "original_filename": existing.get("original_filename") or original_filename,
            "message": "Duplicate upload request detected; returning existing bill record",
            "existing": True,
        }

    upload_id = existing_upload_id or hashlib.md5(ingestion_request_id.encode("utf-8")).hexdigest()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    temp_pdf_path = UPLOADS_DIR / f"{upload_id}_{original_filename}"

    with open(temp_pdf_path, "wb") as f:
        f.write(contents)

    if existing and existing_status in {"uploaded", "failed"}:
        create_result = {"upload_id": upload_id, "created": False, "status": existing_status}
    else:
        create_result = db.create_upload_record(
            upload_id=upload_id,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            hospital_name=clean_hospital,
            employee_id=clean_employee_id,
            invoice_date=clean_invoice_date,
            source_pdf=original_filename,
            ingestion_request_id=ingestion_request_id,
        )
    effective_upload_id = create_result["upload_id"]
    current_status = str(create_result.get("status") or "uploaded")

    if create_result.get("created", False) or current_status in {"uploaded", "failed"}:
        worker = threading.Thread(
            target=_process_bill_async,
            kwargs={
                "pdf_path": temp_pdf_path,
                "upload_id": effective_upload_id,
                "hospital_name": clean_hospital,
                "original_filename": original_filename,
            },
            daemon=True,
            name=f"bill-process-{effective_upload_id[:8]}",
        )
        worker.start()

    doc = db.get_bill(effective_upload_id) or {}
    return {
        "upload_id": effective_upload_id,
        "employee_id": str(doc.get("employee_id") or clean_employee_id),
        "hospital_name": clean_hospital,
        "status": str(doc.get("status") or current_status),
        "page_count": doc.get("page_count"),
        "file_size_bytes": int(doc.get("file_size_bytes") or file_size_bytes),
        "original_filename": doc.get("original_filename") or original_filename,
        "upload_date": doc.get("upload_date") or doc.get("created_at"),
        "invoice_date": doc.get("invoice_date") or clean_invoice_date,
        "message": "Bill uploaded successfully and processing started",
        "existing": not create_result.get("created", False),
    }

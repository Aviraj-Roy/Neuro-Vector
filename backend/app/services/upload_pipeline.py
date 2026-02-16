from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, UploadFile

from app.config import (
    QUEUE_RECONCILE_INTERVAL_SECONDS,
    QUEUE_STALE_PROCESSING_SECONDS,
    UPLOADS_DIR,
)
from app.db.mongo_client import MongoDBClient
from app.main import process_bill

logger = logging.getLogger(__name__)
_QUEUE_LOCK = threading.Lock()
_QUEUE_WAKE_EVENT = threading.Event()
_WORKER_THREAD: Optional[threading.Thread] = None
_STALE_PROCESSING_SECONDS = QUEUE_STALE_PROCESSING_SECONDS
_QUEUE_RECONCILE_INTERVAL_SECONDS = QUEUE_RECONCILE_INTERVAL_SECONDS
_STATUS_PENDING = "PENDING"
_STATUS_PROCESSING = "PROCESSING"
_STATUS_COMPLETED = "COMPLETED"
_STATUS_UPLOADED = "UPLOADED"
_STATUS_FAILED = "FAILED"


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
            assume_processing_claimed=True,
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


def _queue_worker_loop() -> None:
    """Strict single-worker FIFO queue processor."""
    db = MongoDBClient(validate_schema=False)
    last_reconcile_ts = 0.0
    try:
        stats = db.reconcile_queue_state(stale_after_seconds=_STALE_PROCESSING_SECONDS)
        if stats.get("stale_recovered", 0) > 0 or stats.get("extra_processing_demoted", 0) > 0:
            logger.warning("Queue reconciliation on startup: %s", stats)
    except Exception as e:
        logger.warning("Queue recovery failed: %s", e)

    while True:
        try:
            now_ts = time.time()
            if now_ts - last_reconcile_ts >= max(10, _QUEUE_RECONCILE_INTERVAL_SECONDS):
                last_reconcile_ts = now_ts
                try:
                    db.reconcile_queue_state(stale_after_seconds=_STALE_PROCESSING_SECONDS)
                except Exception as reconcile_err:
                    logger.warning("Queue reconciliation iteration failed: %s", reconcile_err)

            claimed = db.claim_next_pending_job()
            if not claimed:
                _QUEUE_WAKE_EVENT.wait(timeout=5.0)
                _QUEUE_WAKE_EVENT.clear()
                continue

            upload_id = str(claimed.get("upload_id") or claimed.get("_id") or "")
            temp_pdf_path = Path(str(claimed.get("temp_pdf_path") or "").strip())
            hospital_name = str(
                claimed.get("queue_hospital_name")
                or claimed.get("hospital_name_metadata")
                or claimed.get("hospital_name")
                or ""
            ).strip()
            original_filename = str(
                claimed.get("queue_original_filename")
                or claimed.get("original_filename")
                or temp_pdf_path.name
                or "uploaded_bill.pdf"
            ).strip()

            if not upload_id or not temp_pdf_path or not temp_pdf_path.exists():
                db.mark_failed(
                    upload_id,
                    f"Queued PDF not found for processing: {temp_pdf_path}",
                )
                continue

            _process_bill_async(
                pdf_path=temp_pdf_path,
                upload_id=upload_id,
                hospital_name=hospital_name,
                original_filename=original_filename,
            )
            # Loop naturally claims next pending bill immediately (FIFO).
            _QUEUE_WAKE_EVENT.set()

        except Exception as e:
            logger.error("Queue worker iteration failed: %s", e, exc_info=True)
            time.sleep(1.0)


def _ensure_queue_worker_started() -> None:
    global _WORKER_THREAD
    with _QUEUE_LOCK:
        if _WORKER_THREAD and _WORKER_THREAD.is_alive():
            return
        _WORKER_THREAD = threading.Thread(
            target=_queue_worker_loop,
            daemon=True,
            name="bill-queue-worker",
        )
        _WORKER_THREAD.start()


def start_queue_worker() -> None:
    """Public bootstrap for API server startup."""
    _ensure_queue_worker_started()
    _QUEUE_WAKE_EVENT.set()


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
    existing_status = str(existing.get("status") or "").strip().upper() if existing else ""
    if existing and existing_status in {_STATUS_PROCESSING, _STATUS_COMPLETED}:
        return {
            "upload_id": existing_upload_id,
            "employee_id": str(existing.get("employee_id") or clean_employee_id),
            "hospital_name": clean_hospital,
            "status": existing_status or _STATUS_PENDING,
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

    if existing and existing_status in {_STATUS_PENDING, _STATUS_UPLOADED, _STATUS_FAILED}:
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
    current_status = str(create_result.get("status") or _STATUS_PENDING).strip().upper()
    db.enqueue_upload_job(
        upload_id=effective_upload_id,
        temp_pdf_path=str(temp_pdf_path),
        hospital_name=clean_hospital,
        original_filename=original_filename,
    )
    _ensure_queue_worker_started()
    _QUEUE_WAKE_EVENT.set()

    doc = db.get_bill(effective_upload_id) or {}
    return {
        "upload_id": effective_upload_id,
        "employee_id": str(doc.get("employee_id") or clean_employee_id),
        "hospital_name": clean_hospital,
        "status": str(doc.get("status") or current_status or _STATUS_PENDING).strip().upper(),
        "queue_position": doc.get("queue_position"),
        "page_count": doc.get("page_count"),
        "file_size_bytes": int(doc.get("file_size_bytes") or file_size_bytes),
        "original_filename": doc.get("original_filename") or original_filename,
        "upload_date": doc.get("upload_date") or doc.get("created_at"),
        "invoice_date": doc.get("invoice_date") or clean_invoice_date,
        "message": "Bill uploaded successfully and queued for processing",
        "existing": not create_result.get("created", False),
    }

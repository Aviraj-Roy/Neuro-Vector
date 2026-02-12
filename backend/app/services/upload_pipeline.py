from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, UploadFile

from app.config import UPLOADS_DIR
from app.db.mongo_client import MongoDBClient
from app.main import process_bill

logger = logging.getLogger(__name__)


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
    client_request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Canonical upload flow for one-PDF-one-document lifecycle."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted.")
    if not hospital_name or not hospital_name.strip():
        raise HTTPException(status_code=400, detail="hospital_name is required and cannot be empty")

    clean_hospital = hospital_name.strip()
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
            "hospital_name": clean_hospital,
            "status": existing_status or "uploaded",
            "page_count": existing.get("page_count"),
            "file_size_bytes": int(existing.get("file_size_bytes") or file_size_bytes),
            "original_filename": existing.get("original_filename") or original_filename,
            "message": "Duplicate upload request detected; returning existing bill record",
            "existing": True,
        }

    upload_id = existing_upload_id or uuid.uuid4().hex
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    temp_pdf_path = UPLOADS_DIR / f"{upload_id}_{original_filename}"

    try:
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
                source_pdf=original_filename,
                ingestion_request_id=ingestion_request_id,
            )
        effective_upload_id = create_result["upload_id"]
        current_status = str(create_result.get("status") or "uploaded")

        if create_result.get("created", False) or current_status in {"uploaded", "failed"}:
            process_bill(
                pdf_path=str(temp_pdf_path),
                hospital_name=clean_hospital,
                upload_id=effective_upload_id,
                original_filename=original_filename,
                auto_cleanup=True,
            )

        doc = db.get_bill(effective_upload_id) or {}
        return {
            "upload_id": effective_upload_id,
            "hospital_name": clean_hospital,
            "status": str(doc.get("status") or current_status),
            "page_count": doc.get("page_count"),
            "file_size_bytes": int(doc.get("file_size_bytes") or file_size_bytes),
            "original_filename": doc.get("original_filename") or original_filename,
            "message": "Bill uploaded and processed successfully",
            "existing": not create_result.get("created", False),
        }
    finally:
        try:
            if temp_pdf_path.exists():
                temp_pdf_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to clean up uploaded PDF {temp_pdf_path}: {e}")

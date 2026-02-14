"""
FastAPI Route Definitions for Medical Bill Verification API.

This module defines all HTTP endpoints for the API:
- POST /upload: Upload and process medical bills
- GET /status/{upload_id}: Check upload processing status
- POST /verify/{upload_id}: Run verification on processed bills
- GET /tieups: List available hospital tie-ups
- POST /tieups/reload: Reload hospital tie-up data

Separation of Concerns:
- This file: API layer (HTTP request/response handling)
- app/main.py: Service layer (business logic)
- backend/main.py: CLI layer (command-line interface)
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

# ============================================================================
# Router Configuration
# ============================================================================
router = APIRouter(
    tags=["Medical Bill Verification"],
    responses={
        500: {"description": "Internal server error"},
        400: {"description": "Bad request"}
    }
)

# ============================================================================
# Request/Response Models
# ============================================================================
class UploadResponse(BaseModel):
    """Response model for /upload endpoint."""
    upload_id: str = Field(..., description="Unique identifier for the uploaded bill")
    employee_id: str = Field(..., description="Employee ID (exactly 8 numeric digits)")
    hospital_name: str = Field(..., description="Hospital name provided in the request")
    message: str = Field(..., description="Success message")
    status: str = Field(..., description="Processing status")
    page_count: Optional[int] = Field(None, description="Number of pages in the PDF")
    original_filename: Optional[str] = Field(None, description="Original uploaded filename")
    file_size_bytes: Optional[int] = Field(None, description="Original uploaded PDF size in bytes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "upload_id": "a1b2c3d4e5f6g7h8i9j0",
                "employee_id": "12345678",
                "hospital_name": "Apollo Hospital",
                "message": "Bill uploaded and processed successfully",
                "status": "completed",
                "original_filename": "bill.pdf",
                "file_size_bytes": 324567,
                "page_count": 3
            }
        }


class UploadRequestForm(BaseModel):
    """Validated upload form payload."""
    hospital_name: Optional[str] = Field(None, description="Hospital name (e.g., 'Apollo Hospital')")
    employee_id: Optional[str] = Field(None, description="Employee ID (exactly 8 digits)")
    invoice_date: Optional[str] = Field(None, description="Optional invoice date in YYYY-MM-DD format")
    client_request_id: Optional[str] = Field(None, description="Optional idempotency key from frontend")

    @field_validator("hospital_name")
    @classmethod
    def validate_hospital_name(cls, value: Optional[str]) -> str:
        if not value or not value.strip():
            raise ValueError("hospital_name is required and cannot be empty")
        return value.strip()

    @field_validator("employee_id")
    @classmethod
    def validate_employee_id(cls, value: Optional[str]) -> str:
        clean_value = str(value or "").strip()
        if not clean_value:
            raise ValueError("employee_id is required")
        if not clean_value.isdigit():
            raise ValueError("employee_id must be numeric only")
        if len(clean_value) != 8:
            raise ValueError("employee_id must contain exactly 8 digits")
        return clean_value

    @field_validator("invoice_date")
    @classmethod
    def validate_invoice_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        clean_value = value.strip()
        if not clean_value:
            return None
        try:
            parsed = datetime.strptime(clean_value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("invoice_date must be in YYYY-MM-DD format") from exc
        return parsed.strftime("%Y-%m-%d")

    @field_validator("client_request_id")
    @classmethod
    def validate_client_request_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class VerificationResponse(BaseModel):
    """Response model for /verify endpoint."""
    upload_id: str
    hospital_name: str
    verification_status: str
    summary: dict
    items: list
    
    class Config:
        json_schema_extra = {
            "example": {
                "upload_id": "a1b2c3d4e5f6g7h8i9j0",
                "hospital_name": "Apollo Hospital",
                "verification_status": "completed",
                "summary": {
                    "total_items": 15,
                    "matched_items": 12,
                    "mismatched_items": 3
                },
                "items": []
            }
        }


class StatusResponse(BaseModel):
    """Response model for /status/{upload_id} endpoint."""
    upload_id: str = Field(..., description="Unique identifier for the uploaded bill")
    status: str = Field(..., description="Current processing status")
    exists: bool = Field(..., description="Whether the upload exists in storage")
    message: str = Field(..., description="Human-readable status message")
    hospital_name: Optional[str] = Field(None, description="Hospital name (if available)")
    page_count: Optional[int] = Field(None, description="Number of pages in the uploaded PDF")
    original_filename: Optional[str] = Field(None, description="Original uploaded filename")
    file_size_bytes: Optional[int] = Field(None, description="Original uploaded PDF size in bytes")

    class Config:
        json_schema_extra = {
            "example": {
                "upload_id": "a1b2c3d4e5f6g7h8i9j0",
                "status": "completed",
                "exists": True,
                "message": "Bill found",
                "hospital_name": "Apollo Hospital",
                "original_filename": "bill.pdf",
                "file_size_bytes": 324567,
                "page_count": 3
            }
        }


class TieupHospital(BaseModel):
    """Model for hospital tie-up information."""
    name: str
    file_path: str
    total_items: int


class BillListItem(BaseModel):
    """Summary model for GET /bills list endpoint."""
    bill_id: str
    employee_id: str
    invoice_date: Optional[str] = None
    upload_date: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    completed_at: Optional[str] = None
    hospital_name: Optional[str] = None
    status: str
    grand_total: float = 0.0
    page_count: Optional[int] = None
    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None


class DeleteBillResponse(BaseModel):
    success: bool
    upload_id: str
    message: str
    deleted_at: Optional[str] = None


class RestoreBillResponse(BaseModel):
    success: bool
    bill: BillListItem


class BillDetailResponse(BaseModel):
    billId: str = Field(..., description="Bill identifier (same as upload_id)")
    upload_id: str = Field(..., description="Upload identifier")
    status: str = Field(..., description="Current processing status")
    hospital_name: Optional[str] = Field(
        None,
        description="Hospital name metadata (if available)",
    )
    verificationResult: str = Field(
        ...,
        description="Raw formatted verification text for frontend parsing",
    )
    formatVersion: str = Field(
        "v1",
        description="Verification result text format version",
    )
    financial_totals: dict[str, float] = Field(
        default_factory=dict,
        description="DB-backed verification financial totals",
    )
    employee_id: str = Field("", description="Employee identifier")
    invoice_date: Optional[str] = None
    upload_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[str] = None


def _is_valid_upload_id(upload_id: str) -> bool:
    """Accept canonical UUID and legacy 32-char hex IDs."""
    if not upload_id or not isinstance(upload_id, str):
        return False
    try:
        uuid.UUID(upload_id)
        return True
    except (ValueError, TypeError, AttributeError):
        pass
    return bool(re.fullmatch(r"[0-9a-fA-F]{32}", upload_id))


def _normalize_status(raw_status: Any) -> str:
    status_mapping = {
        "uploaded": "pending",
        "complete": "completed",
        "completed": "completed",
        "success": "completed",
        "processing": "processing",
        "pending": "pending",
        "failed": "failed",
        "error": "failed",
        "verified": "verified",
    }
    normalized = str(raw_status or "").strip().lower()
    return status_mapping.get(normalized, normalized or "completed")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _derive_processing_time_seconds(doc: dict[str, Any]) -> Optional[float]:
    raw_value = doc.get("processing_time_seconds")
    raw_seconds: Optional[float] = None
    if raw_value is not None:
        try:
            raw_seconds = float(raw_value)
        except (TypeError, ValueError):
            raw_seconds = None

    started = _parse_iso_datetime(
        doc.get("processing_started_at") or doc.get("created_at") or doc.get("upload_date")
    )
    ended = _parse_iso_datetime(
        doc.get("verification_completed_at")
        or doc.get("processing_completed_at")
        or doc.get("completed_at")
    )
    if not ended and started:
        current_status = _derive_dashboard_status(doc)
        if current_status == "processing":
            if started.tzinfo is not None:
                ended = datetime.now(started.tzinfo)
            else:
                ended = datetime.now()
    if not started or not ended:
        return raw_seconds
    try:
        duration = (ended - started).total_seconds()
        derived = round(max(0.0, float(duration)), 3)
        if raw_seconds is not None:
            return round(max(raw_seconds, derived), 3)
        return derived
    except Exception:
        return raw_seconds


def _derive_dashboard_status(doc: dict[str, Any]) -> str:
    """Compute UI-facing lifecycle status across extraction + verification."""
    upload_status = _normalize_status(doc.get("status"))
    raw_verification_status = str(doc.get("verification_status") or "").strip()
    verification_status = (
        _normalize_status(raw_verification_status) if raw_verification_status else ""
    )

    if upload_status in {"pending", "processing", "failed", "not_found"}:
        return upload_status
    if verification_status == "failed":
        return "failed"
    if verification_status in {"processing", "pending"}:
        return "processing"
    if verification_status in {"completed", "verified"}:
        return "completed"

    has_verification_text = bool(str(doc.get("verification_result_text") or "").strip())
    verification_result = doc.get("verification_result")
    has_verification_payload = isinstance(verification_result, dict) and bool(verification_result)
    if upload_status in {"completed", "verified"} and not (has_verification_text or has_verification_payload):
        return "processing"
    return upload_status


def _server_now() -> datetime:
    """Server-local timezone aware current timestamp."""
    return datetime.now().astimezone()


def _parse_status_filter(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = _normalize_status(value)
    allowed = {"pending", "processing", "completed"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: PENDING, PROCESSING, COMPLETED",
        )
    return normalized


def _parse_date_filter(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    allowed = {"TODAY", "YESTERDAY", "THIS_MONTH", "LAST_MONTH"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail="date_filter must be one of: TODAY, YESTERDAY, THIS_MONTH, LAST_MONTH",
        )
    return normalized


def _parse_scope(value: Optional[str]) -> str:
    raw = str(value or "active").strip().lower()
    if raw not in {"active", "deleted"}:
        raise HTTPException(status_code=400, detail="scope must be one of: active, deleted")
    return raw


def _get_date_window(date_filter: Optional[str]) -> tuple[Optional[datetime], Optional[datetime]]:
    """Build [start, end) window in server timezone."""
    normalized = _parse_date_filter(date_filter)
    if not normalized:
        return None, None

    now = _server_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if normalized == "TODAY":
        return today_start, today_start + timedelta(days=1)
    if normalized == "YESTERDAY":
        start = today_start - timedelta(days=1)
        return start, today_start
    if normalized == "THIS_MONTH":
        start = today_start.replace(day=1)
        return start, now
    # LAST_MONTH
    this_month_start = today_start.replace(day=1)
    prev_month_last = this_month_start - timedelta(days=1)
    last_month_start = prev_month_last.replace(day=1)
    return last_month_start, this_month_start


def _get_doc_upload_datetime(doc: dict[str, Any]) -> Optional[datetime]:
    raw_value = doc.get("upload_date") or doc.get("created_at")
    parsed = _parse_iso_datetime(raw_value)
    if not parsed:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed.astimezone()


def _matches_hospital(doc: dict[str, Any], hospital_name: Optional[str]) -> bool:
    if not hospital_name:
        return True
    requested = str(hospital_name).strip().lower()
    if not requested:
        return True
    actual = str(doc.get("hospital_name_metadata") or doc.get("hospital_name") or "").strip().lower()
    return actual == requested


def _build_bill_list_item(doc: dict[str, Any]) -> BillListItem:
    is_deleted = bool(doc.get("is_deleted") is True or doc.get("deleted_at"))
    employee_id = str(doc.get("employee_id") or "").strip()
    bill_id = str(doc.get("_id") or doc.get("upload_id") or "").strip()
    return BillListItem(
        bill_id=bill_id,
        employee_id=employee_id,
        invoice_date=doc.get("invoice_date") or (doc.get("header", {}) or {}).get("billing_date"),
        upload_date=doc.get("upload_date") or doc.get("created_at"),
        processing_time_seconds=_derive_processing_time_seconds(doc),
        completed_at=doc.get("completed_at") or doc.get("processing_completed_at"),
        hospital_name=doc.get("hospital_name_metadata") or doc.get("hospital_name"),
        status=_derive_dashboard_status(doc),
        grand_total=float(doc.get("grand_total") or 0.0),
        page_count=doc.get("page_count"),
        original_filename=doc.get("original_filename") or doc.get("source_pdf"),
        file_size_bytes=doc.get("file_size_bytes"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
        is_deleted=is_deleted,
        deleted_at=doc.get("deleted_at"),
        deleted_by=doc.get("deleted_by"),
    )


def _format_money(value: Any, *, na_when_zero: bool = False) -> str:
    amount = _as_float(value, 0.0)
    if na_when_zero and abs(amount) < 1e-9:
        return "N/A"
    return f"{amount:.2f}"


def _format_verification_result_text(verification_result: dict[str, Any]) -> str:
    """
    Stable parser-oriented rendering contract (v1).

    Required labels for frontend parser:
    - Overall Summary
    - Financial Summary
    - Category: <name>
    - Per-item keys:
      Bill Item, Best Match, Similarity, Allowed, Billed, Extra, Decision, Reason
    """
    if not isinstance(verification_result, dict):
        return ""

    lines: list[str] = []

    green_count = int(verification_result.get("green_count", 0) or 0)
    red_count = int(verification_result.get("red_count", 0) or 0)
    unclassified_count = int(verification_result.get("unclassified_count", 0) or 0)
    mismatch_count = int(verification_result.get("mismatch_count", 0) or 0)
    allowed_not_comparable_count = int(
        verification_result.get("allowed_not_comparable_count", 0) or 0
    )
    total_items = (
        green_count
        + red_count
        + unclassified_count
        + mismatch_count
        + allowed_not_comparable_count
    )

    lines.append("Overall Summary")
    lines.append(f"Total Items: {total_items}")
    lines.append(f"GREEN: {green_count}")
    lines.append(f"RED: {red_count}")
    lines.append(f"UNCLASSIFIED: {unclassified_count}")
    lines.append(f"MISMATCH: {mismatch_count}")
    lines.append(f"ALLOWED_NOT_COMPARABLE: {allowed_not_comparable_count}")
    lines.append("")

    lines.append("Financial Summary")
    lines.append(f"Total Bill Amount: {_format_money(verification_result.get('total_bill_amount'))}")
    lines.append(
        f"Total Allowed Amount: {_format_money(verification_result.get('total_allowed_amount'))}"
    )
    lines.append(f"Total Extra Amount: {_format_money(verification_result.get('total_extra_amount'))}")
    lines.append(
        f"Total Unclassified Amount: {_format_money(verification_result.get('total_unclassified_amount'))}"
    )
    lines.append("")

    results = verification_result.get("results") or []
    if not isinstance(results, list):
        return "\n".join(lines).strip()

    for category_result in results:
        if not isinstance(category_result, dict):
            continue
        category_name = str(category_result.get("category") or "unknown")
        lines.append(f"Category: {category_name}")

        items = category_result.get("items") or []
        if not isinstance(items, list):
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            diagnostics = item.get("diagnostics") or {}
            if not isinstance(diagnostics, dict):
                diagnostics = {}

            best_match = (
                item.get("matched_item")
                or diagnostics.get("best_candidate")
                or "N/A"
            )
            similarity_score = item.get("similarity_score")
            similarity_text = (
                f"{_as_float(similarity_score) * 100:.2f}%"
                if similarity_score is not None
                else "N/A"
            )
            decision = str(item.get("status") or "unknown")
            reason = diagnostics.get("failure_reason")
            if not reason:
                reason = "Match within allowed limit" if decision == "green" else "N/A"

            lines.append(f"Bill Item: {item.get('bill_item') or 'N/A'}")
            lines.append(f"Best Match: {best_match}")
            lines.append(f"Similarity: {similarity_text}")
            lines.append(
                f"Allowed: {_format_money(item.get('allowed_amount'), na_when_zero=decision in {'unclassified', 'mismatch', 'allowed_not_comparable'})}"
            )
            lines.append(f"Billed: {_format_money(item.get('bill_amount'))}")
            lines.append(
                f"Extra: {_format_money(item.get('extra_amount'), na_when_zero=decision in {'unclassified', 'mismatch', 'allowed_not_comparable'})}"
            )
            lines.append(f"Decision: {decision}")
            lines.append(f"Reason: {reason}")
            lines.append("")

    return "\n".join(lines).strip()


# ============================================================================
# POST /upload - Upload and Process Medical Bill
# ============================================================================
@router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_bill(
    file: UploadFile = File(..., description="Medical bill PDF file"),
    hospital_name: Optional[str] = Form(None, description="Hospital name (e.g., 'Apollo Hospital')"),
    employee_id: Optional[str] = Form(None, description="Employee ID (exactly 8 digits)"),
    invoice_date: Optional[str] = Form(None, description="Optional invoice date in YYYY-MM-DD format"),
    client_request_id: Optional[str] = Form(None, description="Optional idempotency key from frontend")
):
    """
    Upload and process a medical bill PDF.
    
    This endpoint:
    1. Receives a PDF file and hospital name
    2. Converts PDF to images
    3. Runs OCR (PaddleOCR)
    4. Extracts structured bill data
    5. Stores in MongoDB
    6. Returns upload_id for verification
    
    Args:
        file: PDF file (multipart/form-data)
        hospital_name: Name of the hospital (form field)
        
    Returns:
        UploadResponse with upload_id and metadata
        
    Raises:
        HTTPException: If file is invalid or processing fails
    """
    try:
        form_payload = UploadRequestForm(
            hospital_name=hospital_name,
            employee_id=employee_id,
            invoice_date=invoice_date,
            client_request_id=client_request_id,
        )
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {}
        error_message = first_error.get("msg") or "Invalid upload request payload"
        if isinstance(error_message, str) and error_message.startswith("Value error, "):
            error_message = error_message.replace("Value error, ", "", 1)
        raise HTTPException(status_code=400, detail=error_message)

    logger.info(
        "Received upload request for hospital: %s (employee_id: %s)",
        form_payload.hospital_name,
        form_payload.employee_id,
    )
    
    try:
        from app.services.upload_pipeline import handle_pdf_upload

        result = await handle_pdf_upload(
            file=file,
            hospital_name=form_payload.hospital_name,
            employee_id=form_payload.employee_id,
            invoice_date=form_payload.invoice_date,
            client_request_id=form_payload.client_request_id,
        )

        logger.info(f"Upload lifecycle completed for upload_id: {result['upload_id']}")
        return UploadResponse(
            upload_id=result["upload_id"],
            employee_id=result["employee_id"],
            hospital_name=result["hospital_name"],
            message=result["message"],
            status=result["status"],
            page_count=result.get("page_count"),
            original_filename=result.get("original_filename"),
            file_size_bytes=result.get("file_size_bytes"),
        )
        
    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to process bill: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process bill: {str(e)}"
        )


# ============================================================================
# GET /status/{upload_id} - Check Processing Status
# ============================================================================
@router.get("/status/{upload_id}", response_model=StatusResponse, status_code=200)
async def get_upload_status(upload_id: str):
    """
    Check status for an uploaded bill by upload_id.

    This endpoint is compatible with frontend polling workflows that call
    GET /status/{upload_id} after POST /upload.
    """
    logger.info(f"Received status request for upload_id: {upload_id}")

    try:
        from app.db.mongo_client import MongoDBClient

        db = MongoDBClient(validate_schema=False)
        bill_doc = db.get_bill(upload_id)
        if bill_doc and (bill_doc.get("is_deleted") is True or bill_doc.get("deleted_at")):
            bill_doc = None

        if not bill_doc:
            return StatusResponse(
                upload_id=upload_id,
                status="not_found",
                exists=False,
                message="Bill not found for the provided upload_id",
                hospital_name=None,
                page_count=None,
                original_filename=None,
                file_size_bytes=None,
            )

        normalized_status = _derive_dashboard_status(bill_doc)

        return StatusResponse(
            upload_id=upload_id,
            status=normalized_status,
            exists=True,
            message="Bill found",
            hospital_name=bill_doc.get("hospital_name_metadata"),
            page_count=bill_doc.get("page_count"),
            original_filename=bill_doc.get("original_filename") or bill_doc.get("source_pdf"),
            file_size_bytes=bill_doc.get("file_size_bytes"),
        )

    except Exception as e:
        logger.error(f"Failed to fetch status for upload_id {upload_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch status: {str(e)}"
        )


# ============================================================================
# GET /bills - List Uploaded Bills (Frontend compatibility)
# ============================================================================
@router.get("/bills", response_model=list[BillListItem], status_code=200)
async def list_bills(
    limit: int = Query(50, ge=1, le=500, description="Maximum bills to return"),
    scope: str = Query("active", description="active | deleted"),
    status: Optional[str] = Query(None, description="PENDING | PROCESSING | COMPLETED"),
    hospital_name: Optional[str] = Query(None, description="Case-insensitive exact hospital name"),
    date_filter: Optional[str] = Query(None, description="TODAY | YESTERDAY | THIS_MONTH | LAST_MONTH"),
):
    """
    List recent uploaded bills.

    This endpoint exists for frontend compatibility where UI screens poll
    GET /bills to render upload history.

    Semantics:
    - scope: `active` (default) or `deleted`
    - hospital_name: case-insensitive exact match
    - date_filter: evaluated in server local timezone using upload_date
      (fallback created_at)
    """
    return await _list_bills_common(
        limit=limit,
        scope=scope,
        status=status,
        hospital_name=hospital_name,
        date_filter=date_filter,
    )


@router.get("/bills/deleted", response_model=list[BillListItem], status_code=200)
async def list_deleted_bills(
    limit: int = Query(50, ge=1, le=500, description="Maximum bills to return"),
    status: Optional[str] = Query(None, description="PENDING | PROCESSING | COMPLETED"),
    hospital_name: Optional[str] = Query(None, description="Case-insensitive exact hospital name"),
    date_filter: Optional[str] = Query(None, description="TODAY | YESTERDAY | THIS_MONTH | LAST_MONTH"),
):
    """List deleted bills only, with the same optional filters as GET /bills."""
    return await _list_bills_common(
        limit=limit,
        scope="deleted",
        status=status,
        hospital_name=hospital_name,
        date_filter=date_filter,
    )


async def _list_bills_common(
    *,
    limit: int,
    scope: str,
    status: Optional[str],
    hospital_name: Optional[str],
    date_filter: Optional[str],
) -> list[BillListItem]:
    """
    Shared list implementation.

    scope behavior:
    - active: return active bills only (is_deleted != true and deleted_at absent)
    - deleted: return deleted bills only (is_deleted == true or deleted_at present)

    date_filter window uses server timezone and evaluates upload_date (fallback created_at).
    """
    try:
        from app.db.mongo_client import MongoDBClient

        requested_scope = _parse_scope(scope)
        requested_status = _parse_status_filter(status)
        date_start, date_end = _get_date_window(date_filter)

        db = MongoDBClient(validate_schema=False)
        cursor = db.collection.find(
            {"upload_id": {"$exists": True, "$ne": ""}},
            {
                "_id": 1,
                "upload_id": 1,
                "employee_id": 1,
                "invoice_date": 1,
                "upload_date": 1,
                "processing_time_seconds": 1,
                "processing_started_at": 1,
                "processing_completed_at": 1,
                "verification_completed_at": 1,
                "completed_at": 1,
                "header": 1,
                "hospital_name_metadata": 1,
                "hospital_name": 1,
                "status": 1,
                "verification_status": 1,
                "verification_result_text": 1,
                "verification_result": 1,
                "grand_total": 1,
                "page_count": 1,
                "original_filename": 1,
                "source_pdf": 1,
                "file_size_bytes": 1,
                "created_at": 1,
                "updated_at": 1,
                "is_deleted": 1,
                "deleted_at": 1,
                "deleted_by": 1,
            },
        ).sort("updated_at", -1)

        bills: list[BillListItem] = []
        for doc in cursor:
            is_deleted = bool(doc.get("is_deleted") is True or doc.get("deleted_at"))
            if requested_scope == "deleted" and not is_deleted:
                continue
            if requested_scope == "active" and is_deleted:
                continue

            if not _matches_hospital(doc, hospital_name):
                continue

            if date_start and date_end:
                doc_dt = _get_doc_upload_datetime(doc)
                if not doc_dt or not (date_start <= doc_dt < date_end):
                    continue

            bill_id = str(doc.get("_id") or doc.get("upload_id") or "").strip()
            if not bill_id:
                continue

            bill_item = _build_bill_list_item(doc)
            # Keep requested status filter authoritative even if helper evolves.
            if requested_status and bill_item.status != requested_status:
                continue
            bills.append(bill_item)
            if len(bills) >= limit:
                break

        return bills

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list bills: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list bills: {str(e)}"
        )


# ============================================================================
# DELETE /bills/{upload_id} - Soft/Hard Delete Bill
# ============================================================================
@router.delete("/bills/{upload_id}", response_model=DeleteBillResponse, status_code=200)
async def delete_bill(
    upload_id: str,
    permanent: bool = Query(
        False,
        description="If false: soft delete. If true: permanent delete (allowed only for soft-deleted bills).",
    ),
    deleted_by: Optional[str] = Query(None, description="Optional actor id/email for audit"),
):
    """Delete a bill/upload with temporary or permanent semantics."""
    if not _is_valid_upload_id(upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id format")

    try:
        from app.db.mongo_client import MongoDBClient

        db = MongoDBClient(validate_schema=False)
        bill_doc = db.get_bill(upload_id)
        if not bill_doc:
            raise HTTPException(status_code=404, detail="Bill not found")

        is_deleted = bool(bill_doc.get("is_deleted") is True or bill_doc.get("deleted_at"))

        if permanent:
            if not is_deleted:
                raise HTTPException(
                    status_code=409,
                    detail="Permanent delete is allowed only for soft-deleted bills",
                )
            hard_delete = db.hard_delete_upload(upload_id)
            if hard_delete.get("deleted_count", 0) <= 0:
                raise HTTPException(status_code=404, detail="Bill not found for permanent delete")
            return DeleteBillResponse(
                success=True,
                upload_id=upload_id,
                message="Bill permanently deleted",
                deleted_at=bill_doc.get("deleted_at"),
            )

        if is_deleted:
            raise HTTPException(status_code=409, detail="Bill is already soft-deleted")

        result = db.soft_delete_upload(upload_id, deleted_by=deleted_by)
        if result["modified_count"] <= 0:
            raise HTTPException(status_code=500, detail="Failed to soft-delete bill")
        return DeleteBillResponse(
            success=True,
            upload_id=upload_id,
            message="Bill soft-deleted successfully",
            deleted_at=result.get("deleted_at"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete bill {upload_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete bill: {str(e)}")


@router.post("/bills/{upload_id}/restore", response_model=RestoreBillResponse, status_code=200)
async def restore_bill(upload_id: str):
    """Restore a soft-deleted bill back to active scope."""
    if not _is_valid_upload_id(upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id format")
    try:
        from app.db.mongo_client import MongoDBClient

        db = MongoDBClient(validate_schema=False)
        bill_doc = db.get_bill(upload_id)
        if not bill_doc:
            raise HTTPException(status_code=404, detail="Bill not found")

        is_deleted = bool(bill_doc.get("is_deleted") is True or bill_doc.get("deleted_at"))
        if not is_deleted:
            raise HTTPException(status_code=409, detail="Bill is already active")

        restore_result = db.restore_upload(upload_id)
        if restore_result.get("modified_count", 0) <= 0:
            raise HTTPException(status_code=500, detail="Failed to restore bill")

        restored_doc = db.get_bill(upload_id)
        if not restored_doc:
            raise HTTPException(status_code=404, detail="Bill not found after restore")

        return RestoreBillResponse(success=True, bill=_build_bill_list_item(restored_doc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore bill {upload_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to restore bill: {str(e)}")


# ============================================================================
# GET /bill/{bill_id} - Bill Details + Formatted Verification Text
# ============================================================================
@router.get("/bill/{bill_id}", response_model=BillDetailResponse, status_code=200)
async def get_bill_details(bill_id: str):
    """Fetch bill with parser-safe verification text payload for dashboard use."""
    if not _is_valid_upload_id(bill_id):
        raise HTTPException(status_code=400, detail="Invalid bill_id format")

    try:
        from app.db.mongo_client import MongoDBClient

        db = MongoDBClient(validate_schema=False)
        bill_doc = db.get_bill(bill_id)
        if bill_doc and (bill_doc.get("is_deleted") is True or bill_doc.get("deleted_at")):
            bill_doc = None

        if not bill_doc:
            raise HTTPException(status_code=404, detail=f"Bill not found with bill_id: {bill_id}")

        upload_id = str(bill_doc.get("upload_id") or bill_doc.get("_id") or bill_id)
        status = _derive_dashboard_status(bill_doc)
        hospital_name = bill_doc.get("hospital_name_metadata") or bill_doc.get("hospital_name")
        format_version = str(bill_doc.get("verification_format_version") or "").strip() or "legacy"
        verification_text = str(bill_doc.get("verification_result_text") or "").strip()
        verification_result = bill_doc.get("verification_result") or {}
        financial_totals = {
            "total_billed": _as_float(verification_result.get("total_bill_amount"), 0.0),
            "total_allowed": _as_float(verification_result.get("total_allowed_amount"), 0.0),
            "total_extra": _as_float(verification_result.get("total_extra_amount"), 0.0),
            "total_unclassified": _as_float(verification_result.get("total_unclassified_amount"), 0.0),
        }

        # Regenerate parser-safe text when:
        # - text is missing
        # - or legacy/non-v1 text is stored
        if (not verification_text or format_version != "v1") and isinstance(verification_result, dict) and verification_result:
            verification_text = _format_verification_result_text(verification_result)
            db.save_verification_result(
                upload_id=upload_id,
                verification_result=verification_result,
                verification_result_text=verification_text,
                format_version="v1",
            )
            format_version = "v1"

        # Do not trigger verification from details endpoint. Verification is expected
        # to be handled by the upload processing pipeline.
        if not verification_text and status == "processing":
            return BillDetailResponse(
                billId=upload_id,
                upload_id=upload_id,
                employee_id=str(bill_doc.get("employee_id") or "").strip(),
                status="processing",
                hospital_name=hospital_name,
                invoice_date=bill_doc.get("invoice_date") or (bill_doc.get("header", {}) or {}).get("billing_date"),
                upload_date=bill_doc.get("upload_date") or bill_doc.get("created_at"),
                created_at=bill_doc.get("created_at"),
                updated_at=bill_doc.get("updated_at"),
                is_deleted=False,
                deleted_at=None,
                verificationResult="Verification is processing. Please retry shortly.",
                formatVersion=format_version,
                financial_totals=financial_totals,
            )
        if not verification_text and status == "failed":
            return BillDetailResponse(
                billId=upload_id,
                upload_id=upload_id,
                employee_id=str(bill_doc.get("employee_id") or "").strip(),
                status="failed",
                hospital_name=hospital_name,
                invoice_date=bill_doc.get("invoice_date") or (bill_doc.get("header", {}) or {}).get("billing_date"),
                upload_date=bill_doc.get("upload_date") or bill_doc.get("created_at"),
                created_at=bill_doc.get("created_at"),
                updated_at=bill_doc.get("updated_at"),
                is_deleted=False,
                deleted_at=None,
                verificationResult="Verification failed. Please retry from the dashboard.",
                formatVersion=format_version,
                financial_totals=financial_totals,
            )

        return BillDetailResponse(
            billId=upload_id,
            upload_id=upload_id,
            employee_id=str(bill_doc.get("employee_id") or "").strip(),
            status=status,
            hospital_name=hospital_name,
            invoice_date=bill_doc.get("invoice_date") or (bill_doc.get("header", {}) or {}).get("billing_date"),
            upload_date=bill_doc.get("upload_date") or bill_doc.get("created_at"),
            created_at=bill_doc.get("created_at"),
            updated_at=bill_doc.get("updated_at"),
            is_deleted=False,
            deleted_at=None,
            verificationResult=verification_text,
            formatVersion=format_version,
            financial_totals=financial_totals,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch bill details for {bill_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch bill details: {str(e)}")


# ============================================================================
# POST /verify/{upload_id} - Run Verification
# ============================================================================
@router.post("/verify/{upload_id}", status_code=200)
async def verify_bill(
    upload_id: str,
    hospital_name: Optional[str] = Form(None, description="Optional: Override hospital name")
):
    """
    Run verification (LLM comparison) on a processed bill.
    
    This endpoint:
    1. Fetches the bill from MongoDB using upload_id
    2. Loads hospital tie-up rates
    3. Runs item-level matching and verification
    4. Returns detailed verification results
    
    Args:
        upload_id: The upload_id returned from /upload
        hospital_name: Optional override for hospital name
        
    Returns:
        Verification results with matched/mismatched items
        
    Raises:
        HTTPException: If bill not found or verification fails
    """
    logger.info(f"Received verification request for upload_id: {upload_id}")
    
    try:
        from app.db.mongo_client import MongoDBClient
        from app.verifier.api import verify_bill_from_mongodb_sync
        
        # Check if bill exists
        db = MongoDBClient(validate_schema=False)
        bill_doc = db.get_bill(upload_id)
        if bill_doc and (bill_doc.get("is_deleted") is True or bill_doc.get("deleted_at")):
            bill_doc = None
        
        if not bill_doc:
            raise HTTPException(
                status_code=404,
                detail=f"Bill not found with upload_id: {upload_id}"
            )
        
        # Use provided hospital_name or fall back to stored metadata
        effective_hospital_name = hospital_name or bill_doc.get("hospital_name_metadata")
        
        if not effective_hospital_name:
            raise HTTPException(
                status_code=400,
                detail="Hospital name not found. Please provide hospital_name in the request."
            )
        db.mark_verification_processing(upload_id)

        # Run verification
        verification_result = verify_bill_from_mongodb_sync(
            upload_id,
            hospital_name=effective_hospital_name
        )
        verification_result_text = _format_verification_result_text(verification_result)
        db.save_verification_result(
            upload_id=upload_id,
            verification_result=verification_result,
            verification_result_text=verification_result_text,
            format_version="v1",
        )
        
        logger.info(f"Verification completed for upload_id: {upload_id}")
        
        return verification_result
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        try:
            db.mark_verification_failed(upload_id, str(e))  # type: ignore[misc]
        except Exception:
            pass
        logger.error(f"Verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {str(e)}"
        )


# ============================================================================
# GET /tieups - List Available Hospitals
# ============================================================================
@router.get("/tieups", response_model=list[TieupHospital], status_code=200)
async def list_tieups():
    """
    List all available hospital tie-ups.
    
    Returns a list of hospitals with tie-up agreements, loaded from
    the backend/data/tieups/ directory.
    
    Returns:
        List of hospital tie-up information
    """
    try:
        from app.config import TIEUPS_DIR
        
        hospitals = []
        
        if not TIEUPS_DIR.exists():
            logger.warning(f"Tie-ups directory not found: {TIEUPS_DIR}")
            return []
        
        # Scan for JSON files in tieups directory
        for json_file in TIEUPS_DIR.glob("*.json"):
            try:
                import json
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Count total items across all categories
                total_items = 0
                if isinstance(data, dict):
                    for category, items in data.items():
                        if isinstance(items, list):
                            total_items += len(items)
                
                hospitals.append(TieupHospital(
                    name=json_file.stem.replace('_', ' ').title(),
                    file_path=str(json_file.name),
                    total_items=total_items
                ))
                
            except Exception as e:
                logger.warning(f"Failed to load tie-up file {json_file}: {e}")
                continue
        
        logger.info(f"Found {len(hospitals)} hospital tie-ups")
        return hospitals
        
    except Exception as e:
        logger.error(f"Failed to list tie-ups: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list tie-ups: {str(e)}"
        )


# ============================================================================
# POST /tieups/reload - Reload Hospital Tie-up Data
# ============================================================================
@router.post("/tieups/reload", status_code=200)
async def reload_tieups():
    """
    Reload hospital tie-up data from disk.
    
    This endpoint is useful during development when tie-up JSON files
    are updated and need to be reloaded without restarting the server.
    
    Returns:
        Success message with count of reloaded hospitals
    """
    try:
        # Clear any cached tie-up data
        # (Implementation depends on your caching strategy)
        
        # Re-scan tie-ups directory
        tieups = await list_tieups()
        
        return {
            "message": "Tie-up data reloaded successfully",
            "hospital_count": len(tieups)
        }
        
    except Exception as e:
        logger.error(f"Failed to reload tie-ups: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload tie-ups: {str(e)}"
        )

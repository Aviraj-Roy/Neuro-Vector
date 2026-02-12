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
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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
                "hospital_name": "Apollo Hospital",
                "message": "Bill uploaded and processed successfully",
                "status": "completed",
                "original_filename": "bill.pdf",
                "file_size_bytes": 324567,
                "page_count": 3
            }
        }


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
    upload_id: str
    hospital_name: Optional[str] = None
    status: str
    grand_total: float = 0.0
    page_count: Optional[int] = None
    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DeleteBillResponse(BaseModel):
    success: bool
    upload_id: str
    message: str


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
        "uploaded": "uploaded",
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
    hospital_name: str = Form(..., description="Hospital name (e.g., 'Apollo Hospital')"),
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
    logger.info(f"Received upload request for hospital: {hospital_name}")
    
    try:
        from app.services.upload_pipeline import handle_pdf_upload

        result = await handle_pdf_upload(
            file=file,
            hospital_name=hospital_name,
            client_request_id=client_request_id,
        )

        logger.info(f"Upload lifecycle completed for upload_id: {result['upload_id']}")
        return UploadResponse(
            upload_id=result["upload_id"],
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
        if bill_doc and bill_doc.get("deleted_at"):
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

        normalized_status = _normalize_status(bill_doc.get("status"))

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
async def list_bills(limit: int = Query(50, ge=1, le=500, description="Maximum bills to return")):
    """
    List recent uploaded bills.

    This endpoint exists for frontend compatibility where UI screens poll
    GET /bills to render upload history.
    """
    try:
        from app.db.mongo_client import MongoDBClient

        db = MongoDBClient(validate_schema=False)
        cursor = db.collection.find(
            {
                "status": {"$in": ["completed", "complete", "success"]},
                "upload_id": {"$exists": True, "$ne": ""},
                "items": {"$type": "object"},
                "grand_total": {"$exists": True},
                "deleted_at": {"$exists": False},
            },
            {
                "_id": 1,
                "upload_id": 1,
                "hospital_name_metadata": 1,
                "status": 1,
                "grand_total": 1,
                "page_count": 1,
                "original_filename": 1,
                "file_size_bytes": 1,
                "created_at": 1,
                "updated_at": 1,
            },
        ).sort("updated_at", -1).limit(limit)

        bills: list[BillListItem] = []
        for doc in cursor:
            upload_id = str(doc.get("upload_id") or doc.get("_id") or "")
            if not upload_id:
                continue

            normalized_status = _normalize_status(doc.get("status"))

            bills.append(
                BillListItem(
                    upload_id=upload_id,
                    hospital_name=doc.get("hospital_name_metadata"),
                    status=normalized_status,
                    grand_total=float(doc.get("grand_total") or 0.0),
                    page_count=doc.get("page_count"),
                    original_filename=doc.get("original_filename") or doc.get("source_pdf"),
                    file_size_bytes=doc.get("file_size_bytes"),
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                )
            )

        return bills

    except Exception as e:
        logger.error(f"Failed to list bills: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list bills: {str(e)}"
        )


# ============================================================================
# DELETE /bills/{upload_id} - Delete Bill (Idempotent)
# ============================================================================
@router.delete("/bills/{upload_id}", response_model=DeleteBillResponse, status_code=200)
async def delete_bill(upload_id: str):
    """Delete a bill/upload by upload_id with idempotent semantics."""
    if not _is_valid_upload_id(upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload_id format")

    try:
        from app.db.mongo_client import MongoDBClient

        db = MongoDBClient(validate_schema=False)
        result = db.soft_delete_upload(upload_id)

        if result["matched_total"] == 0:
            return DeleteBillResponse(
                success=True,
                upload_id=upload_id,
                message="Upload not found or already deleted",
            )

        if result["modified_count"] == 0:
            return DeleteBillResponse(
                success=True,
                upload_id=upload_id,
                message="Bill already deleted",
            )

        return DeleteBillResponse(
            success=True,
            upload_id=upload_id,
            message="Bill deleted successfully",
        )
    except Exception as e:
        logger.error(f"Failed to delete bill {upload_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete bill: {str(e)}")


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
        if bill_doc and bill_doc.get("deleted_at"):
            bill_doc = None

        if not bill_doc:
            raise HTTPException(status_code=404, detail=f"Bill not found with bill_id: {bill_id}")

        upload_id = str(bill_doc.get("upload_id") or bill_doc.get("_id") or bill_id)
        status = _normalize_status(bill_doc.get("status"))
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

        # Backfill verification result on-demand for completed records
        # that were extracted but never passed through /verify.
        if not verification_text and status in {"completed", "verified"}:
            effective_hospital_name = hospital_name
            if effective_hospital_name:
                try:
                    from app.verifier.api import verify_bill_from_mongodb_sync

                    verification_result = verify_bill_from_mongodb_sync(
                        upload_id,
                        hospital_name=effective_hospital_name,
                    )
                    verification_text = _format_verification_result_text(verification_result)
                    db.save_verification_result(
                        upload_id=upload_id,
                        verification_result=verification_result,
                        verification_result_text=verification_text,
                        format_version="v1",
                    )
                    format_version = "v1"
                except Exception as verify_err:
                    logger.warning(
                        "On-demand verification failed for upload_id=%s: %s",
                        upload_id,
                        verify_err,
                    )
            else:
                logger.warning(
                    "Cannot run on-demand verification for upload_id=%s: hospital name missing",
                    upload_id,
                )

        return BillDetailResponse(
            billId=upload_id,
            upload_id=upload_id,
            status=status,
            hospital_name=hospital_name,
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
        if bill_doc and bill_doc.get("deleted_at"):
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

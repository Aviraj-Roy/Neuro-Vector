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
import os
import uuid
from pathlib import Path
from typing import Optional

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
    page_count: Optional[int] = Field(None, description="Number of pages in the PDF")
    
    class Config:
        json_schema_extra = {
            "example": {
                "upload_id": "a1b2c3d4e5f6g7h8i9j0",
                "hospital_name": "Apollo Hospital",
                "message": "Bill uploaded and processed successfully",
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

    class Config:
        json_schema_extra = {
            "example": {
                "upload_id": "a1b2c3d4e5f6g7h8i9j0",
                "status": "completed",
                "exists": True,
                "message": "Bill found",
                "hospital_name": "Apollo Hospital",
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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================================
# POST /upload - Upload and Process Medical Bill
# ============================================================================
@router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_bill(
    file: UploadFile = File(..., description="Medical bill PDF file"),
    hospital_name: str = Form(..., description="Hospital name (e.g., 'Apollo Hospital')")
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
    
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted."
        )
    
    # Validate hospital name
    if not hospital_name or not hospital_name.strip():
        raise HTTPException(
            status_code=400,
            detail="hospital_name is required and cannot be empty"
        )
    
    # Generate unique upload ID
    upload_id = uuid.uuid4().hex
    
    # Create uploads directory if it doesn't exist
    from app.config import UPLOADS_DIR
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded file temporarily
    pdf_path = UPLOADS_DIR / f"{upload_id}_{file.filename}"
    
    try:
        # Save uploaded file
        contents = await file.read()
        with open(pdf_path, "wb") as f:
            f.write(contents)
        
        logger.info(f"Saved uploaded file: {pdf_path}")
        
        # Process the bill using the service layer
        from app.main import process_bill
        
        result_upload_id = process_bill(
            pdf_path=str(pdf_path),
            hospital_name=hospital_name.strip(),
            upload_id=upload_id,
            auto_cleanup=True  # Clean up temporary images after processing
        )
        
        # Get page count from MongoDB
        from app.db.mongo_client import MongoDBClient
        db = MongoDBClient(validate_schema=False)
        bill_doc = db.get_bill(result_upload_id)
        page_count = bill_doc.get("page_count") if bill_doc else None
        
        logger.info(f"Successfully processed bill: {result_upload_id}")
        
        return UploadResponse(
            upload_id=result_upload_id,
            hospital_name=hospital_name.strip(),
            message="Bill uploaded and processed successfully",
            page_count=page_count
        )
        
    except ValueError as e:
        # Validation errors from process_bill
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        # Unexpected errors
        logger.error(f"Failed to process bill: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process bill: {str(e)}"
        )
        
    finally:
        # Clean up the uploaded PDF file
        try:
            if pdf_path.exists():
                pdf_path.unlink()
                logger.info(f"Cleaned up uploaded PDF: {pdf_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up uploaded PDF: {e}")


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

        if not bill_doc:
            return StatusResponse(
                upload_id=upload_id,
                status="not_found",
                exists=False,
                message="Bill not found for the provided upload_id",
                hospital_name=None,
                page_count=None
            )

        raw_status = str(bill_doc.get("status") or "").strip().lower()
        status_mapping = {
            "complete": "completed",
            "completed": "completed",
            "success": "completed",
            "processing": "processing",
            "pending": "pending",
            "failed": "failed",
            "error": "failed",
        }
        normalized_status = status_mapping.get(raw_status, raw_status or "completed")

        return StatusResponse(
            upload_id=upload_id,
            status=normalized_status,
            exists=True,
            message="Bill found",
            hospital_name=bill_doc.get("hospital_name_metadata"),
            page_count=bill_doc.get("page_count")
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
            {},
            {
                "_id": 1,
                "upload_id": 1,
                "hospital_name_metadata": 1,
                "status": 1,
                "grand_total": 1,
                "page_count": 1,
                "created_at": 1,
                "updated_at": 1,
            },
        ).sort("updated_at", -1).limit(limit)

        bills: list[BillListItem] = []
        for doc in cursor:
            upload_id = str(doc.get("upload_id") or doc.get("_id") or "")
            if not upload_id:
                continue

            raw_status = str(doc.get("status") or "").strip().lower()
            status_mapping = {
                "complete": "completed",
                "completed": "completed",
                "success": "completed",
                "processing": "processing",
                "pending": "pending",
                "failed": "failed",
                "error": "failed",
            }
            normalized_status = status_mapping.get(raw_status, raw_status or "completed")

            bills.append(
                BillListItem(
                    upload_id=upload_id,
                    hospital_name=doc.get("hospital_name_metadata"),
                    status=normalized_status,
                    grand_total=float(doc.get("grand_total") or 0.0),
                    page_count=doc.get("page_count"),
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

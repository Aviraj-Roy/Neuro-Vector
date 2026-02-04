from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List

from app.db.mongo_client import MongoDBClient
from app.extraction.bill_extractor import extract_bill_data
from app.extraction.numeric_guards import (
    MAX_GRAND_TOTAL,
    MAX_LINE_ITEM_AMOUNT,
    validate_grand_total,
)
from app.ingestion.pdf_loader import pdf_to_images
from app.ocr.image_preprocessor import preprocess_image
from app.ocr.paddle_engine import run_ocr
from app.utils.cleanup import cleanup_images, should_cleanup

logger = logging.getLogger(__name__)


# =============================================================================
# Post-Extraction Validation
# =============================================================================
class ExtractionValidationError(Exception):
    """Raised when extraction produces invalid/suspect data."""
    pass


def validate_extraction(bill_data: Dict[str, Any]) -> List[str]:
    """Validate extracted bill data against sanity checks.

    IMPORTANT: This function must be called ONCE per upload_id, AFTER full
    aggregation is complete. It validates the final merged object that will
    be persisted to MongoDB.

    Args:
        bill_data: Fully aggregated bill document (not intermediate page results)

    Returns:
        List of warning messages (empty if all valid), deduplicated

    Raises:
        ExtractionValidationError: If critical validation fails
    """
    warnings: List[str] = []

    # Validate grand total
    grand_total = bill_data.get("grand_total", 0.0) or 0.0
    is_valid, reason = validate_grand_total(grand_total)
    if not is_valid:
        warnings.append(f"Grand total validation failed: {reason} (total={grand_total})")
        # Cap it but don't fail
        bill_data["grand_total"] = min(grand_total, MAX_GRAND_TOTAL)

    # Validate individual item amounts
    items = bill_data.get("items", {}) or {}
    for category, item_list in items.items():
        for item in item_list:
            amount = item.get("amount", 0.0) or 0.0
            if amount > MAX_LINE_ITEM_AMOUNT:
                warnings.append(
                    f"Item amount exceeds cap: {item.get('description', '')[:30]} = {amount}"
                )

    # Validate no payment descriptions in items
    payments = bill_data.get("payments", []) or []
    payment_refs = set()
    for p in payments:
        ref = p.get("reference")
        if ref:
            payment_refs.add(ref.upper())

    for category, item_list in items.items():
        for item in item_list:
            desc = (item.get("description") or "").upper()
            for ref in payment_refs:
                if ref in desc:
                    raise ExtractionValidationError(
                        f"Payment reference '{ref}' found in medical item: {desc[:50]}"
                    )

    # Validate patient info exists (check FINAL aggregated state)
    patient = bill_data.get("patient", {}) or {}
    patient_name = (patient.get("name") or "").strip()
    patient_mrn = (patient.get("mrn") or "").strip()
    # Only warn if BOTH name is missing/unknown AND mrn is empty
    has_valid_name = patient_name and patient_name.upper() != "UNKNOWN"
    has_valid_mrn = bool(patient_mrn)
    if not has_valid_name and not has_valid_mrn:
        warnings.append("Patient identification missing (no name or MRN)")

    # Validate header exists (check FINAL aggregated state)
    header = bill_data.get("header", {}) or {}
    primary_bill = (header.get("primary_bill_number") or "").strip()
    bill_numbers = header.get("bill_numbers") or []
    # Filter out empty strings from bill_numbers list
    valid_bill_numbers = [bn for bn in bill_numbers if (bn or "").strip()]
    if not primary_bill and not valid_bill_numbers:
        warnings.append("No bill number extracted")

    # Deduplicate warnings (in case of any duplicate sources)
    return list(dict.fromkeys(warnings))


# =============================================================================
# Main Processing Pipeline
# =============================================================================
def process_bill(
    pdf_path: str, 
    hospital_name: str,  # NEW: Required parameter for hospital selection
    upload_id: str | None = None, 
    auto_cleanup: bool = True
) -> str:
    """Process a medical bill PDF and persist ONE MongoDB document.

    Business rules enforced:
    - One PDF upload == one MongoDB document, even if multiple pages/bill numbers.
    - Hospital name is provided explicitly (NOT extracted from bill).
    - Payments are NOT medical services.
    - No hardcoded hospital/test names.
    - Temporary images are cleaned up after successful OCR + DB save.

    Args:
        pdf_path: Path to the PDF file
        hospital_name: Name of the hospital (used for tie-up rate selection during verification)
        upload_id: Optional stable upload ID (generated if not provided)
        auto_cleanup: Whether to automatically cleanup images after success (default: True)

    Returns:
        The upload_id used for storage

    Raises:
        ExtractionValidationError: If critical validation fails
        ValueError: If hospital_name is invalid
    """
    upload_id = upload_id or uuid.uuid4().hex
    
    # Validate hospital_name parameter
    if not hospital_name or not isinstance(hospital_name, str) or not hospital_name.strip():
        raise ValueError("hospital_name must be a non-empty string")
    
    hospital_name = hospital_name.strip()
    logger.info(f"Processing bill for hospital: {hospital_name}")
    
    # Track pipeline success for cleanup decision
    ocr_success = False
    db_success = False

    try:
        # 1) Convert ALL pages to images
        image_paths = pdf_to_images(pdf_path)
        logger.info(f"Converted {len(image_paths)} pages from {pdf_path}")

        # 2) Preprocess ALL images
        processed_paths = [preprocess_image(p) for p in image_paths]

        # 3) OCR ALL pages together (page-aware)
        ocr_result = run_ocr(processed_paths)
        logger.info(f"OCR completed: {len(ocr_result.get('lines', []))} lines extracted")
        ocr_success = True  # OCR completed successfully

        # 4) Extract bill-scoped structured data (three-stage pipeline)
        #    This returns fully aggregated data across ALL pages
        #    NOTE: Hospital name is NOT extracted - it's provided as parameter
        bill_data = extract_bill_data(ocr_result)

        # 5) Add immutable metadata BEFORE validation
        #    (so validation sees the complete final state)
        bill_data["upload_id"] = upload_id
        bill_data["source_pdf"] = os.path.basename(pdf_path)
        bill_data["page_count"] = len(image_paths)
        bill_data.setdefault("schema_version", 2)  # Bump to v2 (hospital not in schema)
        
        # Store hospital_name as metadata (NOT in header, used for verification only)
        # This is stored at document root level for easy access during verification
        bill_data["hospital_name_metadata"] = hospital_name

        # 6) Post-extraction validation on FINAL aggregated object
        #    This runs exactly ONCE per upload_id after full aggregation
        warnings = validate_extraction(bill_data)
        for w in warnings:
            logger.warning(f"Extraction warning: {w}")
        # Also log structured extraction warnings collected during pipeline
        for w in bill_data.get("extraction_warnings", []):
            logger.warning(f"Extraction warning [{w.get('code')}]: {w.get('message')} :: {w.get('context')}")

        # 7) Log extraction summary
        total_items = sum(len(v) for v in bill_data.get("items", {}).values())
        total_payments = len(bill_data.get("payments", []))
        logger.info(
            f"Extraction complete: {total_items} items, {total_payments} payments, "
            f"grand_total={bill_data.get('grand_total', 0)}"
        )

        # 8) Single bill-scoped upsert
        db = MongoDBClient(validate_schema=False)
        db.upsert_bill(upload_id, bill_data)
        logger.info(f"Stored bill with upload_id: {upload_id}")
        db_success = True  # DB save completed successfully

        return upload_id
    
    finally:
        # 9) Post-processing cleanup (runs even if exceptions occurred)
        #    Only cleans up if both OCR and DB save succeeded
        if auto_cleanup:
            should_run, reason = should_cleanup(ocr_success, db_success)
            
            if should_run:
                try:
                    # Clean up both uploads/ and uploads/processed/ directories
                    from app.config import UPLOADS_DIR, PROCESSED_DIR
                    deleted, failed, failed_paths = cleanup_images(str(UPLOADS_DIR), str(PROCESSED_DIR))
                    
                    if failed > 0:
                        logger.warning(
                            f"Post-OCR cleanup completed with {failed} errors. "
                            f"Successfully deleted {deleted} files. "
                            f"Failed paths: {failed_paths}"
                        )
                    else:
                        logger.info(f"Post-OCR cleanup successful: {deleted} image files deleted")
                except Exception as e:
                    # Never let cleanup failures crash the pipeline
                    logger.error(f"Post-OCR cleanup failed: {type(e).__name__}: {e}", exc_info=True)
            else:
                logger.info(f"Post-OCR cleanup skipped: {reason}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bill_id = process_bill("Apollo.pdf")
    print(f"Stored bill with upload_id: {bill_id}")

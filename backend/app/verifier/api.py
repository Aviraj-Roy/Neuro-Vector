"""
FastAPI Application for Hospital Bill Verification.

Endpoints:
- POST /verify: Verify a bill JSON directly
- POST /verify/{upload_id}: Verify a bill from MongoDB by upload_id
- POST /tieups/reload: Reload tie-up rate sheets
- GET /health: Health check

Usage:
    uvicorn app.verifier.api:app --reload --port 8001
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from app.db.mongo_client import MongoDBClient
from app.verifier.models import BillInput, TieUpRateSheet, VerificationResponse
from app.verifier.verifier import BillVerifier, get_verifier, load_all_tieups

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# Application Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - Railway-optimized startup."""
    logger.info("=" * 80)
    logger.info("🚂 Starting Bill Verifier API on Railway...")
    logger.info("=" * 80)
    
    # Log environment info
    env = os.getenv("ENV", "development")
    railway_env = os.getenv("RAILWAY_ENVIRONMENT", "unknown")
    port = os.getenv("PORT", "8000")
    
    logger.info(f"Environment: {env}")
    logger.info(f"Railway Environment: {railway_env}")
    logger.info(f"Port: {port}")
    
    # Check LLM status
    enable_llm = os.getenv("ENABLE_LLM_MATCHING", "false").lower() in ("true", "1", "yes")
    hf_api_token = os.getenv("HF_API_TOKEN")
    
    if not enable_llm:
        logger.info("⚠️  LLM Matching: DISABLED (using embedding similarity only)")
    elif not hf_api_token:
        logger.warning("⚠️  LLM Matching: DISABLED (HF_API_TOKEN not set)")
        logger.warning("   Set HF_API_TOKEN environment variable to enable LLM matching")
    else:
        logger.info("🤖 LLM Matching: ENABLED (Hugging Face Inference API)")
        logger.info(f"   Primary model: {os.getenv('PRIMARY_LLM', 'phi3:mini')}")
        logger.info(f"   Secondary model: {os.getenv('SECONDARY_LLM', 'qwen2.5:3b')}")
    
    # Check MongoDB status
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        # Mask password in logs
        if "@" in mongo_uri:
            masked_uri = mongo_uri.split("@")[1]
        else:
            masked_uri = "configured"
        logger.info(f"📊 MongoDB: Configured ({masked_uri})")
    else:
        logger.warning("⚠️  MongoDB: NOT CONFIGURED (MONGO_URI not set)")
    
    # Initialize verifier with tie-up rate sheets
    verifier = get_verifier()
    from app.config import get_tieup_dir
    tieup_dir = os.getenv("TIEUP_DATA_DIR", get_tieup_dir())
    
    logger.info(f"📁 Loading tie-up rate sheets from: {tieup_dir}")
    
    # Validate tie-up directory exists
    import os.path
    if not os.path.exists(tieup_dir):
        logger.error(f"❌ Tie-up directory not found: {tieup_dir}")
        logger.error("   API will start but verification will fail")
        logger.error("   Please ensure backend/data/tieups/ exists in deployment")
    
    try:
        verifier.initialize()
        # Count loaded hospitals
        hospital_count = len(verifier.matcher._rate_sheets) if hasattr(verifier.matcher, '_rate_sheets') else 0
        logger.info("=" * 80)
        logger.info(f"✅ Bill Verifier initialized successfully ({hospital_count} hospitals)")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ Failed to initialize verifier: {e}")
        logger.error("   API will start but verification will fail until tie-ups are loaded")
        logger.error("=" * 80)
    
    yield
    
    logger.info("=" * 80)
    logger.info("🛑 Shutting down Bill Verifier API...")
    logger.info("=" * 80)


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Hospital Bill Verifier API",
    description="API for verifying hospital bills against tie-up rates using semantic matching",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# Request/Response Models
# =============================================================================

class VerifyRequest(BaseModel):
    """Request body for direct bill verification."""
    bill: BillInput


class ReloadResponse(BaseModel):
    """Response for tie-up reload endpoint."""
    success: bool
    hospitals_loaded: int
    message: str


class HealthResponse(BaseModel):
    """Response for health check endpoint."""
    status: str
    verifier_initialized: bool
    hospitals_indexed: int


# =============================================================================
# MongoDB Bill Fetcher
# =============================================================================

def fetch_bill_from_mongodb(upload_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a bill document from MongoDB by upload_id.
    
    Args:
        upload_id: The upload_id of the bill
        
    Returns:
        Bill document dict or None if not found
    """
    try:
        db = MongoDBClient(validate_schema=False)
        return db.get_bill_by_upload_id(upload_id)
    except Exception as e:
        logger.error(f"Failed to fetch bill from MongoDB: {e}")
        return None


def transform_mongodb_bill_to_input(
    doc: Dict[str, Any],
    hospital_name: Optional[str] = None
) -> BillInput:
    """
    Transform a MongoDB bill document to BillInput format.
    
    The MongoDB document has items grouped by category like:
    {
        "hospital_name_metadata": "Apollo Hospital",  # NEW: stored at root level
        "items": {
            "medicines": [...],
            "diagnostics_tests": [...],
        }
    }
    
    We need to transform it to:
    {
        "hospital_name": "...",
        "categories": [
            {"category_name": "medicines", "items": [...]}
        ]
    }
    
    Args:
        doc: MongoDB bill document
        hospital_name: Optional hospital name override (takes precedence over metadata)
    
    Returns:
        BillInput object for verification
    """
    # Extract hospital name from parameter, metadata, or legacy header field
    if hospital_name:
        # Explicit parameter takes precedence
        final_hospital_name = hospital_name
    elif doc.get("hospital_name_metadata"):
        # Use metadata field (new schema v2)
        final_hospital_name = doc.get("hospital_name_metadata")
    else:
        # Fallback to legacy header field or default
        header = doc.get("header", {}) or {}
        final_hospital_name = header.get("hospital_name") or "Unknown Hospital"
    
    # Transform items dict to categories list
    items_dict = doc.get("items", {}) or {}
    categories = []
    
    for category_name, items_list in items_dict.items():
        if not items_list:
            continue
            
        category_items = []
        for item in items_list:
            # Handle both 'description' and 'item_name' field names
            item_name = item.get("item_name") or item.get("description") or "Unknown Item"
            # Handle both 'qty' and 'quantity' field names
            quantity = item.get("quantity") or item.get("qty") or 1.0
            # Handle both 'amount' and 'final_amount' field names
            amount = item.get("amount") or item.get("final_amount") or 0.0
            
            category_items.append({
                "item_name": item_name,
                "quantity": float(quantity),
                "amount": float(amount),
            })
        
        if category_items:
            categories.append({
                "category_name": category_name,
                "items": category_items,
            })
    
    return BillInput(
        hospital_name=final_hospital_name,
        categories=categories,
    )


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check API health and verifier status."""
    verifier = get_verifier()
    
    # Count indexed hospitals
    hospitals_indexed = 0
    if verifier._initialized and verifier.matcher._hospital_index:
        hospitals_indexed = verifier.matcher._hospital_index.size
    
    return HealthResponse(
        status="healthy",
        verifier_initialized=verifier._initialized,
        hospitals_indexed=hospitals_indexed,
    )


@app.post("/verify", response_model=VerificationResponse, tags=["Verification"])
async def verify_bill_direct(request: VerifyRequest):
    """
    Verify a bill JSON directly.
    
    This endpoint accepts a bill in the standard format and returns
    verification results comparing against tie-up rates.
    """
    verifier = get_verifier()
    
    try:
        result = verifier.verify_bill(request.bill)
        return result
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )


@app.post("/verify/{upload_id}", response_model=VerificationResponse, tags=["Verification"])
async def verify_bill_from_mongodb(upload_id: str):
    """
    Verify a bill from MongoDB by upload_id.
    
    Fetches the bill document from MongoDB, transforms it to the
    verification format, and returns the verification results.
    """
    # Fetch bill from MongoDB
    doc = fetch_bill_from_mongodb(upload_id)
    
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bill not found with upload_id: {upload_id}"
        )
    
    # Transform to BillInput format
    try:
        bill_input = transform_mongodb_bill_to_input(doc)
    except Exception as e:
        logger.error(f"Failed to transform bill document: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid bill document format: {str(e)}"
        )
    
    # Verify
    verifier = get_verifier()
    
    try:
        result = verifier.verify_bill(bill_input)
        return result
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )


@app.post("/tieups/reload", response_model=ReloadResponse, tags=["Admin"])
async def reload_tieups():
    """
    Reload tie-up rate sheets from the data directory.
    
    Use this endpoint after adding or modifying tie-up JSON files
    to refresh the semantic indices.
    """
    verifier = get_verifier()
    from app.config import get_tieup_dir
    tieup_dir = os.getenv("TIEUP_DATA_DIR", get_tieup_dir())
    
    try:
        # Clear existing indices
        verifier.matcher.clear_indices()
        verifier._initialized = False
        
        # Reload
        rate_sheets = load_all_tieups(tieup_dir)
        verifier.initialize(rate_sheets)
        
        return ReloadResponse(
            success=True,
            hospitals_loaded=len(rate_sheets),
            message=f"Successfully loaded {len(rate_sheets)} tie-up rate sheets"
        )
    except Exception as e:
        logger.error(f"Failed to reload tie-ups: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload tie-ups: {str(e)}"
        )


@app.get("/tieups", tags=["Admin"])
async def list_tieups():
    """List all loaded tie-up hospitals."""
    verifier = get_verifier()
    
    if not verifier._initialized:
        return {"hospitals": [], "message": "Verifier not initialized"}
    
    hospitals = []
    if verifier.matcher._hospital_index:
        hospitals = verifier.matcher._hospital_index.texts
    
    return {
        "hospitals": hospitals,
        "count": len(hospitals),
    }


# =============================================================================
# Synchronous Helper Functions (for use in non-async contexts)
# =============================================================================

def verify_bill_from_mongodb_sync(
    upload_id: str,
    hospital_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronous version of verify_bill_from_mongodb for use in main.py.
    
    Args:
        upload_id: The upload_id of the bill to verify
        hospital_name: Optional hospital name override (uses metadata if not provided)
        
    Returns:
        Verification result as a dictionary
        
    Raises:
        ValueError: If bill not found or verification fails
    """
    # Fetch bill from MongoDB
    doc = fetch_bill_from_mongodb(upload_id)
    
    if doc is None:
        raise ValueError(f"Bill not found with upload_id: {upload_id}")
    
    # Transform to BillInput format (with optional hospital override)
    try:
        bill_input = transform_mongodb_bill_to_input(doc, hospital_name=hospital_name)
    except Exception as e:
        logger.error(f"Failed to transform bill document: {e}", exc_info=True)
        raise ValueError(f"Invalid bill document format: {str(e)}")
    
    # Verify
    verifier = get_verifier()
    
    try:
        result = verifier.verify_bill(bill_input)
        # Convert Pydantic model to dict for easier consumption
        return result.model_dump() if hasattr(result, 'model_dump') else result.dict()
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        raise ValueError(f"Verification failed: {str(e)}")


# =============================================================================
# Run with: uvicorn app.verifier.api:app --reload --port 8001
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    # Railway sets PORT automatically
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


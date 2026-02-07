"""
Pydantic models for the Hospital Bill Verifier system.
Defines schemas for:
- Input: Bill JSON, TieUp rate sheet JSON
- Output: Verification results
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class ItemType(str, Enum):
    """Type of tie-up rate item pricing."""
    UNIT = "unit"       # Price per unit (multiply by quantity)
    SERVICE = "service" # Fixed price for a service
    BUNDLE = "bundle"   # Package/bundle price


class VerificationStatus(str, Enum):
    """Status of item verification."""
    GREEN = "GREEN"       # Bill amount <= allowed amount
    RED = "RED"           # Bill amount > allowed amount (overcharged)
    MISMATCH = "MISMATCH" # No matching item found in tie-up rates
    ALLOWED_NOT_COMPARABLE = "ALLOWED_NOT_COMPARABLE"  # Item exists but no valid price comparison


class FailureReason(str, Enum):
    """Reason for MISMATCH or ALLOWED_NOT_COMPARABLE status."""
    NOT_IN_TIEUP = "NOT_IN_TIEUP"           # No match found in tie-up
    LOW_SIMILARITY = "LOW_SIMILARITY"        # Best match below threshold
    PACKAGE_ONLY = "PACKAGE_ONLY"            # Only exists as package item
    ADMIN_CHARGE = "ADMIN_CHARGE"            # Administrative/artifact item


# =============================================================================
# Bill Input Models (from MongoDB)
# =============================================================================

class BillItem(BaseModel):
    """A single item from the hospital bill."""
    item_name: str
    quantity: float = Field(default=1.0, ge=0)
    amount: float = Field(ge=0)


class BillCategory(BaseModel):
    """A category of items in the bill."""
    category_name: str
    items: List[BillItem] = Field(default_factory=list)


class BillInput(BaseModel):
    """Hospital bill structure from MongoDB."""
    hospital_name: str
    categories: List[BillCategory] = Field(default_factory=list)


# =============================================================================
# Tie-Up Rate Sheet Models
# =============================================================================

class TieUpItem(BaseModel):
    """A single item from the hospital tie-up rate sheet."""
    item_name: str
    rate: float = Field(ge=0)
    type: ItemType = ItemType.UNIT


class TieUpCategory(BaseModel):
    """A category of items in the tie-up rate sheet."""
    category_name: str
    items: List[TieUpItem] = Field(default_factory=list)


class TieUpRateSheet(BaseModel):
    """Hospital tie-up rate sheet structure."""
    hospital_name: str
    categories: List[TieUpCategory] = Field(default_factory=list)


# =============================================================================
# Verification Output Models
# =============================================================================

class MismatchDiagnostics(BaseModel):
    """Diagnostics for items that couldn't be matched (MISMATCH or ALLOWED_NOT_COMPARABLE)."""
    normalized_item_name: str
    best_candidate: Optional[str] = None  # Only if similarity > 0.5
    attempted_category: str
    failure_reason: FailureReason


class ItemVerificationResult(BaseModel):
    """Result of verifying a single bill item."""
    bill_item: str
    matched_item: Optional[str] = None
    status: VerificationStatus
    bill_amount: float
    allowed_amount: float = 0.0
    extra_amount: float = 0.0
    # Additional metadata for debugging
    similarity_score: Optional[float] = None
    # PHASE-1: Enhanced fields for exhaustive matching
    normalized_item_name: Optional[str] = None  # Show normalization applied
    diagnostics: Optional[MismatchDiagnostics] = None  # For non-GREEN/RED items


class CategoryVerificationResult(BaseModel):
    """Result of verifying all items in a category."""
    category: str
    matched_category: Optional[str] = None
    category_similarity: Optional[float] = None
    items: List[ItemVerificationResult] = Field(default_factory=list)


class VerificationResponse(BaseModel):
    """Complete verification response."""
    hospital: str
    matched_hospital: Optional[str] = None
    hospital_similarity: Optional[float] = None
    results: List[CategoryVerificationResult] = Field(default_factory=list)
    # Summary statistics
    total_bill_amount: float = 0.0
    total_allowed_amount: float = 0.0
    total_extra_amount: float = 0.0
    green_count: int = 0
    red_count: int = 0
    mismatch_count: int = 0

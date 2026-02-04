"""MongoDB Schema Definitions for Medical Bills.
Pydantic models used for validation/type-safety of extracted bill documents.
Design constraints:
- One PDF upload = one BillDocument.
- Payments/receipts are NOT medical services and should be stored separately.
"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

ITEM_CATEGORIES: List[str] = [
    "medicines",
    "surgical_consumables",
    "implants_devices",
    "diagnostics_tests",
    "radiology",
    "consultation",
    "hospitalization",
    "packages",
    "administrative",
    "other",
]


class LineItem(BaseModel):
    """A single medical service/line item extracted from the bill.
    Schema supports qty × rate validation with discrepancy detection.
    """
    description: str
    
    qty: Optional[float] = Field(default=1.0, alias="quantity")  # Support both names
    unit_rate: Optional[float] = None
    pdf_amount: Optional[float] = None  # Amount from PDF
    computed_amount: Optional[float] = None  # qty × rate
    final_amount: float  # The amount to use (pdf_amount takes precedence)
    discrepancy: bool = False  # True if pdf_amount != computed_amount
    
    # Legacy field for backward compatibility
    amount: Optional[float] = None  # Deprecated: use final_amount
    category: str = "other"
    
    # Provenance tracking
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    page: int = Field(default=0)  # Non-optional for tracking
    section_raw: Optional[str] = None  # Raw section header text
    
    # Flags (NEW: replaces separate regulated_pricing_drugs category)
    is_regulated_pricing: bool = False  # DPCO/NLEM items
    is_discount: bool = False

    @field_validator("description")
    @classmethod
    def clean_description(cls, v: str) -> str:
        if not v:
            return v
        v = re.sub(r"^\[?\d+\.?\s*", "", v)  # strip leading item number
        v = re.sub(r"\s+", " ", v)
        return v.strip()

    @field_validator("final_amount", "amount")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v < 0:
            raise ValueError("Amount cannot be negative")
        return round(float(v), 2)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        v = (v or "other").strip()
        # Migrate old regulated_pricing_drugs to medicines
        if v == "regulated_pricing_drugs":
            return "medicines"
        return v if v in ITEM_CATEGORIES else "other"
    
    @field_validator("calculated_total", mode="before")
    @classmethod
    def compute_calculated_total(cls, v, info):
        """Auto-compute if qty and rate available but total not provided."""
        if v is not None:
            return round(float(v), 2)
        # Cannot access other fields in 'before' mode reliably, return None
        return None
    
    def model_post_init(self, __context) -> None:
        """Compute derived fields after model initialization."""
        # Sync legacy amount field with final_amount for backward compatibility
        if hasattr(self, 'final_amount') and self.final_amount is not None:
            if self.amount is None:
                object.__setattr__(self, 'amount', self.final_amount)
        # Compute calculated_total if missing
        if self.computed_amount is None and self.qty and self.unit_rate:
            object.__setattr__(self, 'computed_amount', round(self.qty * self.unit_rate, 2))

class PaymentEvent(BaseModel):
    """A payment/receipt entry detected in the document."""
    description: str
    amount: Optional[float] = None
    reference: Optional[str] = None  # e.g., RCPO-..., UTR, TXN
    mode: Optional[str] = None       # e.g., CASH/CARD/UPI
    page: Optional[int] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

class PatientInfo(BaseModel):
    """Patient information extracted from the bill."""
    name: str = "UNKNOWN"
    mrn: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        if not v:
            return v
        # Remove MRN in parentheses: "Name (10010001143682)" -> "Name"
        v = re.sub(r"\s*\([0-9]{6,}\)\s*$", "", v)
        v = re.sub(r"\s+", " ", v)
        return v.strip()

class BillHeader(BaseModel):
    """Bill header / metadata.
    
    NOTE: hospital_name is NO LONGER stored in MongoDB.
    Hospital selection happens at upload time and is used for verification only.
    """
    # Bill numbers may appear multiple times; keep a primary plus a set.
    primary_bill_number: Optional[str] = None
    bill_numbers: List[str] = Field(default_factory=list)
    # hospital_name: REMOVED - provided at upload time, not extracted
    hospital_address: Optional[str] = None
    billing_date: Optional[str] = None
    visit_number: Optional[str] = None
    consultant: Optional[str] = None
    gstin: Optional[str] = None

class BillSummary(BaseModel):
    """Financial summary parsed from the document."""
    gross_total: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    sponsor_payable: float = 0.0
    patient_payable: float = 0.0
    net_total: float = 0.0
    amount_paid: float = 0.0
    balance_to_pay: float = 0.0

class BillDocument(BaseModel):
    """One uploaded PDF = one MongoDB BillDocument."""
    # Stable identity
    upload_id: Optional[str] = None
    source_pdf: Optional[str] = None
    page_count: int = 1
    # Extraction metadata
    extraction_date: datetime = Field(default_factory=datetime.now)
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    schema_version: int = 1
    header: BillHeader = Field(default_factory=BillHeader)
    patient: PatientInfo = Field(default_factory=PatientInfo)
    # Medical items grouped by category
    items: Dict[str, List[LineItem]] = Field(default_factory=lambda: {c: [] for c in ITEM_CATEGORIES})
    # Payments/receipts separated from medical services
    payments: List[PaymentEvent] = Field(default_factory=list)
    # Derived values
    subtotals: Dict[str, float] = Field(default_factory=dict)
    summary: BillSummary = Field(default_factory=BillSummary)
    grand_total: float = 0.0
    # Store raw OCR excerpt for debugging
    raw_ocr_text: Optional[str] = None

    def calculate_subtotals(self) -> Dict[str, float]:
        subtotals: Dict[str, float] = {}
        for category, items in self.items.items():
            subtotals[category] = round(sum(i.amount for i in items if i.amount is not None), 2)
        self.subtotals = subtotals
        return subtotals

    def calculate_grand_total(self) -> float:
        if not self.subtotals:
            self.calculate_subtotals()
        self.grand_total = round(sum(self.subtotals.values()), 2)
        return self.grand_total

    def to_mongo_dict(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["extraction_date"] = self.extraction_date.isoformat()
        return data

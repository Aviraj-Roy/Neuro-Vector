# Phase-2: Aggregation & Clinical Comparison Layer

## 🎯 Executive Summary

**Phase-1 Achievement:** Exhaustive item-level listing with hybrid semantic matching  
**Phase-2 Objective:** Transform Phase-1 output into clinically meaningful, financially auditable comparison layer

**Core Principle:** Non-destructive aggregation with full traceability

---

## 📋 Table of Contents

1. [Phase-2 Goals (Strict)](#phase-2-goals-strict)
2. [Architecture Overview](#architecture-overview)
3. [Updated Processing Logic](#updated-processing-logic)
4. [Output Schema (Phase-2)](#output-schema-phase-2)
5. [Hybrid Matching Strategy (Upgraded)](#hybrid-matching-strategy-upgraded)
6. [Status Resolution Rules](#status-resolution-rules)
7. [Category Reconciliation](#category-reconciliation)
8. [Financial Output (Final)](#financial-output-final)
9. [Worked Example](#worked-example)
10. [Implementation Roadmap](#implementation-roadmap)

---

## 🎯 Phase-2 Goals (Strict)

### 1️⃣ Aggregation Layer (Non-Destructive)

**Principle:** Aggregate items AFTER Phase-1 listing is complete

**Grouping Strategy:**
- **Primary Key:** Normalized item name
- **Secondary Key:** Final matched reference (if any)
- **Tertiary Key:** Category

**Preservation Guarantee:**
- Show aggregate totals
- Show contributing line-items (no deletion)
- Full breakdown for every aggregated group

**Example:**
```
NICORANDIL 5MG (x4 occurrences)
  Total Bill: ₹78.80
  Allowed (per unit): ₹49.25
  Applied Allowed: ₹49.25 × 4 = ₹197.00
  Status: ✅ GREEN
  
  Breakdown:
    - LineItemID: item_001 | Bill: ₹19.70 | Qty: 1
    - LineItemID: item_002 | Bill: ₹19.70 | Qty: 1
    - LineItemID: item_003 | Bill: ₹19.70 | Qty: 1
    - LineItemID: item_004 | Bill: ₹19.70 | Qty: 1
```

---

### 2️⃣ Allowed Rate Re-use Logic

**Caching Strategy:**
- If same normalized item matches same reference code → **cache & reuse**
- Do NOT re-infer pricing for duplicates
- Single reference match → apply to all occurrences

**Implementation:**
```python
# Pseudo-code
rate_cache = {}  # Key: (normalized_item, matched_reference)

for item in phase1_items:
    cache_key = (item.normalized_name, item.matched_reference)
    
    if cache_key in rate_cache:
        # Re-use cached rate
        item.allowed_rate = rate_cache[cache_key]
    else:
        # First occurrence - fetch and cache
        rate = fetch_allowed_rate(item)
        rate_cache[cache_key] = rate
        item.allowed_rate = rate
```

---

### 3️⃣ Hybrid Matching Strategy (Upgrade)

**Current (Phase-1):**
- Semantic similarity: 60%
- Token overlap: 30%
- Containment: 10%

**Phase-2 Enhancement:**
- **Semantic similarity** (embedding): 50%
- **Token overlap** (Jaccard): 25%
- **Medical keyword anchors**: 25%
  - Dosage patterns (5mg, 10ml, 500mg)
  - Modality keywords (MRI, CT, X-Ray, Ultrasound)
  - Body part keywords (brain, chest, abdomen, cardiac)

**Scoring Formula:**
```python
final_score = (
    0.50 * semantic_similarity +
    0.25 * token_overlap +
    0.25 * medical_anchor_score
)

# Medical anchor score calculation
def calculate_medical_anchor_score(bill_item, tieup_item):
    """
    Check for medical-specific anchors:
    - Dosage match (e.g., "5mg" in both)
    - Modality match (e.g., "MRI" in both)
    - Body part match (e.g., "brain" in both)
    """
    score = 0.0
    
    # Dosage pattern match (+0.4 if found in both)
    if has_dosage_match(bill_item, tieup_item):
        score += 0.4
    
    # Modality match (+0.3 if found in both)
    if has_modality_match(bill_item, tieup_item):
        score += 0.3
    
    # Body part match (+0.3 if found in both)
    if has_bodypart_match(bill_item, tieup_item):
        score += 0.3
    
    return min(score, 1.0)  # Cap at 1.0
```

**Weight Rationale:**
- **Semantic (50%):** Core meaning, handles synonyms
- **Token (25%):** Exact term matching, handles abbreviations
- **Medical Anchors (25%):** Domain-specific precision (dosage, modality, anatomy)

---

### 4️⃣ Status Resolution Rules

**After aggregation, assign final status per group:**

| Condition | Final Status | Example |
|-----------|--------------|---------|
| Any RED present | ❌ RED | 3 GREEN + 1 RED → RED |
| Only GREEN + Allowed-Not-Comparable | ✅ GREEN | 4 GREEN + 1 ADMIN → GREEN |
| Only MISMATCH | ⚠️ MISMATCH | All items unmatched |
| Admin / Artifact only | ⚪ IGNORED | Only admin charges |

**Logic:**
```python
def resolve_aggregate_status(line_items):
    """
    Resolve final status for aggregated group.
    Priority: RED > MISMATCH > GREEN > ALLOWED_NOT_COMPARABLE > IGNORED
    """
    statuses = [item.status for item in line_items]
    
    if VerificationStatus.RED in statuses:
        return VerificationStatus.RED
    elif VerificationStatus.MISMATCH in statuses:
        return VerificationStatus.MISMATCH
    elif VerificationStatus.GREEN in statuses:
        return VerificationStatus.GREEN
    elif VerificationStatus.ALLOWED_NOT_COMPARABLE in statuses:
        return VerificationStatus.ALLOWED_NOT_COMPARABLE
    else:
        return VerificationStatus.IGNORED_ARTIFACT
```

---

### 5️⃣ Category Reconciliation

**Strategy:** Even if item fails in original category, attempt best alternative

**Process:**
1. Try original category (Phase-1 behavior)
2. If MISMATCH → try all other categories
3. Pick best match across all categories
4. Record reconciliation path

**Output Fields:**
- `original_category`: Category from bill
- `attempted_categories`: List of categories tried
- `final_category`: Category where match was found (or best attempt)

**Example:**
```json
{
  "item": "CROSS CONSULTATION – IP",
  "original_category": "consultation",
  "attempted_categories": ["consultation", "specialist_consultation", "inpatient_services"],
  "final_category": "specialist_consultation",
  "final_match": "Specialist Consultation - Inpatient",
  "reconciliation_note": "Found in alternative category after original failed"
}
```

---

### 6️⃣ Explicit Ignore Rules

**Hard-exclude from pricing logic (but still list):**

| Pattern | Status | Example |
|---------|--------|---------|
| OCR artifacts | IGNORED_ARTIFACT | "Page 1 of 2" |
| Contact info | IGNORED_ARTIFACT | "Ph: +91-9876543210" |
| App download text | IGNORED_ARTIFACT | "Download our app" |
| Email/phone/headers | IGNORED_ARTIFACT | "info@hospital.com" |
| Bill metadata | IGNORED_ARTIFACT | "Bill No: 12345" |

**Detection Patterns:**
```python
IGNORE_PATTERNS = [
    r'page\s+\d+\s+of\s+\d+',           # Page numbers
    r'\+?\d{2,3}[-.\s]?\d{10}',         # Phone numbers
    r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}',  # Emails
    r'download\s+(our\s+)?app',         # App prompts
    r'bill\s+(no|number|#)',            # Bill metadata
    r'date[:\s]+\d{2}[/-]\d{2}',        # Date headers
]

def is_artifact(item_name):
    """Check if item is an OCR/admin artifact."""
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, item_name, re.IGNORECASE):
            return True
    return False
```

---

### 7️⃣ Mismatch Deep-Explainability (Mandatory)

**For every MISMATCH or Allowed-Not-Comparable, output:**

```python
class MismatchDiagnosticsV2(BaseModel):
    """Enhanced diagnostics for Phase-2."""
    normalized_item_name: str
    best_candidate: Optional[str] = None  # If similarity > 0.5
    best_candidate_similarity: Optional[float] = None
    category_attempted: str
    all_categories_tried: List[str]  # Phase-2: Show reconciliation attempts
    failure_reason: FailureReason
    hybrid_score_breakdown: Optional[dict] = None  # Phase-2: Show scoring details
    
    # Example:
    # {
    #   "normalized_item_name": "consultation_cross",
    #   "best_candidate": "Specialist Consultation",
    #   "best_candidate_similarity": 0.61,
    #   "category_attempted": "consultation",
    #   "all_categories_tried": ["consultation", "specialist_consultation"],
    #   "failure_reason": "NOT_IN_TIEUP",
    #   "hybrid_score_breakdown": {
    #     "semantic": 0.61,
    #     "token_overlap": 0.33,
    #     "medical_anchors": 0.0,
    #     "final_score": 0.52
    #   }
    # }
```

**Display Format:**
```
⚠️ MISMATCH: CROSS CONSULTATION – IP
   Normalized: consultation_cross
   Best Candidate: Specialist Consultation (similarity: 0.61)
   Category Tried: consultation
   All Attempts: consultation → specialist_consultation → inpatient_services
   Failure Reason: NOT_IN_TIEUP
   Hybrid Score: 0.52 (semantic=0.61, token=0.33, medical=0.0)
   Bill: ₹2500.00, Allowed: N/A, Extra: N/A
```

---

### 8️⃣ Package Handling (Phase-2 Rule)

**Package items:**
- Remain non-comparable (cannot break down pricing)
- Must still contribute to totals
- Must NOT absorb or hide individual items

**Status:** `ALLOWED_NOT_COMPARABLE (PACKAGE_ONLY)`

**Example:**
```json
{
  "item": "ICU Package - 24 Hours",
  "status": "ALLOWED_NOT_COMPARABLE",
  "failure_reason": "PACKAGE_ONLY",
  "bill_amount": 15000.00,
  "allowed_amount": 0.0,
  "extra_amount": 0.0,
  "note": "Package pricing - individual item breakdown not available"
}
```

---

### 9️⃣ Financial Output (Final)

**Three levels of totals:**

#### **Level 1: Line-Item Totals (Phase-1 Preserved)**
```json
{
  "line_items": [
    {"id": "item_001", "name": "NICORANDIL 5MG", "bill": 19.70, "allowed": 49.25, "extra": 0.0},
    {"id": "item_002", "name": "NICORANDIL 5MG", "bill": 19.70, "allowed": 49.25, "extra": 0.0},
    {"id": "item_003", "name": "NICORANDIL 5MG", "bill": 19.70, "allowed": 49.25, "extra": 0.0},
    {"id": "item_004", "name": "NICORANDIL 5MG", "bill": 19.70, "allowed": 49.25, "extra": 0.0}
  ]
}
```

#### **Level 2: Aggregated Item Totals**
```json
{
  "aggregated_items": [
    {
      "normalized_name": "nicorandil_5mg",
      "matched_reference": "NICORANDIL 5MG",
      "occurrences": 4,
      "total_bill": 78.80,
      "allowed_per_unit": 49.25,
      "total_allowed": 197.00,
      "total_extra": 0.0,
      "status": "GREEN",
      "line_item_ids": ["item_001", "item_002", "item_003", "item_004"]
    }
  ]
}
```

#### **Level 3: Category Totals**
```json
{
  "category_totals": [
    {
      "category": "medicines",
      "total_bill": 1250.00,
      "total_allowed": 1100.00,
      "total_extra": 150.00,
      "green_count": 12,
      "red_count": 3,
      "mismatch_count": 1
    }
  ]
}
```

#### **Level 4: Grand Totals**
```json
{
  "grand_totals": {
    "total_bill": 45670.00,
    "total_allowed": 38500.00,
    "total_extra": 7170.00,
    "total_allowed_not_comparable": 15000.00,
    "green_count": 45,
    "red_count": 12,
    "mismatch_count": 5,
    "ignored_count": 3
  }
}
```

---

### 🔟 Output Guarantees

✅ **No item disappears** between Phase-1 and Phase-2  
✅ **Aggregation is explainable** and reversible  
✅ **Debug-friendly:** Every number traces back to line items  
✅ **Audit-ready:** Full reconciliation path visible  

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      PHASE-1 OUTPUT                         │
│  (Exhaustive item-level listing with hybrid matching)      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  PHASE-2 AGGREGATION LAYER                  │
│                                                             │
│  ┌───────────────────────────────────────────────────┐     │
│  │  1. Rate Cache Builder                            │     │
│  │     - Group by (normalized_name, matched_ref)     │     │
│  │     - Cache allowed rates                         │     │
│  └───────────────────────────────────────────────────┘     │
│                            │                                │
│                            ▼                                │
│  ┌───────────────────────────────────────────────────┐     │
│  │  2. Item Aggregator                               │     │
│  │     - Group line items                            │     │
│  │     - Calculate aggregate totals                  │     │
│  │     - Preserve line-item breakdown                │     │
│  └───────────────────────────────────────────────────┘     │
│                            │                                │
│                            ▼                                │
│  ┌───────────────────────────────────────────────────┐     │
│  │  3. Status Resolver                               │     │
│  │     - Apply resolution rules                      │     │
│  │     - Handle RED propagation                      │     │
│  │     - Mark IGNORED items                          │     │
│  └───────────────────────────────────────────────────┘     │
│                            │                                │
│                            ▼                                │
│  ┌───────────────────────────────────────────────────┐     │
│  │  4. Category Reconciler                           │     │
│  │     - Retry failed items in other categories      │     │
│  │     - Track reconciliation path                   │     │
│  │     - Update diagnostics                          │     │
│  └───────────────────────────────────────────────────┘     │
│                            │                                │
│                            ▼                                │
│  ┌───────────────────────────────────────────────────┐     │
│  │  5. Financial Aggregator                          │     │
│  │     - Calculate category totals                   │     │
│  │     - Calculate grand totals                      │     │
│  │     - Generate financial summary                  │     │
│  └───────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    PHASE-2 OUTPUT                           │
│  (Clinically meaningful, financially auditable comparison)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📐 Updated Processing Logic

### **Phase-2 Processing Pipeline**

```python
def process_phase2(phase1_response: VerificationResponse) -> Phase2Response:
    """
    Transform Phase-1 output into Phase-2 aggregated comparison.
    
    Args:
        phase1_response: Complete Phase-1 verification response
        
    Returns:
        Phase2Response with aggregated, reconciled, and financially summarized data
    """
    
    # Step 1: Build rate cache
    rate_cache = build_rate_cache(phase1_response)
    
    # Step 2: Aggregate items
    aggregated_items = aggregate_line_items(
        phase1_response=phase1_response,
        rate_cache=rate_cache
    )
    
    # Step 3: Resolve statuses
    for agg_item in aggregated_items:
        agg_item.status = resolve_aggregate_status(agg_item.line_items)
    
    # Step 4: Category reconciliation (for MISMATCH items)
    reconciled_items = reconcile_categories(
        aggregated_items=aggregated_items,
        rate_cache=rate_cache
    )
    
    # Step 5: Calculate financial totals
    financial_summary = calculate_financial_summary(reconciled_items)
    
    # Step 6: Build Phase-2 response
    return Phase2Response(
        phase1_data=phase1_response,  # Preserve original
        aggregated_items=reconciled_items,
        financial_summary=financial_summary,
        metadata=build_metadata()
    )
```

### **Step 1: Build Rate Cache**

```python
def build_rate_cache(phase1_response: VerificationResponse) -> Dict[Tuple[str, str], float]:
    """
    Build cache of allowed rates for matched items.
    
    Cache Key: (normalized_item_name, matched_reference)
    Cache Value: allowed_rate
    """
    rate_cache = {}
    
    for category_result in phase1_response.results:
        for item_result in category_result.items:
            # Only cache successfully matched items
            if item_result.matched_item and item_result.status in [
                VerificationStatus.GREEN,
                VerificationStatus.RED
            ]:
                cache_key = (
                    item_result.normalized_item_name,
                    item_result.matched_item
                )
                
                # Calculate per-unit rate
                rate_cache[cache_key] = item_result.allowed_amount
    
    logger.info(f"Built rate cache with {len(rate_cache)} entries")
    return rate_cache
```

### **Step 2: Aggregate Line Items**

```python
def aggregate_line_items(
    phase1_response: VerificationResponse,
    rate_cache: Dict[Tuple[str, str], float]
) -> List[AggregatedItem]:
    """
    Group line items by (normalized_name, matched_reference, category).
    """
    aggregation_map = defaultdict(list)
    
    for category_result in phase1_response.results:
        for item_result in category_result.items:
            # Group key
            group_key = (
                item_result.normalized_item_name or item_result.bill_item,
                item_result.matched_item,
                category_result.category
            )
            
            aggregation_map[group_key].append(item_result)
    
    # Build aggregated items
    aggregated_items = []
    for group_key, line_items in aggregation_map.items():
        normalized_name, matched_ref, category = group_key
        
        # Calculate totals
        total_bill = sum(item.bill_amount for item in line_items)
        total_allowed = sum(item.allowed_amount for item in line_items)
        total_extra = sum(item.extra_amount for item in line_items)
        
        # Get cached rate (if available)
        cache_key = (normalized_name, matched_ref)
        allowed_per_unit = rate_cache.get(cache_key, 0.0)
        
        aggregated_items.append(AggregatedItem(
            normalized_name=normalized_name,
            matched_reference=matched_ref,
            category=category,
            occurrences=len(line_items),
            total_bill=total_bill,
            allowed_per_unit=allowed_per_unit,
            total_allowed=total_allowed,
            total_extra=total_extra,
            line_items=line_items,  # Preserve breakdown
            status=None  # Will be resolved in next step
        ))
    
    return aggregated_items
```

### **Step 3: Resolve Aggregate Status**

```python
def resolve_aggregate_status(line_items: List[ItemVerificationResult]) -> VerificationStatus:
    """
    Resolve final status for aggregated group.
    Priority: RED > MISMATCH > GREEN > ALLOWED_NOT_COMPARABLE > IGNORED
    """
    statuses = [item.status for item in line_items]
    
    # Check for artifacts first
    if all(is_artifact(item.bill_item) for item in line_items):
        return VerificationStatus.IGNORED_ARTIFACT
    
    # Priority-based resolution
    if VerificationStatus.RED in statuses:
        return VerificationStatus.RED
    elif VerificationStatus.MISMATCH in statuses:
        return VerificationStatus.MISMATCH
    elif VerificationStatus.GREEN in statuses:
        return VerificationStatus.GREEN
    elif VerificationStatus.ALLOWED_NOT_COMPARABLE in statuses:
        return VerificationStatus.ALLOWED_NOT_COMPARABLE
    else:
        return VerificationStatus.IGNORED_ARTIFACT
```

### **Step 4: Category Reconciliation**

```python
def reconcile_categories(
    aggregated_items: List[AggregatedItem],
    rate_cache: Dict[Tuple[str, str], float]
) -> List[AggregatedItem]:
    """
    For MISMATCH items, attempt matching in alternative categories.
    """
    reconciled_items = []
    
    for agg_item in aggregated_items:
        if agg_item.status == VerificationStatus.MISMATCH:
            # Try alternative categories
            best_match = try_alternative_categories(
                item=agg_item,
                rate_cache=rate_cache
            )
            
            if best_match:
                # Update with reconciled match
                agg_item.matched_reference = best_match.matched_item
                agg_item.category = best_match.category
                agg_item.status = best_match.status
                agg_item.reconciliation_note = (
                    f"Found in alternative category '{best_match.category}' "
                    f"after original category '{agg_item.original_category}' failed"
                )
        
        reconciled_items.append(agg_item)
    
    return reconciled_items


def try_alternative_categories(
    item: AggregatedItem,
    rate_cache: Dict[Tuple[str, str], float]
) -> Optional[ItemMatch]:
    """
    Try matching item in all available categories.
    """
    matcher = get_matcher()
    best_match = None
    best_score = 0.0
    
    # Get all available categories from rate sheets
    all_categories = matcher.get_all_categories()
    
    for category in all_categories:
        if category == item.category:
            continue  # Skip original category
        
        # Try matching in this category
        match_result = matcher.match_item(
            item_name=item.normalized_name,
            hospital_name=item.hospital_name,
            category_name=category,
            threshold=ITEM_SIMILARITY_THRESHOLD
        )
        
        if match_result.is_match and match_result.similarity > best_score:
            best_match = match_result
            best_score = match_result.similarity
    
    return best_match
```

### **Step 5: Calculate Financial Summary**

```python
def calculate_financial_summary(
    aggregated_items: List[AggregatedItem]
) -> FinancialSummary:
    """
    Calculate category-level and grand totals.
    """
    # Category totals
    category_map = defaultdict(lambda: {
        'total_bill': 0.0,
        'total_allowed': 0.0,
        'total_extra': 0.0,
        'green_count': 0,
        'red_count': 0,
        'mismatch_count': 0
    })
    
    for agg_item in aggregated_items:
        cat_data = category_map[agg_item.category]
        cat_data['total_bill'] += agg_item.total_bill
        cat_data['total_allowed'] += agg_item.total_allowed
        cat_data['total_extra'] += agg_item.total_extra
        
        if agg_item.status == VerificationStatus.GREEN:
            cat_data['green_count'] += 1
        elif agg_item.status == VerificationStatus.RED:
            cat_data['red_count'] += 1
        elif agg_item.status == VerificationStatus.MISMATCH:
            cat_data['mismatch_count'] += 1
    
    # Grand totals
    grand_totals = {
        'total_bill': sum(item.total_bill for item in aggregated_items),
        'total_allowed': sum(item.total_allowed for item in aggregated_items),
        'total_extra': sum(item.total_extra for item in aggregated_items),
        'total_allowed_not_comparable': sum(
            item.total_bill for item in aggregated_items
            if item.status == VerificationStatus.ALLOWED_NOT_COMPARABLE
        ),
        'green_count': sum(1 for item in aggregated_items if item.status == VerificationStatus.GREEN),
        'red_count': sum(1 for item in aggregated_items if item.status == VerificationStatus.RED),
        'mismatch_count': sum(1 for item in aggregated_items if item.status == VerificationStatus.MISMATCH),
        'ignored_count': sum(1 for item in aggregated_items if item.status == VerificationStatus.IGNORED_ARTIFACT)
    }
    
    return FinancialSummary(
        category_totals=category_map,
        grand_totals=grand_totals
    )
```

---

## 📊 Output Schema (Phase-2)

### **Enhanced Models**

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


class VerificationStatus(str, Enum):
    """Extended status for Phase-2."""
    GREEN = "GREEN"
    RED = "RED"
    MISMATCH = "MISMATCH"
    ALLOWED_NOT_COMPARABLE = "ALLOWED_NOT_COMPARABLE"
    IGNORED_ARTIFACT = "IGNORED_ARTIFACT"  # NEW in Phase-2


class FailureReason(str, Enum):
    """Failure reasons for diagnostics."""
    NOT_IN_TIEUP = "NOT_IN_TIEUP"
    LOW_SIMILARITY = "LOW_SIMILARITY"
    PACKAGE_ONLY = "PACKAGE_ONLY"
    ADMIN_CHARGE = "ADMIN_CHARGE"


class MismatchDiagnosticsV2(BaseModel):
    """Enhanced diagnostics for Phase-2."""
    normalized_item_name: str
    best_candidate: Optional[str] = None
    best_candidate_similarity: Optional[float] = None
    category_attempted: str
    all_categories_tried: List[str] = Field(default_factory=list)  # Phase-2
    failure_reason: FailureReason
    hybrid_score_breakdown: Optional[Dict[str, float]] = None  # Phase-2


class AggregatedItem(BaseModel):
    """Aggregated item with line-item breakdown."""
    normalized_name: str
    matched_reference: Optional[str] = None
    category: str
    original_category: Optional[str] = None  # For reconciliation tracking
    
    # Aggregation data
    occurrences: int
    total_bill: float
    allowed_per_unit: float
    total_allowed: float
    total_extra: float
    
    # Status
    status: VerificationStatus
    
    # Breakdown (preserve Phase-1 data)
    line_items: List[ItemVerificationResult] = Field(default_factory=list)
    
    # Reconciliation
    reconciliation_note: Optional[str] = None
    
    # Diagnostics (for MISMATCH/ALLOWED_NOT_COMPARABLE)
    diagnostics: Optional[MismatchDiagnosticsV2] = None


class CategoryTotals(BaseModel):
    """Financial totals for a category."""
    category: str
    total_bill: float
    total_allowed: float
    total_extra: float
    green_count: int
    red_count: int
    mismatch_count: int
    ignored_count: int = 0


class GrandTotals(BaseModel):
    """Overall financial summary."""
    total_bill: float
    total_allowed: float
    total_extra: float
    total_allowed_not_comparable: float
    green_count: int
    red_count: int
    mismatch_count: int
    ignored_count: int


class FinancialSummary(BaseModel):
    """Complete financial breakdown."""
    category_totals: List[CategoryTotals]
    grand_totals: GrandTotals


class Phase2Response(BaseModel):
    """Complete Phase-2 verification response."""
    # Hospital matching (from Phase-1)
    hospital: str
    matched_hospital: Optional[str] = None
    hospital_similarity: Optional[float] = None
    
    # Phase-1 data (preserved for traceability)
    phase1_line_items: List[ItemVerificationResult] = Field(default_factory=list)
    
    # Phase-2 aggregated data
    aggregated_items: List[AggregatedItem] = Field(default_factory=list)
    
    # Financial summary
    financial_summary: FinancialSummary
    
    # Metadata
    processing_metadata: Dict[str, any] = Field(default_factory=dict)
```

---

## 🔬 Hybrid Matching Strategy (Upgraded)

### **Medical Keyword Anchors**

```python
import re
from typing import Tuple


# Medical keyword dictionaries
DOSAGE_PATTERNS = [
    r'\d+\s*mg',      # 5mg, 10 mg
    r'\d+\s*ml',      # 10ml, 5 ml
    r'\d+\s*mcg',     # 500mcg
    r'\d+\s*iu',      # 1000iu
    r'\d+\s*%',       # 5% (concentration)
]

MODALITY_KEYWORDS = {
    'mri', 'ct', 'xray', 'x-ray', 'ultrasound', 'usg',
    'ecg', 'eeg', 'echo', 'endoscopy', 'colonoscopy',
    'mammography', 'pet', 'scan'
}

BODYPART_KEYWORDS = {
    'brain', 'head', 'chest', 'abdomen', 'cardiac', 'heart',
    'lung', 'liver', 'kidney', 'spine', 'knee', 'shoulder',
    'pelvis', 'neck', 'back', 'ankle', 'wrist'
}


def extract_dosage(text: str) -> Optional[str]:
    """Extract dosage pattern from text."""
    for pattern in DOSAGE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).lower().replace(' ', '')
    return None


def extract_modality(text: str) -> Optional[str]:
    """Extract modality keyword from text."""
    text_lower = text.lower()
    for modality in MODALITY_KEYWORDS:
        if modality in text_lower:
            return modality
    return None


def extract_bodypart(text: str) -> Optional[str]:
    """Extract body part keyword from text."""
    text_lower = text.lower()
    for bodypart in BODYPART_KEYWORDS:
        if bodypart in text_lower:
            return bodypart
    return None


def calculate_medical_anchor_score(bill_item: str, tieup_item: str) -> Tuple[float, dict]:
    """
    Calculate medical anchor score based on domain-specific matches.
    
    Returns:
        Tuple of (score, breakdown_dict)
    """
    breakdown = {
        'dosage_match': False,
        'modality_match': False,
        'bodypart_match': False,
        'score': 0.0
    }
    
    score = 0.0
    
    # Dosage match (+0.4)
    bill_dosage = extract_dosage(bill_item)
    tieup_dosage = extract_dosage(tieup_item)
    if bill_dosage and tieup_dosage and bill_dosage == tieup_dosage:
        score += 0.4
        breakdown['dosage_match'] = True
    
    # Modality match (+0.3)
    bill_modality = extract_modality(bill_item)
    tieup_modality = extract_modality(tieup_item)
    if bill_modality and tieup_modality and bill_modality == tieup_modality:
        score += 0.3
        breakdown['modality_match'] = True
    
    # Body part match (+0.3)
    bill_bodypart = extract_bodypart(bill_item)
    tieup_bodypart = extract_bodypart(tieup_item)
    if bill_bodypart and tieup_bodypart and bill_bodypart == tieup_bodypart:
        score += 0.3
        breakdown['bodypart_match'] = True
    
    breakdown['score'] = min(score, 1.0)  # Cap at 1.0
    return breakdown['score'], breakdown


def calculate_hybrid_score_v2(
    bill_item: str,
    tieup_item: str,
    semantic_similarity: float,
    weights: dict = None
) -> Tuple[float, dict]:
    """
    Phase-2 hybrid scoring with medical anchors.
    
    Args:
        bill_item: Normalized bill item text
        tieup_item: Normalized tie-up item text
        semantic_similarity: Semantic similarity score (0.0 to 1.0)
        weights: Optional custom weights
        
    Returns:
        Tuple of (final_score, breakdown_dict)
    """
    if weights is None:
        weights = {
            "semantic": 0.50,
            "token": 0.25,
            "medical_anchors": 0.25
        }
    
    # Calculate all metrics
    from app.verifier.partial_matcher import calculate_token_overlap
    
    token_overlap = calculate_token_overlap(bill_item, tieup_item)
    medical_anchor_score, medical_breakdown = calculate_medical_anchor_score(bill_item, tieup_item)
    
    # Weighted combination
    final_score = (
        weights["semantic"] * semantic_similarity +
        weights["token"] * token_overlap +
        weights["medical_anchors"] * medical_anchor_score
    )
    
    breakdown = {
        "semantic": semantic_similarity,
        "token_overlap": token_overlap,
        "medical_anchors": medical_anchor_score,
        "medical_breakdown": medical_breakdown,
        "final_score": final_score,
        "weights": weights
    }
    
    return final_score, breakdown
```

---

## 📈 Worked Example

### **Input: Hospital Bill (Phase-1 Output)**

```json
{
  "hospital": "Apollo Hospital",
  "matched_hospital": "Apollo Hospital - Chennai",
  "results": [
    {
      "category": "medicines",
      "items": [
        {"bill_item": "NICORANDIL 5MG", "matched_item": "NICORANDIL 5MG", "status": "GREEN", "bill_amount": 19.70, "allowed_amount": 49.25, "normalized_item_name": "nicorandil_5mg"},
        {"bill_item": "NICORANDIL 5MG", "matched_item": "NICORANDIL 5MG", "status": "GREEN", "bill_amount": 19.70, "allowed_amount": 49.25, "normalized_item_name": "nicorandil_5mg"},
        {"bill_item": "NICORANDIL 5MG", "matched_item": "NICORANDIL 5MG", "status": "GREEN", "bill_amount": 19.70, "allowed_amount": 49.25, "normalized_item_name": "nicorandil_5mg"},
        {"bill_item": "NICORANDIL 5MG", "matched_item": "NICORANDIL 5MG", "status": "GREEN", "bill_amount": 19.70, "allowed_amount": 49.25, "normalized_item_name": "nicorandil_5mg"},
        {"bill_item": "PARACETAMOL 500MG", "matched_item": "PARACETAMOL 500MG", "status": "RED", "bill_amount": 25.00, "allowed_amount": 15.00, "extra_amount": 10.00, "normalized_item_name": "paracetamol_500mg"}
      ]
    },
    {
      "category": "diagnostics",
      "items": [
        {"bill_item": "MRI BRAIN", "matched_item": "MRI Brain", "status": "RED", "bill_amount": 10770.00, "allowed_amount": 8500.00, "extra_amount": 2270.00, "normalized_item_name": "mri_brain"},
        {"bill_item": "CONSULTATION - FIRST VISIT", "matched_item": "Consultation", "status": "GREEN", "bill_amount": 1500.00, "allowed_amount": 1500.00, "normalized_item_name": "consultation_first_visit"},
        {"bill_item": "CROSS CONSULTATION - IP", "matched_item": null, "status": "MISMATCH", "bill_amount": 2500.00, "normalized_item_name": "cross_consultation_ip", "diagnostics": {"failure_reason": "NOT_IN_TIEUP"}}
      ]
    }
  ]
}
```

---

### **Phase-2 Processing**

#### **Step 1: Build Rate Cache**

```python
rate_cache = {
    ("nicorandil_5mg", "NICORANDIL 5MG"): 49.25,
    ("paracetamol_500mg", "PARACETAMOL 500MG"): 15.00,
    ("mri_brain", "MRI Brain"): 8500.00,
    ("consultation_first_visit", "Consultation"): 1500.00
}
```

#### **Step 2: Aggregate Items**

```python
aggregated_items = [
    {
        "normalized_name": "nicorandil_5mg",
        "matched_reference": "NICORANDIL 5MG",
        "category": "medicines",
        "occurrences": 4,
        "total_bill": 78.80,
        "allowed_per_unit": 49.25,
        "total_allowed": 197.00,
        "total_extra": 0.0,
        "line_items": [/* 4 line items */]
    },
    {
        "normalized_name": "paracetamol_500mg",
        "matched_reference": "PARACETAMOL 500MG",
        "category": "medicines",
        "occurrences": 1,
        "total_bill": 25.00,
        "allowed_per_unit": 15.00,
        "total_allowed": 15.00,
        "total_extra": 10.00,
        "line_items": [/* 1 line item */]
    },
    {
        "normalized_name": "mri_brain",
        "matched_reference": "MRI Brain",
        "category": "diagnostics",
        "occurrences": 1,
        "total_bill": 10770.00,
        "allowed_per_unit": 8500.00,
        "total_allowed": 8500.00,
        "total_extra": 2270.00,
        "line_items": [/* 1 line item */]
    },
    {
        "normalized_name": "consultation_first_visit",
        "matched_reference": "Consultation",
        "category": "diagnostics",
        "occurrences": 1,
        "total_bill": 1500.00,
        "allowed_per_unit": 1500.00,
        "total_allowed": 1500.00,
        "total_extra": 0.0,
        "line_items": [/* 1 line item */]
    },
    {
        "normalized_name": "cross_consultation_ip",
        "matched_reference": null,
        "category": "diagnostics",
        "occurrences": 1,
        "total_bill": 2500.00,
        "allowed_per_unit": 0.0,
        "total_allowed": 0.0,
        "total_extra": 0.0,
        "line_items": [/* 1 line item */]
    }
]
```

#### **Step 3: Resolve Statuses**

```python
# NICORANDIL 5MG: All GREEN → GREEN
# PARACETAMOL 500MG: RED → RED
# MRI BRAIN: RED → RED
# CONSULTATION: GREEN → GREEN
# CROSS CONSULTATION: MISMATCH → MISMATCH (will try reconciliation)
```

#### **Step 4: Category Reconciliation**

```python
# Try "CROSS CONSULTATION - IP" in alternative categories
# Attempt 1: "consultation" → No match
# Attempt 2: "specialist_consultation" → Match found!
#   - Matched: "Specialist Consultation - Inpatient"
#   - Similarity: 0.78
#   - Hybrid Score: 0.82 (semantic=0.78, token=0.67, medical=0.0)
#   - Status: GREEN (bill=2500, allowed=2500)

# Update item
{
    "normalized_name": "cross_consultation_ip",
    "matched_reference": "Specialist Consultation - Inpatient",
    "category": "specialist_consultation",
    "original_category": "diagnostics",
    "status": "GREEN",
    "reconciliation_note": "Found in alternative category 'specialist_consultation' after original category 'diagnostics' failed"
}
```

#### **Step 5: Calculate Financial Summary**

```python
financial_summary = {
    "category_totals": [
        {
            "category": "medicines",
            "total_bill": 103.80,
            "total_allowed": 212.00,
            "total_extra": 10.00,
            "green_count": 1,  # NICORANDIL (aggregated)
            "red_count": 1,    # PARACETAMOL
            "mismatch_count": 0
        },
        {
            "category": "diagnostics",
            "total_bill": 12270.00,
            "total_allowed": 10000.00,
            "total_extra": 2270.00,
            "green_count": 1,  # CONSULTATION
            "red_count": 1,    # MRI BRAIN
            "mismatch_count": 0
        },
        {
            "category": "specialist_consultation",
            "total_bill": 2500.00,
            "total_allowed": 2500.00,
            "total_extra": 0.0,
            "green_count": 1,  # CROSS CONSULTATION (reconciled)
            "red_count": 0,
            "mismatch_count": 0
        }
    ],
    "grand_totals": {
        "total_bill": 14873.80,
        "total_allowed": 12712.00,
        "total_extra": 2280.00,
        "total_allowed_not_comparable": 0.0,
        "green_count": 3,
        "red_count": 2,
        "mismatch_count": 0,
        "ignored_count": 0
    }
}
```

---

### **Phase-2 Output (Final)**

```json
{
  "hospital": "Apollo Hospital",
  "matched_hospital": "Apollo Hospital - Chennai",
  "hospital_similarity": 0.98,
  
  "aggregated_items": [
    {
      "normalized_name": "nicorandil_5mg",
      "matched_reference": "NICORANDIL 5MG",
      "category": "medicines",
      "occurrences": 4,
      "total_bill": 78.80,
      "allowed_per_unit": 49.25,
      "total_allowed": 197.00,
      "total_extra": 0.0,
      "status": "GREEN",
      "line_items": [
        {"bill_item": "NICORANDIL 5MG", "bill_amount": 19.70, "allowed_amount": 49.25},
        {"bill_item": "NICORANDIL 5MG", "bill_amount": 19.70, "allowed_amount": 49.25},
        {"bill_item": "NICORANDIL 5MG", "bill_amount": 19.70, "allowed_amount": 49.25},
        {"bill_item": "NICORANDIL 5MG", "bill_amount": 19.70, "allowed_amount": 49.25}
      ]
    },
    {
      "normalized_name": "paracetamol_500mg",
      "matched_reference": "PARACETAMOL 500MG",
      "category": "medicines",
      "occurrences": 1,
      "total_bill": 25.00,
      "allowed_per_unit": 15.00,
      "total_allowed": 15.00,
      "total_extra": 10.00,
      "status": "RED",
      "line_items": [
        {"bill_item": "PARACETAMOL 500MG", "bill_amount": 25.00, "allowed_amount": 15.00, "extra_amount": 10.00}
      ]
    },
    {
      "normalized_name": "mri_brain",
      "matched_reference": "MRI Brain",
      "category": "diagnostics",
      "occurrences": 1,
      "total_bill": 10770.00,
      "allowed_per_unit": 8500.00,
      "total_allowed": 8500.00,
      "total_extra": 2270.00,
      "status": "RED",
      "line_items": [
        {"bill_item": "MRI BRAIN", "bill_amount": 10770.00, "allowed_amount": 8500.00, "extra_amount": 2270.00}
      ]
    },
    {
      "normalized_name": "consultation_first_visit",
      "matched_reference": "Consultation",
      "category": "diagnostics",
      "occurrences": 1,
      "total_bill": 1500.00,
      "allowed_per_unit": 1500.00,
      "total_allowed": 1500.00,
      "total_extra": 0.0,
      "status": "GREEN",
      "line_items": [
        {"bill_item": "CONSULTATION - FIRST VISIT", "bill_amount": 1500.00, "allowed_amount": 1500.00}
      ]
    },
    {
      "normalized_name": "cross_consultation_ip",
      "matched_reference": "Specialist Consultation - Inpatient",
      "category": "specialist_consultation",
      "original_category": "diagnostics",
      "occurrences": 1,
      "total_bill": 2500.00,
      "allowed_per_unit": 2500.00,
      "total_allowed": 2500.00,
      "total_extra": 0.0,
      "status": "GREEN",
      "reconciliation_note": "Found in alternative category 'specialist_consultation' after original category 'diagnostics' failed",
      "line_items": [
        {"bill_item": "CROSS CONSULTATION - IP", "bill_amount": 2500.00, "allowed_amount": 2500.00}
      ]
    }
  ],
  
  "financial_summary": {
    "category_totals": [
      {
        "category": "medicines",
        "total_bill": 103.80,
        "total_allowed": 212.00,
        "total_extra": 10.00,
        "green_count": 1,
        "red_count": 1,
        "mismatch_count": 0
      },
      {
        "category": "diagnostics",
        "total_bill": 12270.00,
        "total_allowed": 10000.00,
        "total_extra": 2270.00,
        "green_count": 1,
        "red_count": 1,
        "mismatch_count": 0
      },
      {
        "category": "specialist_consultation",
        "total_bill": 2500.00,
        "total_allowed": 2500.00,
        "total_extra": 0.0,
        "green_count": 1,
        "red_count": 0,
        "mismatch_count": 0
      }
    ],
    "grand_totals": {
      "total_bill": 14873.80,
      "total_allowed": 12712.00,
      "total_extra": 2280.00,
      "total_allowed_not_comparable": 0.0,
      "green_count": 3,
      "red_count": 2,
      "mismatch_count": 0,
      "ignored_count": 0
    }
  },
  
  "processing_metadata": {
    "phase1_items_count": 8,
    "phase2_aggregated_count": 5,
    "reconciliation_attempts": 1,
    "reconciliation_successes": 1,
    "rate_cache_size": 4
  }
}
```

---

## 🚀 Implementation Roadmap

### **Phase 2A: Core Aggregation (Week 1)**

1. **Create Phase-2 models** (`backend/app/verifier/models_v2.py`)
   - `AggregatedItem`
   - `MismatchDiagnosticsV2`
   - `FinancialSummary`
   - `Phase2Response`

2. **Implement rate cache builder** (`backend/app/verifier/aggregator.py`)
   - `build_rate_cache()`
   - Cache key: `(normalized_name, matched_reference)`

3. **Implement item aggregator**
   - `aggregate_line_items()`
   - Group by: `(normalized_name, matched_reference, category)`
   - Preserve line-item breakdown

4. **Implement status resolver**
   - `resolve_aggregate_status()`
   - Priority: RED > MISMATCH > GREEN > ALLOWED_NOT_COMPARABLE

5. **Unit tests for aggregation**
   - Test duplicate handling
   - Test status resolution
   - Test breakdown preservation

---

### **Phase 2B: Enhanced Matching (Week 2)**

1. **Implement medical anchor extraction** (`backend/app/verifier/medical_anchors.py`)
   - `extract_dosage()`
   - `extract_modality()`
   - `extract_bodypart()`

2. **Implement hybrid scoring v2** (`backend/app/verifier/partial_matcher.py`)
   - `calculate_medical_anchor_score()`
   - `calculate_hybrid_score_v2()`
   - Update weights: semantic=0.50, token=0.25, medical=0.25

3. **Update matcher to use hybrid v2**
   - Integrate medical anchors into `match_item()`
   - Log hybrid score breakdown

4. **Unit tests for medical anchors**
   - Test dosage extraction
   - Test modality extraction
   - Test hybrid scoring

---

### **Phase 2C: Category Reconciliation (Week 3)**

1. **Implement category reconciler** (`backend/app/verifier/reconciler.py`)
   - `try_alternative_categories()`
   - `reconcile_categories()`
   - Track reconciliation path

2. **Update diagnostics**
   - Add `all_categories_tried`
   - Add `hybrid_score_breakdown`
   - Add `reconciliation_note`

3. **Implement artifact detection**
   - `is_artifact()` with regex patterns
   - Mark as `IGNORED_ARTIFACT`

4. **Unit tests for reconciliation**
   - Test alternative category matching
   - Test artifact detection
   - Test diagnostics generation

---

### **Phase 2D: Financial Aggregation (Week 4)**

1. **Implement financial aggregator** (`backend/app/verifier/financial.py`)
   - `calculate_category_totals()`
   - `calculate_grand_totals()`
   - `build_financial_summary()`

2. **Implement Phase-2 orchestrator** (`backend/app/verifier/phase2_processor.py`)
   - `process_phase2()`
   - Integrate all Phase-2 components
   - Generate `Phase2Response`

3. **Update API endpoint**
   - Add `/verify/phase2` endpoint
   - Return `Phase2Response`
   - Preserve `/verify` for Phase-1 compatibility

4. **Integration tests**
   - End-to-end Phase-2 processing
   - Test with real hospital bills
   - Validate financial totals

---

### **Phase 2E: Display & Documentation (Week 5)**

1. **Update display formatter** (`backend/main.py`)
   - Format aggregated items
   - Show line-item breakdown
   - Display reconciliation notes
   - Show financial summary

2. **Create Phase-2 documentation**
   - User guide
   - API documentation
   - Migration guide (Phase-1 → Phase-2)

3. **Performance optimization**
   - Profile Phase-2 processing
   - Optimize aggregation queries
   - Cache optimization

4. **User acceptance testing**
   - Test with real bills
   - Validate against business rules
   - Gather feedback

---

## ✅ Success Criteria

### **Functional**
- ✅ No items disappear between Phase-1 and Phase-2
- ✅ Aggregation is reversible (can trace back to line items)
- ✅ Category reconciliation improves match rate by 10-15%
- ✅ Medical anchors improve matching accuracy by 5-10%
- ✅ Financial totals are accurate and auditable

### **Performance**
- ✅ Phase-2 processing adds < 500ms overhead
- ✅ Rate cache reduces redundant lookups
- ✅ Aggregation handles 1000+ line items efficiently

### **Auditability**
- ✅ Every number traces back to line items
- ✅ Reconciliation path is visible
- ✅ Hybrid score breakdown is available
- ✅ All diagnostics are comprehensive

---

## 📝 Summary

**Phase-2 delivers:**
1. ✅ **Non-destructive aggregation** with full traceability
2. ✅ **Enhanced hybrid matching** with medical anchors
3. ✅ **Category reconciliation** for failed items
4. ✅ **Multi-level financial totals** (line → aggregate → category → grand)
5. ✅ **Deep explainability** for all mismatches
6. ✅ **Artifact detection** and filtering
7. ✅ **Audit-ready output** with complete breakdown

**Ready for implementation!** 🚀

# Phase-2 Implementation Plan

## 🎯 Overview

This document provides a step-by-step implementation guide for Phase-2 of the hospital bill verification engine.

**Goal:** Transform Phase-1's exhaustive item-level output into a clinically and financially meaningful comparison layer.

**Principle:** Non-destructive aggregation with full traceability.

---

## 📦 Deliverables Checklist

- [ ] **Phase 2A:** Core Aggregation (Week 1)
- [ ] **Phase 2B:** Enhanced Matching (Week 2)
- [ ] **Phase 2C:** Category Reconciliation (Week 3)
- [ ] **Phase 2D:** Financial Aggregation (Week 4)
- [ ] **Phase 2E:** Display & Documentation (Week 5)

---

## 🏗️ Phase 2A: Core Aggregation (Week 1)

### **Task 1.1: Create Phase-2 Models**

**File:** `backend/app/verifier/models_v2.py`

**Models to Create:**

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from app.verifier.models import (
    VerificationStatus,
    FailureReason,
    ItemVerificationResult
)


class MismatchDiagnosticsV2(BaseModel):
    """Enhanced diagnostics for Phase-2."""
    normalized_item_name: str
    best_candidate: Optional[str] = None
    best_candidate_similarity: Optional[float] = None
    category_attempted: str
    all_categories_tried: List[str] = Field(default_factory=list)
    failure_reason: FailureReason
    hybrid_score_breakdown: Optional[Dict[str, float]] = None


class AggregatedItem(BaseModel):
    """Aggregated item with line-item breakdown."""
    normalized_name: str
    matched_reference: Optional[str] = None
    category: str
    original_category: Optional[str] = None
    
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
    
    # Diagnostics
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
    hospital: str
    matched_hospital: Optional[str] = None
    hospital_similarity: Optional[float] = None
    
    # Phase-1 data (preserved)
    phase1_line_items: List[ItemVerificationResult] = Field(default_factory=list)
    
    # Phase-2 aggregated data
    aggregated_items: List[AggregatedItem] = Field(default_factory=list)
    
    # Financial summary
    financial_summary: FinancialSummary
    
    # Metadata
    processing_metadata: Dict[str, any] = Field(default_factory=dict)
```

**Acceptance Criteria:**
- [ ] All models defined with proper types
- [ ] Models pass Pydantic validation
- [ ] Models are importable from `app.verifier.models_v2`

---

### **Task 1.2: Implement Rate Cache Builder**

**File:** `backend/app/verifier/aggregator.py`

**Function to Implement:**

```python
from typing import Dict, Tuple
from app.verifier.models import VerificationResponse, VerificationStatus
import logging

logger = logging.getLogger(__name__)


def build_rate_cache(
    phase1_response: VerificationResponse
) -> Dict[Tuple[str, str], float]:
    """
    Build cache of allowed rates for matched items.
    
    Cache Key: (normalized_item_name, matched_reference)
    Cache Value: allowed_rate (per unit)
    
    Args:
        phase1_response: Complete Phase-1 verification response
        
    Returns:
        Dictionary mapping (normalized_name, matched_ref) to allowed_rate
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
                    item_result.normalized_item_name or item_result.bill_item,
                    item_result.matched_item
                )
                
                # Store per-unit rate
                rate_cache[cache_key] = item_result.allowed_amount
    
    logger.info(f"Built rate cache with {len(rate_cache)} entries")
    return rate_cache
```

**Test Cases:**

```python
# test_aggregator.py
def test_build_rate_cache():
    """Test rate cache building."""
    phase1_response = create_mock_phase1_response()
    
    rate_cache = build_rate_cache(phase1_response)
    
    # Verify cache contains expected entries
    assert ("nicorandil_5mg", "NICORANDIL 5MG") in rate_cache
    assert rate_cache[("nicorandil_5mg", "NICORANDIL 5MG")] == 49.25
    
    # Verify MISMATCH items are not cached
    assert ("unknown_item", None) not in rate_cache
```

**Acceptance Criteria:**
- [ ] Function correctly caches matched items
- [ ] MISMATCH items are excluded
- [ ] Cache keys are tuples of (normalized_name, matched_ref)
- [ ] Unit tests pass

---

### **Task 1.3: Implement Item Aggregator**

**File:** `backend/app/verifier/aggregator.py`

**Function to Implement:**

```python
from collections import defaultdict
from typing import List
from app.verifier.models_v2 import AggregatedItem


def aggregate_line_items(
    phase1_response: VerificationResponse,
    rate_cache: Dict[Tuple[str, str], float]
) -> List[AggregatedItem]:
    """
    Group line items by (normalized_name, matched_reference, category).
    
    Args:
        phase1_response: Complete Phase-1 verification response
        rate_cache: Pre-built rate cache
        
    Returns:
        List of aggregated items with line-item breakdown
    """
    aggregation_map = defaultdict(list)
    
    for category_result in phase1_response.results:
        for item_result in category_result.items:
            # Group key: (normalized_name, matched_ref, category)
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
    
    logger.info(f"Aggregated {len(phase1_response.results)} line items into {len(aggregated_items)} groups")
    return aggregated_items
```

**Test Cases:**

```python
def test_aggregate_line_items():
    """Test item aggregation."""
    phase1_response = create_mock_phase1_response_with_duplicates()
    rate_cache = build_rate_cache(phase1_response)
    
    aggregated = aggregate_line_items(phase1_response, rate_cache)
    
    # Verify aggregation
    nicorandil_group = next(
        item for item in aggregated
        if item.normalized_name == "nicorandil_5mg"
    )
    
    assert nicorandil_group.occurrences == 4
    assert nicorandil_group.total_bill == 78.80
    assert nicorandil_group.allowed_per_unit == 49.25
    assert len(nicorandil_group.line_items) == 4
```

**Acceptance Criteria:**
- [ ] Items are correctly grouped by (normalized_name, matched_ref, category)
- [ ] Totals are calculated correctly
- [ ] Line-item breakdown is preserved
- [ ] Unit tests pass

---

### **Task 1.4: Implement Status Resolver**

**File:** `backend/app/verifier/aggregator.py`

**Function to Implement:**

```python
def resolve_aggregate_status(line_items: List[ItemVerificationResult]) -> VerificationStatus:
    """
    Resolve final status for aggregated group.
    
    Priority: RED > MISMATCH > GREEN > ALLOWED_NOT_COMPARABLE > IGNORED
    
    Args:
        line_items: List of line items in the group
        
    Returns:
        Final resolved status
    """
    statuses = [item.status for item in line_items]
    
    # Check for artifacts first
    from app.verifier.artifact_detector import is_artifact
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

**Test Cases:**

```python
def test_resolve_aggregate_status():
    """Test status resolution."""
    # Case 1: All GREEN → GREEN
    green_items = [create_item(status=VerificationStatus.GREEN) for _ in range(3)]
    assert resolve_aggregate_status(green_items) == VerificationStatus.GREEN
    
    # Case 2: 3 GREEN + 1 RED → RED
    mixed_items = green_items + [create_item(status=VerificationStatus.RED)]
    assert resolve_aggregate_status(mixed_items) == VerificationStatus.RED
    
    # Case 3: Only MISMATCH → MISMATCH
    mismatch_items = [create_item(status=VerificationStatus.MISMATCH)]
    assert resolve_aggregate_status(mismatch_items) == VerificationStatus.MISMATCH
```

**Acceptance Criteria:**
- [ ] Status resolution follows priority rules
- [ ] Artifacts are detected correctly
- [ ] Unit tests pass

---

### **Task 1.5: Create Artifact Detector**

**File:** `backend/app/verifier/artifact_detector.py`

**Function to Implement:**

```python
import re
from typing import List


IGNORE_PATTERNS = [
    r'page\s+\d+\s+of\s+\d+',           # Page numbers
    r'\+?\d{2,3}[-.\s]?\d{10}',         # Phone numbers
    r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}',  # Emails
    r'download\s+(our\s+)?app',         # App prompts
    r'bill\s+(no|number|#)',            # Bill metadata
    r'date[:\s]+\d{2}[/-]\d{2}',        # Date headers
]


def is_artifact(item_name: str) -> bool:
    """
    Check if item is an OCR/admin artifact.
    
    Args:
        item_name: Item name to check
        
    Returns:
        True if item is an artifact, False otherwise
    """
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, item_name, re.IGNORECASE):
            return True
    return False
```

**Test Cases:**

```python
def test_is_artifact():
    """Test artifact detection."""
    assert is_artifact("Page 1 of 2") == True
    assert is_artifact("Ph: +91-9876543210") == True
    assert is_artifact("info@hospital.com") == True
    assert is_artifact("Download our app") == True
    assert is_artifact("Bill No: 12345") == True
    
    # Valid items should not be artifacts
    assert is_artifact("MRI BRAIN") == False
    assert is_artifact("CONSULTATION") == False
```

**Acceptance Criteria:**
- [ ] Artifact patterns are correctly detected
- [ ] Valid items are not flagged as artifacts
- [ ] Unit tests pass

---

## 🔬 Phase 2B: Enhanced Matching (Week 2)

### **Task 2.1: Implement Medical Anchor Extraction**

**File:** `backend/app/verifier/medical_anchors.py`

**Functions to Implement:**

```python
import re
from typing import Optional, Set


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
```

**Test Cases:**

```python
def test_extract_dosage():
    """Test dosage extraction."""
    assert extract_dosage("NICORANDIL 5MG") == "5mg"
    assert extract_dosage("PARACETAMOL 500 MG") == "500mg"
    assert extract_dosage("INSULIN 10ML") == "10ml"
    assert extract_dosage("CONSULTATION") is None


def test_extract_modality():
    """Test modality extraction."""
    assert extract_modality("MRI BRAIN") == "mri"
    assert extract_modality("CT SCAN ABDOMEN") == "ct"
    assert extract_modality("X-RAY CHEST") == "x-ray"
    assert extract_modality("CONSULTATION") is None


def test_extract_bodypart():
    """Test body part extraction."""
    assert extract_bodypart("MRI BRAIN") == "brain"
    assert extract_bodypart("CT SCAN ABDOMEN") == "abdomen"
    assert extract_bodypart("CARDIAC ECHO") == "cardiac"
    assert extract_bodypart("CONSULTATION") is None
```

**Acceptance Criteria:**
- [ ] Dosage patterns are correctly extracted
- [ ] Modality keywords are correctly extracted
- [ ] Body part keywords are correctly extracted
- [ ] Unit tests pass

---

### **Task 2.2: Implement Hybrid Scoring V2**

**File:** `backend/app/verifier/partial_matcher.py`

**Function to Implement:**

```python
from typing import Tuple, Dict
from app.verifier.medical_anchors import (
    extract_dosage,
    extract_modality,
    extract_bodypart
)


def calculate_medical_anchor_score(bill_item: str, tieup_item: str) -> Tuple[float, dict]:
    """
    Calculate medical anchor score based on domain-specific matches.
    
    Args:
        bill_item: Normalized bill item text
        tieup_item: Normalized tie-up item text
        
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

**Test Cases:**

```python
def test_calculate_medical_anchor_score():
    """Test medical anchor scoring."""
    # Perfect match (dosage + modality + bodypart)
    score, breakdown = calculate_medical_anchor_score("MRI BRAIN 5MG", "MRI BRAIN 5MG")
    assert score == 1.0
    assert breakdown['dosage_match'] == True
    assert breakdown['modality_match'] == True
    assert breakdown['bodypart_match'] == True
    
    # Partial match (modality + bodypart only)
    score, breakdown = calculate_medical_anchor_score("MRI BRAIN", "MRI BRAIN")
    assert score == 0.6  # 0.3 + 0.3
    assert breakdown['dosage_match'] == False
    assert breakdown['modality_match'] == True
    assert breakdown['bodypart_match'] == True


def test_calculate_hybrid_score_v2():
    """Test hybrid scoring v2."""
    # High semantic + medical anchors
    final_score, breakdown = calculate_hybrid_score_v2(
        bill_item="mri brain",
        tieup_item="mri brain",
        semantic_similarity=0.95
    )
    
    # Expected: 0.50*0.95 + 0.25*1.0 + 0.25*0.6 = 0.475 + 0.25 + 0.15 = 0.875
    assert final_score >= 0.85
    assert breakdown['semantic'] == 0.95
    assert breakdown['medical_anchors'] > 0.0
```

**Acceptance Criteria:**
- [ ] Medical anchor scoring works correctly
- [ ] Hybrid scoring v2 combines all metrics
- [ ] Weights are configurable
- [ ] Unit tests pass

---

### **Task 2.3: Update Matcher to Use Hybrid V2**

**File:** `backend/app/verifier/matcher.py`

**Update `match_item()` method:**

```python
def match_item(self, item_name: str, ...) -> ItemMatch:
    """Match item with hybrid scoring v2."""
    
    # ... existing normalization and semantic matching ...
    
    # Phase-2: Use hybrid scoring v2
    from app.verifier.partial_matcher import calculate_hybrid_score_v2
    
    hybrid_score, breakdown = calculate_hybrid_score_v2(
        bill_item=normalized_item_name,
        tieup_item=matched_name,
        semantic_similarity=similarity
    )
    
    # Log hybrid score breakdown
    logger.debug(
        f"Hybrid score for '{item_name}': {hybrid_score:.2f} "
        f"(semantic={breakdown['semantic']:.2f}, "
        f"token={breakdown['token_overlap']:.2f}, "
        f"medical={breakdown['medical_anchors']:.2f})"
    )
    
    # Use hybrid score for matching decision
    if hybrid_score >= 0.60:  # Phase-2 threshold
        return ItemMatch(
            is_match=True,
            matched_text=matched_name,
            similarity=hybrid_score,
            # ... other fields ...
        )
    
    # ... rest of matching logic ...
```

**Acceptance Criteria:**
- [ ] Matcher uses hybrid scoring v2
- [ ] Hybrid score breakdown is logged
- [ ] Matching threshold is configurable
- [ ] Integration tests pass

---

## 🔄 Phase 2C: Category Reconciliation (Week 3)

### **Task 3.1: Implement Category Reconciler**

**File:** `backend/app/verifier/reconciler.py`

**Functions to Implement:**

```python
from typing import Optional, List
from app.verifier.models import ItemVerificationResult, VerificationStatus
from app.verifier.models_v2 import AggregatedItem
from app.verifier.matcher import get_matcher, ITEM_SIMILARITY_THRESHOLD
import logging

logger = logging.getLogger(__name__)


def try_alternative_categories(
    item: AggregatedItem,
    hospital_name: str,
    rate_cache: Dict[Tuple[str, str], float]
) -> Optional[dict]:
    """
    Try matching item in all available categories.
    
    Args:
        item: Aggregated item to reconcile
        hospital_name: Hospital name for matching
        rate_cache: Rate cache for pricing
        
    Returns:
        Best match result or None
    """
    matcher = get_matcher()
    best_match = None
    best_score = 0.0
    
    # Get all available categories from rate sheets
    all_categories = matcher.get_all_categories(hospital_name)
    
    attempted_categories = [item.category]
    
    for category in all_categories:
        if category == item.category:
            continue  # Skip original category
        
        attempted_categories.append(category)
        
        # Try matching in this category
        match_result = matcher.match_item(
            item_name=item.normalized_name,
            hospital_name=hospital_name,
            category_name=category,
            threshold=ITEM_SIMILARITY_THRESHOLD
        )
        
        if match_result.is_match and match_result.similarity > best_score:
            best_match = {
                'matched_item': match_result.matched_text,
                'category': category,
                'similarity': match_result.similarity,
                'attempted_categories': attempted_categories
            }
            best_score = match_result.similarity
    
    if best_match:
        logger.info(
            f"Reconciliation success: '{item.normalized_name}' "
            f"found in '{best_match['category']}' (similarity={best_score:.2f})"
        )
    
    return best_match


def reconcile_categories(
    aggregated_items: List[AggregatedItem],
    hospital_name: str,
    rate_cache: Dict[Tuple[str, str], float]
) -> List[AggregatedItem]:
    """
    For MISMATCH items, attempt matching in alternative categories.
    
    Args:
        aggregated_items: List of aggregated items
        hospital_name: Hospital name for matching
        rate_cache: Rate cache for pricing
        
    Returns:
        List of reconciled items
    """
    reconciled_items = []
    reconciliation_stats = {
        'attempted': 0,
        'succeeded': 0,
        'failed': 0
    }
    
    for agg_item in aggregated_items:
        if agg_item.status == VerificationStatus.MISMATCH:
            reconciliation_stats['attempted'] += 1
            
            # Try alternative categories
            best_match = try_alternative_categories(
                item=agg_item,
                hospital_name=hospital_name,
                rate_cache=rate_cache
            )
            
            if best_match:
                # Update with reconciled match
                agg_item.original_category = agg_item.category
                agg_item.matched_reference = best_match['matched_item']
                agg_item.category = best_match['category']
                agg_item.status = VerificationStatus.GREEN  # Re-check price
                agg_item.reconciliation_note = (
                    f"Found in alternative category '{best_match['category']}' "
                    f"after original category '{agg_item.original_category}' failed"
                )
                
                # Update diagnostics
                if agg_item.diagnostics:
                    agg_item.diagnostics.all_categories_tried = best_match['attempted_categories']
                
                reconciliation_stats['succeeded'] += 1
            else:
                reconciliation_stats['failed'] += 1
        
        reconciled_items.append(agg_item)
    
    logger.info(
        f"Reconciliation complete: {reconciliation_stats['succeeded']}/{reconciliation_stats['attempted']} succeeded"
    )
    
    return reconciled_items
```

**Test Cases:**

```python
def test_try_alternative_categories():
    """Test alternative category matching."""
    item = create_mismatch_item(
        normalized_name="cross_consultation_ip",
        category="consultation"
    )
    
    best_match = try_alternative_categories(
        item=item,
        hospital_name="Apollo Hospital",
        rate_cache={}
    )
    
    assert best_match is not None
    assert best_match['category'] == "specialist_consultation"
    assert best_match['similarity'] > 0.7


def test_reconcile_categories():
    """Test category reconciliation."""
    aggregated_items = [
        create_mismatch_item(normalized_name="cross_consultation_ip"),
        create_green_item(normalized_name="consultation")
    ]
    
    reconciled = reconcile_categories(
        aggregated_items=aggregated_items,
        hospital_name="Apollo Hospital",
        rate_cache={}
    )
    
    # Verify reconciliation
    cross_consult = next(
        item for item in reconciled
        if item.normalized_name == "cross_consultation_ip"
    )
    
    assert cross_consult.status == VerificationStatus.GREEN
    assert cross_consult.reconciliation_note is not None
```

**Acceptance Criteria:**
- [ ] Alternative categories are tried correctly
- [ ] Best match is selected
- [ ] Reconciliation note is added
- [ ] Diagnostics are updated
- [ ] Unit tests pass

---

## 💰 Phase 2D: Financial Aggregation (Week 4)

### **Task 4.1: Implement Financial Aggregator**

**File:** `backend/app/verifier/financial.py`

**Functions to Implement:**

```python
from collections import defaultdict
from typing import List
from app.verifier.models_v2 import (
    AggregatedItem,
    CategoryTotals,
    GrandTotals,
    FinancialSummary
)
from app.verifier.models import VerificationStatus


def calculate_category_totals(
    aggregated_items: List[AggregatedItem]
) -> List[CategoryTotals]:
    """
    Calculate financial totals per category.
    
    Args:
        aggregated_items: List of aggregated items
        
    Returns:
        List of category totals
    """
    category_map = defaultdict(lambda: {
        'total_bill': 0.0,
        'total_allowed': 0.0,
        'total_extra': 0.0,
        'green_count': 0,
        'red_count': 0,
        'mismatch_count': 0,
        'ignored_count': 0
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
        elif agg_item.status == VerificationStatus.IGNORED_ARTIFACT:
            cat_data['ignored_count'] += 1
    
    # Convert to CategoryTotals objects
    category_totals = [
        CategoryTotals(
            category=category,
            **data
        )
        for category, data in category_map.items()
    ]
    
    return category_totals


def calculate_grand_totals(
    aggregated_items: List[AggregatedItem]
) -> GrandTotals:
    """
    Calculate overall financial totals.
    
    Args:
        aggregated_items: List of aggregated items
        
    Returns:
        Grand totals
    """
    return GrandTotals(
        total_bill=sum(item.total_bill for item in aggregated_items),
        total_allowed=sum(item.total_allowed for item in aggregated_items),
        total_extra=sum(item.total_extra for item in aggregated_items),
        total_allowed_not_comparable=sum(
            item.total_bill for item in aggregated_items
            if item.status == VerificationStatus.ALLOWED_NOT_COMPARABLE
        ),
        green_count=sum(1 for item in aggregated_items if item.status == VerificationStatus.GREEN),
        red_count=sum(1 for item in aggregated_items if item.status == VerificationStatus.RED),
        mismatch_count=sum(1 for item in aggregated_items if item.status == VerificationStatus.MISMATCH),
        ignored_count=sum(1 for item in aggregated_items if item.status == VerificationStatus.IGNORED_ARTIFACT)
    )


def build_financial_summary(
    aggregated_items: List[AggregatedItem]
) -> FinancialSummary:
    """
    Build complete financial summary.
    
    Args:
        aggregated_items: List of aggregated items
        
    Returns:
        Financial summary with category and grand totals
    """
    return FinancialSummary(
        category_totals=calculate_category_totals(aggregated_items),
        grand_totals=calculate_grand_totals(aggregated_items)
    )
```

**Test Cases:**

```python
def test_calculate_category_totals():
    """Test category totals calculation."""
    aggregated_items = create_mock_aggregated_items()
    
    category_totals = calculate_category_totals(aggregated_items)
    
    # Verify medicines category
    medicines = next(cat for cat in category_totals if cat.category == "medicines")
    assert medicines.total_bill == 103.80
    assert medicines.green_count == 1
    assert medicines.red_count == 1


def test_calculate_grand_totals():
    """Test grand totals calculation."""
    aggregated_items = create_mock_aggregated_items()
    
    grand_totals = calculate_grand_totals(aggregated_items)
    
    assert grand_totals.total_bill > 0
    assert grand_totals.green_count + grand_totals.red_count + grand_totals.mismatch_count > 0
```

**Acceptance Criteria:**
- [ ] Category totals are calculated correctly
- [ ] Grand totals are calculated correctly
- [ ] All status counts are accurate
- [ ] Unit tests pass

---

### **Task 4.2: Implement Phase-2 Orchestrator**

**File:** `backend/app/verifier/phase2_processor.py`

**Main Function:**

```python
from app.verifier.models import VerificationResponse
from app.verifier.models_v2 import Phase2Response
from app.verifier.aggregator import (
    build_rate_cache,
    aggregate_line_items,
    resolve_aggregate_status
)
from app.verifier.reconciler import reconcile_categories
from app.verifier.financial import build_financial_summary
import logging

logger = logging.getLogger(__name__)


def process_phase2(
    phase1_response: VerificationResponse,
    hospital_name: str
) -> Phase2Response:
    """
    Transform Phase-1 output into Phase-2 aggregated comparison.
    
    Args:
        phase1_response: Complete Phase-1 verification response
        hospital_name: Hospital name for reconciliation
        
    Returns:
        Phase2Response with aggregated, reconciled, and financially summarized data
    """
    logger.info("Starting Phase-2 processing")
    
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
        hospital_name=hospital_name,
        rate_cache=rate_cache
    )
    
    # Step 5: Calculate financial totals
    financial_summary = build_financial_summary(reconciled_items)
    
    # Step 6: Build Phase-2 response
    # Collect all Phase-1 line items
    phase1_line_items = []
    for category_result in phase1_response.results:
        phase1_line_items.extend(category_result.items)
    
    response = Phase2Response(
        hospital=phase1_response.hospital,
        matched_hospital=phase1_response.matched_hospital,
        hospital_similarity=phase1_response.hospital_similarity,
        phase1_line_items=phase1_line_items,
        aggregated_items=reconciled_items,
        financial_summary=financial_summary,
        processing_metadata={
            'phase1_items_count': len(phase1_line_items),
            'phase2_aggregated_count': len(reconciled_items),
            'rate_cache_size': len(rate_cache)
        }
    )
    
    logger.info(
        f"Phase-2 processing complete: "
        f"{len(phase1_line_items)} line items → {len(reconciled_items)} aggregated items"
    )
    
    return response
```

**Acceptance Criteria:**
- [ ] Phase-2 orchestrator integrates all components
- [ ] Phase-1 data is preserved
- [ ] Metadata is populated
- [ ] Integration tests pass

---

## 📊 Phase 2E: Display & Documentation (Week 5)

### **Task 5.1: Update Display Formatter**

**File:** `backend/main.py`

**Add Phase-2 display function:**

```python
def display_phase2_response(response: Phase2Response):
    """Display Phase-2 verification response."""
    
    print(f"\n{'='*80}")
    print(f"PHASE-2 VERIFICATION RESULTS")
    print(f"{'='*80}")
    
    print(f"\n🏥 Hospital: {response.hospital}")
    if response.matched_hospital:
        print(f"   Matched: {response.matched_hospital} (similarity={response.hospital_similarity:.2f})")
    
    print(f"\n📦 Aggregated Items ({len(response.aggregated_items)}):")
    print(f"{'='*80}")
    
    for agg_item in response.aggregated_items:
        status_icon = {
            VerificationStatus.GREEN: "✅",
            VerificationStatus.RED: "❌",
            VerificationStatus.MISMATCH: "⚠️",
            VerificationStatus.ALLOWED_NOT_COMPARABLE: "⚪",
            VerificationStatus.IGNORED_ARTIFACT: "🚫"
        }.get(agg_item.status, "❓")
        
        print(f"\n{status_icon} {agg_item.normalized_name.upper()}")
        print(f"   Matched: {agg_item.matched_reference or 'N/A'}")
        print(f"   Category: {agg_item.category}")
        print(f"   Occurrences: {agg_item.occurrences}")
        print(f"   Total Bill: ₹{agg_item.total_bill:.2f}")
        print(f"   Total Allowed: ₹{agg_item.total_allowed:.2f}")
        if agg_item.total_extra > 0:
            print(f"   Total Extra: ₹{agg_item.total_extra:.2f}")
        
        if agg_item.reconciliation_note:
            print(f"   📝 {agg_item.reconciliation_note}")
        
        # Show line-item breakdown
        if agg_item.occurrences > 1:
            print(f"\n   Breakdown:")
            for idx, line_item in enumerate(agg_item.line_items, 1):
                print(f"     {idx}. Bill: ₹{line_item.bill_amount:.2f}")
    
    # Financial summary
    print(f"\n{'='*80}")
    print(f"FINANCIAL SUMMARY")
    print(f"{'='*80}")
    
    print(f"\nCategory Totals:")
    for cat_total in response.financial_summary.category_totals:
        print(f"\n  📁 {cat_total.category}")
        print(f"     Bill: ₹{cat_total.total_bill:.2f}")
        print(f"     Allowed: ₹{cat_total.total_allowed:.2f}")
        print(f"     Extra: ₹{cat_total.total_extra:.2f}")
        print(f"     ✅ {cat_total.green_count} | ❌ {cat_total.red_count} | ⚠️ {cat_total.mismatch_count}")
    
    grand = response.financial_summary.grand_totals
    print(f"\n{'='*80}")
    print(f"GRAND TOTALS")
    print(f"{'='*80}")
    print(f"  Total Bill: ₹{grand.total_bill:.2f}")
    print(f"  Total Allowed: ₹{grand.total_allowed:.2f}")
    print(f"  Total Extra: ₹{grand.total_extra:.2f}")
    print(f"  Total Allowed-Not-Comparable: ₹{grand.total_allowed_not_comparable:.2f}")
    print(f"\n  Status Counts:")
    print(f"    ✅ GREEN: {grand.green_count}")
    print(f"    ❌ RED: {grand.red_count}")
    print(f"    ⚠️ MISMATCH: {grand.mismatch_count}")
    print(f"    🚫 IGNORED: {grand.ignored_count}")
    print(f"{'='*80}\n")
```

**Acceptance Criteria:**
- [ ] Phase-2 response is displayed clearly
- [ ] Aggregated items show breakdown
- [ ] Financial summary is formatted
- [ ] Reconciliation notes are visible

---

### **Task 5.2: Create Phase-2 Documentation**

**Files to Create:**

1. **User Guide:** `docs/PHASE_2_USER_GUIDE.md`
2. **API Documentation:** `docs/PHASE_2_API.md`
3. **Migration Guide:** `docs/PHASE_1_TO_PHASE_2_MIGRATION.md`

**Acceptance Criteria:**
- [ ] User guide explains Phase-2 features
- [ ] API documentation covers all endpoints
- [ ] Migration guide helps transition from Phase-1

---

## ✅ Final Checklist

### **Code Quality**
- [ ] All functions have docstrings
- [ ] All functions have type hints
- [ ] Code follows PEP 8 style guide
- [ ] No hardcoded values (use config)

### **Testing**
- [ ] Unit tests for all functions
- [ ] Integration tests for Phase-2 pipeline
- [ ] Test coverage > 80%
- [ ] All tests pass

### **Documentation**
- [ ] User guide created
- [ ] API documentation created
- [ ] Migration guide created
- [ ] Code comments are clear

### **Performance**
- [ ] Phase-2 processing < 500ms overhead
- [ ] Rate cache reduces redundant lookups
- [ ] Aggregation handles 1000+ items

### **Validation**
- [ ] No items disappear between Phase-1 and Phase-2
- [ ] Financial totals are accurate
- [ ] Reconciliation improves match rate
- [ ] Output is audit-ready

---

## 🚀 Ready to Implement!

Follow this plan step-by-step to build Phase-2 of the hospital bill verification engine.

**Good luck!** 🎉

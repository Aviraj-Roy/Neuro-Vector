# Phase-1: Exhaustive, Non-Lossy Matching - Implementation Plan

## 🎯 Objective
Refactor the verification pipeline to ensure **EVERY bill line item appears in the output** without exception.
This is Phase-1: focused on **correctness, traceability, and completeness** — not optimization.

## ✅ Hard Requirements (Must Not Be Violated)

### 1️⃣ No Item Loss — Ever
- Every line item from MongoDB must appear in the final output
- This includes:
  - Duplicate items
  - Repeated charges
  - Low-similarity items
  - Administrative charges
  - Non-comparable items
- **DO NOT deduplicate**
- **DO NOT aggregate before display**
- The same allowed rate may be reused multiple times

### 2️⃣ Matching ≠ Visibility
- Matching logic must ONLY decide status, not visibility
- ❌ **FORBIDDEN**: `if similarity < threshold: return None`
- ✅ **REQUIRED**: `return VerificationResult(status=..., diagnostics=...)`
- **Zero code paths where an item is not appended to results**

## 🟢🔴⚠️🟦 Verification Status Rules

### Status Enum (Updated)
```python
class VerificationStatus(str, Enum):
    GREEN = "GREEN"                           # ✅ Matched, bill ≤ allowed
    RED = "RED"                               # ❌ Matched, bill > allowed
    MISMATCH = "MISMATCH"                     # ⚠️ Could not match reliably
    ALLOWED_NOT_COMPARABLE = "ALLOWED_NOT_COMPARABLE"  # 🟦 Exists but no price comparison
```

### Status Assignment Logic
1. **GREEN**: Item matched AND bill amount ≤ allowed rate
2. **RED**: Item matched AND bill amount > allowed rate (show Extra = Bill − Allowed)
3. **MISMATCH**: Item could not be matched reliably
4. **ALLOWED_NOT_COMPARABLE**: Item exists, category matched, but no valid price comparison possible
   - Allowed = N/A
   - Extra = N/A
   - Bill amount must still be shown

## 🧠 Matching Strategy (Hybrid, Non-Hardcoded)

### Category Matching
- Use semantic + fuzzy hybrid
- If category similarity < threshold:
  - **Still assign item to best category**
  - Log warning
  - **DO NOT drop item**

### Item Matching
- Normalize item names by:
  - Removing doctor names
  - Removing quantities, dates, lot numbers
  - Removing OCR artifacts
- Use hybrid matching (semantic + token overlap)
- **DO NOT hardcode mappings**

## 🧪 Mismatch Diagnostics (Mandatory)

### Diagnostic Structure
For every item with status ≠ GREEN / RED, output:

```python
@dataclass
class MismatchDiagnostics:
    normalized_item_name: str
    best_candidate: Optional[str]  # only if similarity > 0.5
    attempted_category: str
    failure_reason: FailureReason
```

### Failure Reason ENUM
```python
class FailureReason(str, Enum):
    NOT_IN_TIEUP = "NOT_IN_TIEUP"           # No match found in tie-up
    LOW_SIMILARITY = "LOW_SIMILARITY"        # Best match below threshold
    PACKAGE_ONLY = "PACKAGE_ONLY"            # Only exists as package item
    ADMIN_CHARGE = "ADMIN_CHARGE"            # Administrative/artifact item
```

## 📦 Special Rules

### Administrative / Artifact Items
- Registration fees, admission charges, processing fees, OCR junk
- **Must still be listed**
- Mark as:
  - Status: `ALLOWED_NOT_COMPARABLE`
  - Failure reason: `ADMIN_CHARGE`

### Package Items
- If item exists only as part of a package and not standalone:
  - Status: `MISMATCH`
  - Failure reason: `PACKAGE_ONLY`

## 🧾 Output Formatting Rules

### Each Item Output Must Include:
1. Original bill item name
2. Normalized item name
3. Status
4. Bill amount
5. Allowed amount (or N/A)
6. Extra amount (or N/A)
7. Diagnostics (if applicable)

⚠️ **Duplicates must appear as separate rows**

## 🧱 Required Refactor (Structural)

### Current Issues to Fix

#### Issue 1: Matcher can return items without appending
**Location**: `verifier.py`, lines 308-314
```python
# CURRENT (WRONG):
for bill_item in bill_category.items:
    item_result = self._verify_item(...)
    result.items.append(item_result)  # ✅ This is OK
```

**Verification**: The current code DOES append all items. ✅ No issue here.

#### Issue 2: Category mismatch blocks items (FIXED in Phase-1)
**Location**: `verifier.py`, lines 286-304
```python
# CURRENT (CORRECT for Phase-1):
# PHASE-1: ALWAYS process items (regardless of category confidence)
for bill_item in bill_category.items:
    item_result = self._verify_item(...)
    result.items.append(item_result)
```

**Verification**: Already fixed. ✅ No blocking on category confidence.

#### Issue 3: Matcher returns -1 index for non-matches
**Location**: `matcher.py`, line 745-750
```python
# CURRENT:
return ItemMatch(
    matched_text=matched_name,
    similarity=similarity,
    index=-1,  # ← This signals MISMATCH
    item=None
)
```

**Verification**: This is correct. The verifier handles this properly. ✅

### New Data Models Required

#### Enhanced ItemVerificationResult
```python
class ItemVerificationResult(BaseModel):
    # Original fields
    bill_item: str
    matched_item: Optional[str] = None
    status: VerificationStatus
    bill_amount: float
    allowed_amount: float = 0.0
    extra_amount: float = 0.0
    similarity_score: Optional[float] = None
    
    # NEW FIELDS for Phase-1
    normalized_item_name: Optional[str] = None  # Show normalization
    diagnostics: Optional[MismatchDiagnostics] = None  # For non-GREEN/RED items
```

#### New Diagnostics Model
```python
@dataclass
class MismatchDiagnostics:
    normalized_item_name: str
    best_candidate: Optional[str]
    attempted_category: str
    failure_reason: FailureReason
```

## 🔧 Implementation Steps

### Step 1: Update Models (models.py)
- [x] Add `ALLOWED_NOT_COMPARABLE` to `VerificationStatus` enum
- [ ] Add `FailureReason` enum
- [ ] Add `MismatchDiagnostics` dataclass
- [ ] Update `ItemVerificationResult` with new fields

### Step 2: Update Text Normalizer (text_normalizer.py)
- [ ] Add `is_administrative_charge()` function
- [ ] Identify common admin charges (registration, admission, processing)

### Step 3: Update Verifier Logic (verifier.py)
- [ ] Update `_verify_item()` to detect administrative charges
- [ ] Update `_create_mismatch_item_result()` to include diagnostics
- [ ] Ensure normalized_item_name is captured and returned
- [ ] Add failure reason detection logic

### Step 4: Update Matcher (matcher.py)
- [ ] Return normalized_item_name in ItemMatch
- [ ] Return best_candidate even for mismatches (if similarity > 0.5)
- [ ] Never return None for items

### Step 5: Testing & Validation
- [ ] Verify total output items == total MongoDB items
- [ ] Verify no silent drops
- [ ] Verify all mismatches have diagnostics
- [ ] Verify duplicates appear as separate rows

## 🧪 Acceptance Criteria

After refactor:
1. ✅ Total number of output items == number of MongoDB bill items
2. ✅ No silent drops
3. ✅ All mismatches are explainable (have diagnostics)
4. ✅ Debugging is possible from output alone
5. ✅ Phase-1 favors completeness over precision

## ❗ Do NOT

- ❌ Optimize
- ❌ Deduplicate
- ❌ Collapse categories
- ❌ Hide mismatches
- ❌ Short-circuit matching logic

## 📊 Expected Outcomes

### Before Phase-1 Exhaustive Matching
```
Total Items: 100
Output Items: 100 (but some might have been filtered)
GREEN: 55 (55%)
RED: 25 (25%)
MISMATCH: 20 (20%)
```

### After Phase-1 Exhaustive Matching
```
Total Items: 100
Output Items: 100 (GUARANTEED - every item listed)
GREEN: 55 (55%)
RED: 25 (25%)
MISMATCH: 15 (15%)
ALLOWED_NOT_COMPARABLE: 5 (5%) ← New status for admin charges
```

### Key Improvements
1. **Traceability**: Every item has diagnostics explaining its status
2. **Completeness**: Zero items lost in processing
3. **Debuggability**: Can trace exactly why each item got its status
4. **Transparency**: Normalized names shown alongside original names

---

**Status**: Ready for Implementation  
**Priority**: CRITICAL (Phase-1 Foundation)  
**Date**: 2026-02-07

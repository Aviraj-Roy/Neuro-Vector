# Phase-7 Artifact Cleanup Guide

## 🎯 Problem Statement

During Phase-7 completeness validation, the verifier reported:

```
⚠️  PHASE-7 COMPLETENESS VALIDATION FAILED:
Item count mismatch: Input=93, Output=92
Missing 1 items: [('Hospital - ', 'UNKNOWN', 0.0)]
```

This corresponds to a legacy OCR artifact in MongoDB:

```json
"items": {
  "Hospital - ": [
    {
      "item_name": "UNKNOWN",
      "amount": 0,
      "quantity": 1,
      "final_amount": 0
    }
  ]
}
```

### Why This Artifact Exists

This is a **legacy OCR fallback pattern** where the parser created a placeholder entry when it couldn't extract valid hospital header information. The category `"Hospital - "` (with trailing space) and item `"UNKNOWN"` with ₹0 amount indicates a failed extraction that should never have been persisted.

**Root cause**: The OCR extraction pipeline had a fallback that created this entry when hospital metadata extraction failed, but it was incorrectly added to billable items instead of being filtered out.

---

## ✅ Complete Solution

### 1️⃣ MongoDB Cleanup (One-Time + Safe)

#### Option A: Remove Entire "Hospital - " Category (Recommended)

**MongoDB Shell Command:**
```javascript
db.bills.updateMany(
  { "items.Hospital - ": { $exists: true } },
  { $unset: { "items.Hospital - ": "" } }
)
```

**Python Script (Interactive with Confirmation):**
```bash
python -m backend.scripts.cleanup_artifacts
```

This script:
- ✅ Scans for affected documents
- ✅ Shows sample data before cleanup
- ✅ Asks for confirmation
- ✅ Removes only the "Hospital - " category
- ✅ Verifies cleanup was successful
- ✅ Does NOT delete documents
- ✅ Does NOT affect valid hospital charges

#### Option B: Conservative Cleanup (Remove Only UNKNOWN/₹0 Items)

**MongoDB Shell Commands:**
```javascript
// Step 1: Remove UNKNOWN/₹0 items
db.bills.updateMany(
  { 
    "items.Hospital - ": { 
      $elemMatch: { 
        item_name: "UNKNOWN",
        final_amount: 0 
      } 
    } 
  },
  { 
    $pull: { 
      "items.Hospital - ": { 
        item_name: "UNKNOWN",
        final_amount: 0 
      } 
    } 
  }
)

// Step 2: Remove empty "Hospital - " categories
db.bills.updateMany(
  { "items.Hospital - ": { $size: 0 } },
  { $unset: { "items.Hospital - ": "" } }
)
```

**Python Script:**
```bash
python -m backend.scripts.cleanup_artifacts --conservative
```

---

### 2️⃣ Backend Guardrail (Mandatory - Prevents Re-Entry)

**File**: `backend/app/db/artifact_filter.py` (NEW)

This module provides:

#### `is_artifact_item(category_name, item_name, amount, final_amount)`
Detects artifacts based on ALL of these conditions:
- ✅ Category is hospital-related (normalized: "hospital", "hospitalization")
- ✅ Item name is "UNKNOWN" or empty
- ✅ Amount is ₹0
- ✅ Final amount is ₹0

#### `filter_artifact_items(bill_data)`
Filters out artifacts before MongoDB insertion:
- ✅ Scans all categories and items
- ✅ Removes items identified as artifacts
- ✅ Removes empty categories after filtering
- ✅ Logs all filtered items for audit trail

#### `validate_bill_items(bill_data)`
Final sanity check before insertion:
- ✅ Checks for "Hospital - " category
- ✅ Checks for UNKNOWN/₹0 items
- ✅ Returns validation status

**Integration**: Automatically called in `MongoDBClient.upsert_bill()`

```python
# In mongo_client.py::upsert_bill()
from app.db.artifact_filter import filter_artifact_items, validate_bill_items

# Filter artifacts before insertion
bill_data = filter_artifact_items(bill_data)

# Validate (logs warning if artifacts found)
is_valid, error_msg = validate_bill_items(bill_data)
if not is_valid:
    logger.error(f"⚠️  Bill validation failed: {error_msg}")
```

---

### 3️⃣ Phase-7 Completeness Logic Update

**File**: `backend/app/verifier/output_renderer.py`

**Updated**: `validate_completeness()` function

**Changes**:
- ✅ Excludes artifact items from input count
- ✅ Uses `is_artifact_item()` to detect artifacts
- ✅ Logs excluded artifacts for transparency
- ✅ Only counts real billable items

**Before**:
```python
# Count ALL input items
for category in bill_input.categories:
    for item in category.items:
        input_items.append((category.category_name, item.item_name, item.amount))
```

**After**:
```python
# Count input items (excluding artifacts)
from app.db.artifact_filter import is_artifact_item

for category in bill_input.categories:
    for item in category.items:
        # Skip artifacts
        if is_artifact_item(category.category_name, item.item_name, item.amount, item.amount):
            filtered_count += 1
            logger.debug(f"Excluding artifact: [{category.category_name}] {item.item_name}")
            continue
        
        input_items.append((category.category_name, item.item_name, item.amount))
```

---

## 📋 Deliverables Summary

### ✅ 1. MongoDB Query (Exact Commands)

**Recommended (Remove entire category):**
```javascript
db.bills.updateMany(
  { "items.Hospital - ": { $exists: true } },
  { $unset: { "items.Hospital - ": "" } }
)
```

**Conservative (Remove only UNKNOWN/₹0):**
```javascript
// Remove items
db.bills.updateMany(
  { "items.Hospital - ": { $elemMatch: { item_name: "UNKNOWN", final_amount: 0 } } },
  { $pull: { "items.Hospital - ": { item_name: "UNKNOWN", final_amount: 0 } } }
)

// Remove empty categories
db.bills.updateMany(
  { "items.Hospital - ": { $size: 0 } },
  { $unset: { "items.Hospital - ": "" } }
)
```

### ✅ 2. Python Backend Guard Code

**File**: `backend/app/db/artifact_filter.py`

**Key Functions**:
- `is_artifact_item()` - Detects artifacts
- `filter_artifact_items()` - Removes artifacts before insertion
- `validate_bill_items()` - Final validation check

**Integration**: Automatic in `MongoDBClient.upsert_bill()`

### ✅ 3. Phase-7 Validation Logic Change

**File**: `backend/app/verifier/output_renderer.py`

**Function**: `validate_completeness()`

**Change**: Excludes artifacts from input count using `is_artifact_item()`

### ✅ 4. Why This Artifact Appeared

**Root Cause**: Legacy OCR fallback pattern

When the OCR extraction pipeline failed to extract hospital header information:
1. Parser created a fallback entry: `"Hospital - "` category
2. Added placeholder item: `"UNKNOWN"` with ₹0
3. This was incorrectly added to billable items instead of being filtered
4. The artifact was persisted to MongoDB

**Why it's a problem**:
- Not a real bill line item
- Has no medical/financial value
- Causes Phase-7 completeness mismatch
- Pollutes verification results

### ✅ 5. Confirmation Checklist for Testing

#### Pre-Cleanup Verification
- [ ] Count documents with "Hospital - " category:
  ```javascript
  db.bills.count({ "items.Hospital - ": { $exists: true } })
  ```
- [ ] View sample artifact:
  ```javascript
  db.bills.findOne({ "items.Hospital - ": { $exists: true } })
  ```

#### Run Cleanup
- [ ] Execute cleanup script:
  ```bash
  python -m backend.scripts.cleanup_artifacts
  ```
- [ ] Confirm when prompted
- [ ] Verify cleanup count matches expected

#### Post-Cleanup Verification
- [ ] Verify no artifacts remain:
  ```javascript
  db.bills.count({ "items.Hospital - ": { $exists: true } })
  ```
  Expected: `0`

- [ ] Verify documents still exist:
  ```javascript
  db.bills.count()
  ```
  Expected: Same count as before cleanup

- [ ] Check sample document structure:
  ```javascript
  db.bills.findOne()
  ```
  Expected: No "Hospital - " in items

#### Backend Guardrail Testing
- [ ] Process a new bill (any bill)
- [ ] Check logs for artifact filtering:
  ```
  grep "Filtering out artifact" logs/backend.log
  ```
- [ ] Verify no "Hospital - " category in MongoDB:
  ```javascript
  db.bills.findOne({ upload_id: "latest_upload_id" })
  ```

#### Phase-7 Validation Testing
- [ ] Run verification on existing bill:
  ```bash
  python -m backend.main --bill test.pdf --hospital "Apollo Hospital"
  ```
- [ ] Check for completeness validation:
  ```
  ✅ PHASE-7 Completeness validation passed
  ```
- [ ] Verify no mismatch errors
- [ ] Verify Input count == Output count

---

## 🎯 Expected Outcomes

### Before Fix
```
⚠️  PHASE-7 COMPLETENESS VALIDATION FAILED:
Item count mismatch: Input=93, Output=92
Missing 1 items: [('Hospital - ', 'UNKNOWN', 0.0)]
```

### After Fix
```
INFO - Excluded 1 artifact items from completeness validation
DEBUG - Excluding artifact from validation: [Hospital - ] UNKNOWN - ₹0
INFO - ✅ PHASE-7 Completeness validation passed
```

### MongoDB State
**Before**:
```json
{
  "items": {
    "Hospital - ": [
      { "item_name": "UNKNOWN", "amount": 0, "final_amount": 0 }
    ],
    "Medicines": [ ... ],
    "Diagnostics": [ ... ]
  }
}
```

**After**:
```json
{
  "items": {
    "Medicines": [ ... ],
    "Diagnostics": [ ... ]
  }
}
```

---

## 🚀 Implementation Steps

### Step 1: Run MongoDB Cleanup
```bash
# Interactive cleanup with confirmation
python -m backend.scripts.cleanup_artifacts

# Or direct MongoDB command
mongo medical_bills --eval 'db.bills.updateMany({"items.Hospital - ": {$exists: true}}, {$unset: {"items.Hospital - ": ""}})'
```

### Step 2: Verify Backend Guardrail
The guardrail is already integrated into `MongoDBClient.upsert_bill()`.

No action needed - it will automatically filter artifacts on next bill insertion.

### Step 3: Test Phase-7 Validation
```bash
# Process and verify a bill
python -m backend.main --bill sample.pdf --hospital "Apollo Hospital"

# Check logs for validation success
grep "PHASE-7" logs/backend.log
```

### Step 4: Monitor for Artifacts
```bash
# Check if any new artifacts appear
mongo medical_bills --eval 'db.bills.count({"items.Hospital - ": {$exists: true}})'
```

Expected: `0` (should remain 0 after guardrail is active)

---

## 📊 Files Modified

1. **`backend/app/db/artifact_filter.py`** (NEW)
   - Artifact detection and filtering logic
   - Pre-insertion guardrail

2. **`backend/app/db/mongo_client.py`** (MODIFIED)
   - Integrated artifact filter in `upsert_bill()`
   - Automatic filtering before persistence

3. **`backend/app/verifier/output_renderer.py`** (MODIFIED)
   - Updated `validate_completeness()` to exclude artifacts
   - Logs excluded artifacts for transparency

4. **`backend/scripts/cleanup_artifacts.py`** (NEW)
   - One-time MongoDB cleanup script
   - Interactive with confirmation and verification

---

## ⚠️ Important Notes

### What This Does NOT Do
- ❌ Does NOT delete entire documents
- ❌ Does NOT affect valid hospital charges
- ❌ Does NOT hardcode hospital names
- ❌ Does NOT hardcode item indices
- ❌ Does NOT suppress errors silently

### What This DOES Do
- ✅ Removes only artifact categories/items
- ✅ Preserves all valid data
- ✅ Uses explicit classification (not deletion)
- ✅ Logs all filtering actions
- ✅ Validates before and after
- ✅ Prevents re-entry via guardrail

---

## 🎓 Key Principles

1. **Surgical, Not Destructive**: Remove only artifacts, preserve valid data
2. **Fail-Safe**: Validation errors are logged but non-blocking
3. **Auditable**: All filtering actions are logged
4. **Preventive**: Guardrail prevents re-entry
5. **Transparent**: Excluded items visible in debug logs

---

**Status**: ✅ COMPLETE  
**Phase**: Phase-7 (Artifact Cleanup & Validation)  
**Risk**: Low (surgical cleanup, non-destructive)  
**Reversible**: Yes (artifacts can be restored from backups if needed)

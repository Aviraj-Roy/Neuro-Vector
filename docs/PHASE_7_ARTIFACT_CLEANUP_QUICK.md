# Phase-7 Artifact Cleanup - Quick Reference

## 🎯 Problem
```
PHASE-7 COMPLETENESS VALIDATION FAILED:
Item count mismatch: Input=93, Output=92
Missing 1 items: [('Hospital - ', 'UNKNOWN', 0.0)]
```

## ✅ Solution (3 Parts)

### 1️⃣ MongoDB Cleanup (One-Time)

**Quick Command:**
```bash
python -m backend.scripts.cleanup_artifacts
```

**Or MongoDB Shell:**
```javascript
db.bills.updateMany(
  { "items.Hospital - ": { $exists: true } },
  { $unset: { "items.Hospital - ": "" } }
)
```

### 2️⃣ Backend Guardrail (Already Integrated)

**File**: `backend/app/db/artifact_filter.py`

**Auto-filters artifacts before MongoDB insertion**:
- Detects: `Hospital - / UNKNOWN / ₹0` patterns
- Removes: Before persistence
- Logs: All filtering actions

**Integration**: Automatic in `MongoDBClient.upsert_bill()`

### 3️⃣ Phase-7 Validation Update (Already Applied)

**File**: `backend/app/verifier/output_renderer.py`

**Excludes artifacts from completeness validation**:
- Skips: Artifact items in input count
- Logs: Excluded items for transparency
- Result: Input count == Output count ✅

## 📋 Testing Checklist

### Before Cleanup
```bash
# Count artifacts
mongo medical_bills --eval 'db.bills.count({"items.Hospital - ": {$exists: true}})'
```

### Run Cleanup
```bash
python -m backend.scripts.cleanup_artifacts
# Confirm when prompted
```

### After Cleanup
```bash
# Verify no artifacts
mongo medical_bills --eval 'db.bills.count({"items.Hospital - ": {$exists: true}})'
# Expected: 0

# Test verification
python -m backend.main --bill test.pdf --hospital "Apollo Hospital"
# Expected: ✅ PHASE-7 Completeness validation passed
```

## 🎯 Expected Result

**Before**:
```
⚠️  PHASE-7 COMPLETENESS VALIDATION FAILED
```

**After**:
```
INFO - Excluded 1 artifact items from completeness validation
INFO - ✅ PHASE-7 Completeness validation passed
```

## 📁 Files Created/Modified

1. ✅ `backend/app/db/artifact_filter.py` (NEW) - Artifact detection & filtering
2. ✅ `backend/app/db/mongo_client.py` (MODIFIED) - Integrated filter
3. ✅ `backend/app/verifier/output_renderer.py` (MODIFIED) - Exclude artifacts from validation
4. ✅ `backend/scripts/cleanup_artifacts.py` (NEW) - Cleanup script
5. ✅ `PHASE_7_ARTIFACT_CLEANUP.md` (NEW) - Full documentation

## 🚀 Quick Start

```bash
# 1. Run cleanup
python -m backend.scripts.cleanup_artifacts

# 2. Test verification
python -m backend.main --bill sample.pdf --hospital "Apollo Hospital"

# 3. Verify success
grep "PHASE-7 Completeness validation passed" logs/backend.log
```

Done! ✅

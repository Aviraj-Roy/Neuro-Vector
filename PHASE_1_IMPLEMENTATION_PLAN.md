# Phase-1 Implementation Plan: Coverage & Recall Optimization

## 🎯 Authoritative Objectives

### Core Principles
1. **NO deduplication** - List duplicate bill items multiple times
2. **Allowed rate reuse** - Multiple bill items can match the same rate-sheet entry
3. **Hybrid matching** - Combine semantic + token/keyword overlap
4. **Default to GREEN** - If match found, classify as GREEN (unless overcharged → RED)
5. **MISMATCH only when no match** - Only use MISMATCH when no reasonable match exists
6. **Category assignment** - Every item gets best matching category (even if low confidence)
7. **Ignore non-medical artifacts** - Filter out IDs, lot numbers, batch codes, etc.

### Goal
**Maximize correct recognition** - False positives acceptable, false negatives NOT acceptable

---

## 📋 Current State Analysis

### ✅ Already Implemented (Working)
1. **Medical core extraction** (`medical_core_extractor.py`)
   - Removes inventory metadata (SKU codes, lot numbers, expiry dates)
   - Extracts drug name + strength
   - Pattern: `(30049099) NICORANDIL-TABLET-5MG |GTF` → `nicorandil 5mg`

2. **Partial matching** (`partial_matcher.py`)
   - Token overlap (Jaccard similarity)
   - Containment ratio (tie-up terms in bill)
   - Thresholds: overlap=0.4, containment=0.6, semantic=0.65

3. **Soft category threshold** (`matcher.py`, `verifier.py`)
   - Hard threshold: 0.70
   - Soft threshold: 0.65
   - Categories with 0.65-0.70 similarity accepted with INFO log

4. **No duplicate output** (`verifier.py`)
   - Each category processed once
   - Each item processed once
   - Aggregation logic is correct

### ⚠️ Issues to Address

1. **Hybrid matching not comprehensive enough**
   - Current: Semantic → Partial → LLM
   - Needed: More aggressive combination of signals

2. **MISMATCH classification too strict**
   - Current: If similarity < 0.65 → MISMATCH
   - Needed: Try harder to find matches before giving up

3. **Category mismatch blocks items**
   - Current: If category < 0.65 → all items MISMATCH
   - Needed: Still try to match items even with weak category match

4. **No explicit non-medical artifact filtering**
   - Current: Relies on extraction patterns
   - Needed: Explicit ignore list for common noise

---

## 🔧 Required Changes

### 1. Enhanced Hybrid Matcher (CRITICAL)

**File**: `backend/app/verifier/matcher.py`

**Current flow** (lines 513-698):
```
Step 1: Extract medical core
Step 2: Normalize text
Step 3: Get semantic similarity
Step 4: If >= 0.85 → AUTO-MATCH
Step 5: If >= 0.65 → Try partial match
Step 6: If >= 0.65 → Try LLM
Step 7: Otherwise → MISMATCH
```

**New flow** (Phase-1):
```
Step 1: Normalize text (lowercase, strip symbols)
Step 2: Remove quantities, doctors, IDs (medical core extraction)
Step 3: Run semantic similarity (embeddings)
Step 4: Run token/keyword overlap (fuzzy or Jaccard)
Step 5: Combine scores (weighted average)
Step 6: Select best match above threshold
Step 7: If match found → GREEN (unless overcharged → RED)
Step 8: Only if NO match → MISMATCH
```

**Changes needed**:
- Lower thresholds further (0.65 → 0.55 for borderline cases)
- Add weighted scoring: `final_score = 0.6 * semantic + 0.4 * token_overlap`
- Accept match if `final_score >= 0.60` (instead of requiring semantic >= 0.65)
- Try top-3 matches instead of just top-1

### 2. Relaxed Category Handling

**File**: `backend/app/verifier/verifier.py`

**Current behavior** (lines 286-303):
- If category similarity < 0.65 → mark all items as MISMATCH
- If category similarity >= 0.65 → process items normally

**New behavior** (Phase-1):
- **ALWAYS** assign best matching category (even if similarity = 0.30)
- **ALWAYS** try to match items (don't block on category)
- Log category confidence but don't use it to block item matching
- Only use category to narrow down item search space

**Changes needed**:
```python
# BEFORE
if category_match.similarity < CATEGORY_SOFT_THRESHOLD:
    # Mark all items as MISMATCH
    for bill_item in bill_category.items:
        item_result = self._create_mismatch_item_result(bill_item)
        result.items.append(item_result)
    return result

# AFTER (Phase-1)
# Always assign best category, always try to match items
if category_match.similarity < CATEGORY_SOFT_THRESHOLD:
    logger.info(
        f"Low category confidence: '{bill_category.category_name}' → '{category_match.matched_text}' "
        f"(similarity={category_match.similarity:.4f}), but still trying to match items"
    )
# Continue to process items regardless of category confidence
```

### 3. Non-Medical Artifact Filter

**File**: `backend/app/verifier/text_normalizer.py` (existing)

**Add explicit ignore patterns**:
```python
NON_MEDICAL_PATTERNS = [
    r'^\d+$',  # Pure numbers
    r'^[A-Z0-9]{10,}$',  # Long alphanumeric codes
    r'LOT[:\s]*[A-Z0-9\-]+',  # Lot numbers
    r'BATCH[:\s]*[A-Z0-9\-]+',  # Batch codes
    r'EXP[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # Expiry dates
    r'SKU[:\s]*[A-Z0-9\-]+',  # SKU codes
    r'^\s*$',  # Empty strings
]

def is_non_medical_artifact(text: str) -> bool:
    """Check if text is a non-medical artifact to ignore."""
    for pattern in NON_MEDICAL_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    return False
```

### 4. Enhanced Scoring Logic

**File**: `backend/app/verifier/partial_matcher.py`

**Current scoring**:
- Token overlap OR containment (separate checks)
- Returns first passing metric

**New scoring** (Phase-1):
```python
def calculate_hybrid_score(
    bill_item: str,
    tieup_item: str,
    semantic_similarity: float,
    weights: dict = {"semantic": 0.6, "token": 0.3, "containment": 0.1}
) -> Tuple[float, dict]:
    """
    Calculate hybrid matching score combining multiple signals.
    
    Returns:
        (final_score, breakdown_dict)
    """
    # Calculate all metrics
    token_overlap = calculate_token_overlap(bill_item, tieup_item)
    containment = calculate_containment(bill_item, tieup_item)
    
    # Weighted combination
    final_score = (
        weights["semantic"] * semantic_similarity +
        weights["token"] * token_overlap +
        weights["containment"] * containment
    )
    
    breakdown = {
        "semantic": semantic_similarity,
        "token_overlap": token_overlap,
        "containment": containment,
        "final_score": final_score,
        "weights": weights,
    }
    
    return final_score, breakdown
```

### 5. Top-K Matching Strategy

**File**: `backend/app/verifier/matcher.py`

**Current**: Only considers top-1 match from FAISS

**New** (Phase-1): Consider top-3 matches, pick best hybrid score

```python
# In match_item() method
results = item_index.search(query_embedding, k=3)  # Get top-3

best_match = None
best_score = 0.0

for idx, semantic_sim in results:
    matched_name = item_index.texts[idx]
    item = item_refs[idx]
    
    # Calculate hybrid score
    hybrid_score, breakdown = calculate_hybrid_score(
        bill_item=item_name_for_matching,
        tieup_item=matched_name.lower(),
        semantic_similarity=semantic_sim,
    )
    
    if hybrid_score > best_score:
        best_score = hybrid_score
        best_match = (idx, matched_name, item, hybrid_score, breakdown)

# Use best_match if score >= threshold (e.g., 0.60)
```

---

## 📊 Expected Outcomes

### Before Phase-1
```
Total Items: 100
GREEN: 15 (15%)
RED: 5 (5%)
MISMATCH: 80 (80%)  ← Excessive false negatives
```

### After Phase-1
```
Total Items: 100
GREEN: 60 (60%)
RED: 20 (20%)
MISMATCH: 20 (20%)  ← Acceptable (true mismatches)
```

### Metrics to Track
1. **Mismatch rate** - Should drop from ~80% to ~20%
2. **False positives** - May increase slightly (acceptable)
3. **False negatives** - Should decrease significantly (goal)
4. **LLM usage** - May decrease (hybrid scoring catches more)
5. **Category confidence** - Track but don't block on it

---

## 🚀 Implementation Order

### Phase 1A: Foundation (This PR)
1. ✅ Enhanced hybrid scoring in `partial_matcher.py`
2. ✅ Top-K matching in `matcher.py`
3. ✅ Relaxed category handling in `verifier.py`
4. ✅ Non-medical artifact filter in `text_normalizer.py`

### Phase 1B: Tuning (Next PR)
1. Adjust thresholds based on real data
2. Fine-tune weights for hybrid scoring
3. Add configurable parameters
4. Performance optimization

### Phase 2: Deduplication & Pricing (Future)
- NOT in scope for Phase-1
- Will be addressed after coverage is maximized

---

## 🧪 Testing Strategy

### Unit Tests
```bash
# Test hybrid scoring
python backend/app/verifier/partial_matcher.py

# Test medical core extraction
python backend/app/verifier/medical_core_extractor.py

# Test top-K matching
python test_matcher_refactor.py
```

### Integration Tests
```bash
# Run full verification on sample bills
python backend/main.py
```

### Validation Criteria
1. ✅ Duplicate bill items appear multiple times in output
2. ✅ Same rate-sheet entry can be reused for multiple bill items
3. ✅ Hybrid scoring combines semantic + token signals
4. ✅ Items get GREEN/RED when match found (not MISMATCH)
5. ✅ MISMATCH only when no reasonable match exists
6. ✅ Every item assigned to best category (even if low confidence)
7. ✅ Non-medical artifacts ignored in similarity scoring

---

## 📝 Configuration

### Environment Variables
```bash
# Thresholds (can be adjusted)
CATEGORY_SIMILARITY_THRESHOLD=0.70  # Hard threshold (not used for blocking)
CATEGORY_SOFT_THRESHOLD=0.50        # Soft threshold (log only)
ITEM_SIMILARITY_THRESHOLD=0.85      # Auto-match threshold
HYBRID_SCORE_THRESHOLD=0.60         # New: Hybrid matching threshold

# Weights for hybrid scoring
HYBRID_WEIGHT_SEMANTIC=0.6
HYBRID_WEIGHT_TOKEN=0.3
HYBRID_WEIGHT_CONTAINMENT=0.1

# Top-K matching
TOP_K_MATCHES=3  # Consider top-3 candidates
```

---

## ⚠️ Explicit Non-Goals (Phase-2)

**DO NOT** implement in Phase-1:
- ❌ Deduplication of bill items
- ❌ One-to-one consumption of rate entries
- ❌ Strict category equality enforcement
- ❌ Performance optimization
- ❌ Pricing accuracy optimization
- ❌ Advanced LLM strategies

---

## ✅ Success Criteria

Phase-1 is successful if:
1. ✅ Mismatch rate drops from ~80% to ~20%
2. ✅ Duplicate bill items are preserved in output
3. ✅ Rate-sheet entries can be reused
4. ✅ Hybrid matching is implemented and working
5. ✅ Category mismatch doesn't block item matching
6. ✅ Non-medical artifacts are filtered
7. ✅ All tests pass
8. ✅ No regressions in existing working cases (consultations)

---

**Author**: AI Assistant  
**Date**: 2026-02-07  
**Status**: Ready for Implementation  
**Priority**: CRITICAL (Phase-1 foundation)

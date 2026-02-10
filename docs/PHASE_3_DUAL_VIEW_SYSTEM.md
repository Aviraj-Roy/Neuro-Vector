# Phase-3: Dual-View Output System

## 🎯 Overview

**Phase-3 Goal:** Introduce two output views from the same verification run:

1. **Debug View** (Full Trace) - For developers/internal use
2. **Final View** (Clean Report) - For users/reports

**Core Principle:** One verification, two perspectives

---

## 📊 Phase Evolution

### **Phase-1: Exhaustive Item-Level Listing**
- Every bill item processed and listed (including duplicates)
- No deduplication
- Final status: GREEN | RED | MISMATCH | ALLOWED_NOT_COMPARABLE

### **Phase-2: Clinically Meaningful Aggregation**
- Aggregation layer with line-item breakdown
- Category reconciliation
- Enhanced diagnostics with hybrid scoring
- Financial summary (4 levels)

### **Phase-3: Dual-View Output System** ⭐ NEW
- **Debug View:** Full trace with all matching details
- **Final View:** Clean, user-facing report
- **Consistency validation:** Ensures no items disappear

---

## 🔍 Debug View (Full Trace)

### **Purpose**
For developers, debugging, and detailed analysis.

### **What It Shows**
For **every bill item**, include:

✅ **Original Data**
- Original bill line text
- Normalized item name
- Bill amount

✅ **Category Detection**
- Detected bill category
- Category attempted for matching
- All categories tried (if reconciliation occurred)

✅ **Matching Details**
- Matching strategy used (exact / fuzzy / hybrid / hybrid_v2 / package / none)
- Semantic similarity score
- Token overlap score
- Medical anchor score
- Hybrid score (final)

✅ **Matching Result**
- Best candidate from tie-up (even if rejected)
- Best candidate similarity
- Matched item (only if accepted)

✅ **Pricing**
- Allowed rate (per unit)
- Allowed amount
- Extra amount (if overcharged)

✅ **Final Result**
- Final verification status
- Failure reason (if not GREEN)

✅ **Additional Context**
- Notes (e.g., "admin charge", "package-only item", "reconciliation succeeded")
- Reconciliation attempted/succeeded flags
- All categories tried list

### **Rules**
- ❌ No collapsing
- ❌ No hiding duplicates
- ✅ Every match attempt must be visible
- ✅ Order must match original bill order

### **Output Format**
Structured JSON or verbose console log (consistent).

### **Example Output**

```
================================================================================
DEBUG VIEW (Full Trace)
================================================================================
Hospital: Apollo Hospital
Matched Hospital: Apollo Hospitals (similarity=0.950)
Total Items Processed: 8
================================================================================

================================================================================
CATEGORY: MEDICINES
================================================================================

  [1] 1. NICORANDIL 5MG
      Normalized: nicorandil 5mg
      Bill Amount: ₹19.70
      Category: medicines
      Matching Strategy: hybrid_v2
      Semantic Similarity: 0.980
      Token Overlap: 0.950
      Medical Anchor Score: 0.400
      Hybrid Score: 0.938
      Best Candidate: NICORANDIL 5MG (sim=0.980)
      ✅ Matched: NICORANDIL 5MG
      Allowed Rate: ₹49.25
      Allowed Amount: ₹49.25
      Status: ✅ GREEN

  [2] 2. NICORANDIL 5MG
      Normalized: nicorandil 5mg
      Bill Amount: ₹19.70
      Category: medicines
      Matching Strategy: hybrid_v2
      Semantic Similarity: 0.980
      Hybrid Score: 0.938
      ✅ Matched: NICORANDIL 5MG
      Allowed Rate: ₹49.25
      Allowed Amount: ₹49.25
      Status: ✅ GREEN

  [3] 3. PARACETAMOL 500MG
      Normalized: paracetamol 500mg
      Bill Amount: ₹25.00
      Category: medicines
      Matching Strategy: hybrid_v2
      Semantic Similarity: 0.990
      Medical Anchor Score: 0.400
      Hybrid Score: 0.945
      ✅ Matched: PARACETAMOL 500MG
      Allowed Rate: ₹15.00
      Allowed Amount: ₹15.00
      Status: ❌ RED
      Extra Amount: ₹10.00

================================================================================
CATEGORY: DIAGNOSTICS
================================================================================

  [1] 5. MRI BRAIN
      Normalized: mri brain
      Bill Amount: ₹10770.00
      Category: diagnostics
      Matching Strategy: hybrid_v2
      Semantic Similarity: 0.920
      Medical Anchor Score: 0.600
      Hybrid Score: 0.910
      ✅ Matched: MRI Brain
      Allowed Rate: ₹8500.00
      Allowed Amount: ₹8500.00
      Status: ❌ RED
      Extra Amount: ₹2270.00

================================================================================
CATEGORY: CONSULTATION
================================================================================

  [1] 7. CONSULTATION - FIRST VISIT | Dr. Vivek Jacob P
      Normalized: consultation first visit
      Bill Amount: ₹1500.00
      Category: consultation
      Matching Strategy: hybrid_v2
      Semantic Similarity: 0.750
      Hybrid Score: 0.688
      ✅ Matched: Consultation
      Allowed Rate: ₹1500.00
      Allowed Amount: ₹1500.00
      Status: ✅ GREEN

  [2] 8. CROSS CONSULTATION – IP
      Normalized: cross consultation ip
      Bill Amount: ₹2500.00
      Category: consultation
      Category Attempted: specialist_consultation (reconciled)
      Matching Strategy: hybrid_v2
      Semantic Similarity: 0.780
      Hybrid Score: 0.780
      Best Candidate: Specialist Consultation - Inpatient (sim=0.780)
      ✅ Matched: Specialist Consultation - Inpatient
      Allowed Rate: ₹2500.00
      Allowed Amount: ₹2500.00
      Status: ✅ GREEN
      Note: Found in alternative category 'specialist_consultation' after original category 'consultation' failed
      Reconciliation: ✅ Succeeded
      Categories Tried: consultation, specialist_consultation

================================================================================
END DEBUG VIEW
================================================================================
```

---

## 📋 Final View (Clean Report)

### **Purpose**
For users, reports, and presentations.

### **What It Shows**
For each category, show only **final resolved items**:

✅ **Display name** (cleaned, human-readable)
✅ **Final status:**
- GREEN → matched within allowed
- RED → overcharged
- ALLOWED_NOT_COMPARABLE → allowed but not rate-compared
- MISMATCH → not covered
✅ **Bill amount**
✅ **Allowed amount** (if applicable)
✅ **Extra amount** (if RED)

For **MISMATCH items**, show a short reason tag only:
- NOT_IN_TIEUP
- LOW_SIMILARITY
- PACKAGE_ONLY
- ADMIN_CHARGE

### **Rules**
- ❌ No similarity scores
- ❌ No candidates
- ❌ No internal notes
- ✅ One line per bill item
- ✅ Duplicates still appear multiple times (no deduplication)
- ✅ Readable by non-technical users

### **Output Format**
Clean, structured report.

### **Example Output**

```
================================================================================
FINAL VIEW (User Report)
================================================================================
Hospital: Apollo Hospital
Matched Hospital: Apollo Hospitals
================================================================================

────────────────────────────────────────────────────────────────────────────────
📁 MEDICINES
────────────────────────────────────────────────────────────────────────────────
  1. ✅ NICORANDIL 5MG | Bill: ₹19.70 | Allowed: ₹49.25
  2. ✅ NICORANDIL 5MG | Bill: ₹19.70 | Allowed: ₹49.25
  3. ✅ NICORANDIL 5MG | Bill: ₹19.70 | Allowed: ₹49.25
  4. ✅ NICORANDIL 5MG | Bill: ₹19.70 | Allowed: ₹49.25
  5. ❌ PARACETAMOL 500MG | Bill: ₹25.00 | Allowed: ₹15.00 | Extra: ₹10.00

  Category Totals:
    Bill: ₹103.80
    Allowed: ₹212.00
    Extra: ₹10.00

────────────────────────────────────────────────────────────────────────────────
📁 DIAGNOSTICS
────────────────────────────────────────────────────────────────────────────────
  1. ❌ MRI Brain | Bill: ₹10770.00 | Allowed: ₹8500.00 | Extra: ₹2270.00
  2. ✅ X-Ray Chest | Bill: ₹1500.00 | Allowed: ₹1500.00

  Category Totals:
    Bill: ₹12270.00
    Allowed: ₹10000.00
    Extra: ₹2270.00

────────────────────────────────────────────────────────────────────────────────
📁 CONSULTATION
────────────────────────────────────────────────────────────────────────────────
  1. ✅ Consultation | Bill: ₹1500.00 | Allowed: ₹1500.00

────────────────────────────────────────────────────────────────────────────────
📁 SPECIALIST_CONSULTATION
────────────────────────────────────────────────────────────────────────────────
  1. ✅ Specialist Consultation - Inpatient | Bill: ₹2500.00 | Allowed: ₹2500.00

  Category Totals:
    Bill: ₹2500.00
    Allowed: ₹2500.00

================================================================================
GRAND TOTALS
================================================================================
  Total Bill: ₹14873.80
  Total Allowed: ₹12712.00
  Total Extra: ₹2280.00

  Status Summary:
    ✅ GREEN: 6
    ❌ RED: 2
    ⚠️ MISMATCH: 0
    ℹ️ ALLOWED_NOT_COMPARABLE: 0

================================================================================
END FINAL VIEW
================================================================================
```

---

## 🔄 Implementation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE-1 VERIFICATION                             │
│              (Exhaustive Item-Level Listing)                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE-2 AGGREGATION                              │
│         (Clinically Meaningful Comparison Layer)                    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PHASE-3 DUAL-VIEW TRANSFORM                        │
│                                                                     │
│  ┌───────────────────────────────────────────────────────┐         │
│  │  Build Debug View (Full Trace)                       │         │
│  │  • Extract all matching details                       │         │
│  │  • Preserve all scores and candidates                 │         │
│  │  • Add notes and diagnostics                          │         │
│  └───────────────────────────────────────────────────────┘         │
│                         │                                           │
│                         ▼                                           │
│  ┌───────────────────────────────────────────────────────┐         │
│  │  Build Final View (Clean Report)                     │         │
│  │  • Transform debug traces to clean items             │         │
│  │  • Calculate category and grand totals               │         │
│  │  • Remove internal details                            │         │
│  └───────────────────────────────────────────────────────┘         │
│                         │                                           │
│                         ▼                                           │
│  ┌───────────────────────────────────────────────────────┐         │
│  │  Validate Consistency                                 │         │
│  │  • Verify item counts match                           │         │
│  │  • Verify totals match                                │         │
│  │  • Ensure no items disappeared                        │         │
│  └───────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE-3 OUTPUT                                   │
│                                                                     │
│  • Debug View (Full Trace)                                          │
│  • Final View (Clean Report)                                        │
│  • Consistency Check Results                                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ✅ Validation Checklist

Before finishing, verify:

- [ ] **No bill item disappears between Debug and Final views**
  - Item count in Debug View == Item count in Final View
  
- [ ] **Duplicate bill lines appear multiple times**
  - No automatic deduplication
  - Each occurrence is listed separately
  
- [ ] **Debug view contains full reasoning**
  - All matching attempts visible
  - All scores and candidates shown
  - All notes and diagnostics included
  
- [ ] **Final view is readable by non-technical users**
  - No similarity scores
  - No internal candidates
  - Clean status indicators
  - Short reason tags only
  
- [ ] **Totals match between views**
  - Grand total bill matches
  - Grand total allowed matches
  - Grand total extra matches

---

## 📁 File Structure

```
backend/app/verifier/
├── models_v3.py              # Phase-3 models (Debug + Final views)
├── phase3_transformer.py     # View transformation logic
└── phase3_display.py         # Display formatters
```

---

## 🚀 Usage Example

```python
from app.verifier.phase2_processor import process_phase2
from app.verifier.phase3_transformer import transform_to_phase3
from app.verifier.phase3_display import display_phase3_response

# Run Phase-1 and Phase-2
phase1_response = verifier.verify_bill(bill_input)
phase2_response = process_phase2(phase1_response, hospital_name)

# Transform to Phase-3 dual-view
phase3_response = transform_to_phase3(phase2_response)

# Display both views
display_phase3_response(phase3_response, view="both")

# Or display only one view
display_phase3_response(phase3_response, view="debug")   # Developer view
display_phase3_response(phase3_response, view="final")   # User view

# Access views programmatically
debug_view = phase3_response.debug_view
final_view = phase3_response.final_view

# Check consistency
if phase3_response.consistency_check['all_checks_passed']:
    print("✅ Consistency validation passed")
else:
    print("❌ Consistency validation failed")
```

---

## 🎯 Key Benefits

### **For Developers**
- ✅ Full visibility into matching process
- ✅ Easy debugging with complete trace
- ✅ All scores and candidates visible
- ✅ Reconciliation path tracked

### **For Users**
- ✅ Clean, readable report
- ✅ No technical jargon
- ✅ Clear status indicators
- ✅ Financial totals at a glance

### **For Both**
- ✅ Consistent data (one verification run)
- ✅ No items disappear
- ✅ Duplicates preserved
- ✅ Validation guarantees

---

## 📊 Success Metrics

### **Functional**
- ✅ Debug view shows all matching details
- ✅ Final view is user-friendly
- ✅ No items disappear between views
- ✅ Totals match exactly
- ✅ Duplicates preserved

### **Usability**
- ✅ Developers can debug easily
- ✅ Users can understand reports
- ✅ Both views are consistent
- ✅ Validation catches discrepancies

---

## 🎉 Phase-3 Complete!

**Core Principle:** One verification, two perspectives

**Guarantee:** No data loss, full traceability, dual perspectives

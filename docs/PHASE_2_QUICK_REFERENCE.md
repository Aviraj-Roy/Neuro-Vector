# Phase-2 Quick Reference

## 🎯 What is Phase-2?

**Phase-1:** Exhaustive item-level listing (every item listed, even duplicates)  
**Phase-2:** Clinically meaningful aggregation layer (group duplicates, reconcile categories, financial summary)

**Core Principle:** Non-destructive aggregation with full traceability

---

## 📊 Key Differences: Phase-1 vs Phase-2

| Aspect | Phase-1 | Phase-2 |
|--------|---------|---------|
| **Output** | Every line item listed | Aggregated groups + breakdown |
| **Duplicates** | Listed separately | Grouped together |
| **Matching** | Semantic + Token + Containment | + Medical Anchors (dosage, modality, bodypart) |
| **Category Handling** | Single category attempt | Multi-category reconciliation |
| **Financial Summary** | Basic totals | Category + Grand totals |
| **Diagnostics** | Basic failure reason | Deep explainability with hybrid scores |

---

## 🔑 Key Components

### **1. Rate Cache**
```python
# Cache allowed rates to avoid re-lookup
rate_cache = {
    ("nicorandil_5mg", "NICORANDIL 5MG"): 49.25,
    ("paracetamol_500mg", "PARACETAMOL 500MG"): 15.00
}
```

### **2. Item Aggregation**
```python
# Group by: (normalized_name, matched_reference, category)
{
    "normalized_name": "nicorandil_5mg",
    "occurrences": 4,
    "total_bill": 78.80,
    "line_items": [...]  # Preserve breakdown
}
```

### **3. Status Resolution**
```
Priority: RED > MISMATCH > GREEN > ALLOWED_NOT_COMPARABLE > IGNORED
```

### **4. Category Reconciliation**
```
Original category fails → Try all other categories → Pick best match
```

### **5. Medical Anchors**
```python
# Dosage: "5mg", "10ml", "500mcg"
# Modality: "MRI", "CT", "X-Ray"
# Body Part: "brain", "chest", "abdomen"
```

### **6. Hybrid Scoring V2**
```
Final Score = 0.50 × Semantic + 0.25 × Token + 0.25 × Medical Anchors
```

---

## 📐 Processing Pipeline

```
Phase-1 Output
      ↓
1. Build Rate Cache
      ↓
2. Aggregate Items (group duplicates)
      ↓
3. Resolve Statuses (RED > MISMATCH > GREEN)
      ↓
4. Reconcile Categories (retry failed items)
      ↓
5. Calculate Financial Summary
      ↓
Phase-2 Output
```

---

## 🎨 Output Structure

### **Aggregated Item**
```json
{
  "normalized_name": "nicorandil_5mg",
  "matched_reference": "NICORANDIL 5MG",
  "category": "medicines",
  "occurrences": 4,
  "total_bill": 78.80,
  "total_allowed": 197.00,
  "status": "GREEN",
  "line_items": [
    {"bill_amount": 19.70, "allowed_amount": 49.25},
    {"bill_amount": 19.70, "allowed_amount": 49.25},
    {"bill_amount": 19.70, "allowed_amount": 49.25},
    {"bill_amount": 19.70, "allowed_amount": 49.25}
  ]
}
```

### **Financial Summary**
```json
{
  "category_totals": [
    {
      "category": "medicines",
      "total_bill": 103.80,
      "total_allowed": 212.00,
      "green_count": 1,
      "red_count": 1
    }
  ],
  "grand_totals": {
    "total_bill": 14873.80,
    "total_allowed": 12712.00,
    "total_extra": 2280.00,
    "green_count": 3,
    "red_count": 2,
    "mismatch_count": 0
  }
}
```

---

## 🚀 Implementation Phases

### **Week 1: Core Aggregation**
- Create Phase-2 models
- Implement rate cache builder
- Implement item aggregator
- Implement status resolver

### **Week 2: Enhanced Matching**
- Implement medical anchor extraction
- Implement hybrid scoring v2
- Update matcher to use hybrid v2

### **Week 3: Category Reconciliation**
- Implement category reconciler
- Update diagnostics
- Implement artifact detection

### **Week 4: Financial Aggregation**
- Implement financial aggregator
- Implement Phase-2 orchestrator
- Update API endpoint

### **Week 5: Display & Documentation**
- Update display formatter
- Create documentation
- Performance optimization
- User acceptance testing

---

## 📋 Status Resolution Rules

| Condition | Final Status |
|-----------|--------------|
| Any RED present | ❌ RED |
| Only GREEN + Allowed-Not-Comparable | ✅ GREEN |
| Only MISMATCH | ⚠️ MISMATCH |
| Admin / Artifact only | ⚪ IGNORED |

---

## 🔍 Diagnostics (Enhanced)

```json
{
  "normalized_item_name": "cross_consultation_ip",
  "best_candidate": "Specialist Consultation",
  "best_candidate_similarity": 0.61,
  "category_attempted": "consultation",
  "all_categories_tried": ["consultation", "specialist_consultation"],
  "failure_reason": "NOT_IN_TIEUP",
  "hybrid_score_breakdown": {
    "semantic": 0.61,
    "token_overlap": 0.33,
    "medical_anchors": 0.0,
    "final_score": 0.52
  }
}
```

---

## 🎯 Success Metrics

### **Functional**
- ✅ No items disappear between Phase-1 and Phase-2
- ✅ Aggregation is reversible
- ✅ Category reconciliation improves match rate by 10-15%
- ✅ Medical anchors improve accuracy by 5-10%

### **Performance**
- ✅ Phase-2 processing < 500ms overhead
- ✅ Rate cache reduces redundant lookups
- ✅ Handles 1000+ line items efficiently

### **Auditability**
- ✅ Every number traces back to line items
- ✅ Reconciliation path is visible
- ✅ Hybrid score breakdown available
- ✅ All diagnostics are comprehensive

---

## 📚 Documentation

- **Architecture:** `PHASE_2_ARCHITECTURE.md` - Complete technical specification
- **Implementation Plan:** `PHASE_2_IMPLEMENTATION_PLAN.md` - Step-by-step guide
- **Quick Reference:** `PHASE_2_QUICK_REFERENCE.md` - This document

---

## 🛠️ Key Files to Create

```
backend/app/verifier/
├── models_v2.py              # Phase-2 models
├── aggregator.py             # Rate cache + aggregation
├── reconciler.py             # Category reconciliation
├── financial.py              # Financial aggregation
├── phase2_processor.py       # Main orchestrator
├── medical_anchors.py        # Medical keyword extraction
└── artifact_detector.py      # OCR artifact detection
```

---

## ⚡ Quick Start

1. **Read:** `PHASE_2_ARCHITECTURE.md` for complete specification
2. **Follow:** `PHASE_2_IMPLEMENTATION_PLAN.md` for step-by-step tasks
3. **Reference:** This document for quick lookups

---

## 🎉 Ready to Build Phase-2!

**Remember:** Phase-2 is about making Phase-1's exhaustive data clinically and financially meaningful, without losing any information.

**Core Principle:** Non-destructive aggregation with full traceability.

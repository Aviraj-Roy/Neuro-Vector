# System Architecture & Data Flow
## Medical Bill Verification Backend

---

## 🏗️ Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MEDICAL BILL VERIFICATION SYSTEM              │
│                                                                      │
│  ┌────────────┐                                                     │
│  │   PDF File │                                                     │
│  └──────┬─────┘                                                     │
│         │                                                           │
│         ▼                                                           │
│  ┌────────────────────┐                                            │
│  │  PDF to Images     │  (pdf_loader.py)                           │
│  │  - Multi-page      │                                            │
│  │  - Poppler-based   │                                            │
│  └──────┬─────────────┘                                            │
│         │                                                           │
│         ▼                                                           │
│  ┌────────────────────┐                                            │
│  │  Image Preprocess  │  (image_preprocessor.py)                   │
│  │  - Grayscale       │                                            │
│  │  - Denoise         │                                            │
│  └──────┬─────────────┘                                            │
│         │                                                           │
│         ▼                                                           │
│  ┌────────────────────┐                                            │
│  │   PaddleOCR        │  (paddle_engine.py)                        │
│  │  - Text extraction │                                            │
│  │  - Bounding boxes  │                                            │
│  │  - Confidence      │                                            │
│  └──────┬─────────────┘                                            │
│         │                                                           │
│         ▼                                                           │
│  ┌────────────────────────────────────────────────────┐            │
│  │           BILL EXTRACTOR (bill_extractor.py)       │            │
│  │                                                     │            │
│  │  ┌──────────────────────────────────────────────┐  │            │
│  │  │  Stage 1: Header Parser                      │  │            │
│  │  │  ┌────────────────────────────────────────┐  │  │            │
│  │  │  │ ✨ NEW: Hospital Name Extraction      │  │  │            │
│  │  │  │  - Label patterns                      │  │  │            │
│  │  │  │  - Fallback patterns                   │  │  │            │
│  │  │  │  - Validation                          │  │  │            │
│  │  │  └────────────────────────────────────────┘  │  │            │
│  │  │  - Patient info (name, MRN)                  │  │            │
│  │  │  - Bill metadata (number, date)              │  │            │
│  │  └──────────────────────────────────────────────┘  │            │
│  │                                                     │            │
│  │  ┌──────────────────────────────────────────────┐  │            │
│  │  │  Stage 2: Item Parser                        │  │            │
│  │  │  - Categorize items (medicines, tests, etc)  │  │            │
│  │  │  - Extract amounts                           │  │            │
│  │  │  - Separate discounts                        │  │            │
│  │  └──────────────────────────────────────────────┘  │            │
│  │                                                     │            │
│  │  ┌──────────────────────────────────────────────┐  │            │
│  │  │  Stage 3: Payment Parser                     │  │            │
│  │  │  - Detect RCPO/RCP* entries                  │  │            │
│  │  │  - Excluded from final output                │  │            │
│  │  └──────────────────────────────────────────────┘  │            │
│  │                                                     │            │
│  │  ┌────────────────────────────────────────────┐    │            │
│  │  │ ✨ NEW: Hospital Category Creation        │    │            │
│  │  │  {                                         │    │            │
│  │  │    "Hospital - ": [                        │    │            │
│  │  │      {                                     │    │            │
│  │  │        "item_name": "Apollo Hospital",    │    │            │
│  │  │        "amount": 0                         │    │            │
│  │  │      }                                     │    │            │
│  │  │    ]                                       │    │            │
│  │  │  }                                         │    │            │
│  │  └────────────────────────────────────────────┘    │            │
│  └─────────────────────────────────────────────────────┘            │
│         │                                                           │
│         ▼                                                           │
│  ┌────────────────────┐                                            │
│  │   MongoDB Storage  │  (mongo_client.py)                         │
│  │  - Structured bill │                                            │
│  │  - Hospital name   │  ✨ NEW!                                   │
│  │  - Hospital cat    │  ✨ NEW!                                   │
│  └──────┬─────────────┘                                            │
│         │                                                           │
│         ▼                                                           │
│  ┌────────────────────────────────────────────────────┐            │
│  │  ✨ NEW: VERIFICATION PIPELINE (verifier.py)      │            │
│  │                                                     │            │
│  │  ┌──────────────────────────────────────────────┐  │            │
│  │  │  Step 1: Hospital Matching                   │  │            │
│  │  │  - Semantic embedding (BGE-base)             │  │            │
│  │  │  - FAISS similarity search                   │  │            │
│  │  │  - Select best tie-up rate sheet             │  │            │
│  │  └──────────────────────────────────────────────┘  │            │
│  │         │                                           │            │
│  │         ▼                                           │            │
│  │  ┌──────────────────────────────────────────────┐  │            │
│  │  │  Step 2: Category Matching                   │  │            │
│  │  │  - Threshold: 0.70                           │  │            │
│  │  │  - Match bill categories to tie-up           │  │            │
│  │  └──────────────────────────────────────────────┘  │            │
│  │         │                                           │            │
│  │         ▼                                           │            │
│  │  ┌──────────────────────────────────────────────┐  │            │
│  │  │  Step 3: Item Matching                       │  │            │
│  │  │  - Threshold: 0.85                           │  │            │
│  │  │  - Semantic match first                      │  │            │
│  │  │  - LLM fallback if 0.70 < sim < 0.85         │  │            │
│  │  │  - Ollama (Phi-3 / Qwen)                     │  │            │
│  │  └──────────────────────────────────────────────┘  │            │
│  │         │                                           │            │
│  │         ▼                                           │            │
│  │  ┌──────────────────────────────────────────────┐  │            │
│  │  │  Step 4: Price Checking                      │  │            │
│  │  │  - Compare bill amount vs tie-up rate        │  │            │
│  │  │  - GREEN: amount ≤ allowed                   │  │            │
│  │  │  - RED: amount > allowed                     │  │            │
│  │  │  - MISMATCH: no match found                  │  │            │
│  │  └──────────────────────────────────────────────┘  │            │
│  └─────────────────────────────────────────────────────┘            │
│         │                                                           │
│         ▼                                                           │
│  ┌────────────────────────────────────────────────────┐            │
│  │  ✨ NEW: RESULT DISPLAY (main.py)                 │            │
│  │                                                     │            │
│  │  ╔════════════════════════════════════════════╗    │            │
│  │  ║     VERIFICATION RESULTS                   ║    │            │
│  │  ╠════════════════════════════════════════════╣    │            │
│  │  ║  Hospital: Apollo Hospital                 ║    │            │
│  │  ║  Matched: Apollo Hospital (95.23%)         ║    │            │
│  │  ║                                            ║    │            │
│  │  ║  Summary:                                  ║    │            │
│  │  ║    ✅ GREEN: 45                            ║    │            │
│  │  ║    ❌ RED: 3                               ║    │            │
│  │  ║    ⚠️  MISMATCH: 2                         ║    │            │
│  │  ║                                            ║    │            │
│  │  ║  Financial:                                ║    │            │
│  │  ║    Bill: ₹25,430.00                        ║    │            │
│  │  ║    Allowed: ₹24,200.00                     ║    │            │
│  │  ║    Extra: ₹1,230.00                        ║    │            │
│  │  ╚════════════════════════════════════════════╝    │            │
│  └─────────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Transformation Flow

### 1. PDF → OCR Output
```
Input: Apollo.pdf

Output:
{
  "raw_text": "Apollo Hospital\nPatient: Mr Mohak...",
  "lines": [
    {"text": "Apollo Hospital", "page": 0, "box": [...], "confidence": 0.98},
    {"text": "Patient: Mr Mohak Nandy", "page": 0, ...},
    ...
  ],
  "item_blocks": [...]
}
```

### 2. OCR → Structured Bill
```
Input: OCR lines + item_blocks

Processing:
- HeaderParser extracts hospital name ✨ NEW!
- ItemParser categorizes items
- PaymentParser filters payments

Output:
{
  "header": {
    "hospital_name": "Apollo Hospital",  ✨ NEW!
    "primary_bill_number": "APL2024001",
    "billing_date": "2024-01-15"
  },
  "patient": {
    "name": "Mr Mohak Nandy",
    "mrn": "MRN123456"
  },
  "items": {
    "Hospital - ": [...],  ✨ NEW! (at top)
    "medicines": [...],
    "diagnostics_tests": [...]
  },
  "grand_total": 25430.00
}
```

### 3. MongoDB → Verification Input
```
MongoDB Document:
{
  "header": {"hospital_name": "Apollo Hospital"},
  "items": {
    "Hospital - ": [{"item_name": "Apollo Hospital", "amount": 0}],
    "medicines": [{"item_name": "Paracetamol 500mg", "amount": 10.00}]
  }
}

Transformed to BillInput:
{
  "hospital_name": "Apollo Hospital",
  "categories": [
    {
      "category_name": "Hospital - ",
      "items": [{"item_name": "Apollo Hospital", "amount": 0}]
    },
    {
      "category_name": "medicines",
      "items": [{"item_name": "Paracetamol 500mg", "amount": 10.00}]
    }
  ]
}
```

### 4. Verification → Results
```
Input: BillInput

Processing:
1. Match "Apollo Hospital" → Apollo Hospital (95.23%)
2. Match "medicines" → Medicines (98.50%)
3. Match "Paracetamol 500mg" → Paracetamol 500mg Tablet (92.10%)
4. Check price: 10.00 ≤ 2.50 * 4 = 10.00 → GREEN ✅

Output:
{
  "hospital": "Apollo Hospital",
  "matched_hospital": "Apollo Hospital",
  "hospital_similarity": 0.9523,
  "green_count": 45,
  "red_count": 3,
  "mismatch_count": 2,
  "total_extra_amount": 1230.00,
  "results": [...]
}
```

---

## 🎯 Key Integration Points

### Integration Point 1: Hospital Name Extraction
**Location**: `backend/app/extraction/bill_extractor.py`

```python
# HeaderParser._extract_fallback_hospitals()
for line in lines:
    for pattern in HOSPITAL_FALLBACK_PATTERNS:
        m = re.search(pattern, text)
        if m:
            hospital_name = m.group(1).strip()
            if self._is_valid_fallback_hospital(hospital_name):
                self._fallback_hospital_candidates.append(...)
```

### Integration Point 2: Hospital Category Creation
**Location**: `backend/app/extraction/bill_extractor.py`

```python
# BillExtractor.extract()
hospital_name = header_data["header"].get("hospital_name") or "UNKNOWN"
hospital_category = {
    "Hospital - ": [
        {"item_name": hospital_name, "amount": 0, "quantity": 1}
    ]
}
categorized_with_hospital = {**hospital_category, **categorized}
```

### Integration Point 3: Verifier Call
**Location**: `backend/main.py`

```python
# After process_bill()
from app.verifier.api import verify_bill_from_mongodb_sync

bill_id = process_bill(str(pdf_path))
verification_result = verify_bill_from_mongodb_sync(bill_id)

# Display results
print(f"GREEN: {verification_result.get('green_count', 0)}")
print(f"RED: {verification_result.get('red_count', 0)}")
```

---

## 📊 Component Interaction Diagram

```
┌─────────────┐
│   main.py   │  ← Entry point
└──────┬──────┘
       │
       ├─→ process_bill() ────────┐
       │                          │
       │                          ▼
       │                   ┌──────────────┐
       │                   │ pdf_loader   │
       │                   └──────┬───────┘
       │                          │
       │                          ▼
       │                   ┌──────────────┐
       │                   │ paddle_ocr   │
       │                   └──────┬───────┘
       │                          │
       │                          ▼
       │                   ┌──────────────────┐
       │                   │ bill_extractor   │ ✨ Hospital extraction
       │                   └──────┬───────────┘
       │                          │
       │                          ▼
       │                   ┌──────────────┐
       │                   │ mongo_client │ ✨ Hospital category
       │                   └──────────────┘
       │
       └─→ verify_bill_from_mongodb_sync() ✨ NEW!
                          │
                          ▼
                   ┌──────────────┐
                   │   verifier   │
                   └──────┬───────┘
                          │
                          ├─→ SemanticMatcher
                          │   └─→ EmbeddingService
                          │       └─→ FAISS
                          │
                          ├─→ LLMRouter
                          │   └─→ Ollama (Phi-3/Qwen)
                          │
                          └─→ PriceChecker
                              └─→ VerificationResponse
```

---

## 🔐 Security & Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    DATA SECURITY                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  PDF File (Local)                                        │
│      ↓                                                   │
│  Temporary Images (uploads/, uploads/processed/)         │
│      ↓                                                   │
│  OCR Text (In-Memory)                                    │
│      ↓                                                   │
│  Structured Bill (MongoDB - Local/Cloud)                 │
│      ↓                                                   │
│  Embeddings (In-Memory + Cache)                          │
│      ↓                                                   │
│  LLM Processing (Local Ollama - No External API)         │
│      ↓                                                   │
│  Verification Results (Console + Optional MongoDB)       │
│                                                          │
│  ✅ No external API calls                               │
│  ✅ All processing local                                │
│  ✅ Temporary files cleaned up                          │
│  ✅ MongoDB credentials in .env                         │
└─────────────────────────────────────────────────────────┘
```

---

## 📈 Performance Characteristics

| Stage | Time (Typical) | Bottleneck | Optimization |
|-------|----------------|------------|--------------|
| PDF → Images | 1-2s | Poppler | Use SSD |
| OCR | 3-5s/page | PaddleOCR | GPU acceleration |
| Extraction | <1s | CPU | Efficient regex |
| MongoDB Save | <0.5s | Network | Local MongoDB |
| Hospital Match | <0.1s | Embeddings | Cache enabled |
| Item Match | 0.1-0.5s/item | Embeddings | FAISS index |
| LLM Call | 1-3s/call | Ollama | Use phi3:mini |
| **Total** | **10-30s** | **OCR + LLM** | **GPU + Cache** |

---

## 🎓 Learning Path

For new developers, understand the system in this order:

1. **Start**: `backend/main.py` - Entry point
2. **Processing**: `app/main.py` - Bill processing pipeline
3. **OCR**: `app/ocr/paddle_engine.py` - Text extraction
4. **Extraction**: `app/extraction/bill_extractor.py` - Structuring (✨ Hospital extraction here)
5. **Storage**: `app/db/mongo_client.py` - MongoDB interface
6. **Verification**: `app/verifier/verifier.py` - LLM comparison (✨ Integration here)
7. **API**: `app/verifier/api.py` - REST endpoints (✨ Sync wrapper here)

---

**Last Updated**: 2026-02-03  
**Version**: 1.0.0  
**Status**: ✅ Production Ready

# Quick Reference - Medical Bill Verification Backend

## 🚀 Quick Start (30 seconds)

```bash
# 1. Start MongoDB (if not running)
mongod

# 2. Start Ollama (in separate terminal)
ollama serve

# 3. Run the backend
python backend/main.py
```

**Expected Output**: Bill extraction + Verification results with GREEN/RED/MISMATCH status

---

## 📋 What Was Implemented

### ✅ 1. Hospital Category Added
- Hospital name extracted from OCR
- "Hospital - " category in MongoDB bills
- Placed at top of categories
- Used by verifier for matching

### ✅ 2. LLM Comparison Fixed
- Verifier now integrated in main.py
- Results displayed in console
- Shows GREEN/RED/MISMATCH counts
- Financial summaries included

### ✅ 3. Run Guide Created
- Complete setup instructions
- Troubleshooting section
- Multiple run methods
- See: `BACKEND_RUN_GUIDE.md`

---

## 📁 Key Files Changed

| File | What Changed |
|------|--------------|
| `backend/app/extraction/bill_extractor.py` | + Hospital name extraction<br>+ "Hospital - " category creation |
| `backend/main.py` | + Verifier integration<br>+ Result display |
| `backend/app/verifier/api.py` | + Sync verification wrapper |
| `BACKEND_RUN_GUIDE.md` | + Complete documentation (NEW) |
| `IMPLEMENTATION_SUMMARY.md` | + Technical details (NEW) |

---

## 🔍 MongoDB Structure (After Changes)

```json
{
  "header": {
    "hospital_name": "Apollo Hospital",  // ← NEW!
    "primary_bill_number": "APL2024001"
  },
  "items": {
    "Hospital - ": [  // ← NEW! (at top)
      {
        "item_name": "Apollo Hospital",
        "amount": 0
      }
    ],
    "medicines": [...],
    "diagnostics_tests": [...]
  }
}
```

---

## 💻 Console Output (After Changes)

```
✅ Successfully processed bill!
Upload ID: abc123...

================================================================================
VERIFICATION RESULTS                    ← NEW!
================================================================================
Hospital: Apollo Hospital
Matched Hospital: Apollo Hospital
Hospital Similarity: 95.23%

Summary:
  ✅ GREEN (Match): 45
  ❌ RED (Overcharged): 3
  ⚠️  MISMATCH (Not Found): 2

Financial Summary:
  Total Bill Amount: ₹25,430.00
  Total Allowed Amount: ₹24,200.00
  Total Extra Amount: ₹1,230.00
...
```

---

## 🔧 Common Commands

### Run Backend
```bash
python backend/main.py
```

### Run as API Server
```bash
cd backend
uvicorn app.verifier.api:app --reload --port 8001
```

### Run Tests
```bash
cd backend
python app/verifier/test_local_setup.py
```

### Check MongoDB
```bash
mongosh medical_bills
db.bills.findOne({}, {header: 1, items: 1})
```

---

## 🐛 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| "MongoDB connection failed" | `mongod` or check MONGO_URI in .env |
| "Ollama connection refused" | `ollama serve` in separate terminal |
| "No verification results" | Check Ollama is running + tie-ups exist |
| "No hospital name" | Check OCR output, may need custom patterns |

---

## 📚 Documentation

- **Setup Guide**: `BACKEND_RUN_GUIDE.md`
- **Implementation Details**: `IMPLEMENTATION_SUMMARY.md`
- **API Docs**: `http://localhost:8001/docs` (when running API)
- **Project README**: `README.md`

---

## 🎯 Verification Flow

```
PDF → OCR → Extraction → MongoDB → Verification → Display
                ↓            ↓           ↓
         Hospital Name   "Hospital -"  LLM Comparison
         Extracted       Category      Results Shown
```

---

## ✅ Checklist for New Setup

- [ ] MongoDB running
- [ ] Ollama running
- [ ] Models pulled (phi3:mini, qwen2.5:3b)
- [ ] Python deps installed
- [ ] .env configured
- [ ] Run `python backend/main.py`
- [ ] See extraction output
- [ ] See verification results ← **NEW!**

---

## 🔗 Quick Links

- MongoDB: `mongodb://localhost:27017`
- Ollama: `http://localhost:11434`
- API Server: `http://localhost:8001`
- API Docs: `http://localhost:8001/docs`

---

**Last Updated**: 2026-02-03  
**Status**: ✅ All 3 Tasks Complete

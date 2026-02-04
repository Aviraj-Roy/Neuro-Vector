# Quick Testing Guide

## 🚀 How to Test the Refactored Backend

### Prerequisites
```bash
# 1. Start MongoDB
mongod --dbpath /path/to/data

# 2. Start Ollama (for LLM verification)
ollama serve

# 3. Ensure you're in project root
cd c:\Users\USER\Documents\test\Neuro-Vector-Backend
```

---

## 📋 Testing Methods

### Method 1: Direct CLI (Recommended)

```bash
# Basic usage
python -m backend.main --bill "Apollo.pdf" --hospital "Apollo Hospital"

# Different hospital
python -m backend.main --bill "M_Bill.pdf" --hospital "Manipal Hospital"

# Skip verification (faster)
python -m backend.main --bill "bill.pdf" --hospital "Fortis Hospital" --no-verify

# Show help
python -m backend.main --help
```

**Output:**
```
✅ Successfully processed bill!
Upload ID: abc123...
Hospital: Apollo Hospital

================================================================================
VERIFICATION RESULTS
================================================================================
Hospital: Apollo Hospital
Matched Hospital: Apollo Hospital
Hospital Similarity: 100.00%

Summary:
  ✅ GREEN (Match): 45
  ❌ RED (Overcharged): 3
  ⚠️  MISMATCH (Not Found): 2
...
```

---

### Method 2: Test Script (Comprehensive)

```bash
# List available hospitals
python test_backend.py --list-hospitals

# Validate hospital only
python test_backend.py --hospital "Apollo Hospital" --validate-only

# Full test (process + verify)
python test_backend.py --hospital "Apollo Hospital" --bill "Apollo.pdf"

# Process without verification
python test_backend.py --hospital "Fortis Hospital" --bill "bill.pdf" --no-verify
```

**Output:**
```
================================================================================
TESTING HOSPITAL VALIDATION
================================================================================

1. Testing hospital: Apollo Hospital
   Normalized slug: apollo_hospital
   Expected tie-up file: backend\data\tieups\apollo_hospital.json
   File exists: True
   ✅ Validation passed

================================================================================
TESTING BILL PROCESSING
================================================================================

Processing bill: Apollo.pdf
Hospital: Apollo Hospital

✅ Bill processed successfully!
   Upload ID: xyz789...

================================================================================
✅ ALL TESTS PASSED!
================================================================================
```

---

### Method 3: Python REPL (Interactive)

```python
# Start Python
python

# Import functions
from backend.app.main import process_bill
from backend.app.verifier.api import verify_bill_from_mongodb_sync
from backend.app.verifier.hospital_validator import list_available_hospitals

# List hospitals
hospitals = list_available_hospitals("backend/data/tieups")
print(hospitals)
# ['Apollo Hospital', 'Fortis Hospital', 'Manipal Hospital', 'Max Healthcare', 'Medanta Hospital']

# Process a bill
upload_id = process_bill("Apollo.pdf", hospital_name="Apollo Hospital")
print(f"Upload ID: {upload_id}")

# Verify the bill
result = verify_bill_from_mongodb_sync(upload_id, hospital_name="Apollo Hospital")
print(f"Green: {result['green_count']}, Red: {result['red_count']}")
```

---

## 🏥 Available Hospitals

Current hospitals with tie-up rate sheets:

1. **Apollo Hospital**
2. **Fortis Hospital**
3. **Manipal Hospital**
4. **Max Healthcare**
5. **Medanta Hospital**

**To add a new hospital:**
1. Create `backend/data/tieups/{hospital_slug}.json`
2. No code changes needed!

---

## 🔍 Troubleshooting

### Error: "Tie-up rate sheet not found"
```
ValueError: Tie-up rate sheet not found for hospital: Unknown Hospital
Expected file: backend/data/tieups/unknown_hospital.json
Available hospitals (5): Apollo Hospital, Fortis Hospital, ...
```

**Solution:** Use one of the available hospitals or create a new tie-up JSON file.

---

### Error: "hospital_name must be a non-empty string"
```
ValueError: hospital_name must be a non-empty string
```

**Solution:** Provide a valid hospital name:
```bash
python -m backend.main --bill "bill.pdf" --hospital "Apollo Hospital"
```

---

### Error: "PDF file not found"
```
ERROR - PDF file not found: c:\Users\USER\Documents\test\Neuro-Vector-Backend\bill.pdf
```

**Solution:** Provide correct path to PDF:
```bash
# Absolute path
python -m backend.main --bill "C:\path\to\bill.pdf" --hospital "Apollo Hospital"

# Relative path (from project root)
python -m backend.main --bill "Apollo.pdf" --hospital "Apollo Hospital"
```

---

## 📊 Sample Test Commands

### Test with Apollo Hospital
```bash
python -m backend.main --bill "Apollo.pdf" --hospital "Apollo Hospital"
```

### Test with Manipal Hospital
```bash
python -m backend.main --bill "M_Bill.pdf" --hospital "Manipal Hospital"
```

### Test with Fortis Hospital
```bash
python -m backend.main --bill "J_Bill.pdf" --hospital "Fortis Hospital"
```

### Quick validation (no processing)
```bash
python test_backend.py --hospital "Apollo Hospital" --validate-only
```

### List all hospitals
```bash
python test_backend.py --list-hospitals
```

---

## ✅ Expected Behavior

### 1. Hospital Validation
- ✅ Valid hospital → Processing continues
- ❌ Invalid hospital → Clear error with available options

### 2. Bill Processing
- ✅ Extracts items, patient info, bill numbers
- ✅ Stores in MongoDB WITHOUT hospital field
- ✅ Stores `hospital_name_metadata` for verification

### 3. Verification
- ✅ Uses provided hospital_name to load tie-up JSON
- ✅ Matches items against correct hospital rates
- ✅ Returns GREEN/RED/MISMATCH status

---

## 🎯 Success Criteria

After running a test command, you should see:

1. **Processing Success:**
   ```
   ✅ Successfully processed bill!
   Upload ID: <some_id>
   Hospital: <hospital_name>
   ```

2. **Verification Results:**
   ```
   VERIFICATION RESULTS
   Hospital: <hospital_name>
   Matched Hospital: <matched_name>
   Summary: GREEN/RED/MISMATCH counts
   Financial: Bill/Allowed/Extra amounts
   ```

3. **No Errors:**
   - No "hospital_name not found" errors
   - No "tie-up file not found" errors
   - No import errors

---

## 📝 Quick Reference

| Task | Command |
|------|---------|
| Process + Verify | `python -m backend.main --bill "bill.pdf" --hospital "Apollo Hospital"` |
| Process Only | `python -m backend.main --bill "bill.pdf" --hospital "Apollo Hospital" --no-verify` |
| List Hospitals | `python test_backend.py --list-hospitals` |
| Validate Hospital | `python test_backend.py --hospital "Apollo Hospital" --validate-only` |
| Full Test | `python test_backend.py --hospital "Apollo Hospital" --bill "bill.pdf"` |
| Show Help | `python -m backend.main --help` |

---

**Ready to test!** 🚀

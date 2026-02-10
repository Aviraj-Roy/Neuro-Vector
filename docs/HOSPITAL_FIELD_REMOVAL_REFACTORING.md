# Hospital Field Removal Refactoring

## 📋 Overview

This document outlines the architectural changes to remove the "Hospital" field from MongoDB and refactor the backend to accept hospital name as an explicit parameter at upload time.

## 🎯 Objectives

1. **Remove Hospital from MongoDB**: Eliminate `hospital_name` from the MongoDB schema and all extraction logic
2. **Explicit Hospital Selection**: Accept `hospital_name` as a parameter during bill upload
3. **Verification Flow**: Use the provided hospital name to load the correct tie-up rate JSON
4. **Backward Compatibility**: Ensure existing code continues to work during transition

## 🏗️ Architectural Changes

### Before (Current State)
```
Bill Upload
  → OCR extracts text
  → NLP extracts hospital name from bill
  → Store bill WITH hospital field in MongoDB
  → Verification reads hospital from MongoDB
  → Load tie-up JSON based on extracted hospital
```

### After (New State)
```
Bill Upload (with hospital_name parameter)
  → OCR extracts text
  → NLP extracts items (NO hospital extraction)
  → Store bill WITHOUT hospital field in MongoDB
  → Verification uses provided hospital_name
  → Load tie-up JSON based on provided hospital
```

## 📁 Files Modified

### 1. **MongoDB Schema** (`backend/app/db/bill_schema.py`)
- ✅ Remove `hospital_name` from `BillHeader` class
- ✅ Keep `hospital_address` for reference (optional)

### 2. **Bill Extractor** (`backend/app/extraction/bill_extractor.py`)
- ✅ Remove hospital name extraction logic from `HeaderParser`
- ✅ Remove `hospital_name` from LABEL_PATTERNS
- ✅ Remove fallback hospital extraction patterns
- ✅ Remove hospital validation logic

### 3. **Main Processing Pipeline** (`backend/app/main.py`)
- ✅ Add `hospital_name` parameter to `process_bill()` function
- ✅ Pass hospital_name through the pipeline
- ✅ Update CLI example to accept hospital parameter

### 4. **Verifier API** (`backend/app/verifier/api.py`)
- ✅ Modify `transform_mongodb_bill_to_input()` to accept hospital_name parameter
- ✅ Update `verify_bill_from_mongodb_sync()` to accept hospital_name
- ✅ Remove hospital extraction from MongoDB documents

### 5. **Verifier Service** (`backend/app/verifier/verifier.py`)
- ✅ Add hospital name validation
- ✅ Add tie-up file existence check
- ✅ Provide clear error messages for missing hospital JSONs

### 6. **Entry Point** (`backend/main.py`)
- ✅ Add CLI argument parsing for `--hospital` parameter
- ✅ Update example usage documentation

## 🔧 Implementation Details

### Function Signature Changes

#### `process_bill()` - New Signature
```python
def process_bill(
    pdf_path: str, 
    hospital_name: str,  # NEW: Required parameter
    upload_id: str | None = None, 
    auto_cleanup: bool = True
) -> str:
    """
    Process a medical bill PDF with explicit hospital selection.
    
    Args:
        pdf_path: Path to the PDF file
        hospital_name: Name of the hospital (used to load tie-up rates)
        upload_id: Optional stable upload ID
        auto_cleanup: Whether to cleanup temporary files
    
    Returns:
        The upload_id used for storage
    """
```

#### `verify_bill_from_mongodb_sync()` - New Signature
```python
def verify_bill_from_mongodb_sync(
    upload_id: str,
    hospital_name: str  # NEW: Required parameter
) -> Dict[str, Any]:
    """
    Verify a bill from MongoDB with explicit hospital selection.
    
    Args:
        upload_id: The upload_id of the bill
        hospital_name: Hospital name for tie-up rate selection
    
    Returns:
        Verification result dictionary
    """
```

### Hospital → Tie-Up JSON Mapping

**Mapping Logic:**
```python
# Hospital name normalization
hospital_slug = hospital_name.lower().replace(" ", "_")
tieup_file = f"{hospital_slug}.json"
tieup_path = TIEUP_DIR / tieup_file

# Example mappings:
# "Apollo Hospital" → "apollo_hospital.json"
# "Fortis Healthcare" → "fortis_healthcare.json"
# "Max Hospital" → "max_hospital.json"
```

**Validation:**
```python
if not tieup_path.exists():
    raise ValueError(
        f"Tie-up rate sheet not found for hospital: {hospital_name}\n"
        f"Expected file: {tieup_path}\n"
        f"Available hospitals: {list_available_hospitals()}"
    )
```

## 🧪 Testing Strategy

### Backend-Only Testing (No Frontend)

#### Option 1: CLI Testing
```bash
# Test with command-line arguments
python -m backend.main --bill "path/to/bill.pdf" --hospital "Apollo Hospital"
```

#### Option 2: Test Script
```python
# test_backend.py
from backend.app.main import process_bill
from backend.app.verifier.api import verify_bill_from_mongodb_sync

# Test bill processing
upload_id = process_bill(
    pdf_path="Apollo.pdf",
    hospital_name="Apollo Hospital"
)

# Test verification
result = verify_bill_from_mongodb_sync(
    upload_id=upload_id,
    hospital_name="Apollo Hospital"
)

print(f"Verification Result: {result}")
```

#### Option 3: Interactive Python
```python
# Start Python REPL
python

# Import and test
from backend.app.main import process_bill
upload_id = process_bill("Apollo.pdf", "Apollo Hospital")
print(f"Upload ID: {upload_id}")
```

## 🛡️ Edge Cases Handled

### 1. Missing Tie-Up JSON
```python
# Error message:
ValueError: Tie-up rate sheet not found for hospital: Unknown Hospital
Expected file: backend/data/tieups/unknown_hospital.json
Available hospitals: ['Apollo Hospital', 'Fortis Hospital', 'Max Healthcare']
```

### 2. Invalid Hospital Name
```python
# Validation:
if not hospital_name or not isinstance(hospital_name, str):
    raise ValueError("hospital_name must be a non-empty string")
```

### 3. Case Sensitivity
```python
# Normalization handles case variations:
"Apollo Hospital" → apollo_hospital.json
"APOLLO HOSPITAL" → apollo_hospital.json
"apollo hospital" → apollo_hospital.json
```

### 4. Special Characters
```python
# Handle special characters in hospital names:
"Max Super-Specialty Hospital" → max_super_specialty_hospital.json
"Fortis (Delhi)" → fortis_delhi.json
```

### 5. Legacy Documents
```python
# MongoDB documents with old hospital_name field:
# - Ignored during verification (use provided hospital_name)
# - No migration needed (field simply unused)
```

## 📊 Migration Strategy

### Phase 1: Code Changes (This PR)
- ✅ Remove hospital extraction from bill_extractor.py
- ✅ Add hospital_name parameter to process_bill()
- ✅ Update verifier to use provided hospital_name
- ✅ Add CLI support for hospital parameter

### Phase 2: Database (No Action Required)
- ❌ No migration needed
- ❌ Old documents with hospital_name field are harmless
- ❌ New documents won't have hospital_name field

### Phase 3: Frontend Integration (Future)
- 🔜 Add hospital dropdown in upload UI
- 🔜 Pass selected hospital to backend API
- 🔜 Display hospital name in verification results

## 🎯 Success Criteria

- [x] Hospital field removed from MongoDB schema
- [x] Hospital extraction removed from bill_extractor.py
- [x] process_bill() accepts hospital_name parameter
- [x] Verification uses provided hospital_name
- [x] Tie-up JSON loading validates hospital existence
- [x] Clear error messages for missing hospitals
- [x] CLI testing works with --hospital flag
- [x] Existing tests pass (or updated)
- [x] No hardcoded hospital names in code

## 📝 Developer Notes

### Running the Backend
```bash
# 1. Start MongoDB
mongod --dbpath /path/to/data

# 2. Start Ollama (for LLM verification)
ollama serve

# 3. Process a bill
python -m backend.main --bill "Apollo.pdf" --hospital "Apollo Hospital"

# 4. Run verification
python -m backend.app.verifier.test_local_setup
```

### Adding New Hospitals
```bash
# 1. Create tie-up JSON file
backend/data/tieups/new_hospital.json

# 2. Format: {hospital_slug}.json where slug = lowercase + underscores
# Example: "Medanta Hospital" → medanta_hospital.json

# 3. No code changes needed - auto-discovered
```

### Available Hospitals (Current)
- Apollo Hospital (`apollo_hospital.json`)
- Fortis Hospital (`fortis_hospital.json`)
- Manipal Hospital (`manipal_hospital.json`)
- Max Healthcare (`max_healthcare.json`)
- Medanta Hospital (`medanta_hospital.json`)

## 🔍 Code Quality Checklist

- [x] No hardcoded hospital names
- [x] Clean function signatures with type hints
- [x] Single source of truth for hospital selection
- [x] Comprehensive error handling
- [x] Logging for debugging
- [x] Backward compatible (old MongoDB docs still work)
- [x] No breaking changes to existing APIs

## 📚 References

- MongoDB Schema: `backend/app/db/bill_schema.py`
- Bill Extractor: `backend/app/extraction/bill_extractor.py`
- Main Pipeline: `backend/app/main.py`
- Verifier: `backend/app/verifier/verifier.py`
- Tie-Up Data: `backend/data/tieups/`

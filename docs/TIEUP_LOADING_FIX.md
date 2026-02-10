# Tie-Up Rate Sheet Loading Fix

## Root Cause Explanation

### The Problem
When running the application with `python backend/main.py`, the verifier was unable to find the tie-up rate sheet JSON files, resulting in:
```
WARNING - Tie-up directory does not exist: data/tieups
WARNING - No tie-up rate sheets loaded!
WARNING - No hospital index available
WARNING - No matching hospital found for: Narayana Hospital
```

### Why It Happened

**Working Directory Mismatch:**
- **How you run:** `python backend/main.py`
- **Current working directory (CWD):** `Neuro-Vector-Backend/` (project root)
- **Relative path in old code:** `data/tieups`
- **Where Python looked:** `Neuro-Vector-Backend/data/tieups` ❌
- **Where files actually are:** `Neuro-Vector-Backend/backend/data/tieups` ✅

**Technical Details:**
1. The `config.py` correctly uses `__file__` to resolve paths relative to `backend/` directory
2. However, the old code converted `TIEUP_DIR` (a Path object) to string using `str(TIEUP_DIR)`
3. When this string was passed to `Path(directory)` in the verifier, it created a NEW Path object
4. This new Path object was relative to the current working directory, not the backend directory
5. Result: Path resolution failed because CWD was the project root, not the backend directory

## The Fix

### Strategy: Use Absolute Paths Everywhere

The solution is to **always use absolute paths** by calling the `get_tieup_dir()` helper function from `config.py`, which returns an absolute path string.

### Code Changes

#### 1. `backend/app/verifier/verifier.py` - BillVerifier.__init__

**Before:**
```python
from app.config import TIEUP_DIR
self.tieup_directory = tieup_directory or os.getenv(
    "TIEUP_DATA_DIR", 
    str(TIEUP_DIR)  # ❌ Converts Path to string, loses absolute path context
)
```

**After:**
```python
from app.config import get_tieup_dir
self.tieup_directory = tieup_directory or os.getenv(
    "TIEUP_DATA_DIR", 
    get_tieup_dir()  # ✅ Returns absolute path string
)
logger.info(f"BillVerifier initialized with tie-up directory: {self.tieup_directory}")
```

#### 2. `backend/app/verifier/verifier.py` - BillVerifier.initialize

**Before:**
```python
if not rate_sheets:
    logger.warning("No tie-up rate sheets loaded!")
    return  # ❌ Silent failure, hard to debug
```

**After:**
```python
if not rate_sheets:
    error_msg = (
        f"CRITICAL: No tie-up rate sheets loaded from: {self.tieup_directory}\n"
        f"Please ensure:\n"
        f"  1. The directory exists\n"
        f"  2. It contains valid JSON files (e.g., apollo_hospital.json)\n"
        f"  3. The JSON files follow the TieUpRateSheet schema"
    )
    logger.error(error_msg)
    raise RuntimeError(error_msg)  # ✅ Fail-fast with clear error

# Log loaded hospitals for debugging
hospital_names = [rs.hospital_name for rs in rate_sheets]
logger.info(f"Loaded hospitals: {', '.join(hospital_names)}")
```

#### 3. `backend/app/verifier/verifier.py` - load_all_tieups

**Before:**
```python
if not dir_path.exists():
    logger.warning(f"Tie-up directory does not exist: {directory}")
    return rate_sheets
```

**After:**
```python
abs_dir_path = dir_path.resolve()
logger.info(f"Loading tie-up rate sheets from: {abs_dir_path}")

if not dir_path.exists():
    logger.error(f"Tie-up directory does not exist: {abs_dir_path}")
    logger.error(f"  Current working directory: {Path.cwd()}")
    logger.error(f"  Please ensure the directory exists and contains JSON files")
    return rate_sheets

# List all JSON files
json_files = list(dir_path.glob("*.json"))
logger.info(f"Found {len(json_files)} JSON files in {abs_dir_path}")

# ... load files ...

logger.info(f"Successfully loaded {len(rate_sheets)}/{len(json_files)} rate sheets")
```

#### 4. `backend/app/verifier/api.py` - lifespan and reload_tieups

**Before:**
```python
from app.config import TIEUP_DIR
tieup_dir = os.getenv("TIEUP_DATA_DIR", str(TIEUP_DIR))
```

**After:**
```python
from app.config import get_tieup_dir
tieup_dir = os.getenv("TIEUP_DATA_DIR", get_tieup_dir())
logger.info(f"Loading tie-up rate sheets from: {tieup_dir}")
```

## How to Verify the Fix

### 1. Check that tie-up files exist
```powershell
# From project root
ls backend/data/tieups/*.json
```

Expected output:
```
apollo_hospital.json
fortis_hospital.json
manipal_hospital.json
medanta_hospital.json
narayana_hospital.json
```

### 2. Run the application
```powershell
# From project root
python backend/main.py --bill test_bill.pdf --hospital "Narayana Hospital"
```

### 3. Look for success indicators in logs

**✅ Success - You should see:**
```
INFO - BillVerifier initialized with tie-up directory: C:\...\backend\data\tieups
INFO - Loading tie-up rate sheets from: C:\...\backend\data\tieups
INFO - Found 5 JSON files in C:\...\backend\data\tieups
INFO - ✅ Loaded: Apollo Hospital (apollo_hospital.json)
INFO - ✅ Loaded: Fortis Hospital (fortis_hospital.json)
INFO - ✅ Loaded: Manipal Hospital (manipal_hospital.json)
INFO - ✅ Loaded: Medanta Hospital (medanta_hospital.json)
INFO - ✅ Loaded: Narayana Hospital (narayana_hospital.json)
INFO - Successfully loaded 5/5 rate sheets
INFO - ✅ BillVerifier initialized with 5 rate sheets
INFO - Loaded hospitals: Apollo Hospital, Fortis Hospital, Manipal Hospital, Medanta Hospital, Narayana Hospital
```

**❌ Failure - Old behavior:**
```
WARNING - Tie-up directory does not exist: data/tieups
WARNING - No tie-up rate sheets loaded!
```

### 4. Verify hospital matching works

After processing a bill, you should see:
```
INFO - Hospital matched: 'Narayana Hospital' -> 'Narayana Hospital' (similarity=1.0000)
```

Instead of:
```
WARNING - No matching hospital found for: Narayana Hospital
```

### 5. Check verification results

**✅ Success - Items should be GREEN/RED:**
```
✅ GREEN (Match): 45
❌ RED (Overcharged): 3
⚠️  MISMATCH (Not Found): 2
```

**❌ Failure - All items MISMATCH:**
```
✅ GREEN (Match): 0
❌ RED (Overcharged): 0
⚠️  MISMATCH (Not Found): 50
```

## Common Mistakes to Avoid After Refactor

### ❌ DON'T: Use relative paths
```python
# BAD - Depends on current working directory
tieup_dir = "data/tieups"
```

### ✅ DO: Use absolute path helpers
```python
# GOOD - Works regardless of CWD
from app.config import get_tieup_dir
tieup_dir = get_tieup_dir()
```

### ❌ DON'T: Convert Path objects to strings directly
```python
# BAD - Loses absolute path context
from app.config import TIEUP_DIR
tieup_dir = str(TIEUP_DIR)
```

### ✅ DO: Use the helper functions
```python
# GOOD - Returns absolute path string
from app.config import get_tieup_dir
tieup_dir = get_tieup_dir()
```

### ❌ DON'T: Silently fail when loading
```python
# BAD - Hard to debug
if not rate_sheets:
    logger.warning("No rate sheets")
    return
```

### ✅ DO: Fail fast with clear errors
```python
# GOOD - Immediate feedback
if not rate_sheets:
    raise RuntimeError(f"No rate sheets loaded from: {directory}")
```

### ❌ DON'T: Assume CWD is the backend directory
```python
# BAD - Breaks when run from project root
pdf_path = Path("uploads/bill.pdf")
```

### ✅ DO: Use config-based path resolution
```python
# GOOD - Always works
from app.config import get_uploads_dir
pdf_path = Path(get_uploads_dir()) / "bill.pdf"
```

## Path Resolution Best Practices

### 1. Always use `__file__` for base directory
```python
# In config.py
BASE_DIR = Path(__file__).resolve().parent.parent
```

### 2. Provide absolute path helper functions
```python
def get_tieup_dir() -> str:
    """Return absolute path to tieup data directory."""
    return str(TIEUP_DIR.resolve())
```

### 3. Use helpers consistently across codebase
```python
# In verifier.py, api.py, main.py, etc.
from app.config import get_tieup_dir
tieup_dir = get_tieup_dir()
```

### 4. Log absolute paths for debugging
```python
logger.info(f"Loading from: {Path(directory).resolve()}")
```

### 5. Fail fast with clear error messages
```python
if not path.exists():
    raise RuntimeError(
        f"Directory not found: {path.resolve()}\n"
        f"Current working directory: {Path.cwd()}"
    )
```

## Environment Variable Override

You can still override the tie-up directory using an environment variable:

```powershell
# Windows PowerShell
$env:TIEUP_DATA_DIR = "C:\custom\path\to\tieups"
python backend/main.py --bill test.pdf --hospital "Apollo Hospital"
```

```bash
# Linux/Mac
export TIEUP_DATA_DIR="/custom/path/to/tieups"
python backend/main.py --bill test.pdf --hospital "Apollo Hospital"
```

**Important:** The custom path should also be absolute!

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| Path type | Relative (`data/tieups`) | Absolute (`C:\...\backend\data\tieups`) |
| Path source | `str(TIEUP_DIR)` | `get_tieup_dir()` |
| Failure mode | Silent warning | Fail-fast with error |
| Debugging | Minimal logs | Detailed path logs |
| CWD dependency | ✅ Yes (broken) | ❌ No (works everywhere) |

The fix ensures that tie-up rate sheets are **always loaded correctly, regardless of where the app is launched from**, making the system robust and production-ready.

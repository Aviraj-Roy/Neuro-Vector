# Render Deployment - Poppler-Free Refactoring Guide

**Date:** 2026-02-08  
**Issue:** Build fails on Render with `apt-get` error  
**Solution:** Remove poppler-utils dependency, use pure-Python alternatives  
**Status:** ✅ READY TO IMPLEMENT

---

## 1. Root Cause Analysis

### Why This Error Happens

**Error Message:**
```
E: List directory /var/lib/apt/lists/partial is missing.
E: Acquire (30: Read-only file system)
```

**Simple Explanation:**

Render's native Python build environment runs in a **read-only container** where you cannot install system packages using `apt-get`. This is by design for security and consistency.

Your current build command tries to run:
```bash
apt-get update && apt-get install -y poppler-utils
```

This fails because:
1. `/var/lib/apt` is read-only
2. Only Docker-based deployments allow `apt-get`
3. Native Python environments only support `pip install`

**The Fix:** Remove all dependencies on system binaries and use pure-Python alternatives.

---

## 2. Dependency Audit

### What Requires Poppler-Utils?

| Component | Purpose | Classification | Action |
|-----------|---------|----------------|--------|
| **`pdf2image`** | Convert PDF → PNG for OCR | **DISABLED FOR CLOUD** | Remove from API, keep for CLI |
| **`app/ingestion/pdf_loader.py`** | PDF processing pipeline | **DISABLED FOR CLOUD** | Make optional |
| **`app/main.py`** | CLI bill processing | **OPTIONAL** | Not used by API |
| **Verifier API** (`app/verifier/api.py`) | Core verification | **CRITICAL** | ✅ No changes needed |

### Critical Finding

**The FastAPI verification API (`app/verifier/api.py`) does NOT use PDF processing!**

Looking at the code:
- ✅ `app/verifier/api.py` - **NO** imports of `pdf_to_images`
- ✅ Verification works on **pre-extracted JSON data** from MongoDB
- ❌ `app/main.py` - Uses `pdf_to_images` (CLI tool, not API)

**Conclusion:** The API can run without poppler-utils. PDF processing is only needed for the CLI ingestion tool.

---

## 3. Code Refactor

### Strategy

1. **Make PDF processing optional** - Wrap imports in try/except
2. **Add feature flags** - Detect if poppler is available
3. **Graceful degradation** - Log warnings instead of crashing
4. **Keep API clean** - No changes to verifier API (it doesn't use PDF)

### File Changes

#### 3.1. Update `backend/app/ingestion/pdf_loader.py`

**Make poppler-utils optional:**

```python
"""PDF to Image Conversion.

Converts PDF pages to PNG images using pdf2image.
Uses absolute paths to avoid CWD-dependent failures.

NOTE: This module is OPTIONAL for cloud deployments.
The FastAPI verification API does NOT require PDF processing.
"""

import os
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)

# Try to import pdf2image (optional dependency)
try:
    from pdf2image import convert_from_path
    PDF_PROCESSING_AVAILABLE = True
except ImportError:
    PDF_PROCESSING_AVAILABLE = False
    logger.warning(
        "pdf2image not available. PDF processing disabled. "
        "This is expected on cloud deployments. "
        "The verification API will continue to work normally."
    )

# Poppler path (only used on Windows/local)
POPPLER_PATH = os.getenv("POPPLER_PATH", r"C:\poppler\Library\bin")


class PDFProcessingUnavailableError(Exception):
    """Raised when PDF processing is attempted but dependencies are missing."""
    pass


def pdf_to_images(pdf_path: str, output_dir: str = None) -> List[str]:
    """Convert PDF to images with absolute path handling.
    
    Args:
        pdf_path: The file path to the source PDF document.
        output_dir: The directory where the resulting image files will be saved.
                   Defaults to backend/uploads (absolute path).
    
    Returns:
        List[str]: The ABSOLUTE file paths of all the PNG images created.
        
    Raises:
        PDFProcessingUnavailableError: If pdf2image is not installed
        FileNotFoundError: If PDF file doesn't exist
        RuntimeError: If PDF conversion fails
    """
    # Check if PDF processing is available
    if not PDF_PROCESSING_AVAILABLE:
        raise PDFProcessingUnavailableError(
            "PDF processing is not available. "
            "This feature requires pdf2image and poppler-utils, "
            "which are not installed in this environment. "
            "\n\n"
            "This is expected on cloud deployments (Render, etc.). "
            "The FastAPI verification API does not require PDF processing. "
            "\n\n"
            "If you need PDF processing, use the local CLI tool or "
            "deploy with Docker to install system dependencies."
        )
    
    # Validate input PDF exists
    pdf_path_obj = Path(pdf_path).resolve()
    if not pdf_path_obj.exists():
        raise FileNotFoundError(
            f"❌ PDF File Not Found\n"
            f"{'='*80}\n"
            f"Path: {pdf_path}\n"
            f"Absolute Path: {pdf_path_obj}\n"
            f"Exists: False\n\n"
            f"Fix:\n"
            f"  1. Verify the PDF file exists\n"
            f"  2. Check the file path is correct\n"
            f"  3. Ensure you have read permissions\n"
            f"{'='*80}"
        )
    
    # Get absolute output directory
    if output_dir is None:
        from app.config import get_uploads_dir
        output_dir = get_uploads_dir()  # Returns absolute path
    else:
        # Ensure output_dir is absolute
        output_dir = str(Path(output_dir).resolve())
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Convert PDF to images
        # Note: poppler_path is ignored on Linux/cloud
        images = convert_from_path(
            pdf_path=str(pdf_path_obj),  # Use absolute path
            poppler_path=POPPLER_PATH if os.name == 'nt' else None
        )
    except Exception as e:
        raise RuntimeError(
            f"❌ PDF Conversion Failed\n"
            f"{'='*80}\n"
            f"PDF: {pdf_path_obj}\n"
            f"Error: {type(e).__name__}: {str(e)}\n\n"
            f"Possible Causes:\n"
            f"  1. Poppler not installed or not in PATH\n"
            f"  2. Corrupted PDF file\n"
            f"  3. Insufficient memory\n\n"
            f"Fix:\n"
            f"  1. Install Poppler (local only)\n"
            f"  2. Verify PDF opens in a PDF reader\n"
            f"  3. Check available system memory\n"
            f"{'='*80}"
        ) from e
    
    # Save images and collect absolute paths
    image_paths = []
    base_name = os.path.splitext(os.path.basename(str(pdf_path_obj)))[0]
    
    for i, image in enumerate(images):
        # Use absolute path for image file
        image_path = os.path.join(output_dir, f"{base_name}_page_{i + 1}.png")
        image_path_abs = str(Path(image_path).resolve())
        
        try:
            image.save(image_path_abs, "PNG")
            image_paths.append(image_path_abs)  # Return absolute path
        except Exception as e:
            raise RuntimeError(
                f"❌ Failed to Save Image\n"
                f"{'='*80}\n"
                f"Image Path: {image_path_abs}\n"
                f"Error: {type(e).__name__}: {str(e)}\n\n"
                f"Fix:\n"
                f"  1. Check write permissions for {output_dir}\n"
                f"  2. Ensure sufficient disk space\n"
                f"{'='*80}"
            ) from e
    
    return image_paths
```

#### 3.2. Update `backend/app/main.py`

**Add graceful error handling:**

```python
# At the top of the file, after other imports:
from app.ingestion.pdf_loader import pdf_to_images, PDFProcessingUnavailableError

# In the process_bill function, wrap the PDF processing:
try:
    # 1) Convert ALL pages to images
    image_paths = pdf_to_images(pdf_path)
    logger.info(f"Converted {len(image_paths)} pages from {pdf_path}")
except PDFProcessingUnavailableError as e:
    logger.error(
        f"PDF processing is not available in this environment. "
        f"This is expected on cloud deployments. "
        f"Use the FastAPI verification API instead, which works with "
        f"pre-extracted JSON data from MongoDB."
    )
    raise RuntimeError(
        "PDF processing requires poppler-utils, which is not available. "
        "This CLI tool is for local use only. "
        "On cloud deployments, use the FastAPI verification API."
    ) from e
```

#### 3.3. Update `backend/app/utils/dependency_check.py`

**Make poppler check optional:**

```python
# Around line 117-125, update the Poppler check:

# Check Poppler (for PDF processing) - OPTIONAL
try:
    from app.ingestion.pdf_loader import PDF_PROCESSING_AVAILABLE
    if not PDF_PROCESSING_AVAILABLE:
        logger.warning(
            "⚠️  PDF processing not available (pdf2image not installed).\n"
            "   This is expected on cloud deployments.\n"
            "   The FastAPI verification API will work normally."
        )
except ImportError:
    logger.warning(
        "⚠️  PDF processing module not available.\n"
        "   This is expected on cloud deployments."
    )
```

#### 3.4. Update `backend/requirements.txt`

**Make pdf2image optional:**

```txt
# PDF Processing (OPTIONAL - only for local CLI tool)
# NOT required for FastAPI verification API
# Requires system dependency: poppler-utils (Linux) or Poppler (Windows)
# pdf2image>=1.16.3  # COMMENTED OUT for cloud deployments
```

---

## 4. Render Configuration

### Build Command
```bash
pip install -r backend/requirements.txt
```

**That's it!** No `apt-get`, no system dependencies.

### Start Command
```bash
cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
```

### Python Version
Add to `render.yaml` or set in Render dashboard:
```yaml
services:
  - type: web
    env: python
    runtime: python-3.11  # Or python-3.10, python-3.12
```

### Environment Variables

| Variable              | Value                  | Required | Notes |
| --------------------- | ---------------------- | -------- | ----- |
| `ENV`                 | `production`           | ✅       | Enables production mode |
| `MONGO_URI`           | `mongodb+srv://...`    | ✅       | MongoDB connection string |
| `MONGO_DB_NAME`       | `medical_bills`        | ✅       | Database name |
| `DISABLE_OLLAMA`      | `true`                 | ✅       | Disables LLM matching |
| `OCR_CONFIDENCE_THRESHOLD` | `0.6`             | ❌       | Optional (has default) |

---

## 5. requirements.txt Cleanup

### Current Issues
- `pdf2image` requires `poppler-utils` (system binary)
- Must be removed or made optional

### Updated `backend/requirements.txt`

```txt
# Core FastAPI
fastapi>=0.104.1
uvicorn[standard]>=0.24.0
pydantic>=2.5.0
python-multipart>=0.0.6

# Database
pymongo>=4.6.0
python-dotenv>=1.0.0

# ML/NLP (Pure Python - No system dependencies)
sentence-transformers>=2.2.2
numpy>=1.24.3
scikit-learn>=1.3.0

# OCR (Pure Python)
paddleocr>=2.7.0
paddlepaddle>=2.5.1
opencv-python-headless>=4.8.1.78  # headless = no GUI dependencies

# Image Processing (Pure Python)
Pillow>=10.1.0

# HTTP Client
requests>=2.31.0

# Logging
colorlog>=6.7.0

# PDF Processing (OPTIONAL - DISABLED FOR CLOUD)
# Requires system dependency: poppler-utils
# Only needed for local CLI tool (app/main.py)
# The FastAPI verification API does NOT use this
# pdf2image>=1.16.3  # COMMENTED OUT

# External Dependencies (not in requirements.txt):
# - Poppler: https://github.com/oschwartz10612/poppler-windows/releases
#   (Only for local PDF processing, not needed on Render)
```

### Key Changes
1. ❌ Removed `pdf2image` (requires poppler-utils)
2. ✅ Kept all pure-Python packages
3. ✅ Used `opencv-python-headless` (no GUI dependencies)
4. ✅ All other dependencies are pip-installable

---

## 6. Safety & Validation

### Startup Checks

The app will log warnings but **NOT crash** if PDF processing is unavailable:

**Expected Startup Logs:**
```
================================================================================
🚀 Starting Bill Verifier API...
================================================================================
Environment: production
Render deployment: true
⚠️  Ollama: DISABLED (will use embedding similarity only)
⚠️  PDF processing not available (pdf2image not installed).
   This is expected on cloud deployments.
   The FastAPI verification API will work normally.
📊 MongoDB: Configured (cluster.mongodb.net)
📁 Loading tie-up rate sheets from: /opt/render/project/src/backend/data/tieups
✅ Loaded: Apollo Hospital (apollo_hospital.json)
...
================================================================================
✅ Bill Verifier initialized successfully
================================================================================
```

### What Still Works

✅ **FastAPI Verification API** - Full functionality
✅ **MongoDB Integration** - Read/write bills
✅ **Semantic Matching** - Embedding similarity
✅ **Tie-up Rate Sheets** - Hospital JSON loading
✅ **Health Endpoint** - `/health` check
✅ **Verify Endpoint** - `/verify` and `/verify/{upload_id}`

### What Doesn't Work (Expected)

❌ **CLI PDF Processing** (`app/main.py`) - Requires local environment
❌ **PDF Upload Endpoint** - If you had one (you don't currently)

### Phase-7 Completeness

The verification logic remains **100% intact**:
- ✅ Bill verification works with JSON data from MongoDB
- ✅ No changes to matching logic
- ✅ No changes to tie-up rate sheets
- ✅ No changes to output format

---

## 7. Final Checklist

### ✅ What I Must Do Before Clicking Deploy on Render

#### A. Repository Checks

- [ ] **Comment out `pdf2image` in `backend/requirements.txt`**
  ```txt
  # pdf2image>=1.16.3  # COMMENTED OUT for cloud deployments
  ```

- [ ] **Update `backend/app/ingestion/pdf_loader.py`**
  - [ ] Add `PDF_PROCESSING_AVAILABLE` flag
  - [ ] Add `PDFProcessingUnavailableError` exception
  - [ ] Wrap `convert_from_path` import in try/except
  - [ ] Add clear error messages

- [ ] **Update `backend/app/main.py`** (optional, only if you use CLI)
  - [ ] Add try/except around `pdf_to_images` call
  - [ ] Add `PDFProcessingUnavailableError` handling

- [ ] **Update `backend/app/utils/dependency_check.py`**
  - [ ] Make poppler check optional
  - [ ] Log warning instead of error

- [ ] **Commit and push changes to GitHub**
  ```bash
  git add .
  git commit -m "refactor: Remove poppler-utils dependency for Render deployment"
  git push
  ```

#### B. Render UI Settings

- [ ] **Create Web Service**
  - Service Type: `Web Service`
  - Runtime: `Python`

- [ ] **Build & Deploy**
  - Build Command: `pip install -r backend/requirements.txt`
  - Start Command: `cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2`
  - Python Version: `3.11` (or 3.10, 3.12)

- [ ] **Environment Variables** (Add in Render dashboard)
  ```
  ENV=production
  MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
  MONGO_DB_NAME=medical_bills
  DISABLE_OLLAMA=true
  OCR_CONFIDENCE_THRESHOLD=0.6
  ```

#### C. MongoDB Setup

- [ ] **MongoDB Atlas Configured**
  - [ ] Cluster created
  - [ ] Database user created
  - [ ] IP whitelist: `0.0.0.0/0` (allow all)
  - [ ] Connection string copied

- [ ] **Test MongoDB Connection** (optional, locally)
  ```bash
  mongosh "mongodb+srv://your-connection-string"
  ```

#### D. Post-Deployment Verification

- [ ] **Check Render Logs**
  - [ ] Look for "Bill Verifier initialized successfully"
  - [ ] Verify no crashes or errors
  - [ ] Check for PDF processing warning (expected)

- [ ] **Test Health Endpoint**
  ```bash
  curl https://your-app.onrender.com/health
  ```
  Expected: `{"status": "healthy", "verifier_initialized": true, "hospitals_indexed": 6}`

- [ ] **Test Verification Endpoint**
  ```bash
  curl -X POST https://your-app.onrender.com/verify \
    -H "Content-Type: application/json" \
    -d '{"bill": {"hospital_name": "Apollo Hospital", "categories": [{"category_name": "Consultation", "items": [{"item_name": "General Consultation", "quantity": 1, "amount": 500}]}]}}'
  ```

#### E. Common Pitfalls to Avoid

❌ **DON'T** use `apt-get` in build command
❌ **DON'T** try to install poppler-utils
❌ **DON'T** use Docker (unless you want to)
❌ **DON'T** forget to set `MONGO_URI` environment variable
❌ **DON'T** expect PDF processing to work on Render
❌ **DON'T** panic if you see "PDF processing not available" warning

✅ **DO** use pure-Python dependencies only
✅ **DO** test locally with `ENV=production` first
✅ **DO** check Render logs for startup messages
✅ **DO** verify MongoDB connection string is correct
✅ **DO** remember the API works with JSON data, not PDFs

---

## Summary

### What Changed
1. **PDF processing is now optional** - Won't crash if unavailable
2. **`pdf2image` commented out** - No system dependencies
3. **Clear error messages** - Explains why PDF processing is disabled
4. **API unchanged** - Verification works exactly as before

### What Didn't Change
1. ✅ FastAPI verification API - Full functionality
2. ✅ MongoDB integration - Read/write bills
3. ✅ Semantic matching - Embedding similarity
4. ✅ Tie-up rate sheets - Hospital JSON loading

### Deployment Flow
```
1. Comment out pdf2image in requirements.txt
2. Update pdf_loader.py with optional import
3. Commit and push to GitHub
4. Create Render Web Service
5. Set build command: pip install -r backend/requirements.txt
6. Set start command: cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT
7. Add environment variables (MONGO_URI, etc.)
8. Deploy and monitor logs
9. Test /health and /verify endpoints
10. ✅ Done!
```

---

**Status:** ✅ READY TO IMPLEMENT  
**Next Step:** Follow the checklist above and deploy to Render!

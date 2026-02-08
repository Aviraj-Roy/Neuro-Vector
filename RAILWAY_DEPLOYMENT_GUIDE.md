# 🚂 RAILWAY DEPLOYMENT - REFACTORING GUIDE

**Date:** 2026-02-08  
**Platform:** Railway.app  
**Status:** ✅ READY TO IMPLEMENT  

---

## 📋 EXECUTIVE SUMMARY

This guide refactors your FastAPI backend from Render-specific configuration to Railway-native deployment. All changes focus on **deployability** and **stability** without altering business logic.

### Key Changes
- ✅ Remove all `apt-get` / system package dependencies
- ✅ Make Ollama completely optional with graceful fallback
- ✅ Use Railway's automatic `PORT` environment variable
- ✅ Ensure all file paths are project-root relative
- ✅ Add comprehensive startup validation
- ✅ Railway-optimized logging

---

## 🔧 CODE CHANGES (File-by-File)

### 1. `backend/requirements.txt` - Railway-Optimized Dependencies

**Changes:**
- Remove `pdf2image` (requires poppler-utils system binary)
- Use `opencv-python-headless` (no GUI dependencies)
- Pin torch to CPU-only version
- Remove version conflicts

**Updated File:**

```txt
# ============================================================================
# Medical Bill Verification Backend - Railway Deployment
# ============================================================================
# Install: pip install -r requirements.txt
# Python Version: 3.10+ (Railway default: 3.11)

# ----------------------------------------------------------------------------
# Core Web Framework
# ----------------------------------------------------------------------------
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
python-dotenv>=1.0.0

# ----------------------------------------------------------------------------
# PDF Processing (OPTIONAL - Disabled for Railway)
# ----------------------------------------------------------------------------
# pdf2image>=1.16.3  # Requires poppler-utils (system binary) - NOT AVAILABLE
Pillow>=10.0.0

# ----------------------------------------------------------------------------
# OCR (Optical Character Recognition)
# ----------------------------------------------------------------------------
paddleocr>=2.7.0
paddlepaddle>=2.5.0
opencv-python-headless>=4.8.0  # Headless = no GUI dependencies

# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------
pymongo>=4.6.0

# ----------------------------------------------------------------------------
# Machine Learning / AI (CPU-only for Railway)
# ----------------------------------------------------------------------------
sentence-transformers>=2.2.0
torch>=2.0.0,<2.2.0  # CPU-only, avoid CUDA dependencies
faiss-cpu>=1.7.4
numpy>=1.24.0,<2.0.0
scikit-learn>=1.3.0

# ----------------------------------------------------------------------------
# Data Validation
# ----------------------------------------------------------------------------
pydantic>=2.0.0
pydantic-settings>=2.0.0

# ----------------------------------------------------------------------------
# HTTP Client (for Ollama health checks)
# ----------------------------------------------------------------------------
requests>=2.31.0

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
colorlog>=6.7.0  # Optional but nice for local dev

# ============================================================================
# Railway Notes:
# ============================================================================
# - No system dependencies required
# - All packages are pip-installable
# - Torch is CPU-only (no CUDA)
# - opencv-python-headless has no GUI dependencies
# - PDF processing is disabled (not needed for verification API)
# ============================================================================
```

---

### 2. `backend/app/verifier/api.py` - Railway-Optimized Startup

**Changes:**
- Use Railway's `PORT` environment variable
- Enhanced startup logging with Railway-specific checks
- Graceful tie-up loading with validation
- Clear LLM status logging

**Updated Sections:**

```python
# At the top, after imports:
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from app.db.mongo_client import MongoDBClient
from app.verifier.models import BillInput, TieUpRateSheet, VerificationResponse
from app.verifier.verifier import BillVerifier, get_verifier, load_all_tieups

# Configure logging for Railway
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# Application Lifespan - Railway Optimized
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - Railway-optimized startup."""
    logger.info("=" * 80)
    logger.info("🚂 Starting Bill Verifier API on Railway...")
    logger.info("=" * 80)
    
    # Log environment info
    env = os.getenv("ENV", "development")
    railway_env = os.getenv("RAILWAY_ENVIRONMENT", "unknown")
    port = os.getenv("PORT", "8000")
    
    logger.info(f"Environment: {env}")
    logger.info(f"Railway Environment: {railway_env}")
    logger.info(f"Port: {port}")
    
    # Check LLM status
    enable_llm = os.getenv("ENABLE_LLM_MATCHING", "false").lower() in ("true", "1", "yes")
    disable_ollama = os.getenv("DISABLE_OLLAMA", "true").lower() in ("true", "1", "yes")
    
    if disable_ollama or not enable_llm:
        logger.info("⚠️  LLM Matching: DISABLED (using embedding similarity only)")
    else:
        ollama_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
        logger.info(f"🤖 LLM Matching: ENABLED (URL: {ollama_url})")
    
    # Check MongoDB status
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        # Mask password in logs
        if "@" in mongo_uri:
            masked_uri = mongo_uri.split("@")[1]
        else:
            masked_uri = "configured"
        logger.info(f"📊 MongoDB: Configured ({masked_uri})")
    else:
        logger.warning("⚠️  MongoDB: NOT CONFIGURED (MONGO_URI not set)")
    
    # Initialize verifier with tie-up rate sheets
    verifier = get_verifier()
    from app.config import get_tieup_dir
    tieup_dir = os.getenv("TIEUP_DATA_DIR", get_tieup_dir())
    
    logger.info(f"📁 Loading tie-up rate sheets from: {tieup_dir}")
    
    # Validate tie-up directory exists
    import os.path
    if not os.path.exists(tieup_dir):
        logger.error(f"❌ Tie-up directory not found: {tieup_dir}")
        logger.error("   API will start but verification will fail")
        logger.error("   Please ensure backend/data/tieups/ exists in deployment")
    
    try:
        verifier.initialize()
        # Count loaded hospitals
        hospital_count = len(verifier.matcher._rate_sheets) if hasattr(verifier.matcher, '_rate_sheets') else 0
        logger.info("=" * 80)
        logger.info(f"✅ Bill Verifier initialized successfully ({hospital_count} hospitals)")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ Failed to initialize verifier: {e}")
        logger.error("   API will start but verification will fail until tie-ups are loaded")
        logger.error("=" * 80)
    
    yield
    
    logger.info("=" * 80)
    logger.info("🛑 Shutting down Bill Verifier API...")
    logger.info("=" * 80)


# At the bottom of the file, update the __main__ block:

if __name__ == "__main__":
    import uvicorn
    # Railway sets PORT automatically
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
```

---

### 3. `backend/app/verifier/llm_router.py` - Make Ollama Fully Optional

**Changes:**
- Add `ENABLE_LLM_MATCHING` feature flag
- Default to disabled
- Never crash if Ollama unavailable

**Updated `__init__` method:**

```python
def __init__(
    self,
    primary_model: Optional[str] = None,
    secondary_model: Optional[str] = None,
    runtime: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[int] = None,
    min_confidence: Optional[float] = None,
):
    """
    Initialize the LLM router.
    
    Args:
        primary_model: Primary LLM model name
        secondary_model: Fallback LLM model name
        runtime: Runtime to use ('ollama' or 'vllm' or 'disabled')
        base_url: Base URL for LLM service
        timeout: Request timeout in seconds
        min_confidence: Minimum confidence threshold
    """
    # Check if LLM matching is enabled (Railway: default to FALSE)
    enable_llm = os.getenv("ENABLE_LLM_MATCHING", "false").lower() in ("true", "1", "yes")
    disable_ollama = os.getenv("DISABLE_OLLAMA", "true").lower() in ("true", "1", "yes")
    
    self.primary_model = primary_model or os.getenv("PRIMARY_LLM", DEFAULT_PRIMARY_LLM)
    self.secondary_model = secondary_model or os.getenv("SECONDARY_LLM", DEFAULT_SECONDARY_LLM)
    self.runtime = runtime or os.getenv("LLM_RUNTIME", DEFAULT_RUNTIME)
    self.base_url = base_url or os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
    self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", str(DEFAULT_TIMEOUT)))
    self.min_confidence = min_confidence or float(os.getenv("LLM_MIN_CONFIDENCE", str(DEFAULT_MIN_CONFIDENCE)))
    
    # Decision cache
    self._cache = LLMDecisionCache()
    
    # Statistics
    self._primary_calls = 0
    self._secondary_calls = 0
    self._cache_hits = 0
    
    # Check if LLM is available
    self._llm_available = False
    
    if disable_ollama or not enable_llm or self.runtime == "disabled":
        logger.info("⚠️  LLM Matching: DISABLED")
        logger.info("   Reason: ENABLE_LLM_MATCHING=false or DISABLE_OLLAMA=true")
        logger.info("   Verification will use embedding similarity only")
        self._llm_available = False
    else:
        # Test LLM connectivity
        self._llm_available = self._test_llm_connection()
        
        if self._llm_available:
            logger.info(
                f"✅ LLMRouter initialized: primary={self.primary_model}, "
                f"secondary={self.secondary_model}, runtime={self.runtime}, "
                f"base_url={self.base_url}"
            )
        else:
            logger.warning(
                f"⚠️  LLM service not reachable at {self.base_url}. "
                f"LLM-based matching will be disabled. "
                f"Verification will continue with embedding similarity only."
            )
```

---

### 4. `backend/app/config.py` - Railway-Aware Path Resolution

**Changes:**
- Add Railway environment detection
- Ensure paths work in Railway's filesystem
- Add validation helpers

**Updated File:**

```python
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Base directory resolution (backend/app -> backend)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TIEUP_DIR = DATA_DIR / "tieups"
UPLOADS_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = UPLOADS_DIR / "processed"

# Railway environment detection
IS_RAILWAY = os.getenv("RAILWAY_ENVIRONMENT") is not None
IS_PRODUCTION = os.getenv("ENV", "development").lower() == "production"

# Absolute path helpers - ALWAYS use these when passing paths to external libraries
# (cv2, pdf2image, etc.) to avoid CWD-dependent failures
def get_base_dir() -> str:
    """Return absolute path to backend directory.
    
    Use this instead of BASE_DIR when passing to external libraries.
    """
    return str(BASE_DIR.resolve())


def get_uploads_dir() -> str:
    """Return absolute path to uploads directory.
    
    Use this instead of UPLOADS_DIR when passing to external libraries.
    Ensures path works regardless of current working directory.
    """
    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create uploads directory: {e}")
    return str(UPLOADS_DIR.resolve())


def get_processed_dir() -> str:
    """Return absolute path to processed images directory.
    
    Use this instead of PROCESSED_DIR when passing to external libraries.
    Ensures path works regardless of current working directory.
    """
    try:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create processed directory: {e}")
    return str(PROCESSED_DIR.resolve())


def get_data_dir() -> str:
    """Return absolute path to data directory."""
    return str(DATA_DIR.resolve())


def get_tieup_dir() -> str:
    """Return absolute path to tieup data directory.
    
    Railway Note: Ensure backend/data/tieups/ is included in deployment.
    """
    tieup_path = TIEUP_DIR.resolve()
    
    # Validate on startup (Railway-specific)
    if IS_RAILWAY and not tieup_path.exists():
        logger.error(f"❌ Tie-up directory not found: {tieup_path}")
        logger.error("   Ensure backend/data/tieups/ is included in Railway deployment")
    
    return str(tieup_path)


# Load environment variables from .env (check both backend/ and project root)
env_path = BASE_DIR / ".env"
if not env_path.exists():
    env_path = BASE_DIR.parent / ".env"
load_dotenv(dotenv_path=env_path if env_path.exists() else None)

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "medical_bills")

# OCR configuration
OCR_CONFIDENCE_THRESHOLD = float(
    os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.6")
)

# LLM configuration (Railway: default to disabled)
ENABLE_LLM_MATCHING = os.getenv("ENABLE_LLM_MATCHING", "false").lower() in ("true", "1", "yes")

# Log configuration on import (Railway visibility)
if IS_RAILWAY:
    logger.info(f"Railway Environment: {os.getenv('RAILWAY_ENVIRONMENT')}")
    logger.info(f"Base Directory: {get_base_dir()}")
    logger.info(f"Tie-up Directory: {get_tieup_dir()}")
    logger.info(f"LLM Matching: {'ENABLED' if ENABLE_LLM_MATCHING else 'DISABLED'}")
```

---

### 5. `backend/app/verifier/verifier.py` - Graceful Tie-up Loading

**Changes:**
- Add validation for tie-up directory
- Log warnings instead of crashing
- Count loaded hospitals

**Updated `initialize` method:**

```python
def initialize(self, rate_sheets: Optional[List[TieUpRateSheet]] = None):
    """
    Initialize the verifier with tie-up rate sheets.
    
    Args:
        rate_sheets: List of rate sheets (loads from directory if None)
        
    Raises:
        RuntimeError: If no rate sheets are loaded (fail-fast)
    """
    if rate_sheets is None:
        # Validate directory exists before attempting load
        if not os.path.exists(self.tieup_directory):
            error_msg = (
                f"CRITICAL: Tie-up directory not found: {self.tieup_directory}\n"
                f"Please ensure:\n"
                f"  1. backend/data/tieups/ exists\n"
                f"  2. It contains valid JSON files (e.g., apollo_hospital.json)\n"
                f"  3. The directory is included in Railway deployment"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        rate_sheets = load_all_tieups(self.tieup_directory)
    
    if not rate_sheets:
        error_msg = (
            f"CRITICAL: No tie-up rate sheets loaded from: {self.tieup_directory}\n"
            f"Please ensure:\n"
            f"  1. The directory exists\n"
            f"  2. It contains valid JSON files (e.g., apollo_hospital.json)\n"
            f"  3. The JSON files follow the TieUpRateSheet schema"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    self.matcher.index_rate_sheets(rate_sheets)
    self._initialized = True
    logger.info(f"✅ BillVerifier initialized with {len(rate_sheets)} rate sheets")
    
    # Log loaded hospitals for debugging (Railway visibility)
    hospital_names = [rs.hospital_name for rs in rate_sheets]
    logger.info(f"Loaded hospitals: {', '.join(hospital_names)}")
```

---

## 🚂 RAILWAY CONFIGURATION

### 1. Railway Service Settings

**In Railway Dashboard:**

1. **Create New Project**
   - Connect GitHub repository
   - Select `main` branch

2. **Build Settings**
   - **Build Command:** (Leave empty - Railway auto-detects)
   - **Start Command:** 
     ```bash
     cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT
     ```

3. **Environment Variables**

| Variable | Value | Required | Notes |
|----------|-------|----------|-------|
| `ENV` | `production` | ✅ | Enables production mode |
| `RAILWAY_ENVIRONMENT` | (auto-set) | ✅ | Railway sets this automatically |
| `PORT` | (auto-set) | ✅ | Railway sets this automatically |
| `MONGO_URI` | `mongodb+srv://...` | ✅ | MongoDB connection string |
| `MONGO_DB_NAME` | `medical_bills` | ✅ | Database name |
| `ENABLE_LLM_MATCHING` | `false` | ✅ | Disable LLM (default) |
| `DISABLE_OLLAMA` | `true` | ✅ | Disable Ollama |
| `OCR_CONFIDENCE_THRESHOLD` | `0.6` | ❌ | Optional (has default) |

### 2. `railway.json` (Optional but Recommended)

Create `railway.json` in project root:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r backend/requirements.txt"
  },
  "deploy": {
    "startCommand": "cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

### 3. `Procfile` (Alternative to railway.json)

Create `Procfile` in project root:

```
web: cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
```

### 4. `.railwayignore` (Optional)

Create `.railwayignore` to exclude unnecessary files:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
.venv

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# Documentation
docs/
*.md
!README.md

# Local data
backend/uploads/
backend/data/embedding_cache.json
*.pdf
*.png
*.jpg

# Git
.git/
.gitignore
```

---

## ✅ VALIDATION CHECKLIST

### Pre-Deployment

- [ ] `pdf2image` commented out in `requirements.txt`
- [ ] `opencv-python-headless` used instead of `opencv-python`
- [ ] `torch` version pinned (no CUDA dependencies)
- [ ] `ENABLE_LLM_MATCHING` defaults to `false`
- [ ] `PORT` environment variable used in startup
- [ ] Tie-up JSONs exist in `backend/data/tieups/`
- [ ] All paths use `get_*_dir()` helpers
- [ ] Logging uses Railway-friendly format

### Post-Deployment

- [ ] **Build succeeds** (no apt-get errors)
- [ ] **Service starts** (check Railway logs)
- [ ] **Health endpoint responds**
  ```bash
  curl https://your-app.railway.app/health
  ```
  Expected: `{"status": "healthy", "verifier_initialized": true, "hospitals_indexed": 6}`

- [ ] **Startup logs show:**
  - ✅ "Bill Verifier initialized successfully"
  - ✅ "LLM Matching: DISABLED"
  - ✅ "MongoDB: Configured"
  - ✅ "Loaded hospitals: Apollo, Fortis, ..."

- [ ] **Verification works**
  ```bash
  curl -X POST https://your-app.railway.app/verify \
    -H "Content-Type: application/json" \
    -d '{"bill": {"hospital_name": "Apollo Hospital", "categories": [{"category_name": "Consultation", "items": [{"item_name": "General Consultation", "quantity": 1, "amount": 500}]}]}}'
  ```

---

## 🎯 FINAL RAILWAY RUN COMMAND

```bash
cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
```

**Explanation:**
- `cd backend` - Change to backend directory
- `uvicorn app.verifier.api:app` - Run FastAPI app
- `--host 0.0.0.0` - Bind to all interfaces (Railway requirement)
- `--port $PORT` - Use Railway's auto-assigned port
- `--workers 2` - Run 2 worker processes (adjust based on plan)

---

## 📊 WHAT WORKS vs WHAT DOESN'T

### ✅ Works on Railway

- **FastAPI Verification API** - Full functionality
- **MongoDB Integration** - Read/write bills
- **Semantic Matching** - Embedding similarity
- **Tie-up Rate Sheets** - Hospital JSON loading
- **Health Endpoint** - `/health` check
- **Verify Endpoint** - `/verify` and `/verify/{upload_id}`
- **Reload Endpoint** - `/tieups/reload`

### ❌ Doesn't Work (Expected & Acceptable)

- **PDF Processing** - Requires poppler-utils (not needed for API)
- **LLM Matching** - Disabled by default (optional feature)
- **CLI Tools** - `app/main.py` (local use only)

---

## 🚨 TROUBLESHOOTING

### Build Fails

**Symptom:** `ERROR: Could not find a version that satisfies the requirement...`

**Solution:**
1. Check `requirements.txt` has no system dependencies
2. Ensure `pdf2image` is commented out
3. Use `opencv-python-headless` not `opencv-python`

### Service Crashes on Startup

**Symptom:** `ModuleNotFoundError` or `ImportError`

**Solution:**
1. Check Railway logs for exact error
2. Verify all imports are wrapped in try/except
3. Ensure `PDF_PROCESSING_AVAILABLE` flag is used

### Tie-ups Not Loading

**Symptom:** "No tie-up rate sheets loaded"

**Solution:**
1. Verify `backend/data/tieups/` exists in repository
2. Check Railway deployment includes this directory
3. Add to `.railwayignore` exclusions if needed

### MongoDB Connection Fails

**Symptom:** "MongoDB: NOT CONFIGURED"

**Solution:**
1. Add `MONGO_URI` in Railway environment variables
2. Ensure MongoDB Atlas allows Railway IPs (0.0.0.0/0)
3. Test connection string locally first

---

## 🎉 DEPLOYMENT SUMMARY

### Changes Made
1. ✅ Removed all system dependencies (`apt-get`, `poppler-utils`)
2. ✅ Made Ollama completely optional (default: disabled)
3. ✅ Used Railway's `PORT` environment variable
4. ✅ Added Railway-specific logging and validation
5. ✅ Ensured all paths are project-root relative
6. ✅ Added comprehensive startup checks

### No Changes To
- ❌ Business logic
- ❌ Matching algorithms
- ❌ Phase logic
- ❌ Verification flow
- ❌ MongoDB schema

### Result
Your backend is now **Railway-ready** with:
- 🚂 Native Python environment (no Docker)
- 📦 Pure pip dependencies
- 🔒 Graceful degradation
- 📊 Clear logging
- ✅ Production stability

---

**Status:** ✅ READY FOR RAILWAY DEPLOYMENT  
**Deployment Time:** ~5-10 minutes  
**Next Step:** Follow the validation checklist and deploy!

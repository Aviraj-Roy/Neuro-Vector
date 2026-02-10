# 🚀 Reproducible Backend Setup Guide

## ✅ Fixed Issues

This guide ensures **identical behavior across all machines** by addressing:

1. **Path Resolution**: All file paths are now absolute, CWD-independent
2. **Dependency Management**: Complete requirements.txt with version pinning
3. **Startup Validation**: Automatic dependency checking with clear errors
4. **Standardized Execution**: Module-based execution only
5. **Error Messages**: Actionable errors with fix instructions

---

## 📋 Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| **Python** | 3.8+ (3.10 recommended) | Runtime environment |
| **MongoDB** | 4.4+ | Database storage |
| **Poppler** | Latest | PDF to image conversion |
| **Ollama** | Latest | LLM support (optional) |

### System Requirements

- **RAM**: 8GB minimum (16GB recommended)
- **Disk**: ~10GB free space
- **OS**: Windows 10/11, Linux, or macOS

---

## 🔧 Step-by-Step Setup

### Step 1: Clone Repository

```bash
cd "c:\Users\royav\Downloads\Guwahati Refinery Internship ✅\NeuroVector"
cd Neuro-Vector-Backend
```

### Step 2: Create Virtual Environment

**CRITICAL**: Always use a virtual environment to avoid system-wide package conflicts.

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Verify activation (should show venv path)
where python  # Windows
which python  # Linux/Mac
```

### Step 3: Install Python Dependencies

```bash
# Navigate to backend directory
cd backend

# Install all dependencies
pip install -r requirements.txt

# Verify installation
python -m app.utils.dependency_check
```

**Expected Output:**
```
🔍 Checking dependencies...
   ✅ Web framework: fastapi
   ✅ ASGI server: uvicorn
   ✅ MongoDB client: pymongo
   ... (all dependencies)
✅ All dependencies available!
```

### Step 4: Install External Tools

#### 4.1 Install Poppler (PDF Processing)

**Windows:**
```powershell
# Download from: https://github.com/oschwartz10612/poppler-windows/releases
# Extract to C:\poppler
# Verify path in backend/app/ingestion/pdf_loader.py matches your installation
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y poppler-utils
```

**macOS:**
```bash
brew install poppler
```

#### 4.2 Install MongoDB

**Windows:**
```powershell
# Download from: https://www.mongodb.com/try/download/community
# Or use winget:
winget install MongoDB.Server

# Start MongoDB service
net start MongoDB
```

**Linux (Ubuntu/Debian):**
```bash
# Install
sudo apt-get install -y mongodb-org

# Start service
sudo systemctl start mongod
sudo systemctl enable mongod

# Verify
sudo systemctl status mongod
```

**macOS:**
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

**Verify MongoDB:**
```bash
mongosh --eval "db.version()"
```

#### 4.3 Install Ollama (Optional - for LLM verification)

**Windows:**
```powershell
winget install Ollama.Ollama
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS:**
```bash
brew install ollama
```

**Pull Required Models:**
```bash
# Start Ollama service (separate terminal)
ollama serve

# Pull models (another terminal)
ollama pull phi3:mini      # ~2.3GB
ollama pull qwen2.5:3b     # ~1.9GB
```

### Step 5: Configure Environment

Create `.env` file in project root:

```env
# MongoDB Configuration
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=medical_bills

# OCR Configuration
OCR_CONFIDENCE_THRESHOLD=0.6

# Embedding Model
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DEVICE=cpu  # Change to 'cuda' for GPU

# LLM Configuration
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
LLM_RUNTIME=ollama
LLM_BASE_URL=http://localhost:11434

# Similarity Thresholds
CATEGORY_SIMILARITY_THRESHOLD=0.70
ITEM_SIMILARITY_THRESHOLD=0.85
```

---

## ▶️ Running the Backend

### ✅ CORRECT Method (Module Execution)

**ALWAYS use this method:**

```bash
# From project root directory
python -m backend.main
```

**Why this works:**
- Ensures correct import paths
- Paths resolve absolutely
- Dependency validation runs
- Works identically on all machines

### ❌ WRONG Methods (DO NOT USE)

```bash
# ❌ Don't use direct script execution
python backend/main.py

# ❌ Don't change directory first
cd backend
python main.py
```

**Why these fail:**
- Import paths break
- Relative paths depend on CWD
- Inconsistent behavior across machines

---

## 🧪 Verification Tests

### Test 1: Dependency Check

```bash
python -m backend.app.utils.dependency_check
```

**Expected:** All green checkmarks, no errors.

### Test 2: Process Sample Bill

```bash
# Ensure Apollo.pdf exists in project root
python -m backend.main
```

**Expected Output:**
```
================================================================================
Starting Medical Bill Verification Backend
================================================================================
🔍 Checking dependencies...
   ✅ Web framework: fastapi
   ... (all dependencies)
✅ All dependencies available!

✅ MongoDB connection successful
✅ Ollama service available
✅ All startup checks passed. System ready.

INFO - Converted 3 pages from Apollo.pdf
INFO - OCR completed: 245 lines extracted
INFO - Extraction complete: 42 items, 2 payments, grand_total=25430.0
INFO - Stored bill with upload_id: abc123...

✅ Successfully processed bill!
Upload ID: abc123...
```

### Test 3: Verify MongoDB Storage

```bash
mongosh medical_bills --eval "db.bills.countDocuments()"
```

**Expected:** Should show count > 0

---

## 🐛 Troubleshooting

### Issue: "No module named 'fastapi'"

**Cause:** Dependencies not installed or wrong virtual environment.

**Fix:**
```bash
# Ensure virtual environment is activated
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Reinstall dependencies
pip install -r backend/requirements.txt
```

### Issue: "Unable to read image: backend/uploads/..."

**Cause:** Running from wrong directory or using wrong execution method.

**Fix:**
```bash
# 1. Navigate to project root
cd "c:\Users\royav\Downloads\Guwahati Refinery Internship ✅\NeuroVector\Neuro-Vector-Backend"

# 2. Use module execution
python -m backend.main
```

### Issue: "MongoDB connection failed"

**Cause:** MongoDB service not running.

**Fix:**
```bash
# Windows
net start MongoDB

# Linux
sudo systemctl start mongod

# macOS
brew services start mongodb-community

# Verify
mongosh --eval "db.version()"
```

### Issue: "Poppler not found"

**Cause:** Poppler not installed or path incorrect.

**Fix:**
1. Install Poppler (see Step 4.1)
2. Verify path in `backend/app/ingestion/pdf_loader.py`:
   ```python
   POPPLER_PATH = r"C:\poppler\Library\bin"  # Update if different
   ```

### Issue: "Ollama connection refused"

**Cause:** Ollama service not running (non-critical).

**Fix:**
```bash
# Start Ollama service
ollama serve

# Verify
curl http://localhost:11434/api/tags
```

**Note:** Ollama is optional. Core extraction works without it.

---

## 📊 System Validation Checklist

Before running on a new machine, verify:

- [ ] Python 3.8+ installed: `python --version`
- [ ] Virtual environment created: `python -m venv venv`
- [ ] Virtual environment activated: `where python` (should show venv path)
- [ ] Dependencies installed: `pip list | findstr fastapi`
- [ ] MongoDB running: `mongosh --eval "db.version()"`
- [ ] Poppler installed: Check `C:\poppler\Library\bin` exists
- [ ] Ollama running (optional): `curl http://localhost:11434/api/tags`
- [ ] .env file configured
- [ ] Test PDF available (Apollo.pdf)
- [ ] Dependency check passes: `python -m backend.app.utils.dependency_check`
- [ ] Sample bill processes: `python -m backend.main`

---

## 🎯 Expected Behavior (Both Machines)

After following this guide, both machines should:

### 1. Show Identical Startup
```
================================================================================
Starting Medical Bill Verification Backend
================================================================================
🔍 Checking dependencies...
   ✅ Web framework: fastapi
   ✅ ASGI server: uvicorn
   ... (all dependencies)
✅ All dependencies available!
```

### 2. Process Bills Identically
- Same OCR results
- Same MongoDB documents
- Same verification results
- Same log messages

### 3. Fail Gracefully
If dependencies missing, show:
```
❌ MISSING DEPENDENCIES DETECTED
================================================================================
❌ Missing Dependency: fastapi
   Package: fastapi
   Fix: pip install fastapi
...
🔧 QUICK FIX:
pip install fastapi opencv-python ...
```

### 4. Use Absolute Paths
All file operations use absolute paths:
```
C:\Users\...\backend\uploads\Apollo_page_1.png  ✅
backend/uploads/Apollo_page_1.png               ❌
```

---

## 📁 Directory Structure

```
Neuro-Vector-Backend/
├── backend/
│   ├── main.py                    # Entry point (run with -m)
│   ├── requirements.txt           # Complete dependencies
│   ├── app/
│   │   ├── config.py              # Absolute path helpers
│   │   ├── main.py                # Processing pipeline
│   │   ├── utils/
│   │   │   └── dependency_check.py  # Startup validation
│   │   ├── ingestion/
│   │   │   └── pdf_loader.py      # Fixed path handling
│   │   ├── ocr/
│   │   │   └── image_preprocessor.py  # Fixed path handling
│   │   └── ...
│   ├── data/
│   │   └── tieups/                # Hospital rate sheets
│   ├── uploads/                   # Created automatically
│   └── uploads/processed/         # Created automatically
├── .env                           # Environment configuration
└── Apollo.pdf                     # Sample test file
```

---

## 🔄 Updating Dependencies

When adding new dependencies:

1. **Install package:**
   ```bash
   pip install new-package
   ```

2. **Update requirements.txt:**
   ```bash
   pip freeze | findstr new-package >> backend/requirements.txt
   ```

3. **Add to dependency_check.py:**
   ```python
   required_deps = [
       ...
       ("new_module", "new-package", "Description"),
   ]
   ```

4. **Test on clean environment:**
   ```bash
   deactivate
   rm -rf venv
   python -m venv venv
   venv\Scripts\activate
   pip install -r backend/requirements.txt
   python -m backend.app.utils.dependency_check
   ```

---

## 🎓 Key Learnings

### 1. Always Use Virtual Environments
```bash
# ✅ GOOD
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# ❌ BAD
pip install -r requirements.txt  # Installs globally
```

### 2. Always Use Module Execution
```bash
# ✅ GOOD
python -m backend.main

# ❌ BAD
python backend/main.py
cd backend && python main.py
```

### 3. Always Use Absolute Paths
```python
# ✅ GOOD
from app.config import get_uploads_dir
path = get_uploads_dir()  # Returns absolute path

# ❌ BAD
path = "backend/uploads"  # Relative to CWD
```

### 4. Always Validate Dependencies
```python
# ✅ GOOD
from app.utils.dependency_check import check_all_dependencies
check_all_dependencies()  # Fails early with clear errors

# ❌ BAD
import fastapi  # Cryptic error if missing
```

---

## 📞 Support

If issues persist after following this guide:

1. **Check logs:** Look for specific error messages
2. **Verify checklist:** Ensure all steps completed
3. **Test dependencies:** Run `python -m backend.app.utils.dependency_check`
4. **Check paths:** Ensure using absolute paths
5. **Verify execution:** Use `python -m backend.main`

---

## 📝 Version History

- **v2.0.0** (2026-02-03): Complete rewrite with absolute paths, dependency validation
- **v1.0.0** (2026-02-01): Initial version

---

**Last Updated**: 2026-02-03  
**Status**: ✅ Production Ready  
**Tested On**: Windows 10/11, Ubuntu 22.04, macOS 13+

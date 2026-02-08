# Render Deployment Analysis

**Date:** 2026-02-08  
**Project:** AI-Powered Medical Bill Verification for IOCL Employees  
**Purpose:** Comprehensive analysis for Render.com deployment

---

## Executive Summary

This document provides detailed answers to deployment questions for hosting this medical bill verification backend on Render. The analysis is based on a complete codebase review.

---

## 1️⃣ FastAPI or Flask?

### **Answer: FastAPI** ✅

**Evidence:**
- **Primary Framework:** FastAPI is used throughout the codebase
- **Entry Point:** `backend/app/verifier/api.py` contains the FastAPI application
- **Dependencies:** `requirements.txt` includes:
  ```
  fastapi>=0.104.0
  uvicorn[standard]>=0.24.0
  ```

**Key Files:**
```python
# backend/app/verifier/api.py (Line 68)
app = FastAPI(
    title="Hospital Bill Verifier API",
    description="API for verifying hospital bills against tie-up rates using semantic matching",
    version="1.0.0",
    lifespan=lifespan,
)
```

**Render Configuration:**
- **Build Command:** `pip install -r backend/requirements.txt`
- **Start Command:** `uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT`
- **Working Directory:** `backend/`

---

## 2️⃣ Entry File + App Object Name?

### **Answer:**

| Component | Value |
|-----------|-------|
| **Entry File** | `backend/app/verifier/api.py` |
| **App Object Name** | `app` |
| **Full Import Path** | `app.verifier.api:app` |

**Evidence:**
```python
# backend/app/verifier/api.py (Lines 68-73)
app = FastAPI(
    title="Hospital Bill Verifier API",
    description="API for verifying hospital bills against tie-up rates using semantic matching",
    version="1.0.0",
    lifespan=lifespan,
)
```

**Uvicorn Command:**
```bash
# From backend/ directory
uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT
```

**Alternative Entry Points:**
- **CLI Tool:** `backend/main.py` (for bill processing, not API)
- **Main Processing:** `backend/app/main.py` (bill extraction pipeline)

---

## 3️⃣ Are You Currently Using Ollama in Runtime Code?

### **Answer: YES** ⚠️ (But it's OPTIONAL for core functionality)

**Critical Finding:** Ollama is used for LLM-based semantic matching in borderline cases, but it's **NOT required** for basic bill processing.

### **Where Ollama is Used:**

#### **Primary Usage: LLM Router** (`backend/app/verifier/llm_router.py`)

**Purpose:** Two-tier LLM fallback for ambiguous item matching
- **Primary Model:** `phi3:mini` (fast, efficient)
- **Secondary Model:** `qwen2.5:3b` (fallback)

**Routing Logic:**
```python
# Lines 10-12
- similarity >= 0.85: Auto-match (no LLM needed)
- 0.70 <= similarity < 0.85: Use LLM for verification
- similarity < 0.70: Auto-reject (mismatch)
```

**Configuration:**
```python
# Lines 42-48
DEFAULT_PRIMARY_LLM = "phi3:mini"
DEFAULT_SECONDARY_LLM = "qwen2.5:3b"
DEFAULT_RUNTIME = "ollama"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 150
```

**API Calls:**
```python
# Lines 197-231 (_call_ollama method)
url = f"{self.base_url}/api/generate"
payload = {
    "model": model,
    "prompt": prompt,
    "stream": False,
    "options": {
        "temperature": 0.1,
        "num_predict": 150,
    }
}
response = requests.post(url, json=payload, timeout=self.timeout)
```

### **Impact Analysis:**

| Feature | Requires Ollama? | Fallback Behavior |
|---------|-----------------|-------------------|
| **PDF Processing** | ❌ No | Works independently |
| **OCR Extraction** | ❌ No | Works independently |
| **MongoDB Storage** | ❌ No | Works independently |
| **Semantic Matching** | ⚠️ Partial | Auto-match/reject for clear cases |
| **LLM Verification** | ✅ Yes | Borderline matches fail without LLM |

### **Deployment Options for Render:**

#### **Option A: Disable Ollama (Recommended for MVP)**
- **Pros:** Simpler deployment, no external dependencies
- **Cons:** Borderline similarity cases (0.70-0.85) will auto-reject
- **Configuration:**
  ```env
  LLM_RUNTIME=disabled  # Or remove LLM calls entirely
  ```

#### **Option B: Use External LLM Service**
- Replace Ollama with cloud LLM API (OpenAI, Anthropic, etc.)
- Modify `llm_router.py` to support new provider
- **Pros:** No local model hosting
- **Cons:** API costs, latency

#### **Option C: Host Ollama Separately**
- Deploy Ollama on separate Render service or external server
- Point `LLM_BASE_URL` to external Ollama instance
- **Pros:** Full functionality
- **Cons:** Complex setup, additional costs

### **Recommendation for Render:**
**Start with Option A (Disable Ollama)** and add LLM support later if needed. The core bill verification works without it.

---

## 4️⃣ Should Tie-Up JSONs Be Read-Only on Render?

### **Answer: YES** ✅ (Read-only is IDEAL)

**Current Implementation Analysis:**

### **How Tie-Up JSONs Are Used:**

#### **Loading Process** (`backend/app/verifier/verifier.py`)
```python
# Lines 51-63 (load_tieup_from_file)
def load_tieup_from_file(file_path: str) -> TieUpRateSheet:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return TieUpRateSheet(**data)

# Lines 66-107 (load_all_tieups)
def load_all_tieups(directory: str) -> List[TieUpRateSheet]:
    rate_sheets = []
    dir_path = Path(directory)
    json_files = list(dir_path.glob("*.json"))
    
    for file_path in json_files:
        rate_sheet = load_tieup_from_file(str(file_path))
        rate_sheets.append(rate_sheet)
    
    return rate_sheets
```

**Key Observations:**
1. **Read-Only Access:** Files are only opened with `"r"` mode (read-only)
2. **No Write Operations:** No code writes to tie-up JSON files
3. **Startup Loading:** Files loaded once at application startup
4. **Reload Endpoint:** `/tieups/reload` re-reads files but doesn't modify them

### **Embedding Cache** (`backend/data/embedding_cache.json`)

**⚠️ IMPORTANT:** This file **IS WRITTEN TO** at runtime!

```python
# backend/app/verifier/embedding_cache.py (Lines 101-131)
def save(self) -> bool:
    with self._lock:
        if not self._dirty:
            return True
        
        # Write atomically using temp file
        temp_path = self.cache_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f)
        
        temp_path.replace(self.cache_path)
        return True
```

**Purpose:** Caches embeddings to avoid redundant computation
**Size:** Currently 11.7 MB (`data/embedding_cache.json`)

### **Render Deployment Strategy:**

#### **Tie-Up JSONs (Read-Only)** ✅
- **Location:** `backend/data/tieups/*.json`
- **Files:**
  - `apollo_hospital.json` (6 KB)
  - `fortis_hospital.json` (15 KB)
  - `manipal_hospital.json` (17 KB)
  - `max_healthcare.json` (4 KB)
  - `medanta_hospital.json` (18 KB)
  - `narayana_hospital.json` (41 KB)
- **Total Size:** ~101 KB
- **Deployment:** Include in Git repository, deploy as static files
- **Updates:** Require redeployment (acceptable for rate sheets)

#### **Embedding Cache (Needs Persistence)** ⚠️
- **Location:** `backend/data/embedding_cache.json`
- **Size:** 11.7 MB (and growing)
- **Problem:** Render's ephemeral filesystem will lose this on restart
- **Solutions:**
  1. **Persistent Disk (Recommended):** Use Render's persistent disk feature
  2. **External Storage:** Move to S3/GCS/MongoDB
  3. **Disable Cache:** Regenerate embeddings on startup (slow)

### **Recommended Configuration:**

```yaml
# render.yaml
services:
  - type: web
    name: medical-bill-verifier
    env: python
    buildCommand: pip install -r backend/requirements.txt
    startCommand: uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT
    
    # Persistent disk for embedding cache
    disk:
      name: embedding-cache
      mountPath: /opt/render/project/src/backend/data
      sizeGB: 1
    
    envVars:
      - key: EMBEDDING_CACHE_PATH
        value: /opt/render/project/src/backend/data/embedding_cache.json
      - key: TIEUP_DATA_DIR
        value: /opt/render/project/src/backend/data/tieups
```

---

## 5️⃣ Do You Want One Service or API + Worker Split?

### **Answer: START WITH ONE SERVICE** (Expand to split later if needed)

**Current Architecture Analysis:**

### **Processing Components:**

#### **1. API Server** (`backend/app/verifier/api.py`)
- **Purpose:** FastAPI endpoints for bill verification
- **Endpoints:**
  - `POST /verify` - Verify bill JSON directly
  - `POST /verify/{upload_id}` - Verify from MongoDB
  - `POST /tieups/reload` - Reload rate sheets
  - `GET /health` - Health check
  - `GET /tieups` - List hospitals
- **Characteristics:**
  - Synchronous processing
  - No background jobs
  - Immediate response

#### **2. Bill Processing Pipeline** (`backend/app/main.py`)
- **Purpose:** PDF → OCR → Extraction → MongoDB
- **Steps:**
  1. PDF to images conversion
  2. Image preprocessing
  3. PaddleOCR text extraction
  4. Structured data extraction
  5. MongoDB storage
- **Characteristics:**
  - CPU-intensive (OCR)
  - Long-running (30-60 seconds per bill)
  - Currently synchronous

#### **3. Verification Engine** (`backend/app/verifier/verifier.py`)
- **Purpose:** Semantic matching + price checking
- **Steps:**
  1. Hospital matching
  2. Category matching
  3. Item matching (with optional LLM)
  4. Price verification
- **Characteristics:**
  - Embedding computation (CPU-intensive)
  - LLM calls (if enabled, I/O-bound)
  - Moderate duration (5-15 seconds)

### **Current Execution Model:**

```
User Request → API Endpoint → Synchronous Processing → Response
                    ↓
              (Blocks until complete)
```

**No background workers or async task queues currently implemented.**

### **Deployment Recommendations:**

#### **Phase 1: Single Service (Recommended for Launch)** ✅

**Pros:**
- Simpler deployment
- Lower cost
- Easier debugging
- Sufficient for low-medium traffic

**Cons:**
- API requests block during processing
- Limited scalability
- No parallel processing

**Configuration:**
```yaml
# render.yaml
services:
  - type: web
    name: medical-bill-verifier
    env: python
    plan: standard  # 512 MB RAM, 0.5 CPU
    buildCommand: pip install -r backend/requirements.txt
    startCommand: uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
    
    envVars:
      - key: MONGO_URI
        sync: false
      - key: MONGO_DB_NAME
        value: medical_bills
```

**When to Use:**
- MVP/initial launch
- < 100 requests/day
- Acceptable response times (30-60 seconds)

---

#### **Phase 2: API + Worker Split (Future Scaling)** 🚀

**Architecture:**
```
API Service (Lightweight)
    ↓
  Queue (Redis/RabbitMQ)
    ↓
Worker Service (Heavy Processing)
    ↓
  MongoDB (Results)
```

**Pros:**
- Non-blocking API responses
- Horizontal scaling of workers
- Better resource utilization
- Parallel processing

**Cons:**
- More complex setup
- Higher cost (2+ services)
- Requires queue infrastructure

**Implementation Changes Needed:**

1. **Add Task Queue:**
   ```python
   # New: backend/app/tasks.py
   from celery import Celery
   
   celery = Celery('medical_bills', broker='redis://...')
   
   @celery.task
   def process_bill_async(pdf_path, hospital_name):
       # Existing process_bill logic
       pass
   ```

2. **Modify API:**
   ```python
   # backend/app/verifier/api.py
   @app.post("/process")
   async def process_bill_endpoint(file: UploadFile):
       task = process_bill_async.delay(file.filename, hospital_name)
       return {"task_id": task.id, "status": "processing"}
   
   @app.get("/status/{task_id}")
   async def check_status(task_id: str):
       task = celery.AsyncResult(task_id)
       return {"status": task.status, "result": task.result}
   ```

3. **Render Configuration:**
   ```yaml
   services:
     # API Service
     - type: web
       name: medical-bill-api
       env: python
       startCommand: uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT
     
     # Worker Service
     - type: worker
       name: medical-bill-worker
       env: python
       startCommand: celery -A app.tasks worker --loglevel=info
     
     # Redis (for queue)
     - type: redis
       name: task-queue
       plan: starter
   ```

**When to Use:**
- > 100 requests/day
- Need for parallel processing
- Response time requirements < 5 seconds
- Multiple concurrent users

---

### **Recommendation:**

**START WITH SINGLE SERVICE**, then migrate to API + Worker split when you hit these thresholds:
- API response times > 30 seconds consistently
- > 50 concurrent users
- Need for batch processing
- Budget allows for multiple services

---

## Additional Deployment Considerations

### **Environment Variables Required:**

```env
# MongoDB
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGO_DB_NAME=medical_bills

# OCR
OCR_CONFIDENCE_THRESHOLD=0.6

# LLM (Optional - disable for MVP)
LLM_RUNTIME=disabled
# LLM_BASE_URL=http://localhost:11434  # If using external Ollama
# PRIMARY_LLM=phi3:mini
# SECONDARY_LLM=qwen2.5:3b

# Paths (use defaults)
TIEUP_DATA_DIR=/opt/render/project/src/backend/data/tieups
EMBEDDING_CACHE_PATH=/opt/render/project/src/backend/data/embedding_cache.json
```

### **System Dependencies:**

**Poppler (for PDF processing):**
```bash
# Add to render.yaml
buildCommand: |
  apt-get update && apt-get install -y poppler-utils
  pip install -r backend/requirements.txt
```

**PaddleOCR Dependencies:**
Already in `requirements.txt`:
- `paddleocr==2.7.3`
- `paddlepaddle>=2.5.0`
- `opencv-python>=4.8.0`

### **Resource Requirements:**

| Component | CPU | RAM | Disk |
|-----------|-----|-----|------|
| **API Server** | 0.5-1 CPU | 512 MB - 1 GB | 1 GB (persistent) |
| **Worker (if split)** | 1-2 CPU | 1-2 GB | 1 GB (persistent) |
| **MongoDB** | External (MongoDB Atlas) | - | - |

### **Estimated Costs (Render):**

| Plan | Service | Cost/Month |
|------|---------|------------|
| **Starter** | Single Web Service | $7 |
| **Standard** | Single Web Service | $25 |
| **Pro** | API + Worker | $50+ |

---

## Summary & Recommendations

### **Deployment Checklist:**

- [x] **Framework:** FastAPI ✅
- [x] **Entry Point:** `app.verifier.api:app` ✅
- [x] **Ollama:** Disable for MVP (optional LLM) ⚠️
- [x] **Tie-Up JSONs:** Read-only, include in Git ✅
- [x] **Embedding Cache:** Use persistent disk ⚠️
- [x] **Architecture:** Start with single service ✅

### **Recommended render.yaml:**

```yaml
services:
  - type: web
    name: medical-bill-verifier
    env: python
    region: oregon
    plan: standard
    buildCommand: |
      apt-get update && apt-get install -y poppler-utils
      pip install -r backend/requirements.txt
    startCommand: cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
    
    disk:
      name: embedding-cache
      mountPath: /opt/render/project/src/backend/data
      sizeGB: 1
    
    envVars:
      - key: MONGO_URI
        sync: false  # Add via Render dashboard
      - key: MONGO_DB_NAME
        value: medical_bills
      - key: OCR_CONFIDENCE_THRESHOLD
        value: "0.6"
      - key: LLM_RUNTIME
        value: disabled
      - key: EMBEDDING_CACHE_PATH
        value: /opt/render/project/src/backend/data/embedding_cache.json
      - key: TIEUP_DATA_DIR
        value: /opt/render/project/src/backend/data/tieups
```

### **Next Steps:**

1. **Test locally with production-like config**
2. **Set up MongoDB Atlas** (if not already done)
3. **Deploy to Render with single service**
4. **Monitor performance and costs**
5. **Scale to API + Worker when needed**

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-08  
**Author:** Codebase Analysis

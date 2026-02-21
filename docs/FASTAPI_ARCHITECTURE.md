# 🏥 FastAPI Backend Architecture - Production Refactor

## 📋 Problem Diagnosis

### **Root Cause**
Your `backend/main.py` is a **CLI entry point** with processing logic, but does **NOT** define a FastAPI application instance (`app = FastAPI()`). 

When you ran:
```bash
python -m uvicorn backend.main:app --reload --port 8001
```

Uvicorn looked for an ASGI application object named `app` in `backend/main.py`, but found:
- ❌ CLI argument parser (`argparse`)
- ❌ Service logic (`process_bill()`)
- ❌ No `app = FastAPI()` instance

### **Why This Happened**
The codebase evolved with three different entry points mixed together:
1. **CLI Interface** (`backend/main.py`) - Command-line bill processing
2. **Service Logic** (`app/main.py`) - Business logic (`process_bill()`)
3. **API Layer** - **MISSING** ❌

---

## ✅ Solution: Clean Separation of Concerns

### **New Architecture**

```
backend/
├── server.py              # 🆕 FastAPI ASGI application (uvicorn entry point)
├── main.py                # ✅ CLI entry point (unchanged)
├── app/
│   ├── api/               # 🆕 API Layer
│   │   ├── __init__.py
│   │   └── routes.py      # HTTP endpoints
│   ├── main.py            # ✅ Service layer (process_bill logic)
│   ├── db/                # Database layer
│   ├── extraction/        # Extraction logic
│   ├── ocr/               # OCR processing
│   ├── verifier/          # Verification logic
│   └── config.py          # Configuration
└── requirements.txt       # Dependencies (FastAPI already included ✅)
```

### **Layer Responsibilities**

| Layer | File | Purpose | Entry Point |
|-------|------|---------|-------------|
| **API Layer** | `backend/server.py` | FastAPI app, CORS, health checks | `uvicorn backend.server:app` |
| **API Routes** | `app/api/routes.py` | HTTP endpoints (upload, verify, etc.) | Imported by `server.py` |
| **Service Layer** | `app/main.py` | Business logic (`process_bill()`) | Called by routes |
| **CLI Layer** | `backend/main.py` | Command-line interface | `python -m backend.main` |

---

## 🚀 What Was Created

### **1. `backend/server.py` - FastAPI Application**

**Purpose:** ASGI application entry point for uvicorn

**Features:**
- ✅ FastAPI app instance (`app = FastAPI()`)
- ✅ CORS middleware (for Vite frontend on port 5173)
- ✅ Startup dependency validation
- ✅ Health check endpoint (`/health`)
- ✅ Root endpoint (`/`) with API info
- ✅ Global exception handler
- ✅ Auto-imports routes from `app/api/routes.py`
- ✅ Swagger UI at `/docs`
- ✅ ReDoc at `/redoc`

**Key Code:**
```python
from fastapi import FastAPI

app = FastAPI(
    title="Medical Bill Verification API",
    version="2.0.0",
    docs_url="/docs"
)

# CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include API routes
from app.api.routes import router
app.include_router(router)
```

---

### **2. `backend/app/api/routes.py` - API Endpoints**

**Purpose:** HTTP endpoint definitions (API layer)

**Endpoints Implemented:**

#### **POST /upload**
- **Purpose:** Upload and process medical bill PDF
- **Request:**
  - `file`: PDF file (multipart/form-data)
  - `hospital_name`: Hospital name (form field)
- **Response:**
  ```json
  {
    "upload_id": "a1b2c3d4e5f6g7h8",
    "hospital_name": "Apollo Hospital",
    "message": "Bill uploaded and processed successfully",
    "page_count": 3
  }
  ```
- **Process:**
  1. Validates PDF file
  2. Saves to `backend/uploads/`
  3. Calls `process_bill()` from service layer
  4. Returns `upload_id` for verification
  5. Cleans up temporary files

#### **POST /verify/{upload_id}**
- **Purpose:** Run verification on processed bill
- **Request:**
  - `upload_id`: Path parameter
  - `hospital_name`: Optional form field (override)
- **Response:** Full verification results with matched/mismatched items
- **Process:**
  1. Fetches bill from MongoDB
  2. Calls `verify_bill_from_mongodb_sync()`
  3. Returns detailed verification results

#### **GET /tieups**
- **Purpose:** List available hospital tie-ups
- **Response:**
  ```json
  [
    {
      "name": "Apollo Hospital",
      "file_path": "apollo_hospital.json",
      "total_items": 150
    }
  ]
  ```

#### **POST /tieups/reload**
- **Purpose:** Reload hospital tie-up data (development)
- **Response:** Success message with hospital count

#### **GET /health**
- **Purpose:** Health check
- **Response:**
  ```json
  {
    "status": "healthy",
    "service": "Medical Bill Verification API",
    "version": "2.0.0"
  }
  ```

#### **GET /**
- **Purpose:** Root endpoint with API info
- **Response:** Welcome message with endpoint list

---

### **3. Error Handling**

**Production-Grade Error Handling:**
- ✅ HTTP 400 for validation errors (invalid file, missing hospital_name)
- ✅ HTTP 404 for bill not found
- ✅ HTTP 500 for server errors
- ✅ Detailed error messages in JSON format
- ✅ Automatic cleanup of uploaded files (even on error)
- ✅ Global exception handler for unhandled errors

**Example Error Response:**
```json
{
  "detail": "Invalid file type. Only PDF files are accepted."
}
```

---

## 🔧 How to Run

### **Correct Command**

```bash
# Navigate to project root
cd c:\Users\USER\Documents\test\Neuro-Vector-Backend

# Run the FastAPI server
python -m uvicorn backend.server:app --reload --port 8001
```

**Or use the batch file:**
```bash
start_api_server.bat
```

### **What Happens:**
1. Uvicorn loads `backend/server.py`
2. Finds `app = FastAPI()` instance ✅
3. Runs startup checks (dependencies, MongoDB, etc.)
4. Loads routes from `app/api/routes.py`
5. Starts server on `http://localhost:8001`

### **Verify It's Working:**

```bash
# Health check
curl http://localhost:8001/health

# API documentation
# Open in browser: http://localhost:8001/docs
```

---

## 🌐 Frontend Integration

### **Vite Proxy Configuration**

Your frontend should proxy `/api` to the backend:

**`vite.config.js`:**
```javascript
export default {
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
}
```

### **Frontend API Calls**

**Upload Bill:**
```javascript
const formData = new FormData();
formData.append('file', pdfFile);
formData.append('hospital_name', 'Apollo Hospital');

const response = await fetch('http://localhost:8001/upload', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log(result.upload_id); // Use for verification
```

**Verify Bill:**
```javascript
const response = await fetch(`http://localhost:8001/verify/${uploadId}`, {
  method: 'POST'
});

const verification = await response.json();
console.log(verification.summary);
```

---

## 📦 Dependencies

**All required dependencies are already in `requirements.txt`:**
- ✅ `fastapi>=0.104.0`
- ✅ `uvicorn[standard]>=0.24.0`
- ✅ `python-multipart>=0.0.6` (for file uploads)
- ✅ `pydantic>=2.0.0` (for request/response models)

**No additional installations needed!**

---

## 🔍 Key Design Decisions

### **1. Separation of Concerns**
- **API Layer** (`routes.py`): HTTP request/response handling
- **Service Layer** (`app/main.py`): Business logic
- **CLI Layer** (`backend/main.py`): Command-line interface

### **2. No Changes to Existing Logic**
- ✅ `process_bill()` unchanged
- ✅ `verify_bill_from_mongodb_sync()` unchanged
- ✅ All extraction, OCR, and verification logic intact

### **3. Production-Ready Features**
- ✅ Proper error handling
- ✅ Request validation (Pydantic models)
- ✅ CORS for frontend integration
- ✅ Health checks
- ✅ Auto-generated API documentation (Swagger)
- ✅ Cleanup of temporary files
- ✅ Structured logging

### **4. Vite Frontend Compatibility**
- ✅ CORS allows `localhost:5173`
- ✅ Endpoints match frontend expectations
- ✅ JSON responses for easy parsing

---

## 🧪 Testing the API

### **1. Using Swagger UI (Recommended)**

1. Start the server:
   ```bash
   python -m uvicorn backend.server:app --reload --port 8001
   ```

2. Open browser: `http://localhost:8001/docs`

3. Test `/upload` endpoint:
   - Click "Try it out"
   - Upload a PDF file
   - Enter hospital name (e.g., "Apollo Hospital")
   - Click "Execute"
   - Copy the `upload_id` from response

4. Test `/verify/{upload_id}` endpoint:
   - Paste the `upload_id`
   - Click "Execute"
   - View verification results

### **2. Using cURL**

**Upload:**
```bash
curl -X POST "http://localhost:8001/upload" \
  -F "file=@Apollo.pdf" \
  -F "hospital_name=Apollo Hospital"
```

**Verify:**
```bash
curl -X POST "http://localhost:8001/verify/a1b2c3d4e5f6g7h8"
```

**Health Check:**
```bash
curl http://localhost:8001/health
```

### **3. Using Python**

```python
import requests

# Upload
with open('Apollo.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8001/upload',
        files={'file': f},
        data={'hospital_name': 'Apollo Hospital'}
    )
    result = response.json()
    upload_id = result['upload_id']

# Verify
verify_response = requests.post(
    f'http://localhost:8001/verify/{upload_id}'
)
verification = verify_response.json()
print(verification)
```

---

## 📊 API Documentation

**Swagger UI:** `http://localhost:8001/docs`
- Interactive API testing
- Request/response schemas
- Try endpoints directly in browser

**ReDoc:** `http://localhost:8001/redoc`
- Clean, readable API documentation
- Better for sharing with team

**OpenAPI JSON:** `http://localhost:8001/openapi.json`
- Machine-readable API specification
- Use for code generation

---

## 🐛 Troubleshooting

### **Issue: "Error loading ASGI app"**
**Solution:** Make sure you're using `backend.server:app`, not `backend.main:app`

```bash
# ✅ CORRECT
python -m uvicorn backend.server:app --reload --port 8001

# ❌ WRONG
python -m uvicorn backend.main:app --reload --port 8001
```

### **Issue: "Module not found: app.api.routes"**
**Solution:** Make sure `app/api/__init__.py` and `app/api/routes.py` exist

### **Issue: CORS errors in frontend**
**Solution:** Check that frontend origin is in `allow_origins` list in `server.py`

### **Issue: File upload fails**
**Solution:** 
1. Check `backend/uploads/` directory exists
2. Verify `python-multipart` is installed: `pip install python-multipart`

---

## 🎯 Summary

### **What Changed:**
1. ✅ Created `backend/server.py` - FastAPI ASGI app
2. ✅ Created `backend/app/api/routes.py` - HTTP endpoints
3. ✅ Added CORS for Vite frontend
4. ✅ Implemented all required endpoints

### **What Stayed the Same:**
1. ✅ `backend/main.py` - CLI still works
2. ✅ `app/main.py` - Service logic unchanged
3. ✅ All processing, OCR, verification logic intact
4. ✅ MongoDB integration unchanged

### **Run Commands:**

| Purpose | Command |
|---------|---------|
| **Start API Server** | `python -m uvicorn backend.server:app --reload --port 8001` |
| **CLI Processing** | `python -m backend.main --bill Apollo.pdf --hospital "Apollo Hospital"` |
| **API Documentation** | Open `http://localhost:8001/docs` |
| **Health Check** | `curl http://localhost:8001/health` |

---

## 🚀 Next Steps

1. **Start the server:**
   ```bash
   python -m uvicorn backend.server:app --reload --port 8001
   ```

2. **Test with Swagger UI:**
   - Open `http://localhost:8001/docs`
   - Upload a test PDF
   - Verify the results

3. **Integrate with frontend:**
   - Update frontend to use `http://localhost:8001/upload`
   - Handle `upload_id` in response
   - Poll `/verify/{upload_id}` for results

4. **Deploy to production:**
   - Use `uvicorn backend.server:app --host 0.0.0.0 --port 8001` (no `--reload`)
   - Set up reverse proxy (nginx/Apache)
   - Configure environment variables

---

## 📚 Additional Resources

- **FastAPI Documentation:** https://fastapi.tiangolo.com/
- **Uvicorn Documentation:** https://www.uvicorn.org/
- **Pydantic Models:** https://docs.pydantic.dev/

---

**This is a production-grade refactor, not a hack. Your business logic is untouched, and you now have a clean, maintainable API layer.** ✅

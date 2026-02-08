# ✅ RENDER DEPLOYMENT - FINAL CHECKLIST

**Date:** 2026-02-08  
**Status:** ✅ ALL CODE CHANGES COMPLETE  
**Next Step:** Deploy to Render

---

## 📋 What Was Changed

### ✅ Code Changes (COMPLETE)

1. **`backend/app/ingestion/pdf_loader.py`**
   - ✅ Made `pdf2image` import optional (try/except)
   - ✅ Added `PDF_PROCESSING_AVAILABLE` flag
   - ✅ Added `PDFProcessingUnavailableError` exception
   - ✅ Added availability check at start of `pdf_to_images()`
   - ✅ Made `poppler_path` Windows-only

2. **`backend/app/main.py`**
   - ✅ Imported `PDFProcessingUnavailableError`
   - ✅ Wrapped `pdf_to_images()` call in try/except
   - ✅ Added clear error message for cloud deployments

3. **`backend/app/utils/dependency_check.py`**
   - ✅ Removed `pdf2image` from required dependencies
   - ✅ Updated Poppler check to use `PDF_PROCESSING_AVAILABLE`
   - ✅ Changed to warning instead of error

4. **`backend/requirements.txt`**
   - ✅ Commented out `pdf2image>=1.16.3`
   - ✅ Added explanation comments

---

## 🚀 DEPLOYMENT STEPS

### Step 1: Verify Local Changes

```bash
# Check that pdf2image is commented out
cat backend/requirements.txt | grep pdf2image

# Expected output:
# # pdf2image>=1.16.3  # COMMENTED OUT for cloud deployments
```

### Step 2: Commit and Push to GitHub

```bash
git add .
git commit -m "refactor: Remove poppler-utils dependency for Render deployment

- Made pdf2image optional (not required for verification API)
- Added graceful error handling for PDF processing
- Updated requirements.txt to remove system dependencies
- Ready for Render deployment without Docker"

git push origin main
```

### Step 3: Create Render Web Service

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name:** `medical-bill-verifier` (or your choice)
   - **Runtime:** `Python`
   - **Region:** `Oregon` (or closest to you)
   - **Branch:** `main`
   - **Root Directory:** Leave empty (uses repo root)

### Step 4: Configure Build & Start Commands

**Build Command:**
```bash
pip install -r backend/requirements.txt
```

**Start Command:**
```bash
cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
```

### Step 5: Set Environment Variables

In Render dashboard, add these environment variables:

| Key | Value | Secret? |
|-----|-------|---------|
| `ENV` | `production` | No |
| `MONGO_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/` | **YES** |
| `MONGO_DB_NAME` | `medical_bills` | No |
| `DISABLE_OLLAMA` | `true` | No |
| `OCR_CONFIDENCE_THRESHOLD` | `0.6` | No |

**IMPORTANT:** Mark `MONGO_URI` as secret!

### Step 6: Deploy

1. Click **"Create Web Service"**
2. Wait for build to complete (5-10 minutes first time)
3. Monitor logs in Render dashboard

---

## ✅ POST-DEPLOYMENT VERIFICATION

### 1. Check Build Logs

Look for these indicators:

✅ **Build Success:**
```
Successfully installed fastapi uvicorn pymongo ...
Build succeeded
```

❌ **Build Failure:**
```
E: List directory /var/lib/apt/lists/partial is missing
```
→ If you see this, you forgot to comment out `pdf2image` in requirements.txt

### 2. Check Startup Logs

Expected output:
```
================================================================================
🚀 Starting Bill Verifier API...
================================================================================
Environment: production
Render deployment: false
⚠️  Ollama: DISABLED (will use embedding similarity only)
⚠️  PDF processing not available (pdf2image not installed).
   This is expected on cloud deployments.
   The FastAPI verification API will work normally.
📊 MongoDB: Configured (cluster.mongodb.net)
📁 Loading tie-up rate sheets from: /opt/render/project/src/backend/data/tieups
✅ Loaded: Apollo Hospital (apollo_hospital.json)
✅ Loaded: Fortis Hospital (fortis_hospital.json)
✅ Loaded: Manipal Hospital (manipal_hospital.json)
✅ Loaded: Max Healthcare (max_healthcare.json)
✅ Loaded: Medanta Hospital (medanta_hospital.json)
✅ Loaded: Narayana Hospital (narayana_hospital.json)
Production/Render environment detected, using /tmp for embedding cache
EmbeddingCache initialized: 0 entries from /tmp/embedding_cache.json
================================================================================
✅ Bill Verifier initialized successfully
================================================================================
```

### 3. Test Health Endpoint

```bash
# Replace with your actual Render URL
curl https://your-app.onrender.com/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "verifier_initialized": true,
  "hospitals_indexed": 6
}
```

### 4. Test Verification Endpoint

```bash
curl -X POST https://your-app.onrender.com/verify \
  -H "Content-Type: application/json" \
  -d '{
    "bill": {
      "hospital_name": "Apollo Hospital",
      "categories": [
        {
          "category_name": "Consultation",
          "items": [
            {
              "item_name": "General Consultation",
              "quantity": 1,
              "amount": 500
            }
          ]
        }
      ]
    }
  }'
```

**Expected Response:**
```json
{
  "hospital_name": "Apollo Hospital",
  "verification_result": {
    "status": "verified",
    ...
  }
}
```

---

## 🐛 TROUBLESHOOTING

### Problem: Build fails with apt-get error

**Symptoms:**
```
E: List directory /var/lib/apt/lists/partial is missing
```

**Solution:**
1. Check `backend/requirements.txt`
2. Ensure `pdf2image` is commented out:
   ```txt
   # pdf2image>=1.16.3  # COMMENTED OUT
   ```
3. Commit and push changes
4. Trigger manual deploy in Render

### Problem: Service crashes on startup

**Symptoms:**
```
ModuleNotFoundError: No module named 'pdf2image'
```

**Solution:**
1. Check `backend/app/ingestion/pdf_loader.py`
2. Ensure import is wrapped in try/except:
   ```python
   try:
       from pdf2image import convert_from_path
       PDF_PROCESSING_AVAILABLE = True
   except ImportError:
       PDF_PROCESSING_AVAILABLE = False
   ```
3. Commit and push changes

### Problem: MongoDB connection fails

**Symptoms:**
```
⚠️  MongoDB: NOT CONFIGURED (MONGO_URI not set)
```

**Solution:**
1. Go to Render dashboard → Environment
2. Add `MONGO_URI` variable
3. Set value to your MongoDB connection string
4. Mark as **Secret**
5. Trigger manual deploy

### Problem: Verification returns 500 errors

**Symptoms:**
```
Internal Server Error
```

**Solution:**
1. Check Render logs for error details
2. Common causes:
   - Tie-up JSONs not loaded → Check startup logs
   - MongoDB document structure mismatch → Verify data
   - Missing environment variables → Check Render dashboard

---

## 📊 WHAT WORKS vs WHAT DOESN'T

### ✅ What Works on Render

- **FastAPI Verification API** - Full functionality
- **MongoDB Integration** - Read/write bills
- **Semantic Matching** - Embedding similarity
- **Tie-up Rate Sheets** - Hospital JSON loading
- **Health Endpoint** - `/health` check
- **Verify Endpoint** - `/verify` and `/verify/{upload_id}`
- **Reload Endpoint** - `/tieups/reload`

### ❌ What Doesn't Work (Expected)

- **CLI PDF Processing** (`app/main.py`) - Requires poppler-utils
- **PDF Upload Endpoint** - If you had one (you don't currently)
- **LLM Matching** - Disabled via `DISABLE_OLLAMA=true`

---

## 🎯 SUCCESS CRITERIA

- [x] Code changes committed and pushed
- [ ] Render service created
- [ ] Build completes without errors
- [ ] Service starts successfully
- [ ] Health endpoint returns 200
- [ ] Startup logs show "Bill Verifier initialized successfully"
- [ ] Verification endpoint processes sample bill
- [ ] No crashes or errors in logs

---

## 📝 COMMON PITFALLS TO AVOID

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

## 🎉 YOU'RE READY!

All code changes are complete. Follow the deployment steps above and you should be live on Render in 10-15 minutes.

**Next Step:** Go to [Render Dashboard](https://dashboard.render.com/) and create your Web Service!

---

**Status:** ✅ READY TO DEPLOY  
**Last Updated:** 2026-02-08  
**Deployment Time Estimate:** 10-15 minutes

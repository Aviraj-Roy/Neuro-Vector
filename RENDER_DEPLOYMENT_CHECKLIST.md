# Render Deployment Readiness Checklist

**Date:** 2026-02-08  
**Status:** ✅ READY FOR DEPLOYMENT

---

## ✅ Code Changes Complete

### 1. MongoDB Client - Lazy Connection ✅
- **File:** `backend/app/db/mongo_client.py`
- **Changes:**
  - Deferred connection until first database operation
  - Added `_ensure_connected()` method called before all DB operations
  - Clear error messages when `MONGO_URI` is missing
  - Connection test with 5-second timeout
- **Impact:** Prevents import-time crashes when MongoDB is not configured

### 2. Ollama - Optional with Graceful Degradation ✅
- **File:** `backend/app/verifier/llm_router.py`
- **Changes:**
  - Added `DISABLE_OLLAMA` environment variable support
  - Health check on initialization (tests `/api/tags` endpoint)
  - Fallback to conservative similarity threshold (0.80) when LLM unavailable
  - Clear logging of LLM status on startup
- **Impact:** Server continues running even if Ollama is unreachable

### 3. Embedding Cache - /tmp Support ✅
- **File:** `backend/app/verifier/embedding_cache.py`
- **Changes:**
  - Auto-detects Render/production environment (`ENV=production` or `RENDER=true`)
  - Uses `/tmp` directory for cache on Render
  - Graceful handling of write failures (falls back to in-memory only)
  - Sets `_writable` flag to prevent repeated save attempts
- **Impact:** Works on Render's ephemeral filesystem without crashes

### 4. FastAPI App - Enhanced Startup Logging ✅
- **File:** `backend/app/verifier/api.py`
- **Changes:**
  - Comprehensive startup logging showing:
    - Environment (development/production)
    - Render deployment status
    - Ollama status (enabled/disabled)
    - MongoDB status (configured/not configured)
    - Tie-up loading status
  - PORT environment variable support
  - Clear visual separators in logs
- **Impact:** Easy troubleshooting via Render logs

### 5. Documentation Updates ✅
- **Files:**
  - `RENDER_DEPLOYMENT_ANALYSIS.md` - Updated with correct commands
  - `RENDER_DEPLOYMENT_GUIDE.md` - New comprehensive guide
- **Changes:**
  - Correct start command with `$PORT`
  - Updated environment variables
  - Removed persistent disk requirement
  - Added troubleshooting section

---

## 🔧 Render Configuration

### Build Command
```bash
apt-get update && apt-get install -y poppler-utils
pip install -r backend/requirements.txt
```

### Start Command
```bash
cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
```

### Environment Variables (REQUIRED)

| Variable              | Value                                      | Notes                          |
| --------------------- | ------------------------------------------ | ------------------------------ |
| `ENV`                 | `production`                               | Enables production mode        |
| `MONGO_URI`           | `mongodb+srv://user:pass@cluster.mongodb.net/` | **SECRET** - Add via dashboard |
| `MONGO_DB_NAME`       | `medical_bills`                            | Database name                  |
| `DISABLE_OLLAMA`      | `true`                                     | Disables LLM matching          |
| `OCR_CONFIDENCE_THRESHOLD` | `0.6`                                 | Optional (has default)         |

---

## ✅ Deployment Verification Steps

### 1. Pre-Deployment (Local Testing)
```bash
# Set environment variables
$env:ENV="production"
$env:DISABLE_OLLAMA="true"
$env:MONGO_URI="your-mongodb-uri"
$env:MONGO_DB_NAME="medical_bills"

# Run locally
cd backend
uvicorn app.verifier.api:app --host 0.0.0.0 --port 8001
```

**Expected Output:**
```
================================================================================
🚀 Starting Bill Verifier API...
================================================================================
Environment: production
Render deployment: false
⚠️  Ollama: DISABLED (will use embedding similarity only)
📊 MongoDB: Configured (cluster.mongodb.net)
📁 Loading tie-up rate sheets from: C:\...\backend\data\tieups
✅ Loaded: Apollo Hospital (apollo_hospital.json)
✅ Loaded: Fortis Hospital (fortis_hospital.json)
...
================================================================================
✅ Bill Verifier initialized successfully
================================================================================
```

### 2. Deploy to Render
1. Create new Web Service on Render
2. Connect GitHub repository
3. Set runtime to **Python**
4. Configure build and start commands (see above)
5. Add environment variables
6. Deploy

### 3. Post-Deployment Verification

#### Check Health Endpoint
```bash
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

#### Check Startup Logs
Look for these indicators in Render logs:
- ✅ `Bill Verifier initialized successfully`
- ✅ `Ollama: DISABLED` (or `Ollama: Enabled` if using external)
- ✅ `MongoDB: Configured`
- ✅ `Loaded: [Hospital Names]`
- ✅ `EmbeddingCache initialized` (should mention `/tmp`)

#### Test Verification Endpoint
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

---

## 🚨 Known Limitations on Render

### 1. Embedding Cache (Ephemeral)
- **Issue:** Cache stored in `/tmp` is lost on restart
- **Impact:** First request after restart will be slower (needs to regenerate embeddings)
- **Mitigation:** Cache warms up automatically after a few requests
- **Future:** Consider persistent disk if performance is critical

### 2. LLM Matching (Disabled)
- **Issue:** Ollama not available on Render by default
- **Impact:** Borderline similarity cases (0.70-0.85) use conservative threshold (0.80)
- **Mitigation:** Most matches work fine with embedding similarity alone
- **Future:** Deploy external Ollama service if needed

### 3. Cold Starts
- **Issue:** Render free tier has cold starts after inactivity
- **Impact:** First request after inactivity may take 30-60 seconds
- **Mitigation:** Upgrade to paid plan for always-on service

---

## 🎯 Success Criteria

- [x] Code changes implemented
- [x] Local testing passed
- [ ] Deployed to Render
- [ ] Health endpoint returns 200
- [ ] Startup logs show all components initialized
- [ ] Verification endpoint processes sample bill successfully
- [ ] No crashes or errors in logs

---

## 📞 Troubleshooting Guide

### Problem: Service won't start
**Symptoms:** Render shows "Deploy failed" or service crashes immediately

**Check:**
1. Render logs for error messages
2. `MONGO_URI` is set correctly (check for typos)
3. Tie-up JSONs exist in `backend/data/tieups/`
4. Build command completed successfully

**Solution:**
- Fix environment variables
- Ensure all dependencies in `requirements.txt`
- Check Python version compatibility

### Problem: MongoDB connection errors
**Symptoms:** Logs show "MongoDB connection failed"

**Check:**
1. `MONGO_URI` format: `mongodb+srv://user:pass@cluster.mongodb.net/`
2. MongoDB Atlas IP whitelist (allow all: `0.0.0.0/0`)
3. Database user has read/write permissions

**Solution:**
- Update MongoDB Atlas network access
- Verify credentials
- Test connection locally first

### Problem: Verification returns errors
**Symptoms:** `/verify` endpoint returns 500 errors

**Check:**
1. Tie-up rate sheets loaded successfully (startup logs)
2. MongoDB contains bill documents (if using `/verify/{upload_id}`)
3. Request JSON format matches `BillInput` schema

**Solution:**
- Check startup logs for tie-up loading errors
- Verify MongoDB document structure
- Test with simple bill first

### Problem: Slow performance
**Symptoms:** Requests take > 10 seconds

**Check:**
1. Embedding cache hit rate (should increase over time)
2. Number of items in bill
3. Render plan (Starter vs Standard)

**Solution:**
- Wait for cache to warm up
- Upgrade Render plan for more resources
- Consider persistent disk for embedding cache

---

## 📝 Next Steps After Deployment

1. **Monitor Logs:** Watch Render logs for first 24 hours
2. **Test Thoroughly:** Run verification on various bills
3. **Performance Tuning:** Monitor response times and adjust workers if needed
4. **Consider Upgrades:**
   - Persistent disk for embedding cache
   - External Ollama service for LLM matching
   - API + Worker split for high traffic

---

**Deployment Status:** ✅ READY  
**Last Updated:** 2026-02-08  
**Next Review:** After first deployment

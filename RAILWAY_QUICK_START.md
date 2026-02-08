# 🚂 RAILWAY DEPLOYMENT - QUICK START

**Status:** ✅ READY TO DEPLOY  
**Time to Deploy:** ~5 minutes  

---

## 🚀 DEPLOY NOW (3 Steps)

### 1. Commit & Push
```bash
git add .
git commit -m "refactor: Railway deployment ready"
git push origin main
```

### 2. Create Railway Project
1. Go to https://railway.app/dashboard
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository → `main` branch

### 3. Set Environment Variables
```
ENV=production
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGO_DB_NAME=medical_bills
ENABLE_LLM_MATCHING=false
DISABLE_OLLAMA=true
```

**Done!** Railway will build and deploy automatically.

---

## ✅ VERIFY DEPLOYMENT

### Health Check
```bash
curl https://your-app.railway.app/health
```

**Expected:**
```json
{"status": "healthy", "verifier_initialized": true, "hospitals_indexed": 6}
```

### Test Verification
```bash
curl -X POST https://your-app.railway.app/verify \
  -H "Content-Type: application/json" \
  -d '{"bill": {"hospital_name": "Apollo Hospital", "categories": [{"category_name": "Consultation", "items": [{"item_name": "General Consultation", "quantity": 1, "amount": 500}]}]}}'
```

---

## 📋 WHAT CHANGED

### Code Files Modified
- ✅ `backend/requirements.txt` - Railway-optimized dependencies
- ✅ `backend/app/verifier/api.py` - Railway PORT and logging
- ✅ `backend/app/config.py` - Railway environment detection
- ✅ `backend/app/verifier/llm_router.py` - Optional LLM with fallback

### New Files Created
- ✅ `railway.json` - Railway build/deploy config
- ✅ `Procfile` - Web service command
- ✅ `.railwayignore` - Exclude unnecessary files

---

## 🎯 KEY FEATURES

### ✅ Works on Railway
- FastAPI Verification API (full functionality)
- MongoDB Integration
- Semantic Matching (embedding similarity)
- Tie-up Rate Sheets
- All API endpoints

### ⚠️ Disabled (Optional)
- LLM Matching (uses conservative threshold instead)
- PDF Processing (not needed for API)

---

## 🔧 RAILWAY RUN COMMAND

```bash
cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
```

*(Automatically used via railway.json)*

---

## 📊 EXPECTED STARTUP LOGS

```
================================================================================
🚂 Starting Bill Verifier API on Railway...
================================================================================
Environment: production
Railway Environment: production
Port: 8080
⚠️  LLM Matching: DISABLED (using embedding similarity only)
📊 MongoDB: Configured (cluster.mongodb.net)
📁 Loading tie-up rate sheets from: /app/backend/data/tieups
================================================================================
✅ Bill Verifier initialized successfully (6 hospitals)
================================================================================
```

---

## 🐛 TROUBLESHOOTING

### Build Fails
- Check `pdf2image` is commented out in `requirements.txt`
- Verify `opencv-python-headless` is used

### Service Crashes
- Check Railway logs for errors
- Verify `MONGO_URI` is set correctly

### Tie-ups Not Loading
- Ensure `backend/data/tieups/` exists in repo
- Check `.railwayignore` doesn't exclude it

---

## 📚 FULL DOCUMENTATION

- **Comprehensive Guide:** `RAILWAY_DEPLOYMENT_GUIDE.md`
- **Implementation Summary:** `RAILWAY_DEPLOYMENT_COMPLETE.md`

---

**Ready to deploy? Run the 3 steps above!** 🚂✨

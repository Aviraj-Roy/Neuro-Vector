# Render Deployment - Quick Reference

## 🚀 Deployment Commands

### Build Command
```bash
apt-get update && apt-get install -y poppler-utils && pip install -r backend/requirements.txt
```

### Start Command
```bash
cd backend && uvicorn app.verifier.api:app --host 0.0.0.0 --port $PORT --workers 2
```

---

## 🔑 Environment Variables

### Required
```env
ENV=production
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGO_DB_NAME=medical_bills
DISABLE_OLLAMA=true
```

### Optional
```env
OCR_CONFIDENCE_THRESHOLD=0.6
LLM_BASE_URL=https://your-ollama-service.com  # Only if using external Ollama
```

---

## ✅ Quick Verification

### 1. Health Check
```bash
curl https://your-app.onrender.com/health
```

**Expected:**
```json
{"status": "healthy", "verifier_initialized": true, "hospitals_indexed": 6}
```

### 2. Check Logs
Look for:
- ✅ `Bill Verifier initialized successfully`
- ✅ `Ollama: DISABLED`
- ✅ `MongoDB: Configured`
- ✅ `Loaded: [6 hospitals]`

### 3. Test Verification
```bash
curl -X POST https://your-app.onrender.com/verify \
  -H "Content-Type: application/json" \
  -d '{"bill": {"hospital_name": "Apollo Hospital", "categories": [{"category_name": "Consultation", "items": [{"item_name": "General Consultation", "quantity": 1, "amount": 500}]}]}}'
```

---

## 🐛 Common Issues

### Service Won't Start
- ✅ Check `MONGO_URI` is set
- ✅ Verify tie-up JSONs exist in `backend/data/tieups/`
- ✅ Check Render logs for errors

### MongoDB Connection Failed
- ✅ Update MongoDB Atlas IP whitelist to `0.0.0.0/0`
- ✅ Verify credentials
- ✅ Check connection string format

### Verification Returns 500
- ✅ Check startup logs for tie-up loading errors
- ✅ Verify MongoDB document structure
- ✅ Test with simple bill first

---

## 📚 Full Documentation

- **Deployment Guide:** `RENDER_DEPLOYMENT_GUIDE.md`
- **Checklist:** `RENDER_DEPLOYMENT_CHECKLIST.md`
- **Summary:** `RENDER_REFACTORING_SUMMARY.md`
- **Analysis:** `RENDER_DEPLOYMENT_ANALYSIS.md`

---

## 🎯 What Changed

1. **MongoDB:** Lazy connection (no import-time crash)
2. **Ollama:** Optional with graceful fallback
3. **Cache:** Uses `/tmp` on Render
4. **Logging:** Comprehensive startup diagnostics
5. **Port:** Respects `$PORT` variable

---

**Status:** ✅ READY FOR DEPLOYMENT

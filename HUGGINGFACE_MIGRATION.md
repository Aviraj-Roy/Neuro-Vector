# Hugging Face Inference API Migration - Complete

## Overview

Successfully refactored the LLM router from **Ollama** to **Hugging Face Inference API** while maintaining all existing verification logic, thresholds, and behavior.

---

## 🎯 What Changed

### Files Modified

1. **`backend/app/verifier/llm_router.py`** - Complete refactor
   - Replaced Ollama/vLLM API calls with Hugging Face Inference API
   - Added internal model name mapping
   - Updated connection testing
   - Maintained all existing logic (caching, fallback, thresholds)

2. **`backend/app/verifier/api.py`** - Startup logging update
   - Removed `DISABLE_OLLAMA` check
   - Added `HF_API_TOKEN` validation
   - Updated startup messages

---

## 🔧 Technical Changes

### Environment Variables

#### **REMOVED:**
- ~~`DISABLE_OLLAMA`~~ (no longer needed)
- ~~`LLM_RUNTIME`~~ (no longer needed)
- ~~`LLM_BASE_URL`~~ (no longer needed)

#### **ADDED:**
- **`HF_API_TOKEN`** (REQUIRED for LLM matching)
  - Your Hugging Face API token
  - Get it from: https://huggingface.co/settings/tokens

#### **UNCHANGED:**
- `ENABLE_LLM_MATCHING` (default: `false`)
- `PRIMARY_LLM` (default: `phi3:mini`)
- `SECONDARY_LLM` (default: `qwen2.5:3b`)
- `LLM_TIMEOUT` (default: `30` seconds)
- `LLM_MIN_CONFIDENCE` (default: `0.7`)

### Model Name Mapping

External model names (used in config) are **unchanged**:
- `phi3:mini`
- `qwen2.5:3b`

Internal mapping to HuggingFace repos (automatic):
```python
MODEL_NAME_MAPPING = {
    "phi3:mini": "microsoft/Phi-3-mini-4k-instruct",
    "qwen2.5:3b": "Qwen/Qwen2.5-3B-Instruct",
}
```

**This mapping is internal only** - you don't need to change any configuration.

### API Changes

#### Before (Ollama):
```python
# POST to http://localhost:11434/api/generate
{
  "model": "phi3:mini",
  "prompt": "...",
  "stream": false,
  "options": {
    "temperature": 0.1,
    "num_predict": 150
  }
}
```

#### After (Hugging Face):
```python
# POST to https://api-inference.huggingface.co/models/microsoft/Phi-3-mini-4k-instruct
# Headers: Authorization: Bearer <HF_API_TOKEN>
{
  "inputs": "...",
  "parameters": {
    "temperature": 0.1,
    "max_new_tokens": 150,
    "return_full_text": false
  }
}
```

---

## ✅ What Stayed the Same

### Verification Logic (100% Unchanged)
- ✅ Similarity thresholds (0.85 auto-match, 0.70 auto-reject)
- ✅ Two-tier fallback (Phi-3 → Qwen2.5)
- ✅ Decision caching
- ✅ Error handling and fallback behavior
- ✅ Prompt template
- ✅ JSON response parsing
- ✅ Confidence scoring
- ✅ All verification phases
- ✅ Output format

### Behavior
- If LLM fails → falls back to conservative threshold (0.80)
- If LLM disabled → uses embedding similarity only
- Same logging levels and messages
- Same error recovery

---

## 🚀 Deployment Guide

### Railway

1. **Add Environment Variable:**
   ```
   HF_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

2. **Enable LLM Matching (optional):**
   ```
   ENABLE_LLM_MATCHING=true
   ```

3. **Deploy:**
   - No code changes needed
   - No system dependencies required
   - Works immediately on Railway

### Render

Same as Railway - just add `HF_API_TOKEN` to environment variables.

### Streamlit Cloud

1. Go to **Settings** → **Secrets**
2. Add:
   ```toml
   HF_API_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ENABLE_LLM_MATCHING = "true"
   ```

### Local Development

1. **Create `.env` file:**
   ```bash
   # backend/.env
   HF_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ENABLE_LLM_MATCHING=true
   PRIMARY_LLM=phi3:mini
   SECONDARY_LLM=qwen2.5:3b
   LLM_TIMEOUT=30
   LLM_MIN_CONFIDENCE=0.7
   ```

2. **Run the backend:**
   ```bash
   cd backend
   python main.py
   ```

---

## 🔑 Getting Your HF API Token

1. Go to https://huggingface.co/settings/tokens
2. Click **"New token"**
3. Name: `medical-bill-verifier`
4. Type: **Read** (sufficient for Inference API)
5. Copy the token (starts with `hf_`)

**Free Tier Limits:**
- ~1,000 requests/day per model
- Rate limit: ~10 requests/minute
- Sufficient for development and small-scale production

---

## 🧪 Testing

### Test LLM Availability

```python
from app.verifier.llm_router import get_llm_router

router = get_llm_router()
print(f"LLM Available: {router._llm_available}")
```

### Test a Match

```python
result = router.match_with_llm(
    bill_item="CONSULTATION - FIRST VISIT",
    tieup_item="Consultation",
    similarity=0.75
)
print(f"Match: {result.match}, Confidence: {result.confidence}")
print(f"Model Used: {result.model_used}")
```

### Expected Output (when enabled):

```
✅ LLMRouter initialized with Hugging Face Inference API
   Primary: phi3:mini -> microsoft/Phi-3-mini-4k-instruct
   Secondary: qwen2.5:3b -> Qwen/Qwen2.5-3B-Instruct
```

---

## 🐛 Troubleshooting

### Issue: "LLM Matching: DISABLED (HF_API_TOKEN not set)"

**Solution:**
- Set `HF_API_TOKEN` environment variable
- Verify token is valid at https://huggingface.co/settings/tokens

### Issue: "Rate limit exceeded"

**Solution:**
- HF free tier has rate limits (~10 req/min)
- Wait a few minutes and retry
- Consider upgrading to HF Pro for higher limits

### Issue: "Model is loading (estimated time: Xs)"

**Solution:**
- HF API cold-starts models on first request
- Wait for the estimated time and retry
- Subsequent requests will be fast

### Issue: "Timeout calling phi3:mini"

**Solution:**
- Increase `LLM_TIMEOUT` (default: 30s)
- Check internet connectivity
- Verify HF API status: https://status.huggingface.co/

---

## 📊 Performance Comparison

| Metric | Ollama (Local) | HuggingFace API |
|--------|----------------|-----------------|
| **Setup** | Install Ollama + pull models | Just API token |
| **Latency** | ~1-2s | ~2-4s (cold start: ~10-20s) |
| **Cost** | Free (local compute) | Free tier: 1K req/day |
| **Deployment** | Requires local server | Cloud-native |
| **Scalability** | Limited by hardware | Automatic scaling |
| **Maintenance** | Model updates manual | Always latest |

---

## 🎓 Key Learnings

1. **Model names are preserved** - No config changes needed
2. **Internal mapping is transparent** - Users don't see HF repo names
3. **Fallback behavior identical** - Same error handling
4. **No architectural changes** - Drop-in replacement
5. **Cloud-native** - No local dependencies

---

## 📝 Migration Checklist

- [x] Refactored `llm_router.py` to use HF Inference API
- [x] Added `HF_API_TOKEN` environment variable
- [x] Removed `DISABLE_OLLAMA` checks
- [x] Updated startup logging in `api.py`
- [x] Maintained all verification logic
- [x] Preserved model names and thresholds
- [x] Kept error handling and fallback behavior
- [x] No changes to verification phases
- [x] No changes to output format
- [x] Tested locally (ready for deployment)

---

## 🚀 Next Steps

1. **Get HF API Token** from https://huggingface.co/settings/tokens
2. **Set Environment Variable** on Railway/Render/Streamlit
3. **Enable LLM Matching** with `ENABLE_LLM_MATCHING=true`
4. **Deploy** - No code changes needed!

---

## 📚 References

- **HuggingFace Inference API Docs:** https://huggingface.co/docs/api-inference/index
- **Phi-3 Model:** https://huggingface.co/microsoft/Phi-3-mini-4k-instruct
- **Qwen2.5 Model:** https://huggingface.co/Qwen/Qwen2.5-3B-Instruct
- **HF API Pricing:** https://huggingface.co/pricing

---

**Migration completed successfully! 🎉**

The system now uses Hugging Face Inference API instead of Ollama, with zero changes to verification logic or behavior.

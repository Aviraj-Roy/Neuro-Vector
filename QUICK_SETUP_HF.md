# Quick Setup: HuggingFace API Token

## 🚀 5-Minute Setup Guide

### Step 1: Get Your HuggingFace API Token

1. Go to: **https://huggingface.co/settings/tokens**
2. Click **"New token"**
3. Fill in:
   - **Name:** `medical-bill-verifier`
   - **Type:** **Read** (sufficient for Inference API)
4. Click **"Generate"**
5. **Copy the token** (starts with `hf_`)
   - ⚠️ Save it somewhere safe - you won't see it again!

---

### Step 2: Set Environment Variable

#### **Railway:**
1. Go to your project dashboard
2. Click **"Variables"** tab
3. Click **"New Variable"**
4. Add:
   ```
   HF_API_TOKEN = hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ENABLE_LLM_MATCHING = true
   ```
5. Click **"Deploy"**

#### **Render:**
1. Go to your service dashboard
2. Click **"Environment"** tab
3. Add:
   ```
   HF_API_TOKEN = hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ENABLE_LLM_MATCHING = true
   ```
4. Click **"Save Changes"**

#### **Streamlit Cloud:**
1. Go to **Settings** → **Secrets**
2. Add:
   ```toml
   HF_API_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ENABLE_LLM_MATCHING = "true"
   ```
3. Click **"Save"**

#### **Local Development:**
Create `backend/.env`:
```bash
HF_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ENABLE_LLM_MATCHING=true
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
```

---

### Step 3: Verify Setup

#### Check Startup Logs:
Look for:
```
🤖 LLM Matching: ENABLED (Hugging Face Inference API)
   Primary model: phi3:mini
   Secondary model: qwen2.5:3b
✅ LLMRouter initialized with Hugging Face Inference API
   Primary: phi3:mini -> microsoft/Phi-3-mini-4k-instruct
   Secondary: qwen2.5:3b -> Qwen/Qwen2.5-3B-Instruct
```

#### Test API:
```bash
# Test health endpoint
curl http://localhost:8000/health

# Test verification (should use LLM for borderline matches)
curl -X POST http://localhost:8000/verify \
  -H "Content-Type: application/json" \
  -d @test_bill.json
```

---

## ⚠️ Troubleshooting

### "LLM Matching: DISABLED (HF_API_TOKEN not set)"
**Fix:** Set `HF_API_TOKEN` environment variable

### "Rate limit exceeded"
**Fix:** Wait a few minutes (free tier: ~10 req/min)

### "Model is loading (estimated time: Xs)"
**Fix:** Wait for model to load (first request only)

### "Timeout calling phi3:mini"
**Fix:** Increase `LLM_TIMEOUT` (default: 30s)

---

## 📊 Free Tier Limits

| Limit | Value |
|-------|-------|
| Requests/day | ~1,000 per model |
| Rate limit | ~10 requests/minute |
| Timeout | 60 seconds |
| Cost | **FREE** |

**Upgrade to HF Pro for:**
- Higher rate limits
- Faster inference
- Priority access

---

## ✅ Done!

Your backend now uses **Hugging Face Inference API** for LLM matching!

**No Ollama installation required** 🎉

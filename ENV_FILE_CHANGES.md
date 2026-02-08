# .env File Changes Summary

## 🔄 What Changed in .env

### ❌ REMOVED Variables (Ollama-specific)
```bash
LLM_RUNTIME=ollama           # No longer needed
LLM_BASE_URL=http://localhost:11434  # No longer needed
DISABLE_OLLAMA=true          # No longer needed
```

### ✅ ADDED Variables (HuggingFace API)
```bash
HF_API_TOKEN=your_hf_token_here      # REQUIRED for LLM matching
ENABLE_LLM_MATCHING=false            # Enable/disable LLM (default: false)
```

### ✓ UNCHANGED Variables
```bash
PRIMARY_LLM=phi3:mini                # Same model names
SECONDARY_LLM=qwen2.5:3b             # Same model names
LLM_TIMEOUT=30                       # Same timeout
LLM_MIN_CONFIDENCE=0.7               # Same confidence threshold
```

---

## 📝 Updated .env File

Your `.env` file has been updated with the new configuration. Here's what you need to do:

### Step 1: Get Your HuggingFace API Token

1. Go to: **https://huggingface.co/settings/tokens**
2. Click **"New token"**
3. Name: `medical-bill-verifier`
4. Type: **Read** (sufficient for Inference API)
5. Click **"Generate"**
6. **Copy the token** (starts with `hf_`)

### Step 2: Update Your .env File

Replace `your_hf_token_here` with your actual token:

```bash
# Before:
HF_API_TOKEN=your_hf_token_here

# After:
HF_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 3: Enable LLM Matching (Optional)

If you want to use LLM matching, set:

```bash
ENABLE_LLM_MATCHING=true
```

If you want to use embedding similarity only (no LLM), leave it as:

```bash
ENABLE_LLM_MATCHING=false
```

---

## 📋 Complete .env Example

Here's what your `.env` should look like after the changes:

```bash
# MongoDB Configuration
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?appName=YourApp
MONGO_DB_NAME=medical_bills
MONGO_COLLECTION_NAME=bills

# Embedding Service (Local)
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DEVICE=cpu
EMBEDDING_CACHE_PATH=data/embedding_cache.json

# LLM Configuration - HuggingFace Inference API
HF_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # ← YOUR TOKEN HERE
ENABLE_LLM_MATCHING=true                        # ← Set to true to enable
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
LLM_TIMEOUT=30
LLM_MIN_CONFIDENCE=0.7

# Tie-up Rate Sheets
TIEUP_DATA_DIR=data/tieups
CATEGORY_SIMILARITY_THRESHOLD=0.70
ITEM_SIMILARITY_THRESHOLD=0.85

# OCR Configuration
OCR_CONFIDENCE_THRESHOLD=0.6
```

---

## 🚀 For Deployment (Railway/Render/Streamlit)

You don't need to commit `.env` to your repository. Instead, set environment variables directly in your deployment platform:

### Railway:
1. Go to **Variables** tab
2. Add:
   ```
   HF_API_TOKEN = hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ENABLE_LLM_MATCHING = true
   ```

### Render:
1. Go to **Environment** tab
2. Add:
   ```
   HF_API_TOKEN = hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ENABLE_LLM_MATCHING = true
   ```

### Streamlit Cloud:
1. Go to **Settings** → **Secrets**
2. Add:
   ```toml
   HF_API_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ENABLE_LLM_MATCHING = "true"
   ```

---

## ✅ Verification

After updating your `.env`, verify the changes:

```bash
# Check if HF_API_TOKEN is set
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('HF_API_TOKEN:', 'SET' if os.getenv('HF_API_TOKEN') else 'NOT SET')"

# Start the backend and check logs
cd backend
python main.py
```

Look for this in the startup logs:
```
🤖 LLM Matching: ENABLED (Hugging Face Inference API)
   Primary model: phi3:mini
   Secondary model: qwen2.5:3b
✅ LLMRouter initialized with Hugging Face Inference API
   Primary: phi3:mini -> microsoft/Phi-3-mini-4k-instruct
   Secondary: qwen2.5:3b -> Qwen/Qwen2.5-3B-Instruct
```

---

## 🔒 Security Note

**NEVER commit your `.env` file to version control!**

- ✅ `.env` is already in `.gitignore`
- ✅ Use `.env.example` as a template (no secrets)
- ✅ Set actual secrets in deployment platform environment variables

---

## 📚 Related Files

- **`.env`** - Your local environment configuration (updated)
- **`.env.example`** - Template file (created)
- **`QUICK_SETUP_HF.md`** - Detailed setup guide
- **`HUGGINGFACE_MIGRATION.md`** - Full migration documentation

---

## ❓ FAQ

### Q: Do I need to change PRIMARY_LLM or SECONDARY_LLM?
**A:** No! Keep them as `phi3:mini` and `qwen2.5:3b`. The mapping to HuggingFace repos is automatic and internal.

### Q: What if I don't have an HF_API_TOKEN?
**A:** The system will work fine without it! LLM matching will be disabled, and verification will use embedding similarity only (with a conservative threshold of 0.80 for borderline cases).

### Q: Can I use a different LLM model?
**A:** Yes, but you'll need to update the `MODEL_NAME_MAPPING` in `backend/app/verifier/llm_router.py` to map your model name to the HuggingFace repo.

### Q: Is the free tier enough?
**A:** Yes! The free tier provides ~1,000 requests/day per model, which is sufficient for development and small-scale production.

---

**Your `.env` file is now ready for HuggingFace Inference API! 🎉**

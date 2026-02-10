# Quick Setup Guide - Local LLM Medical Bill Verifier

## 🚀 Quick Start (5 minutes)

### Step 1: Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Install Ollama
**Windows (PowerShell):**
```powershell
winget install Ollama.Ollama
```

**Or download from:** https://ollama.com/download

### Step 3: Pull LLM Models
```bash
ollama pull phi3:mini      # Primary model (~2.3GB)
ollama pull qwen2.5:3b     # Fallback model (~1.9GB)
```

### Step 4: Start Ollama Service
```bash
ollama serve
```
Leave this running in a separate terminal.

### Step 5: Verify Setup
```bash
python app/verifier/test_local_setup.py
```

If all tests pass ✅, you're ready to go!

---

## 📋 System Requirements

- **Python:** 3.8+
- **RAM:** 8GB minimum (16GB recommended)
- **Disk:** ~5GB for models
- **OS:** Windows, Linux, or macOS

---

## 🔧 Configuration

All configuration is in `.env`:

```bash
# Embedding Model (IMPORTANT: Use full Hugging Face identifier)
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DEVICE=cpu  # Change to 'cuda' for GPU

# LLM Models
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
LLM_RUNTIME=ollama
LLM_BASE_URL=http://localhost:11434

# Thresholds
CATEGORY_SIMILARITY_THRESHOLD=0.70
ITEM_SIMILARITY_THRESHOLD=0.85
```

---

## 🧪 Testing Individual Components

### Test Embeddings Only
```python
from app.verifier.embedding_service import get_embedding_service

service = get_embedding_service()
embeddings = service.get_embeddings(["CT Scan", "MRI"])
print(embeddings.shape)  # (2, 768)
```

### Test LLM Router Only
```python
from app.verifier.llm_router import get_llm_router

router = get_llm_router()
result = router.match_with_llm(
    bill_item="CT Scan Head",
    tieup_item="CT Brain",
    similarity=0.78
)
print(f"Match: {result.match}, Confidence: {result.confidence}")
```

### Test Full Matcher
```python
from app.verifier.matcher import get_matcher

matcher = get_matcher()
# Load your rate sheets and test...
```

---

## 🐛 Common Issues

### "sentence-transformers not found"
```bash
pip install sentence-transformers torch
```

### "Cannot connect to Ollama"
```bash
# Make sure Ollama is running:
ollama serve

# Test connection:
curl http://localhost:11434/api/tags
```

### "Model not found"
```bash
# List installed models:
ollama list

# Pull missing models:
ollama pull phi3:mini
ollama pull qwen2.5:3b
```

### Slow performance
```bash
# Use GPU if available (in .env):
EMBEDDING_DEVICE=cuda

# Or use smaller models:
PRIMARY_LLM=phi3:mini  # Already the smallest Phi-3
```

---

## 📊 Monitoring Performance

```python
from app.verifier.matcher import get_matcher

matcher = get_matcher()
# ... process bills ...

# Check statistics
stats = matcher.stats
print(f"LLM Usage: {stats['llm_usage_percentage']:.2f}%")  # Target: <10%
print(f"Cache Hit Rate: {stats['llm_cache_hit_rate']:.2%}")
```

---

## 🔄 Switching Runtimes

### Using vLLM instead of Ollama

1. Install vLLM:
```bash
pip install vllm
```

2. Start vLLM server:
```bash
python -m vllm.entrypoints.openai.api_server \
    --model microsoft/Phi-3-mini-4k-instruct \
    --port 8000
```

3. Update `.env`:
```bash
LLM_RUNTIME=vllm
LLM_BASE_URL=http://localhost:8000
```

---

## 📈 Performance Targets

- ✅ **LLM Usage:** < 10% of total matches
- ✅ **Embedding Cache Hit Rate:** > 80%
- ✅ **LLM Cache Hit Rate:** > 70%
- ✅ **No External API Calls:** 100% offline

---

## 🆘 Getting Help

1. Check logs for errors
2. Run `python app/verifier/test_local_setup.py`
3. Verify Ollama is running: `ollama list`
4. Check model availability: `curl http://localhost:11434/api/tags`

---

## ✅ Verification Checklist

- [ ] Python dependencies installed
- [ ] Ollama installed and running
- [ ] Models pulled (phi3:mini, qwen2.5:3b)
- [ ] `.env` configured
- [ ] Test script passes all checks
- [ ] Embedding service working
- [ ] LLM router working
- [ ] Full integration test passes

---

## 🎯 Next Steps

1. Load your tie-up rate sheets
2. Process sample bills
3. Monitor LLM usage statistics
4. Tune thresholds if needed
5. Deploy to production

---

**For detailed documentation, see:** `LOCAL_LLM_REFACTORING.md`

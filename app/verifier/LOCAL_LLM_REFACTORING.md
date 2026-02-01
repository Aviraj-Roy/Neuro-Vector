# Local LLM Refactoring - Medical Bill Verifier

## Overview

This document describes the refactoring of the medical bill verification system to use **ONLY local LLM models**. All external API dependencies (OpenAI) have been removed.

## Architecture Changes

### 1. **Embedding Service** (`embedding_service.py`)
**Before:** OpenAI API with rate limiting, retries, and quota handling  
**After:** Local sentence-transformers with bge-base-en-v1.5

**Key Changes:**
- ✅ Removed all OpenAI SDK imports and API calls
- ✅ Removed rate limit handling, exponential backoff, and retry logic
- ✅ Removed API key configuration
- ✅ Model loads once at startup (cached in memory)
- ✅ Embeddings generated locally on CPU/GPU
- ✅ Persistent disk cache retained for performance

**Performance:**
- No network latency
- No rate limits or quotas
- Deterministic behavior
- Embedding dimension: 768 (bge-base-en-v1.5)

---

### 2. **LLM Router** (`llm_router.py`) - **NEW MODULE**
Intelligent routing system for borderline similarity cases.

**Routing Logic:**
```
IF similarity >= 0.85:
    ✅ Auto-match (no LLM needed)
ELSE IF 0.70 <= similarity < 0.85:
    🤖 Use Phi-3 Mini for verification
    IF Phi-3 fails OR confidence < 0.7:
        🤖 Fallback to Qwen2.5-3B
ELSE (similarity < 0.70):
    ❌ Auto-reject (mismatch)
```

**Features:**
- Two-tier fallback system (Phi-3 → Qwen2.5)
- In-memory decision cache (text_pair → result)
- Strict JSON-only prompts for deterministic output
- Supports both Ollama and vLLM runtimes
- Tracks usage statistics

**Prompt Template:**
```
You are a medical billing auditor.

Decide if these two terms refer to the same medical service.

Term A: "{bill_item}"
Term B: "{tieup_item}"

Answer ONLY in JSON:
{
  "match": true|false,
  "confidence": 0.0-1.0,
  "normalized_name": ""
}

No explanations. No extra text.
```

---

### 3. **Matcher** (`matcher.py`)
**Before:** Pure embedding-based matching with fixed thresholds  
**After:** Hybrid embedding + LLM for borderline cases

**Integration:**
- High similarity (≥0.85): Auto-match using embeddings only
- Borderline (0.70-0.85): LLM verification via router
- Low similarity (<0.70): Auto-reject
- LLM usage tracked and reported in stats

**Statistics Tracking:**
```python
matcher.stats
# Returns:
{
    "total_matches": 150,
    "llm_calls": 12,
    "llm_usage_percentage": 8.0,  # Target: < 10%
    "llm_cache_size": 45,
    "llm_cache_hit_rate": 0.73
}
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# Local Embedding Model
EMBEDDING_MODEL=bge-base-en-v1.5
EMBEDDING_DEVICE=cpu  # or 'cuda' for GPU

# Local LLM Models
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
LLM_RUNTIME=ollama  # or 'vllm'
LLM_BASE_URL=http://localhost:11434
LLM_TIMEOUT=30
LLM_MIN_CONFIDENCE=0.7

# Matching Thresholds
CATEGORY_SIMILARITY_THRESHOLD=0.70
ITEM_SIMILARITY_THRESHOLD=0.85
```

---

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

**New Dependencies:**
- `sentence-transformers>=2.2.0` - Local embeddings
- `torch>=2.0.0` - PyTorch backend
- `requests>=2.31.0` - LLM API calls

**Removed:**
- `openai>=1.0.0` ❌

---

### 2. Install Ollama (Recommended Runtime)

**Windows:**
```powershell
# Download from https://ollama.com/download
# Or use winget:
winget install Ollama.Ollama
```

**Linux/Mac:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

---

### 3. Pull LLM Models

```bash
# Primary model (Phi-3 Mini - 2.3GB)
ollama pull phi3:mini

# Secondary model (Qwen2.5-3B - 1.9GB)
ollama pull qwen2.5:3b
```

**Model Sizes:**
- Phi-3 Mini: ~2.3GB
- Qwen2.5-3B: ~1.9GB
- bge-base-en-v1.5: ~438MB (auto-downloaded by sentence-transformers)

---

### 4. Start Ollama Service

```bash
# Ollama runs as a service on port 11434 by default
ollama serve
```

Verify it's running:
```bash
curl http://localhost:11434/api/tags
```

---

### 5. Test the System

```python
from app.verifier.embedding_service import get_embedding_service
from app.verifier.llm_router import get_llm_router
from app.verifier.matcher import get_matcher

# Test embeddings
emb_service = get_embedding_service()
embeddings = emb_service.get_embeddings(["CT Scan", "MRI Scan"])
print(f"Embeddings shape: {embeddings.shape}")  # (2, 768)

# Test LLM router
llm_router = get_llm_router()
result = llm_router.match_with_llm(
    bill_item="CT Scan Head",
    tieup_item="CT Brain",
    similarity=0.78
)
print(f"Match: {result.match}, Confidence: {result.confidence}")

# Test matcher (full integration)
matcher = get_matcher()
# ... (load rate sheets and test)
```

---

## Performance Requirements

### Target Metrics
- ✅ **LLM Usage:** < 10% of total matches
- ✅ **Embedding Cache Hit Rate:** > 80% after warmup
- ✅ **LLM Cache Hit Rate:** > 70% after warmup
- ✅ **No External API Calls:** 100% offline

### Monitoring

```python
from app.verifier.matcher import get_matcher

matcher = get_matcher()
# After processing bills...
stats = matcher.stats

print(f"LLM Usage: {stats['llm_usage_percentage']:.2f}%")
print(f"LLM Cache Hit Rate: {stats['llm_cache_hit_rate']:.2%}")
```

---

## File Structure

```
app/
├─ verifier/
│   ├─ embedding_service.py   ✅ REFACTORED (local embeddings)
│   ├─ llm_router.py          ✅ NEW (LLM fallback logic)
│   ├─ matcher.py             ✅ UPDATED (LLM integration)
│   ├─ price_checker.py       (unchanged)
│   ├─ verifier.py            (unchanged - uses matcher)
│   ├─ models.py              (unchanged)
│   └─ embedding_cache.py     (unchanged)
└─ main.py                    (unchanged)
```

---

## Migration Checklist

- [x] Remove OpenAI SDK from requirements.txt
- [x] Add sentence-transformers, torch, requests
- [x] Rewrite embedding_service.py for local models
- [x] Create llm_router.py with Phi-3/Qwen fallback
- [x] Update matcher.py to use LLM for borderline cases
- [x] Remove API keys from .env
- [x] Add local model configuration to .env
- [x] Remove rate limit handling code
- [x] Remove retry/backoff logic
- [x] Add LLM decision caching
- [x] Add usage statistics tracking

---

## Troubleshooting

### Issue: "sentence-transformers package not installed"
```bash
pip install sentence-transformers torch
```

### Issue: "Ollama connection refused"
```bash
# Start Ollama service
ollama serve

# Or check if it's running
curl http://localhost:11434/api/tags
```

### Issue: "Model not found: phi3:mini"
```bash
ollama pull phi3:mini
ollama pull qwen2.5:3b
```

### Issue: Slow embedding generation
```bash
# Use GPU if available
# In .env:
EMBEDDING_DEVICE=cuda
```

### Issue: LLM timeout errors
```bash
# Increase timeout in .env:
LLM_TIMEOUT=60
```

---

## Advantages of Local Architecture

1. **No Rate Limits:** Process unlimited bills without API quotas
2. **No Network Dependency:** Works completely offline
3. **Deterministic:** Same input always produces same output
4. **Cost-Free:** No per-request API charges
5. **Privacy:** Medical data never leaves your infrastructure
6. **Low Latency:** No network round-trips
7. **Predictable Performance:** No API throttling or downtime

---

## Model Information

### bge-base-en-v1.5
- **Type:** Embedding model
- **Dimension:** 768
- **Size:** ~438MB
- **Use Case:** Semantic similarity for all matching
- **License:** MIT

### Phi-3 Mini
- **Type:** Language model (3.8B parameters)
- **Size:** ~2.3GB
- **Use Case:** Primary reasoning for borderline matches
- **License:** MIT

### Qwen2.5-3B
- **Type:** Language model (3B parameters)
- **Size:** ~1.9GB
- **Use Case:** Fallback reasoning if Phi-3 fails
- **License:** Apache 2.0

---

## Next Steps

1. **Test with Real Bills:** Run verification on sample bills
2. **Monitor LLM Usage:** Ensure < 10% of matches use LLM
3. **Tune Thresholds:** Adjust similarity thresholds if needed
4. **Optimize Cache:** Monitor cache hit rates
5. **GPU Acceleration:** Use CUDA if available for faster embeddings

---

## Support

For issues or questions:
1. Check Ollama logs: `ollama logs`
2. Check application logs for embedding/LLM errors
3. Verify model downloads: `ollama list`
4. Test individual components (embedding service, LLM router)

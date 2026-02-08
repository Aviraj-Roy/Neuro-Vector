# Project Versions and Models Reference

**Project:** AI-Powered Medical Bill Verification for IOCL Employees  
**Last Updated:** 2026-02-08  
**Environment:** Railway Deployment (Python 3.10+)

---

## 📦 Core Dependencies & Versions

### Web Framework
| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | >=0.104.0 | Core web framework |
| `uvicorn[standard]` | >=0.24.0 | ASGI server |
| `python-multipart` | >=0.0.6 | File upload support |
| `python-dotenv` | >=1.0.0 | Environment variable management |

### Database
| Package | Version | Purpose |
|---------|---------|---------|
| `pymongo` | >=4.6.0 | MongoDB client |

### Data Validation
| Package | Version | Purpose |
|---------|---------|---------|
| `pydantic` | >=2.0.0 | Data validation |
| `pydantic-settings` | >=2.0.0 | Settings management |

### HTTP Client
| Package | Version | Purpose |
|---------|---------|---------|
| `requests` | >=2.31.0 | HTTP requests (Ollama health checks) |

### Logging
| Package | Version | Purpose |
|---------|---------|---------|
| `colorlog` | >=6.7.0 | Colored logging output |

---

## 🖼️ OCR (Optical Character Recognition)

### PaddleOCR Stack
| Package | Version | Purpose |
|---------|---------|---------|
| `paddleocr` | >=2.7.0 | OCR engine for text extraction |
| `paddlepaddle` | >=2.5.0 | PaddlePaddle deep learning framework |
| `opencv-python-headless` | >=4.8.0 | Image processing (no GUI dependencies) |
| `Pillow` | >=10.0.0 | Image manipulation |

**Note:** `pdf2image` is **DISABLED** for Railway deployment (requires poppler-utils system binary)

---

## 🤖 Machine Learning & AI

### Embedding Models

#### Primary Embedding Model
- **Model Name:** `BAAI/bge-base-en-v1.5`
- **Source:** Hugging Face (sentence-transformers)
- **Dimension:** 768
- **Purpose:** Generate semantic embeddings for medical terms
- **Device:** CPU (Railway deployment)
- **Configuration:**
  - Environment Variable: `EMBEDDING_MODEL` (default: `BAAI/bge-base-en-v1.5`)
  - Device: `EMBEDDING_DEVICE` (default: `cpu`)
  - Cache Path: `EMBEDDING_CACHE_PATH` (default: `data/embedding_cache.json`)

#### ML Dependencies
| Package | Version | Purpose |
|---------|---------|---------|
| `sentence-transformers` | >=2.2.0 | Embedding model framework |
| `torch` | >=2.0.0, <2.2.0 | PyTorch (CPU-only, no CUDA) |
| `faiss-cpu` | >=1.7.4 | Vector similarity search |
| `numpy` | >=1.24.0, <2.0.0 | Numerical computing |
| `scikit-learn` | >=1.3.0 | Machine learning utilities |

---

## 🧠 LLM (Large Language Models) - Hugging Face Inference API

### LLM Configuration
**Status:** **OPTIONAL** (disabled by default, requires HF_API_TOKEN)

#### Primary LLM Model
- **Model Name:** `phi3:mini`
- **HuggingFace Repo:** `microsoft/Phi-3-mini-4k-instruct`
- **Runtime:** Hugging Face Inference API
- **Purpose:** Fast, efficient medical term matching for borderline cases
- **Similarity Range:** 0.70 - 0.85 (borderline cases only)
- **Configuration:**
  - Environment Variable: `PRIMARY_LLM` (default: `phi3:mini`)

#### Secondary LLM Model (Fallback)
- **Model Name:** `qwen2.5:3b`
- **HuggingFace Repo:** `Qwen/Qwen2.5-3B-Instruct`
- **Runtime:** Hugging Face Inference API
- **Purpose:** Fallback when primary model fails or has low confidence
- **Configuration:**
  - Environment Variable: `SECONDARY_LLM` (default: `qwen2.5:3b`)

#### LLM Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `HF_API_TOKEN` | *(required)* | Hugging Face API token (get from https://huggingface.co/settings/tokens) |
| `ENABLE_LLM_MATCHING` | `false` | Enable/disable LLM matching |
| `PRIMARY_LLM` | `phi3:mini` | Primary model name |
| `SECONDARY_LLM` | `qwen2.5:3b` | Secondary model name |
| `LLM_TIMEOUT` | `30` | Request timeout (seconds) |
| `LLM_MIN_CONFIDENCE` | `0.7` | Minimum confidence threshold |

#### LLM Routing Logic
- **similarity >= 0.85:** Auto-match (no LLM needed)
- **0.70 <= similarity < 0.85:** Use LLM for verification
  1. Try primary model (Phi-3 Mini)
  2. If fails or low confidence, try secondary (Qwen2.5-3B)
- **similarity < 0.70:** Auto-reject (mismatch)

**Fallback Behavior (when LLM unavailable):**
- Uses conservative threshold of **0.80** for matching
- Verification continues with embedding similarity only

---

## 🎯 Model Usage Summary

### Active Models (Railway Deployment)

#### 1. **Embedding Model** ✅ ACTIVE
- **Name:** `BAAI/bge-base-en-v1.5`
- **Type:** Sentence Transformer
- **Dimension:** 768
- **Device:** CPU
- **Status:** Always enabled, required for verification

#### 2. **OCR Model** ✅ ACTIVE
- **Name:** PaddleOCR (version >=2.7.0)
- **Backend:** PaddlePaddle (>=2.5.0)
- **Status:** Always enabled, required for text extraction

#### 3. **LLM Models** ⚠️ OPTIONAL (Disabled by default)
- **Primary:** `phi3:mini` → `microsoft/Phi-3-mini-4k-instruct` (HuggingFace)
- **Secondary:** `qwen2.5:3b` → `Qwen/Qwen2.5-3B-Instruct` (HuggingFace)
- **Status:** Disabled by default, requires `HF_API_TOKEN`
- **Requirement:** Hugging Face API token (no local installation needed)

---

## 🔧 Configuration Files

### Main Configuration
- **File:** `backend/app/config.py`
- **Purpose:** Application configuration, path management, environment detection

### Requirements
- **File:** `backend/requirements.txt`
- **Purpose:** Python package dependencies
- **Python Version:** 3.10+ (Railway default: 3.11)

---

## 🚀 Deployment Notes

### Railway Environment
- **Python Version:** 3.11 (automatic)
- **Torch:** CPU-only (no CUDA dependencies)
- **OpenCV:** Headless version (no GUI dependencies)
- **PDF Processing:** Disabled (no poppler-utils)
- **LLM Matching:** Optional via Hugging Face Inference API (set `HF_API_TOKEN`)
- **System Dependencies:** None required (all pip-installable)

### Local Development
- **Python Version:** 3.10+
- **Required Services:**
  - MongoDB (required for bill storage)
- **Optional Services:**
  - Hugging Face API (optional, for LLM matching - requires API token)
- **No Local Models Required:**
  - LLM inference handled by HuggingFace API
  - No Ollama installation needed

---

## 📊 Model Performance Characteristics

### Embedding Model (BAAI/bge-base-en-v1.5)
- **First Load:** ~1-2 seconds (model download on first run)
- **Inference:** ~10-50ms per batch (32 items)
- **Memory:** ~500MB RAM
- **Caching:** Persistent disk cache (JSON)

### OCR (PaddleOCR)
- **Processing:** 3-5 seconds per page
- **Memory:** ~1-2GB RAM
- **Accuracy:** High for printed medical bills

### LLM Models (when enabled)
- **Phi-3 Mini:** Fast (~1-2s per request)
- **Qwen2.5-3B:** Moderate (~2-4s per request)
- **Memory:** ~2-4GB RAM per model

---

## 🔍 Quick Reference

### To Check Installed Versions
```bash
pip list | grep -E "(fastapi|paddleocr|sentence-transformers|torch|faiss)"
```

### To Verify Models
```bash
# Check embedding model
python -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('BAAI/bge-base-en-v1.5'); print(f'Dimension: {model.get_sentence_embedding_dimension()}')"

# Check HuggingFace API token (if LLM enabled)
python -c "import os; print('HF_API_TOKEN:', 'SET' if os.getenv('HF_API_TOKEN') else 'NOT SET')"

# Test LLM router
python -c "from app.verifier.llm_router import get_llm_router; router = get_llm_router(); print(f'LLM Available: {router._llm_available}')"
```

### Environment Variables Summary
```bash
# Embedding
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DEVICE=cpu

# LLM (optional - requires HuggingFace API token)
HF_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ENABLE_LLM_MATCHING=false
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
LLM_TIMEOUT=30
LLM_MIN_CONFIDENCE=0.7

# Database
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=medical_bills

# OCR
OCR_CONFIDENCE_THRESHOLD=0.6
```

---

## 📝 Notes

1. **Embedding Model is Required:** The system cannot function without the embedding model for semantic similarity matching.

2. **LLM is Optional:** LLM matching improves accuracy for borderline cases but is not required. The system falls back to a conservative threshold (0.80) when LLM is unavailable.

3. **Railway Deployment:** Optimized for Railway's native Python environment with no system dependencies.

4. **Model Downloads:** First run will download the embedding model from Hugging Face. LLM inference is handled via API (no local download).

5. **Caching:** Embedding and LLM results are cached to minimize redundant computations.

6. **HuggingFace API:** LLM calls are made via HTTPS to HuggingFace Inference API. No local model installation required.

---

**For more details, see:**
- `backend/requirements.txt` - Full dependency list
- `backend/app/config.py` - Configuration management
- `backend/app/verifier/embedding_service.py` - Embedding model implementation
- `backend/app/verifier/llm_router.py` - LLM routing logic (HuggingFace API)
- `HUGGINGFACE_MIGRATION.md` - Migration guide from Ollama to HuggingFace

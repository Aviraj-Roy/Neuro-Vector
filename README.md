# NeuroVector — AI-Powered Medical Bill Verification Backend

> **Purpose:** Automate verification of hospital bills submitted by IOCL employees against pre-negotiated hospital tie-up rate sheets using OCR, semantic embedding matching, and local LLMs.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Key Technologies & Versions](#key-technologies--versions)
4. [Project Structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [Installation](#installation)
7. [Configuration (.env)](#configuration-env)
8. [Running the Server](#running-the-server)
9. [CLI Usage](#cli-usage)
10. [API Reference](#api-reference)
11. [Processing Pipeline](#processing-pipeline)
12. [Verification Engine](#verification-engine)
13. [Hospital Tie-Up Rate Sheets](#hospital-tie-up-rate-sheets)
14. [Database (MongoDB)](#database-mongodb)
15. [AI Models Used](#ai-models-used)
16. [Testing](#testing)
17. [Additional Documentation](#additional-documentation)

---

## Project Overview

This is the **backend** for the NeuroVector Medical Bill Verification System. When an IOCL employee submits a hospital bill (PDF), the system:

1. **OCRs** the PDF pages using PaddleOCR.
2. **Extracts** structured bill data (patient info, categories, line items, grand total).
3. **Persists** a single MongoDB document per upload.
4. **Verifies** each bill line item against the hospital's pre-negotiated tie-up rate sheet using sentence-transformer embeddings + FAISS similarity search.
5. **Returns** a structured result with per-item statuses (`GREEN`, `RED`, `UNCLASSIFIED`, `ALLOWED_NOT_COMPARABLE`, `MISMATCH`) and financial totals.

---

## Architecture

```
HTTP Request (PDF + metadata)
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ FastAPI Server  (backend/server.py)  :8001                       │
│   └── API Router (app/api/routes.py)                             │
│         ├── POST /upload  ──► Upload Pipeline (app/services/)    │
│         ├── GET  /status/{id}                                    │
│         ├── GET  /bills                                          │
│         ├── POST /verify/{id} ──► Verifier Engine (app/verifier/)│
│         ├── GET  /bills/{id}                                     │
│         ├── DELETE /bills/{id}                                   │
│         ├── POST /bills/{id}/restore                             │
│         ├── PATCH /bills/{id}/line-items                         │
│         ├── GET  /tieups                                         │
│         └── POST /tieups/reload                                  │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────┐    ┌──────────────────────────────────┐
│  Processing Pipeline      │    │   Verifier Engine                │
│  (app/main.py)            │    │   (app/verifier/)                │
│  1. pdf_to_images()       │    │  1. Load tie-up rate sheets      │
│  2. preprocess_image()    │    │  2. FAISS hospital match         │
│  3. run_ocr()             │    │  3. FAISS category match         │
│  4. extract_bill_data()   │    │  4. V2 6-layer item match        │
│  5. validate_extraction() │    │  5. Price comparison             │
│  6. complete_bill() (DB)  │    │  6. Financial reconciliation     │
└──────────────┬───────────┘    └───────────────┬──────────────────┘
               │                                │
               ▼                                ▼
       ┌───────────────┐               ┌─────────────────────────┐
       │   MongoDB      │◄─────────────│  Embedding Cache (FAISS) │
       │ (medical_bills)│               │  bge-base-en-v1.5       │
       └───────────────┘               └─────────────────────────┘
```

### Module Separation

| Layer | File | Purpose |
|---|---|---|
| ASGI Entry Point | `backend/server.py` | FastAPI app, CORS, startup events |
| API Routes | `backend/app/api/routes.py` | All HTTP endpoint handlers |
| Service Layer | `backend/app/main.py` | `process_bill()` business logic |
| CLI Entry Point | `backend/main.py` | Command-line interface |
| Configuration | `backend/app/config.py` | Path resolution, env variables |

---

## Key Technologies & Versions

| Category | Library | Version |
|---|---|---|
| Web Framework | FastAPI | 0.121.1 |
| ASGI Server | Uvicorn | 0.38.0 |
| PDF → Images | pdf2image | 1.17.0 |
| OCR | PaddleOCR | 3.3.2 |
| OCR Backend | PaddlePaddle | 3.2.2 |
| Image Processing | OpenCV | 4.10.0.84 |
| Image Processing | Pillow | 10.2.0 |
| Embeddings | sentence-transformers | 5.2.2 |
| Deep Learning | PyTorch | 2.6.0 |
| Vector Search | FAISS (CPU) | 1.13.2 |
| Numerical | NumPy | 1.26.4 |
| Data Validation | Pydantic | 2.12.4 |
| Database Driver | PyMongo | 3.12.0 |
| HTTP Client | Requests | 2.32.5 |
| Multipart | python-multipart | 0.0.20 |
| Env Variables | python-dotenv | 1.2.1 |
| Python | — | 3.8+ (3.10 recommended) |

**External dependencies (not pip):**

| Tool | Purpose | Link |
|---|---|---|
| **Poppler** | PDF rendering (required by pdf2image) | [GitHub releases](https://github.com/oschwartz10612/poppler-windows/releases) |
| **MongoDB** | Document storage | [mongodb.com/try/download/community](https://www.mongodb.com/try/download/community) |
| **Ollama** | Local LLM inference (phi3:mini, qwen2.5:3b) | [ollama.com](https://ollama.com/) |

---

## Project Structure

```
Neuro-Vector-Backend/
├── backend/                          # All backend code
│   ├── server.py                     # FastAPI ASGI app (production entry)
│   ├── main.py                       # CLI entry point
│   ├── requirements.txt              # Python dependencies
│   ├── app/
│   │   ├── config.py                 # Path/env configuration
│   │   ├── main.py                   # Core process_bill() pipeline
│   │   ├── api/
│   │   │   └── routes.py             # All API endpoint handlers (~1875 lines)
│   │   ├── classification/           # Bill classification logic
│   │   ├── db/
│   │   │   ├── mongo_client.py       # MongoDB CRUD + lifecycle management
│   │   │   ├── bill_schema.py        # Bill document schema
│   │   │   ├── init_indexes.py       # MongoDB index initialization
│   │   │   └── artifact_filter.py   # OCR artifact filtering
│   │   ├── extraction/
│   │   │   ├── bill_extractor.py     # 3-stage extraction pipeline
│   │   │   ├── column_parser.py      # Table column parsing
│   │   │   ├── numeric_guards.py     # Amount sanity checks
│   │   │   ├── regex_utils.py        # Extraction regex utilities
│   │   │   ├── section_tracker.py   # Bill section state machine
│   │   │   └── zone_detector.py      # Page zone classification
│   │   ├── ingestion/
│   │   │   └── pdf_loader.py         # PDF → images via pdf2image
│   │   ├── ocr/
│   │   │   ├── paddle_engine.py      # PaddleOCR runner
│   │   │   └── image_preprocessor.py # OpenCV preprocessing
│   │   ├── services/
│   │   │   ├── upload_pipeline.py    # Async upload queue worker
│   │   │   └── bill_retention.py     # Soft-delete cleanup background worker
│   │   ├── tools/
│   │   │   └── (embedding builder CLI)
│   │   ├── utils/
│   │   │   ├── cleanup.py            # Post-OCR image cleanup
│   │   │   ├── dependency_check.py   # Startup dependency validation
│   │   │   └── file_utils.py         # File helpers
│   │   └── verifier/
│   │       ├── verifier.py           # BillVerifier orchestrator
│   │       ├── matcher.py            # SemanticMatcher (FAISS + embeddings)
│   │       ├── embedding_service.py  # bge-base-en-v1.5 wrapper
│   │       ├── embedding_cache.py    # Persistent disk embedding cache
│   │       ├── models.py             # Pydantic schemas (input/output)
│   │       ├── models_v2.py / models_v3.py
│   │       ├── price_checker.py      # Price comparison logic
│   │       ├── partial_matcher.py    # Partial/semantic item matching
│   │       ├── text_normalizer.py    # Item name normalization
│   │       ├── smart_normalizer.py   # Enhanced normalization
│   │       ├── output_renderer.py    # Human-readable output formatting
│   │       ├── financial_contribution.py  # Financial reconciliation
│   │       ├── failure_reasons.py    # Failure reason taxonomy
│   │       ├── failure_reasons_v2.py
│   │       ├── llm_router.py         # Ollama LLM integration
│   │       ├── hospital_validator.py # Hospital name validation
│   │       ├── aggregator.py         # Result aggregation
│   │       ├── enhanced_matcher.py   # Enhanced matching logic
│   │       ├── medical_core_extractor.py
│   │       ├── medical_core_extractor_v2.py
│   │       ├── phase2_processor.py
│   │       ├── phase3_display.py
│   │       ├── phase3_transformer.py
│   │       ├── reconciler.py
│   │       ├── category_enforcer.py
│   │       ├── artifact_detector.py
│   │       ├── medical_anchors.py
│   │       └── api.py                # verify_bill_from_mongodb_sync()
│   ├── reports/                      # Generated verification reports
│   ├── tests/                        # Unit tests
│   └── uploads/                      # Temporary image files (auto-cleaned)
│       └── processed/                # Preprocessed images
├── data/
│   ├── tieups/                       # Hospital tie-up rate sheets (JSON)
│   │   ├── apollo_hospital.json
│   │   ├── fortis_hospital.json
│   │   ├── manipal_hospital.json
│   │   ├── max_healthcare.json
│   │   ├── medanta_hospital.json
│   │   └── narayana_hospital.json
│   └── embedding_cache.json          # Persistent FAISS embedding cache
├── docs/                             # Architecture & phase documentation
├── start_api_server.bat              # Windows one-click server start
├── .env                              # Environment configuration
├── .gitignore
├── LICENSE
└── README.md                         # This file
```

---

## Prerequisites

1. **Python 3.8+** (3.12 recommended)
2. **Poppler** — Required by `pdf2image` for PDF rendering.
   - Windows: Download from [oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases), extract, and add the `bin/` folder to your system `PATH`.
3. **MongoDB** — Running locally (default: `mongodb://localhost:27017`) or via connection string in `.env`.
4. **Ollama** — For LLM-based analysis (`phi3:mini` and `qwen2.5:3b`).
   ```bash
   ollama pull phi3:mini
   ollama pull qwen2.5:3b
   ```

---

## Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd Neuro-Vector-Backend

# 2. Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

# 3. Install Python dependencies
pip install -r backend/requirements.txt

# 4. Copy and configure .env
# (edit the values as described in the Configuration section)
```

---

## Configuration (.env)

The `.env` file lives at the project root (or inside `backend/`). The system checks `backend/.env` first, then the project root `.env`.

```dotenv
# ── MongoDB ──────────────────────────────────────────────────────────────────
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=medical_bills
MONGO_COLLECTION_NAME=bills

# Bill soft-delete retention (days before permanent purge)
BILL_RETENTION_DAYS=30
BILL_RETENTION_CLEANUP_INTERVAL_SECONDS=3600

# Queue processing
QUEUE_STALE_PROCESSING_SECONDS=1800
QUEUE_RECONCILE_INTERVAL_SECONDS=60

# ── Embedding Model (local, no API calls) ────────────────────────────────────
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DEVICE=cpu
EMBEDDING_CACHE_PATH=data/embedding_cache.json

# ── Local LLM (via Ollama) ───────────────────────────────────────────────────
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
LLM_RUNTIME=ollama
LLM_BASE_URL=http://localhost:11434
LLM_TIMEOUT=150
LLM_MIN_CONFIDENCE=0.7

# ── Tie-up Rate Sheets ───────────────────────────────────────────────────────
TIEUP_DATA_DIR=data/tieups

# Semantic matching thresholds
CATEGORY_SIMILARITY_THRESHOLD=0.70
ITEM_SIMILARITY_THRESHOLD=0.85

# ── OCR ──────────────────────────────────────────────────────────────────────
OCR_CONFIDENCE_THRESHOLD=0.6
```

---

## Running the Server

### Option 1 — Windows Batch File (Recommended)

```bat
start_api_server.bat
```

This starts the API server at `http://localhost:8001` with hot-reload enabled.

### Option 2 — Direct Uvicorn Command

Run from the **project root**:

```bash
python -m uvicorn backend.server:app --reload --port 8001 --host 0.0.0.0
```

### Option 3 — Python Module

```bash
python -m backend.server
```

### Verify Server is Running

| URL | Description |
|---|---|
| `http://localhost:8001/health` | Health check |
| `http://localhost:8001/docs` | Swagger UI (interactive API docs) |
| `http://localhost:8001/redoc` | ReDoc documentation |
| `http://localhost:8001/openapi.json` | OpenAPI schema |

---

## CLI Usage

Process a bill from the command line (without the HTTP layer):

```bash
# Basic usage (process + verify)
python -m backend.main --bill Apollo.pdf --hospital "Apollo Hospital"

# Process only (skip verification)
python -m backend.main --bill M_Bill.pdf --hospital "Manipal Hospital" --no-verify

# Show detailed matching debug view
python -m backend.main --bill J_Bill.pdf --hospital "Fortis Hospital" --debug
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `--bill` | ✅ | Path to the medical bill PDF |
| `--hospital` | ✅ | Hospital name (must match a tie-up JSON hospital name) |
| `--no-verify` | ❌ | Skip verification, only extract & store |
| `--debug` | ❌ | Show debug view with detailed match scores |

> **Important:** Always run using `python -m backend.main` (not `python backend/main.py`) to ensure correct path resolution.

---

## API Reference

### POST `/upload`

Upload and process a medical bill PDF. Returns an `upload_id` that is used for all subsequent operations.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | ✅ | Medical bill PDF |
| `hospital_name` | string | ✅ | Hospital name (e.g. `"Apollo Hospital"`) |
| `employee_id` | string | ✅ | Employee ID — exactly 8 numeric digits |
| `invoice_date` | string | ❌ | Invoice date in `YYYY-MM-DD` format |
| `client_request_id` | string | ❌ | Idempotency key for deduplication |

**Response:**
```json
{
  "upload_id": "a1b2c3d4...",
  "employee_id": "12345678",
  "hospital_name": "Apollo Hospital",
  "message": "Bill uploaded and queued for processing",
  "status": "pending",
  "queue_position": 1,
  "page_count": 3,
  "original_filename": "bill.pdf",
  "file_size_bytes": 324567
}
```

---

### GET `/status/{upload_id}`

Poll the processing status of an uploaded bill.

**Response statuses:** `pending` | `processing` | `completed` | `failed` | `not_found`

**Processing stages:** `OCR` → `EXTRACTION` → `LLM_VERIFY` → `FORMAT_RESULT` → `DONE` | `FAILED`

```json
{
  "upload_id": "a1b2c3d4...",
  "status": "COMPLETED",
  "exists": true,
  "message": "Bill found",
  "hospital_name": "Apollo Hospital",
  "page_count": 3,
  "original_filename": "bill.pdf",
  "file_size_bytes": 324567,
  "queue_position": null,
  "processing_started_at": "2026-02-21T10:00:00",
  "completed_at": "2026-02-21T10:02:30",
  "processing_time_seconds": 150.5,
  "details_ready": true,
  "processing_stage": "DONE"
}
```

---

### GET `/bills`

List uploaded bills with filtering.

| Query Param | Default | Description |
|---|---|---|
| `limit` | `50` | Max bills to return (1–500) |
| `scope` | `active` | `active` or `deleted` |
| `status` | — | Filter by status: `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `hospital_name` | — | Exact hospital name filter (case-insensitive) |
| `date_filter` | — | `TODAY`, `YESTERDAY`, `THIS_MONTH`, `LAST_MONTH` |
| `include_deleted` | `false` | Include deleted bills when `true` |

---

### GET `/bills/deleted`

List only soft-deleted bills. Accepts the same query filters as `GET /bills` (except `scope`).

---

### GET `/bills/{upload_id}`

Get full bill details including structured verification results and line items.

**Response includes:**
- Bill metadata (employee, hospital, dates)
- `verificationResult` — raw formatted text for frontend parsing
- `line_items` — structured array of verified line items with decisions
- `financial_totals` — DB-backed financial summary

---

### POST `/verify/{upload_id}`

Trigger verification of a stored bill against hospital tie-up rates. Runs the full semantic matching + price checking engine.

---

### DELETE `/bills/{upload_id}`

Soft-delete or permanently delete a bill.

| Query Param | Default | Description |
|---|---|---|
| `permanent` | `false` | `true` = hard delete, `false` = soft delete |
| `deleted_by` | — | Optional audit actor ID |

---

### POST `/bills/{upload_id}/restore`

Restore a soft-deleted bill.

---

### PATCH `/bills/{upload_id}/line-items`

Manually edit extracted line item data (quantity, rate, tie-up rate).

**Request body:**
```json
{
  "line_items": [
    {
      "category_name": "Pharmacy",
      "item_index": 0,
      "qty": 2.0,
      "rate": 150.0,
      "tieup_rate": 140.0
    }
  ],
  "edited_by": "admin@iocl.in"
}
```

---

### GET `/tieups`

List all loaded hospital tie-up rate sheets with item counts.

---

### POST `/tieups/reload`

Hot-reload tie-up rate sheet JSON files without restarting the server.

---

## Processing Pipeline

Each upload goes through this 9-step pipeline in `app/main.py`:

```
1. pdf_to_images()          PDF → PNG images per page (via pdf2image + Poppler)
2. preprocess_image()       Grayscale, denoise, threshold (OpenCV)
3. run_ocr()                PaddleOCR on all preprocessed images (page-aware)
4. extract_bill_data()      3-stage: header → categories → line items
5. Add metadata             upload_id, source_pdf, hospital_name, page_count
6. validate_extraction()    Sanity checks on amounts, patient info, bill numbers
7. Log extraction summary   Item count, payment count, grand total
8. complete_bill()          Single MongoDB upsert (one doc per upload)
9. cleanup_images()         Auto-delete temp images after successful DB save
```

**Failure handling:** Any exception calls `db.mark_failed(upload_id, error)` and bubbles up. Cleanup only runs if both OCR and DB save succeeded.

---

## Verification Engine

The `BillVerifier` class (`app/verifier/verifier.py`) orchestrates:

### Matching Thresholds

| Level | Threshold | Behavior if below |
|---|---|---|
| Hospital | Configurable | All items marked `UNCLASSIFIED` |
| Category | 0.70 (configurable) | Still processes items (soft threshold) |
| Item | 0.85 (configurable) | Item marked `UNCLASSIFIED` |
| Category soft | 0.50 | Item matching continues with warning |

### Item Statuses

| Status | Meaning |
|---|---|
| `GREEN` | Bill amount ≤ allowed amount — within tie-up rate |
| `RED` | Bill amount > allowed amount — overcharged |
| `UNCLASSIFIED` | No matching item in tie-up; needs manual review |
| `MISMATCH` | Explicitly mismatched after full matching attempt |
| `ALLOWED_NOT_COMPARABLE` | Administrative/non-medical charge; not comparable |
| `IGNORED_ARTIFACT` | OCR artifact detected; excluded from financials |

### Financial Reconciliation

The engine enforces:
```
total_bill_amount == total_allowed_amount + total_extra_amount + total_unclassified_amount
```
A `financials_balanced` flag is returned in the response. Any imbalance is logged as a critical error.

### V2 Matching Architecture (6-layer)

1. Exact match
2. Normalized exact match
3. Acronym/abbreviation expansion
4. Partial string matching
5. FAISS cosine similarity (bge-base-en-v1.5 embeddings)
6. LLM-assisted disambiguation (phi3:mini via Ollama)

---

## Hospital Tie-Up Rate Sheets

Rate sheets are JSON files in `data/tieups/`. Currently available:

| Hospital | File |
|---|---|
| Apollo Hospital | `apollo_hospital.json` |
| Fortis Hospital | `fortis_hospital.json` |
| Manipal Hospital | `manipal_hospital.json` |
| Max Healthcare | `max_healthcare.json` |
| Medanta Hospital | `medanta_hospital.json` |
| Narayana Hospital | `narayana_hospital.json` |

### Rate Sheet Schema

```json
{
  "hospital_name": "Apollo Hospital",
  "categories": [
    {
      "category_name": "Pharmacy",
      "items": [
        {
          "item_name": "Paracetamol 500mg",
          "rate": 5.50,
          "type": "unit"
        }
      ]
    }
  ]
}
```

Item types:
- `unit` — rate × quantity
- `service` — fixed rate per service
- `bundle` — package price

---

## Database (MongoDB)

**Default:** `mongodb://localhost:27017/medical_bills`, collection: `bills`

### Bill Document Structure

Each uploaded bill produces **one document** (regardless of PDF page count):

```
{
  upload_id         : string (UUID hex)   — primary key for all operations
  employee_id       : string              — 8-digit IOCL employee ID
  hospital_name     : string              — from upload form
  hospital_name_metadata : string         — canonical hospital name
  original_filename : string              — uploaded PDF filename
  source_pdf        : string              — same as original_filename
  page_count        : int                 — number of PDF pages
  file_size_bytes   : int                 — original PDF size
  schema_version    : int (2)             — schema version
  status            : string              — pending|processing|completed|failed
  verification_status : string            — pending|processing|completed|failed
  verification_result : object            — structured verification output
  verification_result_text : string       — rendered human-readable text
  details_ready     : bool                — whether frontend can render results
  patient           : { name, mrn, ... }
  header            : { primary_bill_number, bill_numbers, ... }
  items             : { category: [{ item_name, amount, qty, rate }] }
  payments          : [{ reference, amount }]
  grand_total       : float
  extraction_warnings : [{ code, message, context }]
  line_item_edits   : [{ category_name, item_index, qty, rate, tieup_rate }]
  queue_position    : int
  upload_date       : ISO datetime
  processing_started_at : ISO datetime
  completed_at      : ISO datetime
  created_at        : ISO datetime
  updated_at        : ISO datetime
  is_deleted        : bool                — soft-delete flag
  deleted_at        : ISO datetime
  deleted_by        : string
}
```

### Soft Delete & Retention

- Soft-delete sets `is_deleted=true` and records `deleted_at`.
- A background worker (`app/services/bill_retention.py`) permanently purges soft-deleted bills older than `BILL_RETENTION_DAYS` (default 30 days).

---

## AI Models Used

| Model | Library | Purpose |
|---|---|---|
| `BAAI/bge-base-en-v1.5` | sentence-transformers | Semantic embeddings for FAISS similarity search (hospital, category, item matching) |
| `phi3:mini` | Ollama | Primary LLM for LLM-assisted disambiguation |
| `qwen2.5:3b` | Ollama | Secondary/fallback LLM |

Embedding vectors are cached in `data/embedding_cache.json` to avoid redundant inference across runs.

---

## Testing

```bash
# Run all backend tests
cd backend
pytest tests/

# Run verifier local setup test
python app/verifier/test_local_setup.py

# Run specific test files from project root
python test_backend.py
python test_upload_api.py
python test_matcher_refactor.py
python test_normalization.py
python test_llm_router_fix.py
```

---

## Additional Documentation

The `docs/` directory contains detailed technical documentation for each development phase:

| Document | Description |
|---|---|
| `docs/SYSTEM_ARCHITECTURE.md` | Full system architecture overview |
| `docs/MODEL_ARCHITECTURE_ANALYSIS.md` | In-depth AI model analysis |
| `docs/PHASE_2_ARCHITECTURE.md` | FastAPI migration architecture |
| `docs/PHASE_8_AUDIT.md` | Financial reconciliation implementation |
| `docs/TESTING_GUIDE.md` | Testing strategies and test cases |
| `docs/QUICK_START.md` | Minimal quick-start guide |
| `API_DOCUMENTATION.md` | Detailed API documentation (root level) |
| `FASTAPI_ARCHITECTURE.md` | FastAPI-specific architecture notes |
| `BACKEND_RUN_GUIDE.md` | Comprehensive run guide |
| `backend/app/verifier/README.md` | Verifier module documentation |

---

## License

See [LICENSE](./LICENSE) for license information.

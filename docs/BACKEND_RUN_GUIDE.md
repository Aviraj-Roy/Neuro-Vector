# Complete Backend Run Guide
## Medical Bill Verification System

This guide provides step-by-step instructions to run the entire backend system from scratch.

---

## 📋 Prerequisites

### Required Software
- **Python 3.8+** (Python 3.10 recommended)
- **MongoDB** (Community Edition or Cloud)
- **Ollama** (for local LLM support)
- **Poppler** (for PDF processing)

### System Requirements
- **RAM**: 8GB minimum (16GB recommended for LLM)
- **Disk Space**: ~10GB (including models)
- **OS**: Windows, Linux, or macOS

---

## 🚀 Step-by-Step Setup

### Step 1: Install Python Dependencies

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Install and Configure MongoDB

#### Option A: Local MongoDB Installation

**Windows:**
```powershell
# Using winget
winget install MongoDB.Server

# Or download from: https://www.mongodb.com/try/download/community
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

**macOS:**
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

#### Option B: MongoDB Atlas (Cloud)

1. Sign up at https://www.mongodb.com/cloud/atlas
2. Create a free cluster
3. Get connection string
4. Update `.env` file with your connection string

#### Verify MongoDB is Running

```bash
# Check if MongoDB is accessible
mongosh --eval "db.version()"
```

### Step 3: Install Ollama (for LLM Support)

#### Windows:
```powershell
winget install Ollama.Ollama
```

#### Linux:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### macOS:
```bash
brew install ollama
```

#### Pull Required Models:
```bash
# Start Ollama service (in a separate terminal)
ollama serve

# Pull models (in another terminal)
ollama pull phi3:mini      # Primary model (~2.3GB)
ollama pull qwen2.5:3b     # Fallback model (~1.9GB)
```

### Step 4: Install Poppler (for PDF Processing)

#### Windows:
```powershell
# Download from: https://github.com/oschwartz10612/poppler-windows/releases
# Extract and add bin/ directory to PATH
```

#### Linux (Ubuntu/Debian):
```bash
sudo apt-get install -y poppler-utils
```

#### macOS:
```bash
brew install poppler
```

### Step 5: Configure Environment Variables

Create or update `.env` file in the project root:

```env
# MongoDB Configuration
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=medical_bills

# OCR Configuration
OCR_CONFIDENCE_THRESHOLD=0.6

# Embedding Model (IMPORTANT: Use full Hugging Face identifier)
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DEVICE=cpu  # Change to 'cuda' for GPU

# LLM Configuration
PRIMARY_LLM=phi3:mini
SECONDARY_LLM=qwen2.5:3b
LLM_RUNTIME=ollama
LLM_BASE_URL=http://localhost:11434

# Similarity Thresholds
CATEGORY_SIMILARITY_THRESHOLD=0.70
ITEM_SIMILARITY_THRESHOLD=0.85

# Data Directories (optional - defaults are set in config.py)
TIEUP_DATA_DIR=backend/data/tieups
EMBEDDING_CACHE_PATH=backend/data/embedding_cache.json
```

---

## ▶️ Running the Backend

### Method 1: Process a Single Bill (Recommended for Testing)

```bash
# Make sure you're in the project root directory
python backend/main.py
```

**What this does:**
1. Processes `Apollo.pdf` (or specified PDF)
2. Extracts text using PaddleOCR
3. Structures data and stores in MongoDB
4. Runs LLM-based verification
5. Displays verification results with GREEN/RED/MISMATCH status

**Expected Output:**
```
✅ Successfully processed bill!
Upload ID: abc123...

================================================================================
VERIFICATION RESULTS
================================================================================
Hospital: Apollo Hospital
Matched Hospital: Apollo Hospital
Hospital Similarity: 95.23%

Summary:
  ✅ GREEN (Match): 45
  ❌ RED (Overcharged): 3
  ⚠️  MISMATCH (Not Found): 2

Financial Summary:
  Total Bill Amount: ₹25,430.00
  Total Allowed Amount: ₹24,200.00
  Total Extra Amount: ₹1,230.00
...
```

### Method 2: Run as API Server

```bash
# Navigate to backend directory
cd backend

# Start the FastAPI server
uvicorn app.verifier.api:app --reload --port 8001
```

**Access Points:**
- API Base: `http://localhost:8001`
- Interactive Docs: `http://localhost:8001/docs`
- Health Check: `http://localhost:8001/health`

**API Endpoints:**
- `POST /verify` - Verify a bill JSON directly
- `POST /verify/{upload_id}` - Verify a bill from MongoDB
- `POST /tieups/reload` - Reload tie-up rate sheets
- `GET /tieups` - List all loaded hospitals

### Method 3: Run as Python Module

```bash
# From project root
python -m backend.app.main
```

---

## 🧪 Testing the Setup

### Quick Verification Test

```bash
cd backend
python app/verifier/test_local_setup.py
```

**This test checks:**
- ✅ Embedding service working
- ✅ LLM router working
- ✅ Semantic matcher working
- ✅ Full integration test

### Run Unit Tests

```bash
cd backend
pytest tests/
```

---

## 📊 Understanding the Data Flow

```
PDF File
  ↓
[PDF to Images] (pdf_loader.py)
  ↓
[Image Preprocessing] (image_preprocessor.py)
  ↓
[PaddleOCR] (paddle_engine.py)
  ↓
[Text Extraction & Structuring] (bill_extractor.py)
  ├─ Hospital Name Extraction (NEW!)
  ├─ Patient Info Extraction
  ├─ Line Items Categorization
  └─ Payment Detection
  ↓
[MongoDB Storage] (mongo_client.py)
  ├─ "Hospital - " category added (NEW!)
  └─ Structured bill document
  ↓
[Verification Pipeline] (verifier.py) (NEW INTEGRATION!)
  ├─ Hospital Matching (semantic)
  ├─ Category Matching (semantic)
  ├─ Item Matching (semantic + LLM)
  └─ Price Checking
  ↓
[Verification Results] (DISPLAYED IN OUTPUT!)
  ├─ GREEN: Within allowed rates
  ├─ RED: Overcharged
  └─ MISMATCH: Not found in tie-up
```

---

## 🗂️ MongoDB Structure

After processing, bills are stored with this structure:

```json
{
  "upload_id": "abc123...",
  "source_pdf": "Apollo.pdf",
  "extraction_date": "2026-02-03T12:00:00",
  "header": {
    "hospital_name": "Apollo Hospital",  // NEW!
    "primary_bill_number": "APL2024001",
    "billing_date": "2024-01-15"
  },
  "patient": {
    "name": "Mr Mohak Nandy",
    "mrn": "MRN123456"
  },
  "items": {
    "Hospital - ": [  // NEW! Added at top
      {
        "item_name": "Apollo Hospital",
        "amount": 0,
        "quantity": 1
      }
    ],
    "medicines": [...],
    "diagnostics_tests": [...],
    "radiology": [...]
  },
  "grand_total": 25430.00,
  "summary": {
    "discounts": {...}
  }
}
```

---

## 🔧 Troubleshooting

### Issue: "MongoDB connection failed"

**Solution:**
```bash
# Check if MongoDB is running
mongosh --eval "db.version()"

# If not running, start it:
# Windows:
net start MongoDB

# Linux:
sudo systemctl start mongod

# macOS:
brew services start mongodb-community
```

### Issue: "PaddleOCR not found" or "Poppler not found"

**Solution:**
```bash
# Reinstall PaddleOCR
pip install paddleocr paddlepaddle

# Install Poppler (see Step 4 above)
```

### Issue: "Ollama connection refused"

**Solution:**
```bash
# Start Ollama service
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags
```

### Issue: "No hospital name extracted"

**Possible causes:**
- Hospital name not in standard format
- OCR quality issues
- Hospital name pattern not recognized

**Solution:**
- Check OCR output in MongoDB (`raw_ocr_text` field)
- Verify hospital name appears in first few lines
- May need to add custom patterns to `HOSPITAL_FALLBACK_PATTERNS`

### Issue: "Verification results not showing"

**Solution:**
1. Check MongoDB connection
2. Verify bill was stored successfully
3. Check Ollama is running
4. Verify tie-up rate sheets exist in `backend/data/tieups/`

---

## 📁 Important File Locations

```
backend/
├── main.py                    # Entry point (run this!)
├── app/
│   ├── main.py                # Bill processing pipeline
│   ├── extraction/
│   │   └── bill_extractor.py  # Hospital name extraction (MODIFIED)
│   ├── verifier/
│   │   ├── verifier.py        # Verification logic
│   │   └── api.py             # API + sync wrapper (MODIFIED)
│   ├── ocr/
│   │   └── paddle_engine.py   # OCR engine
│   └── db/
│       └── mongo_client.py    # MongoDB interface
├── data/
│   └── tieups/                # Hospital tie-up rate sheets
│       ├── apollo_hospital.json
│       ├── fortis_hospital.json
│       └── ...
└── requirements.txt           # Python dependencies
```

---

## 🎯 What Was Fixed

### 1. ✅ Hospital Category Added
- Hospital name now extracted from OCR
- "Hospital - " category added to MongoDB bills
- Placed at the top of categories list
- Used by verifier for hospital matching

### 2. ✅ LLM Comparison Results Now Visible
- Verifier integrated into `main.py`
- Results displayed in console output
- Shows GREEN/RED/MISMATCH status
- Displays financial summaries
- Category-wise breakdown included

### 3. ✅ Complete Run Guide Created
- Step-by-step setup instructions
- All prerequisites documented
- Multiple run methods explained
- Troubleshooting section added

---

## 🚦 Quick Start Checklist

- [ ] Python 3.8+ installed
- [ ] MongoDB installed and running
- [ ] Ollama installed and running
- [ ] Models pulled (phi3:mini, qwen2.5:3b)
- [ ] Poppler installed
- [ ] Python dependencies installed (`pip install -r backend/requirements.txt`)
- [ ] `.env` file configured
- [ ] Test PDF available (e.g., Apollo.pdf)
- [ ] Run `python backend/main.py`
- [ ] Verify output shows extraction AND verification results

---

## 📞 Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs in console output
3. Verify all prerequisites are met
4. Check MongoDB and Ollama are running

---

## 🎓 Next Steps

1. **Add More Tie-Up Hospitals**: Place JSON files in `backend/data/tieups/`
2. **Process Multiple Bills**: Modify `main.py` to loop through PDFs
3. **Use API Mode**: Run as server for frontend integration
4. **Tune Thresholds**: Adjust similarity thresholds in `.env`
5. **Monitor Performance**: Check LLM usage statistics

---

**Last Updated**: 2026-02-03
**Version**: 1.0.0

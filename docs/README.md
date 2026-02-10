# AI-Powered Medical Bill Verification for IOCL Employees

AI-powered system for verifying hospital medical bills against tie-up rate sheets using semantic matching and local LLM verification.

## Project Structure

```
project-root/
├── backend/              # Backend application (Python)
│   ├── app/              # Main application code
│   ├── data/             # Data files (tie-ups, cache)
│   ├── tests/            # Test files
│   ├── main.py           # Entry point
│   └── requirements.txt  # Python dependencies
│
├── frontend/             # Frontend (reserved for future development)
│
├── docs/                 # Documentation
├── .env                  # Environment variables
└── README.md             # This file
```

## Quick Start

### Prerequisites

- Python 3.8+
- MongoDB (running locally or remote)
- PaddleOCR dependencies
- Poppler (for PDF processing)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd AI-Powered-Medical-Bill-Verification-for-IOCL-Employees
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Configure environment variables**
   
   Create a `.env` file in the project root:
   ```env
   MONGO_URI=mongodb://localhost:27017
   MONGO_DB_NAME=medical_bills
   OCR_CONFIDENCE_THRESHOLD=0.6
   ```

### Running the Backend

**Primary method:**
```bash
python backend/main.py
```

**Alternative (as module):**
```bash
python -m backend.app.main
```

**Run the API server:**
```bash
cd backend
uvicorn app.verifier.api:app --reload --port 8001
```

Access the API at: `http://localhost:8001`  
API documentation: `http://localhost:8001/docs`

### Running Tests

```bash
cd backend
python app/verifier/test_local_setup.py
```

Or using pytest:
```bash
cd backend
pytest tests/
```

## Features

### Core Capabilities

- **PDF Ingestion**: Convert medical bill PDFs to images
- **OCR Processing**: Extract text using PaddleOCR
- **Structured Extraction**: Parse bills into structured JSON
- **Semantic Matching**: Match hospitals, categories, and items using embeddings
- **Price Verification**: Compare billed amounts against tie-up rates
- **MongoDB Storage**: Persist processed bills
- **REST API**: FastAPI-based verification endpoints

### Verification Pipeline

1. **Hospital Matching**: Semantic matching to identify the hospital
2. **Category Matching**: Match bill categories (e.g., "Radiology", "Medicines")
3. **Item Matching**: Match individual items/services
4. **Price Checking**: Compare against tie-up rates
5. **Status Assignment**: GREEN (within limits), RED (overcharged), MISMATCH (not found)

## Architecture

### Backend Structure

The backend is completely self-contained in the `backend/` directory with:

- **Absolute imports**: All imports use `from app.module import ...`
- **Path resolution**: Uses pathlib-based resolution from `app/config.py`
- **Environment handling**: Loads `.env` from backend or project root
- **Frontend-ready**: Designed to work alongside a future frontend

See `backend/README.md` for detailed backend documentation.

### Key Technologies

- **Python 3.8+**: Core language
- **FastAPI**: REST API framework
- **MongoDB**: Document storage
- **PaddleOCR**: OCR engine
- **Sentence Transformers**: Semantic embeddings
- **FAISS**: Vector similarity search
- **Ollama**: Local LLM for ambiguous matches

## Configuration

All configuration is managed through:

1. **Environment variables** (`.env` file)
2. **Config module** (`backend/app/config.py`)

### Key Configuration Paths

Defined in `backend/app/config.py`:

- `BASE_DIR`: Backend root directory
- `DATA_DIR`: Data files location
- `TIEUP_DIR`: Hospital tie-up rate sheets
- `UPLOADS_DIR`: Temporary uploaded files
- `PROCESSED_DIR`: Preprocessed images

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | `medical_bills` | Database name |
| `TIEUP_DATA_DIR` | `backend/data/tieups` | Tie-up rate sheets directory |
| `EMBEDDING_CACHE_PATH` | `backend/data/embedding_cache.json` | Embedding cache file |
| `OCR_CONFIDENCE_THRESHOLD` | `0.6` | OCR confidence threshold |

## Development

### Adding Tie-Up Rate Sheets

1. Create a JSON file in `backend/data/tieups/`
2. Follow the schema in existing files
3. Reload via API: `POST /tieups/reload`

### Running in Development Mode

```bash
cd backend
uvicorn app.verifier.api:app --reload --port 8001
```

The `--reload` flag enables auto-reload on code changes.

## API Endpoints

### Health Check
```
GET /health
```

### Verify Bill (Direct)
```
POST /verify
Body: { "bill": { ... } }
```

### Verify Bill (from MongoDB)
```
POST /verify/{upload_id}
```

### Reload Tie-Ups
```
POST /tieups/reload
```

### List Hospitals
```
GET /tieups
```

## Testing

The project includes comprehensive tests:

- **Unit tests**: Individual component testing
- **Integration tests**: Full pipeline testing
- **Setup verification**: `backend/app/verifier/test_local_setup.py`

## Future Development

### Frontend

A frontend application will be added to the `frontend/` directory, which will:

- Provide a web UI for bill upload and verification
- Display verification results visually
- Communicate with the backend via REST API
- Run independently from the backend

### Planned Features

- Real-time verification dashboard
- Batch processing
- Advanced reporting
- User authentication
- Audit trails

## License

See `LICENSE` file for details.

## Documentation

Additional documentation available in:

- `backend/README.md` - Backend-specific documentation
- `frontend/README.md` - Frontend integration notes
- `docs/` - Additional technical documentation
- API docs at `/docs` when running the server

## Support

For issues, questions, or contributions, please refer to the project repository.

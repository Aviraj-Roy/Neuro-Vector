import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory resolution (backend/app -> backend)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TIEUP_DIR = DATA_DIR / "tieups"
TIEUPS_DIR = TIEUP_DIR  # Alias for consistency
UPLOADS_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = UPLOADS_DIR / "processed"

# Absolute path helpers - ALWAYS use these when passing paths to external libraries
# (cv2, pdf2image, etc.) to avoid CWD-dependent failures
def get_base_dir() -> str:
    """Return absolute path to backend directory.
    
    Use this instead of BASE_DIR when passing to external libraries.
    """
    return str(BASE_DIR.resolve())


def get_uploads_dir() -> str:
    """Return absolute path to uploads directory.
    
    Use this instead of UPLOADS_DIR when passing to external libraries.
    Ensures path works regardless of current working directory.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return str(UPLOADS_DIR.resolve())


def get_processed_dir() -> str:
    """Return absolute path to processed images directory.
    
    Use this instead of PROCESSED_DIR when passing to external libraries.
    Ensures path works regardless of current working directory.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    return str(PROCESSED_DIR.resolve())


def get_data_dir() -> str:
    """Return absolute path to data directory."""
    return str(DATA_DIR.resolve())


def get_tieup_dir() -> str:
    """Return absolute path to tieup data directory."""
    return str(TIEUP_DIR.resolve())


# Load environment variables from .env (check both backend/ and project root)
env_path = BASE_DIR / ".env"
if not env_path.exists():
    env_path = BASE_DIR.parent / ".env"
load_dotenv(dotenv_path=env_path if env_path.exists() else None)

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "medical_bills")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "bills")

# Soft-delete retention configuration
BILL_RETENTION_DAYS = int(os.getenv("BILL_RETENTION_DAYS", "30"))
BILL_RETENTION_CLEANUP_INTERVAL_SECONDS = int(
    os.getenv("BILL_RETENTION_CLEANUP_INTERVAL_SECONDS", "3600")
)

# Queue processing configuration
QUEUE_STALE_PROCESSING_SECONDS = int(os.getenv("QUEUE_STALE_PROCESSING_SECONDS", "1800"))
QUEUE_RECONCILE_INTERVAL_SECONDS = int(os.getenv("QUEUE_RECONCILE_INTERVAL_SECONDS", "60"))

# OCR configuration
OCR_CONFIDENCE_THRESHOLD = float(
    os.getenv("OCR_CONFIDENCE_THRESHOLD", 0.6)
)

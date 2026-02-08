import os
from pathlib import Path
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Base directory resolution (backend/app -> backend)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TIEUP_DIR = DATA_DIR / "tieups"
UPLOADS_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = UPLOADS_DIR / "processed"

# Railway environment detection
IS_RAILWAY = os.getenv("RAILWAY_ENVIRONMENT") is not None
IS_PRODUCTION = os.getenv("ENV", "development").lower() == "production"

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
    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create uploads directory: {e}")
    return str(UPLOADS_DIR.resolve())


def get_processed_dir() -> str:
    """Return absolute path to processed images directory.
    
    Use this instead of PROCESSED_DIR when passing to external libraries.
    Ensures path works regardless of current working directory.
    """
    try:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create processed directory: {e}")
    return str(PROCESSED_DIR.resolve())


def get_data_dir() -> str:
    """Return absolute path to data directory."""
    return str(DATA_DIR.resolve())


def get_tieup_dir() -> str:
    """Return absolute path to tieup data directory.
    
    Railway Note: Ensure backend/data/tieups/ is included in deployment.
    """
    tieup_path = TIEUP_DIR.resolve()
    
    # Validate on startup (Railway-specific)
    if IS_RAILWAY and not tieup_path.exists():
        logger.error(f"❌ Tie-up directory not found: {tieup_path}")
        logger.error("   Ensure backend/data/tieups/ is included in Railway deployment")
    
    return str(tieup_path)


# Load environment variables from .env (check both backend/ and project root)
env_path = BASE_DIR / ".env"
if not env_path.exists():
    env_path = BASE_DIR.parent / ".env"
load_dotenv(dotenv_path=env_path if env_path.exists() else None)

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "medical_bills")

# OCR configuration
OCR_CONFIDENCE_THRESHOLD = float(
    os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.6")
)

# LLM configuration (Railway: default to disabled)
ENABLE_LLM_MATCHING = os.getenv("ENABLE_LLM_MATCHING", "false").lower() in ("true", "1", "yes")

# Log configuration on import (Railway visibility)
if IS_RAILWAY:
    logger.info(f"Railway Environment: {os.getenv('RAILWAY_ENVIRONMENT')}")
    logger.info(f"Base Directory: {get_base_dir()}")
    logger.info(f"Tie-up Directory: {get_tieup_dir()}")
    logger.info(f"LLM Matching: {'ENABLED' if ENABLE_LLM_MATCHING else 'DISABLED'}")

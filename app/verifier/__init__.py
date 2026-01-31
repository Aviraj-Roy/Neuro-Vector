"""
Hospital Bill Verifier Module.
Provides semantic matching and price verification for medical bills.

Features:
- Persistent embedding cache to minimize API calls
- Batched embedding requests with retry logic
- Graceful degradation when API unavailable
"""

from app.verifier.models import (
    BillInput,
    BillCategory,
    BillItem,
    TieUpRateSheet,
    TieUpCategory,
    TieUpItem,
    ItemType,
    VerificationStatus,
    VerificationResponse,
    CategoryVerificationResult,
    ItemVerificationResult,
)
from app.verifier.embedding_service import (
    EmbeddingService, 
    EmbeddingServiceUnavailable,
    EmbeddingServiceError,
    get_embedding_service,
    reset_embedding_service,
)
from app.verifier.embedding_cache import EmbeddingCache, get_embedding_cache
from app.verifier.matcher import SemanticMatcher, get_matcher
from app.verifier.price_checker import check_price, calculate_allowed_amount
from app.verifier.verifier import BillVerifier, get_verifier, load_all_tieups

__all__ = [
    # Models
    "BillInput",
    "BillCategory",
    "BillItem",
    "TieUpRateSheet",
    "TieUpCategory",
    "TieUpItem",
    "ItemType",
    "VerificationStatus",
    "VerificationResponse",
    "CategoryVerificationResult",
    "ItemVerificationResult",
    # Exceptions
    "EmbeddingServiceUnavailable",
    "EmbeddingServiceError",
    # Services
    "EmbeddingService",
    "get_embedding_service",
    "reset_embedding_service",
    "EmbeddingCache",
    "get_embedding_cache",
    "SemanticMatcher",
    "get_matcher",
    "check_price",
    "calculate_allowed_amount",
    "BillVerifier",
    "get_verifier",
    "load_all_tieups",
]

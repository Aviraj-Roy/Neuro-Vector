"""
Embedding Service for the Hospital Bill Verifier - LOCAL VERSION.

Features:
- Uses sentence-transformers with bge-base-en-v1.5 (fully local)
- Persistent disk cache (JSON) to avoid redundant computations
- Batched embedding generation for efficiency
- No external API calls
- Model loaded once at startup

Usage:
    service = EmbeddingService()
    embeddings = service.get_embeddings(["text1", "text2"])

Environment Variables:
    EMBEDDING_MODEL: Model name (default: bge-base-en-v1.5)
    EMBEDDING_CACHE_PATH: Path to cache file (default: data/embedding_cache.json)
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import List, Optional, Tuple

import numpy as np

# Import sentence-transformers for local embeddings
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

from app.verifier.embedding_cache import EmbeddingCache, get_embedding_cache

logger = logging.getLogger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================

class EmbeddingServiceUnavailable(Exception):
    """Raised when embedding service is temporarily unavailable."""
    pass


class EmbeddingServiceError(Exception):
    """Raised when embedding service encounters an error."""
    pass


# =============================================================================
# Embedding Service (Local)
# =============================================================================

class EmbeddingService:
    """
    Production-ready local embedding service with caching.
    
    Features:
    - Fully local using sentence-transformers
    - Persistent disk cache to minimize computation
    - Automatic batching for efficiency
    - Model loaded once at startup
    - Thread-safe operations
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        cache: Optional[EmbeddingCache] = None,
        device: Optional[str] = None,
    ):
        """
        Initialize the local embedding service.
        
        Args:
            model_name: Model name (defaults to EMBEDDING_MODEL env var)
            cache: EmbeddingCache instance (uses global singleton if None)
            device: Device to run model on ('cpu', 'cuda', or None for auto)
        """
        # Configuration from env vars with defaults
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "bge-base-en-v1.5")
        self.device = device or os.getenv("EMBEDDING_DEVICE", "cpu")
        
        # Use persistent cache (global singleton by default)
        self._cache = cache or get_embedding_cache()
        
        # Initialize model (lazy loading)
        self._model: Optional[SentenceTransformer] = None
        self._model_initialized = False
        self._dimension: Optional[int] = None
        
        # Track service availability
        self._available = True
        self._last_error: Optional[str] = None
        
        # Register cache save on exit
        atexit.register(self._save_cache_on_exit)
        
        logger.info(
            f"EmbeddingService initialized: model={self.model_name}, device={self.device}"
        )
    
    def _get_model(self) -> Optional[SentenceTransformer]:
        """Lazy-initialize and return the sentence-transformers model."""
        if not self._model_initialized:
            self._model_initialized = True
            
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.error("sentence-transformers package not installed. Run: pip install sentence-transformers")
                self._available = False
                self._last_error = "sentence-transformers package not installed"
                return None
            
            try:
                logger.info(f"Loading model '{self.model_name}' on device '{self.device}'...")
                self._model = SentenceTransformer(self.model_name, device=self.device)
                
                # Get embedding dimension
                self._dimension = self._model.get_sentence_embedding_dimension()
                
                logger.info(
                    f"Model loaded successfully: dimension={self._dimension}"
                )
                self._available = True
                self._last_error = None
                
            except Exception as e:
                logger.error(f"Failed to load model '{self.model_name}': {e}")
                self._available = False
                self._last_error = str(e)
                return None
        
        return self._model
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            # Try to initialize model to get dimension
            model = self._get_model()
            if model is None:
                # Default dimension for bge-base-en-v1.5
                return 768
        return self._dimension or 768
    
    def _save_cache_on_exit(self):
        """Save cache to disk when service is destroyed."""
        try:
            if self._cache and self._cache.is_dirty:
                self._cache.save()
        except Exception as e:
            logger.warning(f"Failed to save cache on exit: {e}")
    
    def _generate_embeddings(self, texts: List[str]) -> Tuple[Optional[np.ndarray], Optional[str]]:
        """
        Generate embeddings using local model.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            Tuple of (embeddings array, error message or None)
        """
        model = self._get_model()
        if model is None:
            return None, self._last_error or "Embedding model unavailable"
        
        try:
            # Generate embeddings with normalization
            embeddings = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            
            # Ensure float32 dtype
            embeddings = embeddings.astype(np.float32)
            
            return embeddings, None
            
        except Exception as e:
            error_msg = f"Embedding generation failed: {e}"
            logger.error(error_msg)
            self._last_error = error_msg
            return None, error_msg
    
    def get_embedding(self, text: str) -> np.ndarray:
        """
        Get embedding for a single text string.
        
        Args:
            text: Input text to embed
            
        Returns:
            numpy array of shape (dimension,)
            
        Raises:
            EmbeddingServiceUnavailable: If service is unavailable
        """
        # Check persistent cache first
        cached = self._cache.get(text)
        if cached is not None:
            logger.debug(f"Cache hit for text: {text[:50]}...")
            return cached
        
        # Generate embedding
        embeddings, error = self._generate_embeddings([text])
        
        if error or embeddings is None:
            raise EmbeddingServiceUnavailable(
                f"Embedding service unavailable: {error}"
            )
        
        embedding = embeddings[0]
        
        # Store in persistent cache
        self._cache.set(text, embedding)
        
        return embedding
    
    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Get embeddings for multiple text strings with caching.
        
        - Checks cache first for all texts
        - Only generates embeddings for uncached texts
        - Saves results to persistent cache
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            numpy array of shape (len(texts), dimension)
            
        Raises:
            EmbeddingServiceUnavailable: If service is unavailable for uncached texts
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)
        
        # Separate cached vs uncached texts
        results: List[Tuple[int, np.ndarray]] = []  # (original_index, embedding)
        texts_to_fetch: List[Tuple[int, str]] = []  # (original_index, text)
        
        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                results.append((i, cached))
            else:
                texts_to_fetch.append((i, text))
        
        cache_hits = len(results)
        cache_misses = len(texts_to_fetch)
        
        if cache_hits > 0:
            logger.debug(f"Cache: {cache_hits} hits, {cache_misses} misses")
        
        # Generate uncached embeddings
        if texts_to_fetch:
            batch_texts = [text for _, text in texts_to_fetch]
            batch_indices = [idx for idx, _ in texts_to_fetch]
            
            logger.info(f"Generating {len(batch_texts)} embeddings locally...")
            
            # Generate embeddings
            embeddings, error = self._generate_embeddings(batch_texts)
            
            if error or embeddings is None:
                raise EmbeddingServiceUnavailable(
                    f"Embedding service unavailable: {error}"
                )
            
            # Store results and cache
            new_cache_items = {}
            for j, embedding in enumerate(embeddings):
                original_idx = batch_indices[j]
                text = batch_texts[j]
                results.append((original_idx, embedding))
                new_cache_items[text] = embedding
            
            # Batch save to cache
            if new_cache_items:
                self._cache.set_batch(new_cache_items)
            
            logger.debug(f"Generated {len(embeddings)} embeddings")
        
        # Sort by original index and stack into array
        results.sort(key=lambda x: x[0])
        
        # Auto-save cache periodically
        if cache_misses > 0 and self._cache.is_dirty:
            self._cache.save()
        
        return np.stack([emb for _, emb in results], axis=0)
    
    def get_embeddings_safe(
        self, 
        texts: List[str]
    ) -> Tuple[Optional[np.ndarray], Optional[str]]:
        """
        Get embeddings with graceful degradation (never raises).
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            Tuple of (embeddings array or None, error message or None)
        """
        try:
            embeddings = self.get_embeddings(texts)
            return embeddings, None
        except EmbeddingServiceUnavailable as e:
            return None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error in get_embeddings_safe: {e}")
            return None, f"Embedding service error: {e}"
    
    def clear_cache(self):
        """Clear the persistent embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")
    
    def save_cache(self):
        """Manually save cache to disk."""
        self._cache.save()
    
    @property
    def cache_size(self) -> int:
        """Return the number of cached embeddings."""
        return self._cache.size
    
    @property
    def is_available(self) -> bool:
        """Check if embedding service is available."""
        return self._available
    
    @property
    def last_error(self) -> Optional[str]:
        """Get the last error message."""
        return self._last_error


# =============================================================================
# Module-level singleton for convenience
# =============================================================================

_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def reset_embedding_service():
    """Reset the global embedding service instance (for testing)."""
    global _embedding_service
    if _embedding_service is not None:
        _embedding_service.save_cache()
    _embedding_service = None

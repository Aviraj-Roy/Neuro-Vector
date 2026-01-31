"""
Embedding Service for the Hospital Bill Verifier.

Features:
- Persistent disk cache (JSON) to avoid redundant API calls
- Batched requests (max 20 texts per API call)
- Exponential backoff retry for rate limits (429 errors)
- Graceful degradation when API unavailable
- Configurable provider via environment variables

Usage:
    service = EmbeddingService()
    embeddings = service.get_embeddings(["text1", "text2"])

Environment Variables:
    EMBEDDING_PROVIDER: "openai" (default) or other compatible provider
    EMBEDDING_MODEL: Model name (default: text-embedding-3-small)
    EMBEDDING_DIMENSION: Vector dimension (default: 1536)
    EMBEDDING_API_BASE: API endpoint URL
    OPENAI_API_KEY: API key
    EMBEDDING_CACHE_PATH: Path to cache file (default: data/embedding_cache.json)
    EMBEDDING_MAX_BATCH_SIZE: Max texts per API call (default: 20)
    EMBEDDING_MAX_RETRIES: Max retry attempts (default: 3)
"""

from __future__ import annotations

import atexit
import logging
import os
import time
from typing import List, Optional, Tuple

import numpy as np

# Import OpenAI with error handling for rate limits
try:
    from openai import OpenAI, RateLimitError, APIError, APIConnectionError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None
    RateLimitError = Exception
    APIError = Exception
    APIConnectionError = Exception

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
# Configuration Constants
# =============================================================================

# Max texts per API batch (OpenAI limit is higher, but 20 is safe)
DEFAULT_MAX_BATCH_SIZE = 20

# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 1.0  # seconds
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAX_BACKOFF = 60.0  # seconds


# =============================================================================
# Embedding Service
# =============================================================================

class EmbeddingService:
    """
    Production-ready embedding service with caching, batching, and retry logic.
    
    Features:
    - Persistent disk cache to minimize API calls
    - Automatic batching (configurable max batch size)
    - Exponential backoff retry for rate limit errors
    - Graceful degradation (returns error instead of crashing)
    - Thread-safe operations
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
        cache: Optional[EmbeddingCache] = None,
        max_batch_size: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Initialize the embedding service.
        
        Args:
            api_key: API key (defaults to OPENAI_API_KEY env var)
            api_base: API base URL (defaults to EMBEDDING_API_BASE env var)
            model: Embedding model name (defaults to EMBEDDING_MODEL env var)
            dimension: Embedding dimension (defaults to EMBEDDING_DIMENSION env var)
            cache: EmbeddingCache instance (uses global singleton if None)
            max_batch_size: Max texts per API call (defaults to EMBEDDING_MAX_BATCH_SIZE)
            max_retries: Max retry attempts (defaults to EMBEDDING_MAX_RETRIES)
        """
        # Configuration from env vars with defaults
        self.provider = os.getenv("EMBEDDING_PROVIDER", "openai")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.api_base = api_base or os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1")
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.dimension = dimension or int(os.getenv("EMBEDDING_DIMENSION", "1536"))
        
        # Batching and retry config
        self.max_batch_size = max_batch_size or int(
            os.getenv("EMBEDDING_MAX_BATCH_SIZE", str(DEFAULT_MAX_BATCH_SIZE))
        )
        self.max_retries = max_retries or int(
            os.getenv("EMBEDDING_MAX_RETRIES", str(DEFAULT_MAX_RETRIES))
        )
        
        # Use persistent cache (global singleton by default)
        self._cache = cache or get_embedding_cache()
        
        # Initialize OpenAI client (lazy, only if available)
        self._client: Optional[OpenAI] = None
        self._client_initialized = False
        
        # Track service availability
        self._available = True
        self._last_error: Optional[str] = None
        
        # Register cache save on exit
        atexit.register(self._save_cache_on_exit)
        
        logger.info(
            f"EmbeddingService initialized: provider={self.provider}, "
            f"model={self.model}, dimension={self.dimension}, "
            f"max_batch={self.max_batch_size}, max_retries={self.max_retries}"
        )
    
    def _get_client(self) -> Optional[OpenAI]:
        """Lazy-initialize and return the OpenAI client."""
        if not self._client_initialized:
            self._client_initialized = True
            
            if not OPENAI_AVAILABLE:
                logger.error("OpenAI package not installed. Run: pip install openai")
                self._available = False
                self._last_error = "OpenAI package not installed"
                return None
            
            if not self.api_key:
                logger.error("OPENAI_API_KEY not set")
                self._available = False
                self._last_error = "API key not configured"
                return None
            
            try:
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.api_base,
                )
                logger.info(f"OpenAI client initialized for {self.api_base}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self._available = False
                self._last_error = str(e)
                return None
        
        return self._client
    
    def _save_cache_on_exit(self):
        """Save cache to disk when service is destroyed."""
        try:
            if self._cache and self._cache.is_dirty:
                self._cache.save()
        except Exception as e:
            logger.warning(f"Failed to save cache on exit: {e}")
    
    def _call_api_with_retry(
        self, 
        texts: List[str]
    ) -> Tuple[List[np.ndarray], Optional[str]]:
        """
        Call embedding API with exponential backoff retry.
        
        Args:
            texts: List of texts to embed (should be <= max_batch_size)
            
        Returns:
            Tuple of (embeddings list, error message or None)
        """
        client = self._get_client()
        if client is None:
            return [], self._last_error or "Embedding service unavailable"
        
        backoff = DEFAULT_INITIAL_BACKOFF
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Make API call
                response = client.embeddings.create(
                    input=texts,
                    model=self.model,
                )
                
                # Extract embeddings
                embeddings = [
                    np.array(item.embedding, dtype=np.float32)
                    for item in response.data
                ]
                
                # Success - reset availability flag
                self._available = True
                self._last_error = None
                
                return embeddings, None
                
            except RateLimitError as e:
                # Rate limit (429) - retry with backoff
                last_error = f"Rate limit exceeded: {e}"
                logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{self.max_retries}), "
                    f"retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
                backoff = min(backoff * DEFAULT_BACKOFF_MULTIPLIER, DEFAULT_MAX_BACKOFF)
                
            except APIConnectionError as e:
                # Connection error - retry
                last_error = f"API connection error: {e}"
                logger.warning(
                    f"Connection error (attempt {attempt + 1}/{self.max_retries}), "
                    f"retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
                backoff = min(backoff * DEFAULT_BACKOFF_MULTIPLIER, DEFAULT_MAX_BACKOFF)
                
            except APIError as e:
                # API error - check if retryable
                last_error = f"API error: {e}"
                if hasattr(e, 'status_code') and e.status_code == 429:
                    # Quota exceeded - this is the insufficient_quota error
                    logger.error(
                        f"API quota exceeded (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * DEFAULT_BACKOFF_MULTIPLIER, DEFAULT_MAX_BACKOFF)
                else:
                    # Non-retryable error
                    logger.error(f"API error (non-retryable): {e}")
                    break
                    
            except Exception as e:
                # Unexpected error - don't retry
                last_error = f"Unexpected error: {e}"
                logger.error(f"Unexpected embedding error: {type(e).__name__}: {e}")
                break
        
        # All retries exhausted
        self._available = False
        self._last_error = last_error
        logger.error(f"Embedding API failed after {self.max_retries} attempts: {last_error}")
        
        return [], last_error
    
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
        
        # Call API
        embeddings, error = self._call_api_with_retry([text])
        
        if error or not embeddings:
            raise EmbeddingServiceUnavailable(
                f"Embedding service temporarily unavailable: {error}"
            )
        
        embedding = embeddings[0]
        
        # Store in persistent cache
        self._cache.set(text, embedding)
        
        return embedding
    
    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Get embeddings for multiple text strings with batching.
        
        - Checks cache first for all texts
        - Only fetches uncached texts from API
        - Batches API calls (max_batch_size texts per call)
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
        
        # Fetch uncached embeddings from API in batches
        if texts_to_fetch:
            # Split into batches
            batches = []
            for i in range(0, len(texts_to_fetch), self.max_batch_size):
                batches.append(texts_to_fetch[i:i + self.max_batch_size])
            
            logger.info(
                f"Fetching {len(texts_to_fetch)} embeddings in {len(batches)} batch(es)..."
            )
            
            all_errors = []
            
            for batch_idx, batch in enumerate(batches):
                batch_texts = [text for _, text in batch]
                batch_indices = [idx for idx, _ in batch]
                
                # Call API with retry
                embeddings, error = self._call_api_with_retry(batch_texts)
                
                if error:
                    all_errors.append(error)
                    logger.warning(
                        f"Batch {batch_idx + 1}/{len(batches)} failed: {error}"
                    )
                    continue
                
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
                
                logger.debug(
                    f"Batch {batch_idx + 1}/{len(batches)}: {len(embeddings)} embeddings fetched"
                )
            
            # Check if we got all embeddings
            if len(results) < len(texts):
                missing_count = len(texts) - len(results)
                error_msg = "; ".join(all_errors) if all_errors else "Unknown error"
                raise EmbeddingServiceUnavailable(
                    f"Embedding service temporarily unavailable. "
                    f"Failed to fetch {missing_count} embeddings: {error_msg}"
                )
        
        # Sort by original index and stack into array
        results.sort(key=lambda x: x[0])
        
        # Auto-save cache periodically (every 100 new embeddings)
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

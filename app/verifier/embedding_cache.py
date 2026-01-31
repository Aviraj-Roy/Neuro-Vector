"""
Persistent Embedding Cache for the Hospital Bill Verifier.

Stores embeddings on disk (JSON format) to avoid redundant API calls.
Key = SHA256 hash of normalized text
Value = embedding vector as list of floats

Usage:
    cache = EmbeddingCache()
    cache.get("some text")  # Returns embedding or None
    cache.set("some text", embedding_array)
    cache.save()  # Persist to disk
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Normalize text for consistent cache keys."""
    return text.strip().lower()


def _hash_text(text: str) -> str:
    """Generate SHA256 hash of normalized text for cache key."""
    normalized = _normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """
    Persistent embedding cache using JSON file storage.
    
    Thread-safe with automatic dirty tracking for efficient saves.
    Cache file location configurable via EMBEDDING_CACHE_PATH env var.
    """
    
    def __init__(self, cache_path: Optional[str] = None):
        """
        Initialize the embedding cache.
        
        Args:
            cache_path: Path to cache JSON file. Defaults to EMBEDDING_CACHE_PATH 
                       env var or 'data/embedding_cache.json'
        """
        self.cache_path = Path(
            cache_path or 
            os.getenv("EMBEDDING_CACHE_PATH", "data/embedding_cache.json")
        )
        
        # In-memory cache: hash -> embedding list
        self._cache: Dict[str, List[float]] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Track if cache has unsaved changes
        self._dirty = False
        
        # Load existing cache from disk
        self._load()
        
        logger.info(f"EmbeddingCache initialized: {len(self._cache)} entries from {self.cache_path}")
    
    def _load(self):
        """Load cache from disk if exists."""
        try:
            if self.cache_path.exists():
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Validate structure
                    if isinstance(data, dict):
                        self._cache = data
                        logger.info(f"Loaded {len(self._cache)} cached embeddings")
                    else:
                        logger.warning("Invalid cache file format, starting fresh")
                        self._cache = {}
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted cache file, starting fresh: {e}")
            self._cache = {}
        except Exception as e:
            logger.warning(f"Failed to load cache, starting fresh: {e}")
            self._cache = {}
    
    def save(self) -> bool:
        """
        Persist cache to disk.
        
        Returns:
            True if saved successfully, False otherwise
        """
        with self._lock:
            if not self._dirty:
                logger.debug("Cache not dirty, skipping save")
                return True
            
            try:
                # Ensure directory exists
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write atomically using temp file
                temp_path = self.cache_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f)
                
                # Rename temp to final (atomic on most systems)
                temp_path.replace(self.cache_path)
                
                self._dirty = False
                logger.info(f"Saved {len(self._cache)} embeddings to {self.cache_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to save cache: {e}")
                return False
    
    def get(self, text: str) -> Optional[np.ndarray]:
        """
        Get cached embedding for text.
        
        Args:
            text: Input text
            
        Returns:
            Embedding as numpy array, or None if not cached
        """
        text_hash = _hash_text(text)
        
        with self._lock:
            if text_hash in self._cache:
                embedding_list = self._cache[text_hash]
                return np.array(embedding_list, dtype=np.float32)
        
        return None
    
    def get_batch(self, texts: List[str]) -> Dict[str, Optional[np.ndarray]]:
        """
        Get cached embeddings for multiple texts.
        
        Args:
            texts: List of input texts
            
        Returns:
            Dict mapping text -> embedding (or None if not cached)
        """
        results = {}
        
        with self._lock:
            for text in texts:
                text_hash = _hash_text(text)
                if text_hash in self._cache:
                    results[text] = np.array(self._cache[text_hash], dtype=np.float32)
                else:
                    results[text] = None
        
        return results
    
    def set(self, text: str, embedding: np.ndarray):
        """
        Store embedding in cache.
        
        Args:
            text: Input text
            embedding: Embedding vector as numpy array
        """
        text_hash = _hash_text(text)
        
        with self._lock:
            # Convert numpy array to list for JSON serialization
            self._cache[text_hash] = embedding.tolist()
            self._dirty = True
    
    def set_batch(self, items: Dict[str, np.ndarray]):
        """
        Store multiple embeddings in cache.
        
        Args:
            items: Dict mapping text -> embedding
        """
        with self._lock:
            for text, embedding in items.items():
                text_hash = _hash_text(text)
                self._cache[text_hash] = embedding.tolist()
            self._dirty = True
    
    def contains(self, text: str) -> bool:
        """Check if text is in cache."""
        text_hash = _hash_text(text)
        with self._lock:
            return text_hash in self._cache
    
    def clear(self):
        """Clear all cached embeddings."""
        with self._lock:
            self._cache.clear()
            self._dirty = True
        logger.info("Embedding cache cleared")
    
    @property
    def size(self) -> int:
        """Return number of cached embeddings."""
        with self._lock:
            return len(self._cache)
    
    @property
    def is_dirty(self) -> bool:
        """Check if cache has unsaved changes."""
        return self._dirty
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - auto-save."""
        self.save()
        return False


# =============================================================================
# Module-level singleton
# =============================================================================

_cache_instance: Optional[EmbeddingCache] = None
_cache_lock = threading.Lock()


def get_embedding_cache() -> EmbeddingCache:
    """Get or create the global embedding cache instance."""
    global _cache_instance
    
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                _cache_instance = EmbeddingCache()
    
    return _cache_instance

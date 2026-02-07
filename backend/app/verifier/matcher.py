"""
Semantic Matcher for the Hospital Bill Verifier.
Uses FAISS for efficient similarity search on embeddings.

Matching logic:
- Hospital: Pick highest similarity match from all tie-up rate sheets
- Category: Match if similarity >= 0.70, else mark all items as MISMATCH
- Item: 
  * similarity >= 0.85: Auto-match
  * 0.70 <= similarity < 0.85: Use LLM verification
  * similarity < 0.70: Auto-reject (MISMATCH)

Graceful Degradation:
- If embedding service fails, indexing is skipped with a warning
- Queries return empty/no-match results instead of crashing
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import faiss
import numpy as np

from app.verifier.embedding_service import (
    EmbeddingService, 
    EmbeddingServiceUnavailable,
    get_embedding_service,
)
from app.verifier.llm_router import LLMRouter, get_llm_router
from app.verifier.models import TieUpCategory, TieUpItem, TieUpRateSheet

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Similarity thresholds (loaded from env or defaults)
CATEGORY_SIMILARITY_THRESHOLD = float(os.getenv("CATEGORY_SIMILARITY_THRESHOLD", "0.70"))
CATEGORY_SOFT_THRESHOLD = float(os.getenv("CATEGORY_SOFT_THRESHOLD", "0.65"))  # Soft acceptance
ITEM_SIMILARITY_THRESHOLD = float(os.getenv("ITEM_SIMILARITY_THRESHOLD", "0.85"))


# =============================================================================
# Data Classes for Match Results
# =============================================================================

@dataclass
class MatchResult:
    """Result of a semantic match operation."""
    matched_text: Optional[str]
    similarity: float
    index: int  # Index in the original list (-1 if no match)
    error: Optional[str] = None  # Error message if matching failed
    
    @property
    def is_match(self) -> bool:
        """Check if this is a valid match (index >= 0)."""
        return self.index >= 0 and self.error is None
    
    @property
    def has_error(self) -> bool:
        """Check if there was an error during matching."""
        return self.error is not None


@dataclass
class HospitalMatch(MatchResult):
    """Hospital match result with tie-up rate sheet reference."""
    rate_sheet: Optional[TieUpRateSheet] = None


@dataclass
class CategoryMatch(MatchResult):
    """Category match result with tie-up category reference."""
    category: Optional[TieUpCategory] = None


@dataclass
class ItemMatch(MatchResult):
    """Item match result with tie-up item reference."""
    item: Optional[TieUpItem] = None
    normalized_item_name: Optional[str] = None  # PHASE-1: Track normalization for diagnostics


# =============================================================================
# FAISS Index Wrapper
# =============================================================================

class FAISSIndex:
    """
    Wrapper around FAISS index for similarity search.
    Uses inner product (cosine similarity with normalized vectors).
    """
    
    def __init__(self, dimension: int):
        """
        Initialize FAISS index.
        
        Args:
            dimension: Embedding dimension
        """
        self.dimension = dimension
        # Use IndexFlatIP for inner product (cosine similarity with L2 normalized vectors)
        self.index = faiss.IndexFlatIP(dimension)
        self.texts: List[str] = []
    
    def add(self, embeddings: np.ndarray, texts: List[str]):
        """
        Add embeddings to the index.
        
        Args:
            embeddings: Array of shape (n, dimension)
            texts: List of corresponding text strings
        """
        if len(embeddings) == 0:
            return
            
        # L2 normalize for cosine similarity
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        self.texts.extend(texts)
    
    def search(self, query_embedding: np.ndarray, k: int = 1) -> List[Tuple[int, float]]:
        """
        Search for k nearest neighbors.
        
        Args:
            query_embedding: Query vector of shape (dimension,)
            k: Number of results to return
            
        Returns:
            List of (index, similarity_score) tuples
        """
        if self.index.ntotal == 0:
            return []
        
        # Reshape and normalize query
        query = query_embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query)
        
        # Search
        k = min(k, self.index.ntotal)
        distances, indices = self.index.search(query, k)
        
        results = []
        for i in range(k):
            idx = int(indices[0][i])
            # Cosine similarity from inner product (already normalized)
            similarity = float(distances[0][i])
            results.append((idx, similarity))
        
        return results
    
    def search_with_threshold(
        self, 
        query_embedding: np.ndarray, 
        threshold: float
    ) -> Optional[Tuple[int, float, str]]:
        """
        Search for best match above threshold.
        
        Args:
            query_embedding: Query vector
            threshold: Minimum similarity score
            
        Returns:
            Tuple of (index, similarity, text) if match found, else None
        """
        results = self.search(query_embedding, k=1)
        if not results:
            return None
            
        idx, similarity = results[0]
        if similarity >= threshold:
            return (idx, similarity, self.texts[idx])
        return None
    
    @property
    def size(self) -> int:
        """Return number of vectors in the index."""
        return self.index.ntotal


# =============================================================================
# Semantic Matcher
# =============================================================================

class SemanticMatcher:
    """
    Main semantic matcher class.
    Builds FAISS indices from tie-up rate sheets and performs matching.
    
    Graceful Degradation:
    - If embedding service fails during indexing, skips with warning
    - If embedding service fails during query, returns error result
    - Never crashes the application
    """
    
    def __init__(
        self, 
        embedding_service: Optional[EmbeddingService] = None,
        llm_router: Optional[LLMRouter] = None,
    ):
        """
        Initialize the semantic matcher.
        
        Args:
            embedding_service: Embedding service instance (uses global if None)
            llm_router: LLM router instance (uses global if None)
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self.llm_router = llm_router or get_llm_router()
        self.dimension = self.embedding_service.dimension
        
        # Hospital-level index
        self._hospital_index: Optional[FAISSIndex] = None
        self._hospital_rate_sheets: List[TieUpRateSheet] = []
        
        # Per-hospital category indices: hospital_name -> FAISSIndex
        self._category_indices: Dict[str, FAISSIndex] = {}
        self._category_refs: Dict[str, List[TieUpCategory]] = {}
        
        # Per-category item indices: (hospital_name, category_name) -> FAISSIndex
        self._item_indices: Dict[Tuple[str, str], FAISSIndex] = {}
        self._item_refs: Dict[Tuple[str, str], List[TieUpItem]] = {}
        
        # Track indexing status
        self._indexing_error: Optional[str] = None
        self._indexed = False
        
        # Track LLM usage statistics
        self._llm_calls = 0
        self._total_matches = 0
        
        logger.info("SemanticMatcher initialized with LLM router")
    
    @property
    def is_indexed(self) -> bool:
        """Check if rate sheets have been indexed successfully."""
        return self._indexed and self._indexing_error is None
    
    @property
    def indexing_error(self) -> Optional[str]:
        """Get indexing error message if any."""
        return self._indexing_error
    
    def index_rate_sheets(self, rate_sheets: List[TieUpRateSheet]) -> bool:
        """
        Build FAISS indices from tie-up rate sheets.
        
        This creates:
        1. A hospital-level index for matching bill hospital to tie-up hospitals
        2. Category indices for each hospital
        3. Item indices for each category in each hospital
        
        Graceful Degradation:
        - If embedding service fails, logs warning and returns False
        - Partial indexing is allowed (some categories may be indexed)
        
        Args:
            rate_sheets: List of TieUpRateSheet objects
            
        Returns:
            True if indexing succeeded, False if it failed
        """
        if not rate_sheets:
            logger.warning("No rate sheets provided for indexing")
            return False
        
        logger.info(f"Indexing {len(rate_sheets)} rate sheets...")
        
        self._hospital_rate_sheets = rate_sheets
        self._indexing_error = None
        
        try:
            # 1. Index hospital names
            hospital_names = [rs.hospital_name for rs in rate_sheets]
            hospital_embeddings, error = self.embedding_service.get_embeddings_safe(hospital_names)
            
            if error or hospital_embeddings is None:
                self._indexing_error = f"Failed to embed hospital names: {error}"
                logger.error(self._indexing_error)
                return False
            
            self._hospital_index = FAISSIndex(self.dimension)
            self._hospital_index.add(hospital_embeddings, hospital_names)
            
            # 2. Index categories and items for each hospital
            categories_indexed = 0
            items_indexed = 0
            
            for rs in rate_sheets:
                hospital_key = rs.hospital_name.lower()
                
                # Category index for this hospital
                if rs.categories:
                    category_names = [cat.category_name for cat in rs.categories]
                    category_embeddings, error = self.embedding_service.get_embeddings_safe(category_names)
                    
                    if error or category_embeddings is None:
                        logger.warning(
                            f"Skipping category indexing for {rs.hospital_name}: {error}"
                        )
                        continue
                    
                    cat_index = FAISSIndex(self.dimension)
                    cat_index.add(category_embeddings, category_names)
                    
                    self._category_indices[hospital_key] = cat_index
                    self._category_refs[hospital_key] = rs.categories
                    categories_indexed += 1
                    
                    # Item index for each category
                    for cat in rs.categories:
                        if cat.items:
                            cat_key = (hospital_key, cat.category_name.lower())
                            item_names = [item.item_name for item in cat.items]
                            item_embeddings, error = self.embedding_service.get_embeddings_safe(item_names)
                            
                            if error or item_embeddings is None:
                                logger.warning(
                                    f"Skipping item indexing for {rs.hospital_name}/{cat.category_name}: {error}"
                                )
                                continue
                            
                            item_index = FAISSIndex(self.dimension)
                            item_index.add(item_embeddings, item_names)
                            
                            self._item_indices[cat_key] = item_index
                            self._item_refs[cat_key] = cat.items
                            items_indexed += 1
            
            self._indexed = True
            logger.info(
                f"Indexed: {self._hospital_index.size} hospitals, "
                f"{categories_indexed} category indices, "
                f"{items_indexed} item indices"
            )
            
            # Save cache after indexing
            self.embedding_service.save_cache()
            
            return True
            
        except EmbeddingServiceUnavailable as e:
            self._indexing_error = f"Embedding service unavailable: {e}"
            logger.error(self._indexing_error)
            return False
        except Exception as e:
            self._indexing_error = f"Unexpected indexing error: {e}"
            logger.error(self._indexing_error, exc_info=True)
            return False
    
    def match_hospital(self, hospital_name: str) -> HospitalMatch:
        """
        Match a bill hospital name to the best tie-up hospital.
        
        Args:
            hospital_name: Hospital name from the bill
            
        Returns:
            HospitalMatch with the best matching rate sheet
            If embedding fails, returns error result (never crashes)
        """
        # Check if indexing failed
        if self._indexing_error:
            return HospitalMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                rate_sheet=None,
                error=f"Indexing failed: {self._indexing_error}"
            )
        
        if self._hospital_index is None or self._hospital_index.size == 0:
            logger.warning("No hospital index available")
            return HospitalMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                rate_sheet=None,
                error="No hospital index available"
            )
        
        # Get embedding for query hospital (with graceful degradation)
        try:
            query_embedding = self.embedding_service.get_embedding(hospital_name)
        except EmbeddingServiceUnavailable as e:
            logger.warning(f"Embedding service unavailable for hospital match: {e}")
            return HospitalMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                rate_sheet=None,
                error=f"Embedding service temporarily unavailable: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error getting hospital embedding: {e}")
            return HospitalMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                rate_sheet=None,
                error=f"Embedding error: {e}"
            )
        
        # Find best match
        results = self._hospital_index.search(query_embedding, k=1)
        if not results:
            return HospitalMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                rate_sheet=None
            )
        
        idx, similarity = results[0]
        matched_name = self._hospital_index.texts[idx]
        rate_sheet = self._hospital_rate_sheets[idx]
        
        logger.debug(f"Hospital match: '{hospital_name}' -> '{matched_name}' (sim={similarity:.4f})")
        
        return HospitalMatch(
            matched_text=matched_name,
            similarity=similarity,
            index=idx,
            rate_sheet=rate_sheet
        )
    
    def match_category(
        self, 
        category_name: str, 
        hospital_name: str,
        threshold: float = CATEGORY_SIMILARITY_THRESHOLD
    ) -> CategoryMatch:
        """
        Match a bill category to a tie-up category.
        
        Args:
            category_name: Category name from the bill
            hospital_name: Matched hospital name (from match_hospital)
            threshold: Minimum similarity threshold (default 0.70)
            
        Returns:
            CategoryMatch (similarity < threshold means MISMATCH)
            If embedding fails, returns error result (never crashes)
        """
        hospital_key = hospital_name.lower()
        
        if hospital_key not in self._category_indices:
            logger.warning(f"No category index for hospital: {hospital_name}")
            return CategoryMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                category=None
            )
        
        cat_index = self._category_indices[hospital_key]
        cat_refs = self._category_refs[hospital_key]
        
        # Get embedding for query category (with graceful degradation)
        try:
            query_embedding = self.embedding_service.get_embedding(category_name)
        except EmbeddingServiceUnavailable as e:
            logger.warning(f"Embedding service unavailable for category match: {e}")
            return CategoryMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                category=None,
                error=f"Embedding service temporarily unavailable: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error getting category embedding: {e}")
            return CategoryMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                category=None,
                error=f"Embedding error: {e}"
            )
        
        # Find best match
        results = cat_index.search(query_embedding, k=1)
        if not results:
            return CategoryMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                category=None
            )
        
        idx, similarity = results[0]
        matched_name = cat_index.texts[idx]
        category = cat_refs[idx]
        
        logger.debug(f"Category match: '{category_name}' -> '{matched_name}' (sim={similarity:.4f})")
        
        # Return match regardless of threshold (caller decides what to do)
        return CategoryMatch(
            matched_text=matched_name,
            similarity=similarity,
            index=idx if similarity >= threshold else -1,
            category=category if similarity >= threshold else None
        )
    
    def match_item(
        self,
        item_name: str,
        hospital_name: str,
        category_name: str,
        threshold: float = ITEM_SIMILARITY_THRESHOLD,
        use_llm: bool = True,
    ) -> ItemMatch:
        """
        Match a bill item to a tie-up item with LLM fallback for borderline cases.
        
        Matching Strategy:
        - similarity >= 0.85: Auto-match (no LLM)
        - 0.70 <= similarity < 0.85: Use LLM verification (if use_llm=True)
        - similarity < 0.70: Auto-reject (MISMATCH)
        
        Text Normalization:
        - Bill item text is normalized before matching to handle OCR noise
        - Removes numbering, doctor names, separators, etc.
        - Example: "1. CONSULTATION - FIRST VISIT | Dr. Vivek" → "consultation first visit"
        
        Args:
            item_name: Item name from the bill (will be normalized)
            hospital_name: Matched hospital name
            category_name: Matched category name
            threshold: Minimum similarity threshold (default 0.85)
            use_llm: Whether to use LLM for borderline cases (default True)
            
        Returns:
            ItemMatch (similarity < threshold means MISMATCH unless LLM overrides)
            If embedding fails, returns error result (never crashes)
        """
        self._total_matches += 1
        
        # CRITICAL: Extract medical core FIRST (before any other processing)
        # This removes inventory metadata: lot numbers, SKUs, expiry dates, brand suffixes
        # Example: "(30049099) NICORANDIL-TABLET-5MG-KORANDIL- |GTF" → "nicorandil 5mg"
        from app.verifier.medical_core_extractor import extract_medical_core
        medical_core = extract_medical_core(item_name)
        
        # Then normalize the medical core (remove doctor names, etc.)
        from app.verifier.text_normalizer import normalize_bill_item_text
        normalized_item_name = normalize_bill_item_text(medical_core)
        
        # Log extraction and normalization for debugging
        if medical_core != item_name.lower().strip():
            logger.debug(
                f"Medical core extracted: '{item_name}' → '{medical_core}'"
            )
        if normalized_item_name != medical_core.lower().strip():
            logger.debug(
                f"Normalized: '{medical_core}' → '{normalized_item_name}'"
            )
        
        # Use normalized medical core for matching
        item_name_for_matching = normalized_item_name if normalized_item_name else item_name
        
        cat_key = (hospital_name.lower(), category_name.lower())
        
        if cat_key not in self._item_indices:
            logger.warning(f"No item index for: {hospital_name}/{category_name}")
            return ItemMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                item=None,
                normalized_item_name=item_name_for_matching
            )
        
        item_index = self._item_indices[cat_key]
        item_refs = self._item_refs[cat_key]
        
        # Get embedding for query item (with graceful degradation)
        try:
            query_embedding = self.embedding_service.get_embedding(item_name_for_matching)
        except EmbeddingServiceUnavailable as e:
            logger.warning(f"Embedding service unavailable for item match: {e}")
            return ItemMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                item=None,
                normalized_item_name=item_name_for_matching,
                error=f"Embedding service temporarily unavailable: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error getting item embedding: {e}")
            return ItemMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                item=None,
                normalized_item_name=item_name_for_matching,
                error=f"Embedding error: {e}"
            )
        
        # Find best match using TOP-K strategy (PHASE-1 ENHANCEMENT)
        # Instead of just taking top-1 semantic match, evaluate top-3 with hybrid scoring
        k = min(3, item_index.size)  # Get top-3 candidates (or fewer if index is small)
        results = item_index.search(query_embedding, k=k)
        
        if not results:
            return ItemMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                item=None,
                normalized_item_name=item_name_for_matching
            )
        
        # PHASE-1: Evaluate all candidates with hybrid scoring
        from app.verifier.partial_matcher import calculate_hybrid_score
        
        best_match = None
        best_hybrid_score = 0.0
        best_breakdown = None
        
        for idx, semantic_sim in results:
            matched_name = item_index.texts[idx]
            item = item_refs[idx]
            
            # Calculate hybrid score for this candidate
            hybrid_score, breakdown = calculate_hybrid_score(
                bill_item=item_name_for_matching,
                tieup_item=matched_name.lower(),
                semantic_similarity=semantic_sim,
            )
            
            logger.debug(
                f"Candidate {idx+1}: '{matched_name}' "
                f"(semantic={semantic_sim:.4f}, hybrid={hybrid_score:.4f})"
            )
            
            # Track best hybrid score
            if hybrid_score > best_hybrid_score:
                best_hybrid_score = hybrid_score
                best_match = (idx, matched_name, item, semantic_sim)
                best_breakdown = breakdown
        
        # Use best match if found
        if best_match is None:
            return ItemMatch(
                matched_text=None,
                similarity=0.0,
                index=-1,
                item=None,
                normalized_item_name=item_name_for_matching
            )
        
        idx, matched_name, item, similarity = best_match
        
        logger.debug(
            f"Best match: '{item_name_for_matching}' → '{matched_name}' "
            f"(semantic={similarity:.4f}, hybrid={best_hybrid_score:.4f}, "
            f"tok={best_breakdown['token_overlap']:.2f}, "
            f"cont={best_breakdown['containment']:.2f})"
        )
        
        # PHASE-1: Use hybrid score threshold (0.60) instead of pure semantic threshold
        # This allows matches with lower semantic similarity but high token overlap
        HYBRID_SCORE_THRESHOLD = 0.60
        
        # Auto-match for high hybrid score
        if best_hybrid_score >= HYBRID_SCORE_THRESHOLD:
            logger.info(
                f"Hybrid match accepted: '{item_name}' → '{matched_name}' "
                f"(hybrid={best_hybrid_score:.4f})"
            )
            return ItemMatch(
                matched_text=matched_name,
                similarity=best_hybrid_score,  # Use hybrid score as confidence
                index=idx,
                item=item,
                normalized_item_name=item_name_for_matching
            )
        
        # Try partial semantic matching (EXISTING LOGIC - now as fallback)
        # This allows "consultation first visit" to match "consultation"
        from app.verifier.partial_matcher import is_partial_match
        
        is_match, confidence, reason = is_partial_match(
            bill_item=item_name_for_matching,
            tieup_item=matched_name.lower(),
            semantic_similarity=similarity,
        )
        
        if is_match:
            logger.info(
                f"Partial match accepted: '{item_name}' → '{matched_name}' "
                f"(semantic={similarity:.4f}, confidence={confidence:.4f}, reason={reason})"
            )
            return ItemMatch(
                matched_text=matched_name,
                similarity=confidence,  # Use combined confidence
                index=idx,
                item=item,
                normalized_item_name=item_name_for_matching
            )
        
        # Use LLM for borderline cases (0.55 <= similarity < 0.60)
        # PHASE-1: Lowered threshold from 0.65 to 0.55
        PHASE1_LLM_THRESHOLD = 0.55
        if use_llm and similarity >= PHASE1_LLM_THRESHOLD:
            self._llm_calls += 1
            logger.info(
                f"Borderline similarity ({similarity:.4f}), using LLM for verification"
            )
            
            # Use original (non-normalized) text for LLM to preserve context
            llm_result = self.llm_router.match_with_llm(
                bill_item=item_name,  # Original text for LLM
                tieup_item=matched_name,
                similarity=similarity,
            )
            
            if llm_result.is_valid and llm_result.match:
                # LLM confirmed match
                logger.info(
                    f"LLM confirmed match: '{item_name}' → '{matched_name}' "
                    f"(confidence={llm_result.confidence:.4f}, model={llm_result.model_used})"
                )
                return ItemMatch(
                    matched_text=matched_name,
                    similarity=llm_result.confidence,  # Use LLM confidence
                    index=idx,
                    item=item,
                    normalized_item_name=item_name_for_matching
                )
            else:
                # LLM rejected or failed
                logger.info(
                    f"LLM rejected match: '{item_name}' → '{matched_name}' "
                    f"(confidence={llm_result.confidence:.4f}, error={llm_result.error})"
                )
        
        # No match (either below threshold, partial match failed, or LLM rejected)
        logger.debug(
            f"Item rejected: '{item_name}' → '{matched_name}' "
            f"(semantic={similarity:.4f}, partial_match={reason if 'reason' in locals() else 'not_tried'})"
        )
        return ItemMatch(
            matched_text=matched_name,
            similarity=similarity,
            index=-1,
            item=None,
            normalized_item_name=item_name_for_matching
        )
    
    def clear_indices(self):
        """Clear all FAISS indices and references."""
        self._hospital_index = None
        self._hospital_rate_sheets = []
        self._category_indices.clear()
        self._category_refs.clear()
        self._item_indices.clear()
        self._item_refs.clear()
        logger.info("All indices cleared")
    
    @property
    def llm_usage_percentage(self) -> float:
        """Calculate percentage of matches that used LLM."""
        if self._total_matches == 0:
            return 0.0
        return (self._llm_calls / self._total_matches) * 100.0
    
    @property
    def stats(self) -> dict:
        """Return matching statistics."""
        return {
            "total_matches": self._total_matches,
            "llm_calls": self._llm_calls,
            "llm_usage_percentage": self.llm_usage_percentage,
            "llm_cache_size": self.llm_router.cache_size,
            "llm_cache_hit_rate": self.llm_router.cache_hit_rate,
        }


# =============================================================================
# Module-level singleton
# =============================================================================

_matcher: Optional[SemanticMatcher] = None


def get_matcher() -> SemanticMatcher:
    """Get or create the global semantic matcher instance."""
    global _matcher
    if _matcher is None:
        _matcher = SemanticMatcher()
    return _matcher

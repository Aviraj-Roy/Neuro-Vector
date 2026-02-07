"""
Enhanced Item Matching with Partial Semantic Matching.

Provides hybrid matching strategy combining:
1. Token overlap (for partial matches)
2. Semantic similarity (for fuzzy matches)
3. Core term extraction (for medical services)

This allows matching items like:
- "CONSULTATION - FIRST VISIT" → "Consultation"
- "MRI BRAIN" → "MRI Brain"
- "CT Scan - Abdomen" → "CT Scan Abdomen"

Without hardcoding specific item names.
"""

from __future__ import annotations

import re
from typing import Set, Tuple


def extract_core_terms(text: str) -> Set[str]:
    """
    Extract core medical/service terms from text.
    
    Removes:
    - Common stop words (the, a, an, of, for, with, etc.)
    - Very short words (< 2 chars)
    - Pure numbers
    
    Args:
        text: Input text (should be normalized)
        
    Returns:
        Set of core terms
    """
    # Common medical stop words
    stop_words = {
        'the', 'a', 'an', 'of', 'for', 'with', 'in', 'on', 'at',
        'to', 'from', 'by', 'and', 'or', 'but', 'is', 'are',
        'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'should', 'could',
        'may', 'might', 'must', 'can', 'shall',
    }
    
    # Tokenize and filter
    tokens = text.lower().split()
    
    core_terms = set()
    for token in tokens:
        # Remove punctuation
        token = re.sub(r'[^\w]', '', token)
        
        # Skip if too short
        if len(token) < 2:
            continue
        
        # Skip if pure number
        if token.isdigit():
            continue
        
        # Skip stop words
        if token in stop_words:
            continue
        
        core_terms.add(token)
    
    return core_terms


def calculate_token_overlap(text1: str, text2: str) -> float:
    """
    Calculate token overlap ratio between two texts.
    
    Uses Jaccard similarity: |intersection| / |union|
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Overlap ratio (0.0 to 1.0)
    """
    terms1 = extract_core_terms(text1)
    terms2 = extract_core_terms(text2)
    
    if not terms1 or not terms2:
        return 0.0
    
    intersection = terms1 & terms2
    union = terms1 | terms2
    
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


def calculate_containment(text1: str, text2: str) -> float:
    """
    Calculate containment ratio (how much of text2 is in text1).
    
    Useful for partial matches where bill item is more detailed than tie-up item.
    
    Args:
        text1: Longer text (bill item)
        text2: Shorter text (tie-up item)
        
    Returns:
        Containment ratio (0.0 to 1.0)
    """
    terms1 = extract_core_terms(text1)
    terms2 = extract_core_terms(text2)
    
    if not terms2:
        return 0.0
    
    intersection = terms1 & terms2
    
    return len(intersection) / len(terms2)


def calculate_hybrid_score(
    bill_item: str,
    tieup_item: str,
    semantic_similarity: float,
    weights: dict = None,
) -> Tuple[float, dict]:
    """
    Calculate hybrid matching score combining multiple signals.
    
    PHASE-1 CRITICAL: This is the core of the hybrid matching strategy.
    Combines semantic similarity, token overlap, and containment into a single score.
    
    Strategy:
    - Semantic similarity (60% weight): Captures meaning and context
    - Token overlap (30% weight): Catches exact term matches
    - Containment (10% weight): Handles partial matches (bill more detailed than tie-up)
    
    Args:
        bill_item: Normalized bill item text
        tieup_item: Normalized tie-up item text
        semantic_similarity: Semantic similarity score (0.0 to 1.0)
        weights: Optional custom weights dict (default: semantic=0.6, token=0.3, containment=0.1)
        
    Returns:
        Tuple of (final_score, breakdown_dict)
        
    Examples:
        >>> calculate_hybrid_score("nicorandil 5mg", "nicorandil 5mg", 0.98)
        (0.99, {...})  # High semantic + perfect token match
        
        >>> calculate_hybrid_score("consultation first visit", "consultation", 0.72)
        (0.78, {...})  # Medium semantic + high containment
    """
    if weights is None:
        weights = {
            "semantic": 0.6,
            "token": 0.3,
            "containment": 0.1,
        }
    
    # Calculate all metrics
    token_overlap = calculate_token_overlap(bill_item, tieup_item)
    containment = calculate_containment(bill_item, tieup_item)
    
    # Weighted combination
    final_score = (
        weights["semantic"] * semantic_similarity +
        weights["token"] * token_overlap +
        weights["containment"] * containment
    )
    
    breakdown = {
        "semantic": semantic_similarity,
        "token_overlap": token_overlap,
        "containment": containment,
        "final_score": final_score,
        "weights": weights,
    }
    
    return final_score, breakdown


def is_partial_match(
    bill_item: str,
    tieup_item: str,
    semantic_similarity: float,
    overlap_threshold: float = 0.4,  # LOWERED: More permissive for partial matches
    containment_threshold: float = 0.6,  # LOWERED: Accept if 60% of tie-up terms in bill
    min_semantic_similarity: float = 0.55,  # PHASE-1: Lowered from 0.65 to catch more borderline cases
) -> Tuple[bool, float, str]:
    """
    Check if bill item is a partial match for tie-up item.
    
    Strategy (PHASE-1 ENHANCED - Hybrid Scoring):
    1. If semantic similarity >= 0.85: Auto-match (high confidence)
    2. If semantic similarity >= min_threshold (0.55):
       a. Calculate hybrid score (weighted: semantic + token + containment)
       b. If hybrid_score >= 0.60: Accept match
       c. Otherwise: Try individual metrics (overlap OR containment)
    3. Otherwise: Reject
    
    PHASE-1 GOAL: Maximize coverage, minimize false negatives.
    False positives are acceptable, false negatives are NOT.
    
    Examples:
        bill: "nicorandil 5mg"  (after core extraction)
        tieup: "nicorandil 5mg"
        → semantic=0.98, token=1.0, containment=1.0
        → hybrid_score=0.99 → MATCH ✅
        
        bill: "consultation first visit"
        tieup: "consultation"
        → semantic=0.72, token=0.33, containment=1.0
        → hybrid_score=0.63 → MATCH ✅
        
        bill: "mri brain"
        tieup: "mri brain"
        → semantic=0.95, token=1.0, containment=1.0
        → hybrid_score=0.97 → MATCH ✅
        
        bill: "paracetamol 500mg"
        tieup: "paracetamol 500mg"
        → semantic=0.58, token=1.0, containment=1.0
        → hybrid_score=0.75 → MATCH ✅ (caught by hybrid scoring!)
    
    Args:
        bill_item: Normalized bill item text (after medical core extraction)
        tieup_item: Normalized tie-up item text
        semantic_similarity: Semantic similarity score (0.0 to 1.0)
        overlap_threshold: Minimum token overlap ratio (default 0.4)
        containment_threshold: Minimum containment ratio (default 0.6)
        min_semantic_similarity: Minimum semantic similarity to consider (default 0.55)
        
    Returns:
        Tuple of (is_match, confidence, reason)
    """
    # Auto-match for high semantic similarity
    if semantic_similarity >= 0.85:
        return True, semantic_similarity, "high_semantic_similarity"
    
    # Reject if semantic similarity too low
    if semantic_similarity < min_semantic_similarity:
        return False, semantic_similarity, "low_semantic_similarity"
    
    # PHASE-1: Calculate hybrid score (PRIMARY STRATEGY)
    hybrid_score, breakdown = calculate_hybrid_score(
        bill_item=bill_item,
        tieup_item=tieup_item,
        semantic_similarity=semantic_similarity,
    )
    
    # Accept if hybrid score is good (0.60 threshold)
    if hybrid_score >= 0.60:
        reason = (
            f"hybrid_score={hybrid_score:.2f} "
            f"(sem={breakdown['semantic']:.2f}, "
            f"tok={breakdown['token_overlap']:.2f}, "
            f"cont={breakdown['containment']:.2f})"
        )
        return True, hybrid_score, reason
    
    # FALLBACK: Try individual metrics (for edge cases)
    overlap = breakdown['token_overlap']
    containment = breakdown['containment']
    
    # Accept if high overlap (terms are similar)
    if overlap >= overlap_threshold:
        confidence = (semantic_similarity + overlap) / 2
        return True, confidence, f"token_overlap={overlap:.2f}"
    
    # Accept if high containment (tie-up terms fully contained in bill)
    if containment >= containment_threshold:
        confidence = (semantic_similarity + containment) / 2
        return True, confidence, f"containment={containment:.2f}"
    
    # Reject
    return False, hybrid_score, f"hybrid_score={hybrid_score:.2f} (below 0.60)"


# =============================================================================
# Testing and Validation
# =============================================================================

if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("consultation first visit", "consultation", 0.78),
        ("mri brain", "mri brain", 0.98),
        ("ct scan abdomen", "ct scan", 0.82),
        ("blood test cbc", "blood test", 0.85),
        ("x ray chest", "chest x ray", 0.90),
        ("ecg test", "electrocardiogram", 0.72),  # Should fail (different terms)
    ]
    
    print("Partial Match Test Cases:")
    print("="*80)
    
    for bill, tieup, sim in test_cases:
        is_match, confidence, reason = is_partial_match(bill, tieup, sim)
        
        print(f"\nBill:   '{bill}'")
        print(f"Tie-up: '{tieup}'")
        print(f"Semantic Similarity: {sim:.2f}")
        print(f"Result: {'✅ MATCH' if is_match else '❌ NO MATCH'}")
        print(f"Confidence: {confidence:.2f}")
        print(f"Reason: {reason}")
        print("-"*80)

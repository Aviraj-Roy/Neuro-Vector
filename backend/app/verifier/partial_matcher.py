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


def is_partial_match(
    bill_item: str,
    tieup_item: str,
    semantic_similarity: float,
    overlap_threshold: float = 0.5,
    containment_threshold: float = 0.7,
    min_semantic_similarity: float = 0.70,
) -> Tuple[bool, float, str]:
    """
    Check if bill item is a partial match for tie-up item.
    
    Strategy:
    1. If semantic similarity >= 0.85: Auto-match (existing logic)
    2. If semantic similarity >= 0.70:
       - Calculate token overlap
       - Calculate containment (tie-up terms in bill)
       - If overlap >= 0.5 OR containment >= 0.7: Accept match
    3. Otherwise: Reject
    
    Examples:
        bill: "consultation first visit"
        tieup: "consultation"
        → overlap=1.0 (100% of "consultation" is in bill)
        → containment=1.0 (all tie-up terms in bill)
        → MATCH ✅
        
        bill: "mri brain"
        tieup: "mri brain"
        → overlap=1.0, containment=1.0
        → MATCH ✅
        
        bill: "blood test cbc"
        tieup: "blood test"
        → overlap=0.67, containment=1.0
        → MATCH ✅
    
    Args:
        bill_item: Normalized bill item text
        tieup_item: Normalized tie-up item text
        semantic_similarity: Semantic similarity score (0.0 to 1.0)
        overlap_threshold: Minimum token overlap ratio
        containment_threshold: Minimum containment ratio
        min_semantic_similarity: Minimum semantic similarity to consider
        
    Returns:
        Tuple of (is_match, confidence, reason)
    """
    # Auto-match for high semantic similarity
    if semantic_similarity >= 0.85:
        return True, semantic_similarity, "high_semantic_similarity"
    
    # Reject if semantic similarity too low
    if semantic_similarity < min_semantic_similarity:
        return False, semantic_similarity, "low_semantic_similarity"
    
    # Calculate token-based metrics
    overlap = calculate_token_overlap(bill_item, tieup_item)
    containment = calculate_containment(bill_item, tieup_item)
    
    # Accept if high overlap (terms are similar)
    if overlap >= overlap_threshold:
        confidence = (semantic_similarity + overlap) / 2
        return True, confidence, f"token_overlap={overlap:.2f}"
    
    # Accept if high containment (tie-up terms fully contained in bill)
    if containment >= containment_threshold:
        confidence = (semantic_similarity + containment) / 2
        return True, confidence, f"containment={containment:.2f}"
    
    # Reject
    return False, semantic_similarity, f"overlap={overlap:.2f},containment={containment:.2f}"


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

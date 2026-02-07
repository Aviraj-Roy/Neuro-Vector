"""
Text Normalization Utilities for Bill Item Matching.

Provides robust preprocessing of noisy OCR bill text before semantic matching.
Handles common OCR artifacts like numbering, doctor names, separators, etc.
"""

from __future__ import annotations

import re
from typing import Optional

# =============================================================================
# Normalization Patterns
# =============================================================================

# Patterns to remove from bill item text
REMOVAL_PATTERNS = [
    # Numbering prefixes: "1.", "2)", "a.", etc.
    r"^\s*\d+[\.\)]\s*",
    r"^\s*[a-zA-Z][\.\)]\s*",
    
    # Doctor names and credentials
    r"\|\s*Dr\.?\s+[A-Za-z\s\.]+$",  # "| Dr. Vivek Jacob P"
    r"-\s*Dr\.?\s+[A-Za-z\s\.]+$",   # "- Dr. Vivek Jacob"
    r"\bDr\.?\s+[A-Za-z\s\.]+$",     # "Dr. Vivek Jacob"
    r"\bProf\.?\s+[A-Za-z\s\.]+$",   # "Prof. John Doe"
    
    # Credentials at end
    r"\s+M\.?D\.?$",
    r"\s+MBBS$",
    r"\s+MS$",
    r"\s+MD$",
    
    # Common separators and trailing noise
    r"\s*\|\s*$",  # Trailing pipe
    r"\s*-\s*$",   # Trailing dash
    r"\s*:\s*$",   # Trailing colon
]

# Patterns to split on (take only first part)
SPLIT_PATTERNS = [
    r"\s*\|\s*",   # Pipe separator
    r"\s+-\s+Dr",  # Dash before doctor
    r"\s+\|\s+Dr", # Pipe before doctor
]


# =============================================================================
# Normalization Functions
# =============================================================================

def normalize_bill_item_text(text: str) -> str:
    """
    Normalize bill item text for matching.
    
    Removes common OCR artifacts:
    - Numbering prefixes (1., 2), a., etc.)
    - Doctor names and credentials
    - Pipe symbols and separators
    - Extra whitespace
    - Mixed casing
    
    Examples:
        "1. CONSULTATION - FIRST VISIT | Dr. Vivek JaCob P"
        → "consultation first visit"
        
        "MRI BRAIN | Dr. Vivek Jacob Philip"
        → "mri brain"
        
        "2) CT Scan - Abdomen"
        → "ct scan abdomen"
    
    Args:
        text: Raw bill item text from OCR
        
    Returns:
        Normalized text suitable for semantic matching
    """
    if not text or not isinstance(text, str):
        return ""
    
    normalized = text.strip()
    
    # Step 1: Split on common separators (take first part only)
    for pattern in SPLIT_PATTERNS:
        parts = re.split(pattern, normalized, maxsplit=1)
        if len(parts) > 1:
            normalized = parts[0].strip()
            break
    
    # Step 2: Remove unwanted patterns
    for pattern in REMOVAL_PATTERNS:
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
    
    # Step 3: Normalize whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    
    # Step 4: Remove special characters (keep alphanumeric and spaces)
    # But preserve common medical abbreviations like "/"
    normalized = re.sub(r"[^\w\s/\-]", " ", normalized)
    
    # Step 5: Normalize to lowercase
    normalized = normalized.lower().strip()
    
    # Step 6: Remove extra whitespace again
    normalized = re.sub(r"\s+", " ", normalized)
    
    return normalized


def normalize_category_name(text: str) -> str:
    """
    Normalize category name for matching.
    
    Less aggressive than item normalization - only removes obvious artifacts.
    
    Args:
        text: Raw category name
        
    Returns:
        Normalized category name
    """
    if not text or not isinstance(text, str):
        return ""
    
    normalized = text.strip()
    
    # Remove numbering
    normalized = re.sub(r"^\s*\d+[\.\)]\s*", "", normalized)
    
    # Normalize whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    
    # Lowercase
    normalized = normalized.lower().strip()
    
    return normalized


def should_skip_category(category_name: str) -> bool:
    """
    Check if a category should be skipped during verification.
    
    Filters out pseudo-categories that shouldn't be verified:
    - "Hospital" or "Hospital -" (metadata, not a real category)
    - Empty or very short names
    - Categories with only special characters
    
    Args:
        category_name: Category name to check
        
    Returns:
        True if category should be skipped, False otherwise
    """
    if not category_name or not isinstance(category_name, str):
        return True
    
    normalized = category_name.strip().lower()
    
    # Skip empty or very short
    if len(normalized) < 2:
        return True
    
    # Skip "Hospital" pseudo-category (artifact from old schema)
    if normalized in ["hospital", "hospital -", "hospital-", "hospital_"]:
        return True
    
    # Skip if only special characters
    if re.match(r"^[\W_]+$", normalized):
        return True
    
    return False


def is_non_medical_artifact(text: str) -> bool:
    """
    Check if text is a non-medical artifact that should be ignored.
    
    PHASE-1 REQUIREMENT: Explicitly ignore lines containing:
    - Internal IDs (pure numbers, alphanumeric codes)
    - Lot numbers (LOT:ABC123)
    - Batch codes (BATCH:XYZ789)
    - Expiry metadata (EXP:12/2025)
    - Inventory / SKU noise
    
    These should NOT affect similarity scoring.
    
    Examples:
        "123456789" → True (pure number)
        "LOT:ABC123" → True (lot number)
        "BATCH:XYZ789" → True (batch code)
        "EXP:12/2025" → True (expiry date)
        "SKU:ABC-123-XYZ" → True (SKU code)
        "PARACETAMOL 500MG" → False (valid medical item)
    
    Args:
        text: Text to check
        
    Returns:
        True if text is a non-medical artifact, False otherwise
    """
    if not text or not isinstance(text, str):
        return True  # Empty is an artifact
    
    text_upper = text.strip().upper()
    
    # Empty or very short
    if len(text_upper) < 2:
        return True
    
    # PHASE-1: Non-medical artifact patterns
    NON_MEDICAL_PATTERNS = [
        r'^\d+$',  # Pure numbers (e.g., "123456789")
        r'^[A-Z0-9]{10,}$',  # Long alphanumeric codes (e.g., "ABC123XYZ456")
        r'\bLOT[:\s]*[A-Z0-9\-]+',  # Lot numbers
        r'\bBATCH[:\s]*[A-Z0-9\-]+',  # Batch codes
        r'\bEXP[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # Expiry dates
        r'\bSKU[:\s]*[A-Z0-9\-]+',  # SKU codes
        r'^\s*$',  # Whitespace only
        r'^[\W_]+$',  # Only special characters
        r'^\(\d+\)$',  # Just a code in parentheses
    ]
    
    for pattern in NON_MEDICAL_PATTERNS:
        if re.match(pattern, text_upper):
            return True
    
    return False


def is_administrative_charge(text: str) -> bool:
    """
    Check if text represents an administrative charge (non-comparable item).
    
    PHASE-1 REQUIREMENT: Identify administrative/processing charges that:
    - Exist in the bill
    - Cannot be compared against tie-up rates
    - Should be marked as ALLOWED_NOT_COMPARABLE
    
    Examples:
        "Registration Fee" → True
        "Admission Charges" → True
        "Processing Fee" → True
        "File Charges" → True
        "Consultation" → False (this is a medical service)
        "X-Ray" → False (this is a medical service)
    
    Args:
        text: Item name to check
        
    Returns:
        True if item is an administrative charge, False otherwise
    """
    if not text or not isinstance(text, str):
        return False
    
    text_lower = text.strip().lower()
    
    # PHASE-1: Administrative charge patterns
    ADMIN_PATTERNS = [
        r'\b(registration|admission|processing|file)\s+(fee|charge)s?\b',
        r'\b(hospital|facility|service)\s+(fee|charge)s?\b',
        r'\badmin(istrative)?\s+(fee|charge)s?\b',
        r'\bdeposit\b',
        r'\badvance\s+payment\b',
        r'\bmiscellaneous\s+(fee|charge)s?\b',
        r'\bconveyance\s+(fee|charge)s?\b',
        r'\bdocument(ation)?\s+(fee|charge)s?\b',
        r'\brecord\s+(fee|charge)s?\b',
        r'\bcertificate\s+(fee|charge)s?\b',
    ]
    
    for pattern in ADMIN_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    
    return False


def preprocess_for_matching(
    text: str,
    text_type: str = "item"
) -> str:
    """
    Unified preprocessing function for matching.
    
    Args:
        text: Raw text to preprocess
        text_type: Type of text ("item", "category", "hospital")
        
    Returns:
        Preprocessed text ready for embedding/matching
    """
    if text_type == "item":
        return normalize_bill_item_text(text)
    elif text_type == "category":
        return normalize_category_name(text)
    else:
        # For hospital names, just basic cleanup
        return text.strip().lower()


# =============================================================================
# Validation and Testing
# =============================================================================

def validate_normalization(original: str, normalized: str) -> dict:
    """
    Validate normalization result and return diagnostics.
    
    Args:
        original: Original text
        normalized: Normalized text
        
    Returns:
        Dict with validation results
    """
    return {
        "original": original,
        "normalized": normalized,
        "original_length": len(original),
        "normalized_length": len(normalized),
        "removed_chars": len(original) - len(normalized),
        "is_empty": len(normalized) == 0,
        "has_numbers": bool(re.search(r"\d", normalized)),
        "has_special_chars": bool(re.search(r"[^\w\s]", normalized)),
    }


# =============================================================================
# Example Usage and Testing
# =============================================================================

if __name__ == "__main__":
    # Test cases
    test_cases = [
        "1. CONSULTATION - FIRST VISIT | Dr. Vivek JaCob P",
        "MRI BRAIN | Dr. Vivek Jacob Philip",
        "2) CT Scan - Abdomen",
        "BLOOD TEST - CBC",
        "X-Ray Chest PA View | Dr. Smith",
        "Consultation – First Visit",
        "Hospital -",
        "Hospital",
    ]
    
    print("Bill Item Normalization Test Cases:")
    print("=" * 80)
    
    for test in test_cases:
        normalized = normalize_bill_item_text(test)
        skip = should_skip_category(test)
        
        print(f"\nOriginal:   '{test}'")
        print(f"Normalized: '{normalized}'")
        print(f"Skip:       {skip}")
        print("-" * 80)

"""
Medical Core Term Extraction for Bill Item Matching.

Handles noisy medical inventory strings by extracting only the medical core:
- Drug/procedure name
- Strength/dosage
- Key medical identifiers

Removes inventory metadata:
- Lot numbers, batch IDs
- Expiry dates
- Brand/vendor suffixes
- HS/SKU codes
- Packaging details

Example:
    "(30049099) NICORANDIL-TABLET-5MG-KORANDIL- |GTF"
    → "nicorandil 5mg"
    
This is CRITICAL for matching medicines, implants, and consumables.
"""

from __future__ import annotations

import re
from typing import Optional, List


# =============================================================================
# Medical Core Extraction Patterns
# =============================================================================

# Patterns to remove (inventory metadata)
INVENTORY_REMOVAL_PATTERNS = [
    # HS codes, SKU codes in parentheses
    r'\(\d{6,}\)',  # (30049099), (123456789)
    r'\[\d{6,}\]',  # [30049099]
    
    # Lot numbers and batch IDs
    r'\bLOT[\s:]*[A-Z0-9\-]+',
    r'\bBATCH[\s:]*[A-Z0-9\-]+',
    r'\bLOT\s*NO[\s:]*[A-Z0-9\-]+',
    r'\bBATCH\s*NO[\s:]*[A-Z0-9\-]+',
    
    # Expiry dates
    r'\bEXP[\s:]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
    r'\bEXPIRY[\s:]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
    r'\bMFG[\s:]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
    
    # Brand/vendor suffixes (common patterns)
    r'\|[A-Z]{2,4}$',  # |GTF, |ABC, |PHARMA
    r'-\s*[A-Z]{2,4}$',  # - GTF, - ABC
    
    # Packaging details
    r'\b\d+\s*X\s*\d+\s*(ML|MG|GM|L|TABS?|CAPS?)',  # 10X10ML, 5X5TABS
    r'\bSTRIP\s*OF\s*\d+',
    r'\bBOX\s*OF\s*\d+',
    r'\bPACK\s*OF\s*\d+',
    
    # Serial numbers at start
    r'^\d+[\.\)]\s*',  # 1. 2) 3.
    
    # Trailing dashes and pipes
    r'-+$',
    r'\|+$',
]

# Patterns to identify and preserve medical core
MEDICAL_CORE_PATTERNS = [
    # Drug name + strength (most common)
    # Example: NICORANDIL 5MG, PARACETAMOL 500MG
    r'([A-Z][A-Z\s]+?)\s*[-\s]*(\d+\.?\d*\s*(?:MG|MCG|GM|ML|IU|UNITS?))',
    
    # Drug name + form + strength
    # Example: NICORANDIL TABLET 5MG
    r'([A-Z][A-Z\s]+?)\s+(TABLET|CAPSULE|INJECTION|SYRUP|CREAM|OINTMENT)\s*[-\s]*(\d+\.?\d*\s*(?:MG|MCG|GM|ML|IU|UNITS?))',
    
    # Procedure/test name (no strength)
    # Example: MRI BRAIN, CT SCAN, CONSULTATION
    r'([A-Z][A-Z\s]{2,}?)(?:\s*[-|]|\s*$)',
]


# =============================================================================
# Core Extraction Functions
# =============================================================================

def extract_medical_core(text: str) -> str:
    """
    Extract medical core from noisy bill item string.
    
    Strategy:
    1. Remove inventory metadata (lot numbers, SKUs, etc.)
    2. Try to match medical core patterns (drug + strength)
    3. Clean and normalize remaining text
    4. Return core medical term only
    
    Examples:
        "(30049099) NICORANDIL-TABLET-5MG-KORANDIL- |GTF"
        → "nicorandil 5mg"
        
        "PARACETAMOL 500MG STRIP OF 10 LOT:ABC123"
        → "paracetamol 500mg"
        
        "1. CONSULTATION - FIRST VISIT | Dr. Vivek"
        → "consultation"
        
        "MRI BRAIN | Dr. Vivek Jacob Philip"
        → "mri brain"
    
    Args:
        text: Raw bill item text from OCR
        
    Returns:
        Extracted medical core (lowercase, cleaned)
    """
    if not text or not isinstance(text, str):
        return ""
    
    original = text
    cleaned = text.strip().upper()
    
    # Step 1: Remove inventory metadata
    for pattern in INVENTORY_REMOVAL_PATTERNS:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
    
    # Step 2: Try to extract medical core using patterns
    medical_core = None
    
    # Try drug name + strength patterns
    for pattern in MEDICAL_CORE_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            groups = match.groups()
            # Combine matched groups (drug name + strength)
            medical_core = ' '.join(g for g in groups if g).strip()
            break
    
    # If no pattern matched, use cleaned text
    if not medical_core:
        medical_core = cleaned
    
    # Step 3: Additional cleaning
    # Remove common noise words
    noise_words = [
        'TABLET', 'CAPSULE', 'INJECTION', 'SYRUP', 'CREAM', 'OINTMENT',
        'STRIP', 'BOX', 'PACK', 'BOTTLE', 'VIAL',
        'FIRST', 'VISIT', 'FOLLOW', 'UP', 'FOLLOWUP',
    ]
    
    tokens = medical_core.split()
    filtered_tokens = []
    
    for token in tokens:
        # Keep if it's a strength indicator
        if re.match(r'\d+\.?\d*(?:MG|MCG|GM|ML|IU|UNITS?)', token, re.IGNORECASE):
            filtered_tokens.append(token)
        # Keep if it's not a noise word
        elif token not in noise_words and len(token) > 1:
            filtered_tokens.append(token)
    
    medical_core = ' '.join(filtered_tokens)
    
    # Step 4: Final normalization
    # Remove special characters except spaces and numbers
    medical_core = re.sub(r'[^\w\s]', ' ', medical_core)
    
    # Normalize whitespace
    medical_core = re.sub(r'\s+', ' ', medical_core)
    
    # Lowercase
    medical_core = medical_core.lower().strip()
    
    # Log extraction for debugging
    if medical_core != original.lower().strip():
        # Only log if significant change
        pass  # Logging will be added in integration
    
    return medical_core


def extract_strength(text: str) -> Optional[str]:
    """
    Extract strength/dosage from medical text.
    
    Examples:
        "NICORANDIL 5MG" → "5mg"
        "PARACETAMOL 500MG" → "500mg"
        "INSULIN 100IU" → "100iu"
    
    Args:
        text: Medical text
        
    Returns:
        Strength string or None
    """
    # Match strength patterns
    strength_pattern = r'(\d+\.?\d*)\s*(MG|MCG|GM|ML|IU|UNITS?)'
    match = re.search(strength_pattern, text, re.IGNORECASE)
    
    if match:
        value = match.group(1)
        unit = match.group(2).lower()
        return f"{value}{unit}"
    
    return None


def extract_drug_name(text: str) -> str:
    """
    Extract drug/procedure name from medical text.
    
    Removes strength and form, keeps only the name.
    
    Examples:
        "NICORANDIL 5MG" → "nicorandil"
        "PARACETAMOL TABLET 500MG" → "paracetamol"
        "MRI BRAIN" → "mri brain"
    
    Args:
        text: Medical text (should be cleaned)
        
    Returns:
        Drug/procedure name
    """
    # Remove strength
    text = re.sub(r'\d+\.?\d*\s*(?:MG|MCG|GM|ML|IU|UNITS?)', '', text, flags=re.IGNORECASE)
    
    # Remove form
    text = re.sub(r'\b(TABLET|CAPSULE|INJECTION|SYRUP|CREAM|OINTMENT)\b', '', text, flags=re.IGNORECASE)
    
    # Clean and normalize
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.lower().strip()


def is_medical_item(text: str) -> bool:
    """
    Check if text appears to be a medical item (vs administrative).
    
    Args:
        text: Text to check
        
    Returns:
        True if appears to be medical item
    """
    text_upper = text.upper()
    
    # Check for medical indicators
    medical_indicators = [
        r'\d+\s*(?:MG|MCG|GM|ML|IU|UNITS?)',  # Has strength
        r'\b(?:TABLET|CAPSULE|INJECTION|SYRUP|CREAM|OINTMENT)\b',  # Has form
        r'\b(?:MRI|CT|X-RAY|ULTRASOUND|ECG|ECHO)\b',  # Imaging
        r'\b(?:CONSULTATION|PROCEDURE|SURGERY|OPERATION)\b',  # Procedures
    ]
    
    for pattern in medical_indicators:
        if re.search(pattern, text_upper):
            return True
    
    return False


# =============================================================================
# Testing and Validation
# =============================================================================

if __name__ == "__main__":
    # Test cases from real medical bills
    test_cases = [
        # Medicines with inventory metadata
        "(30049099) NICORANDIL-TABLET-5MG-KORANDIL- |GTF",
        "PARACETAMOL 500MG STRIP OF 10 LOT:ABC123",
        "INSULIN INJECTION 100IU BATCH:XYZ789 EXP:12/2025",
        "ASPIRIN-TABLET-75MG-DISPRIN- |PHARMA",
        
        # Procedures (should work like before)
        "1. CONSULTATION - FIRST VISIT | Dr. Vivek JaCob P",
        "MRI BRAIN | Dr. Vivek Jacob Philip",
        "2) CT Scan - Abdomen",
        
        # Implants/consumables
        "STENT CORONARY (HS:90183100) BRAND:MEDTRONIC",
        "SUTURE 3-0 VICRYL LOT:ABC123",
    ]
    
    print("Medical Core Extraction Test Cases:")
    print("=" * 80)
    
    for test in test_cases:
        core = extract_medical_core(test)
        strength = extract_strength(core)
        drug_name = extract_drug_name(core)
        is_medical = is_medical_item(test)
        
        print(f"\nOriginal:  '{test}'")
        print(f"Core:      '{core}'")
        print(f"Drug Name: '{drug_name}'")
        print(f"Strength:  '{strength}'")
        print(f"Medical:   {is_medical}")
        print("-" * 80)

"""Quick test of text normalization functionality."""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.verifier.text_normalizer import (
    normalize_bill_item_text,
    should_skip_category,
    validate_normalization
)

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
    "diagnostics_tests",
    "radiology",
]

print("="*80)
print("TEXT NORMALIZATION TEST RESULTS")
print("="*80)

for test in test_cases:
    normalized = normalize_bill_item_text(test)
    skip = should_skip_category(test)
    
    print(f"\nOriginal:   '{test}'")
    print(f"Normalized: '{normalized}'")
    print(f"Skip:       {skip}")
    print("-"*80)

print("\n✅ Normalization test complete!")

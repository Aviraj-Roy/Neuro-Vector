"""
Backend Testing Script for Hospital Field Removal Refactoring.

This script demonstrates and tests the new flow where hospital name
is provided explicitly at upload time instead of being extracted from bills.

Usage:
    python test_backend.py --hospital "Apollo Hospital"
    python test_backend.py --hospital "Fortis Hospital" --bill "path/to/bill.pdf"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add backend to path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.main import process_bill
from app.verifier.api import verify_bill_from_mongodb_sync
from app.verifier.hospital_validator import (
    list_available_hospitals,
    validate_hospital_exists,
    normalize_hospital_name,
    get_tieup_file_path
)
from app.config import TIEUP_DIR


def test_hospital_validation(hospital_name: str):
    """Test hospital validation logic."""
    print("\n" + "="*80)
    print("TESTING HOSPITAL VALIDATION")
    print("="*80)
    
    print(f"\n1. Testing hospital: {hospital_name}")
    print(f"   Normalized slug: {normalize_hospital_name(hospital_name)}")
    
    tieup_path = get_tieup_file_path(hospital_name, str(TIEUP_DIR))
    print(f"   Expected tie-up file: {tieup_path}")
    print(f"   File exists: {tieup_path.exists()}")
    
    is_valid, error_msg = validate_hospital_exists(hospital_name, str(TIEUP_DIR))
    if is_valid:
        print(f"   ✅ Validation passed")
    else:
        print(f"   ❌ Validation failed:")
        print(f"      {error_msg}")
        return False
    
    return True


def test_available_hospitals():
    """List all available hospitals."""
    print("\n" + "="*80)
    print("AVAILABLE HOSPITALS")
    print("="*80)
    
    hospitals = list_available_hospitals(str(TIEUP_DIR))
    
    if not hospitals:
        print("❌ No hospitals found!")
        print(f"   Tie-up directory: {TIEUP_DIR}")
        return
    
    print(f"\nFound {len(hospitals)} hospitals:")
    for i, hospital in enumerate(hospitals, 1):
        slug = normalize_hospital_name(hospital)
        print(f"  {i}. {hospital}")
        print(f"     → File: {slug}.json")


def test_bill_processing(pdf_path: str, hospital_name: str):
    """Test bill processing with explicit hospital name."""
    print("\n" + "="*80)
    print("TESTING BILL PROCESSING")
    print("="*80)
    
    print(f"\nProcessing bill: {pdf_path}")
    print(f"Hospital: {hospital_name}")
    
    try:
        upload_id = process_bill(pdf_path, hospital_name=hospital_name)
        print(f"\n✅ Bill processed successfully!")
        print(f"   Upload ID: {upload_id}")
        return upload_id
    except Exception as e:
        print(f"\n❌ Bill processing failed:")
        print(f"   Error: {e}")
        logger.error("Bill processing error", exc_info=True)
        return None


def test_verification(upload_id: str, hospital_name: str):
    """Test verification with explicit hospital name."""
    print("\n" + "="*80)
    print("TESTING VERIFICATION")
    print("="*80)
    
    print(f"\nVerifying bill: {upload_id}")
    print(f"Hospital: {hospital_name}")
    
    try:
        result = verify_bill_from_mongodb_sync(upload_id, hospital_name=hospital_name)
        
        print(f"\n✅ Verification completed!")
        print(f"\nResults:")
        print(f"  Hospital: {result.get('hospital', 'N/A')}")
        print(f"  Matched Hospital: {result.get('matched_hospital', 'N/A')}")
        print(f"  Hospital Similarity: {result.get('hospital_similarity', 0):.2%}")
        print(f"\nSummary:")
        print(f"  GREEN (Match): {result.get('green_count', 0)}")
        print(f"  RED (Overcharged): {result.get('red_count', 0)}")
        print(f"  MISMATCH (Not Found): {result.get('mismatch_count', 0)}")
        print(f"\nFinancial:")
        print(f"  Total Bill: ₹{result.get('total_bill_amount', 0):.2f}")
        print(f"  Total Allowed: ₹{result.get('total_allowed_amount', 0):.2f}")
        print(f"  Total Extra: ₹{result.get('total_extra_amount', 0):.2f}")
        
        return True
    except Exception as e:
        print(f"\n❌ Verification failed:")
        print(f"   Error: {e}")
        logger.error("Verification error", exc_info=True)
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="Test backend hospital field removal refactoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available hospitals
  python test_backend.py --list-hospitals
  
  # Test hospital validation
  python test_backend.py --hospital "Apollo Hospital" --validate-only
  
  # Full test: process + verify
  python test_backend.py --hospital "Apollo Hospital" --bill "Apollo.pdf"
  
  # Process only (no verification)
  python test_backend.py --hospital "Fortis Hospital" --bill "bill.pdf" --no-verify
        """
    )
    
    parser.add_argument(
        "--hospital",
        type=str,
        help='Hospital name (e.g., "Apollo Hospital")'
    )
    
    parser.add_argument(
        "--bill",
        type=str,
        help="Path to bill PDF file"
    )
    
    parser.add_argument(
        "--list-hospitals",
        action="store_true",
        help="List all available hospitals and exit"
    )
    
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate hospital (don't process bill)"
    )
    
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip verification step"
    )
    
    args = parser.parse_args()
    
    # List hospitals mode
    if args.list_hospitals:
        test_available_hospitals()
        return
    
    # Validate hospital parameter
    if not args.hospital:
        print("❌ Error: --hospital parameter is required")
        print("\nUse --list-hospitals to see available hospitals")
        parser.print_help()
        sys.exit(1)
    
    # Test hospital validation
    if not test_hospital_validation(args.hospital):
        print("\n❌ Hospital validation failed. Exiting.")
        print("\nUse --list-hospitals to see available hospitals")
        sys.exit(1)
    
    # Validate-only mode
    if args.validate_only:
        print("\n✅ Validation complete (--validate-only mode)")
        return
    
    # Full processing mode
    if not args.bill:
        print("\n❌ Error: --bill parameter is required for processing")
        print("   Use --validate-only to only test hospital validation")
        parser.print_help()
        sys.exit(1)
    
    # Resolve bill path
    bill_path = Path(args.bill)
    if not bill_path.is_absolute():
        bill_path = SCRIPT_DIR / bill_path
    
    if not bill_path.exists():
        print(f"\n❌ Error: Bill file not found: {bill_path}")
        sys.exit(1)
    
    # Process bill
    upload_id = test_bill_processing(str(bill_path), args.hospital)
    
    if not upload_id:
        print("\n❌ Testing failed at bill processing stage")
        sys.exit(1)
    
    # Verify bill (unless --no-verify)
    if not args.no_verify:
        success = test_verification(upload_id, args.hospital)
        
        if not success:
            print("\n❌ Testing failed at verification stage")
            sys.exit(1)
    else:
        print("\n⚠️  Skipping verification (--no-verify flag set)")
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)


if __name__ == "__main__":
    main()

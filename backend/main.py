"""
Main entry point for the Medical Bill Verification backend.

IMPORTANT: Always run using module execution to ensure consistent imports:
    ✅ CORRECT: python -m backend.main
    ❌ WRONG:   python backend/main.py

This ensures:
- Absolute imports work correctly
- Paths resolve regardless of current working directory
- Dependencies are validated at startup
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Add backend directory to Python path to enable absolute imports
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Configure logging BEFORE dependency check
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# ============================================================================
# STARTUP DEPENDENCY VALIDATION
# ============================================================================
# Check all required dependencies before proceeding
# This catches missing packages early with clear error messages
try:
    from app.utils.dependency_check import check_all_dependencies, check_external_tools
    
    logger.info("="*80)
    logger.info("Starting Medical Bill Verification Backend")
    logger.info("="*80)
    
    # Check Python dependencies
    check_all_dependencies()
    
    # Check external tools (MongoDB, Ollama, etc.) - warnings only
    check_external_tools()
    
except Exception as e:
    logger.error(f"\n{str(e)}")
    logger.error("\n❌ Startup validation failed. Fix dependencies and try again.")
    sys.exit(1)

# Now we can safely import from app
from app.main import process_bill

logger.info("✅ All startup checks passed. System ready.\n")





if __name__ == "__main__":
    """
    CLI entry point for bill processing.
    
    Usage:
        python -m backend.main --bill path/to/bill.pdf --hospital "Apollo Hospital"
        python -m backend.main --bill Apollo.pdf --hospital "Fortis Hospital"
    """
    import argparse
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Medical Bill Processing and Verification System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backend.main --bill Apollo.pdf --hospital "Apollo Hospital"
  python -m backend.main --bill M_Bill.pdf --hospital "Manipal Hospital"
  
Available hospitals are determined by JSON files in backend/data/tieups/
        """
    )
    
    parser.add_argument(
        "--bill",
        type=str,
        required=True,
        help="Path to the medical bill PDF file"
    )
    
    parser.add_argument(
        "--hospital",
        type=str,
        required=True,
        help='Hospital name (e.g., "Apollo Hospital", "Fortis Hospital")'
    )
    
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip verification step (only process and extract)"
    )
    
    args = parser.parse_args()
    
    # Resolve PDF path
    pdf_path = BACKEND_DIR.parent / args.bill
    
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        logger.info("Please provide a valid PDF path")
        sys.exit(1)
    
    logger.info(f"Processing bill: {pdf_path}")
    logger.info(f"Hospital: {args.hospital}")
    
    try:
        # Step 1: Process and extract bill data
        bill_id = process_bill(str(pdf_path), hospital_name=args.hospital)
        print(f"\n✅ Successfully processed bill!")
        print(f"Upload ID: {bill_id}")
        print(f"Hospital: {args.hospital}")
        
        # Step 2: Run verification (LLM comparison) unless --no-verify
        if not args.no_verify:
            logger.info("\n" + "="*80)
            logger.info("Running Bill Verification (LLM Comparison)")
            logger.info("="*80)
            
            try:
                from app.verifier.api import verify_bill_from_mongodb_sync
                from app.db.mongo_client import MongoDBClient
                
                # Fetch bill from MongoDB
                db = MongoDBClient(validate_schema=False)
                bill_doc = db.get_bill(bill_id)
                
                if not bill_doc:
                    logger.warning("Bill not found in MongoDB for verification")
                else:
                    # Run verification with explicit hospital name
                    verification_result = verify_bill_from_mongodb_sync(
                        bill_id, 
                        hospital_name=args.hospital
                    )
                    
                    # Display verification results
                    print("\n" + "="*80)
                    print("VERIFICATION RESULTS")
                    print("="*80)
                    print(f"Hospital: {verification_result.get('hospital', 'N/A')}")
                    print(f"Matched Hospital: {verification_result.get('matched_hospital', 'N/A')}")
                    print(f"Hospital Similarity: {verification_result.get('hospital_similarity', 0):.2%}")
                    print(f"\nSummary:")
                    print(f"  ✅ GREEN (Match): {verification_result.get('green_count', 0)}")
                    print(f"  ❌ RED (Overcharged): {verification_result.get('red_count', 0)}")
                    print(f"  ⚠️  MISMATCH (Not Found): {verification_result.get('mismatch_count', 0)}")
                    print(f"\nFinancial Summary:")
                    print(f"  Total Bill Amount: ₹{verification_result.get('total_bill_amount', 0):.2f}")
                    print(f"  Total Allowed Amount: ₹{verification_result.get('total_allowed_amount', 0):.2f}")
                    print(f"  Total Extra Amount: ₹{verification_result.get('total_extra_amount', 0):.2f}")
                    
                    # Display category-wise results
                    print(f"\nCategory-wise Results:")
                    for cat_result in verification_result.get('results', []):
                        cat_name = cat_result.get('category', 'Unknown')
                        matched_cat = cat_result.get('matched_category', 'N/A')
                        print(f"\n  📁 {cat_name} → {matched_cat}")
                        
                        for item in cat_result.get('items', [])[:5]:  # Show first 5 items per category
                            status = item.get('status', 'UNKNOWN')
                            status_icon = "✅" if status == "GREEN" else "❌" if status == "RED" else "⚠️"
                            print(f"    {status_icon} {item.get('bill_item', 'N/A')[:50]} - {status}")
                            if status == "RED":
                                print(f"       Bill: ₹{item.get('bill_amount', 0):.2f}, Allowed: ₹{item.get('allowed_amount', 0):.2f}, Extra: ₹{item.get('extra_amount', 0):.2f}")
                    
                    print("\n" + "="*80)
                    logger.info("Verification complete!")
                    
            except ImportError as e:
                logger.warning(f"Verifier not available: {e}")
                logger.info("Skipping verification step")
            except Exception as e:
                logger.error(f"Verification failed: {e}", exc_info=True)
                logger.info("Bill was processed successfully, but verification encountered an error")
        else:
            logger.info("Skipping verification (--no-verify flag set)")
        
    except Exception as e:
        logger.error(f"Failed to process bill: {e}", exc_info=True)
        sys.exit(1)

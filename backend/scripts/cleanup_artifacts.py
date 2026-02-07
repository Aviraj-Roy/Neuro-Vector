"""
MongoDB Cleanup Script: Remove Legacy OCR Artifacts

PHASE-7: One-time cleanup of "Hospital - / UNKNOWN / ₹0" artifacts.

This script safely removes legacy OCR artifacts from the MongoDB bills collection
without affecting valid data.

Usage:
    python -m backend.scripts.cleanup_artifacts
    
    Or from MongoDB shell:
    db.bills.updateMany(
        { "items.Hospital - ": { $exists: true } },
        { $unset: { "items.Hospital - ": "" } }
    )
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def cleanup_hospital_artifacts():
    """
    Remove legacy 'Hospital - / UNKNOWN / ₹0' artifacts from MongoDB.
    
    This is a safe, surgical cleanup that:
    1. Finds documents with "Hospital - " category (note trailing space)
    2. Removes the entire category (which contains only artifacts)
    3. Does NOT delete documents
    4. Does NOT affect valid hospital charges in other categories
    
    Returns:
        Number of documents modified
    """
    from app.db.mongo_client import MongoDBClient
    
    logger.info("=" * 80)
    logger.info("PHASE-7: MongoDB Artifact Cleanup")
    logger.info("=" * 80)
    
    db = MongoDBClient(validate_schema=False)
    collection = db.collection
    
    # Step 1: Find affected documents
    logger.info("\nStep 1: Scanning for artifacts...")
    affected = collection.count_documents({
        "items.Hospital - ": { "$exists": True }
    })
    
    logger.info(f"Found {affected} documents with 'Hospital - ' category")
    
    if affected == 0:
        logger.info("✅ No cleanup needed - database is clean")
        return 0
    
    # Step 2: Show sample before cleanup
    logger.info("\nStep 2: Sample artifact data (before cleanup):")
    sample = collection.find_one({"items.Hospital - ": { "$exists": True }})
    if sample:
        hospital_items = sample.get("items", {}).get("Hospital - ", [])
        logger.info(f"  Upload ID: {sample.get('upload_id', 'N/A')}")
        logger.info(f"  Hospital - items: {hospital_items}")
    
    # Step 3: Confirm cleanup
    logger.info(f"\n⚠️  About to remove 'Hospital - ' category from {affected} documents")
    logger.info("This will NOT delete documents, only remove the artifact category")
    
    response = input("\nProceed with cleanup? (yes/no): ")
    if response.lower() != "yes":
        logger.info("❌ Cleanup cancelled by user")
        return 0
    
    # Step 4: Perform cleanup
    logger.info("\nStep 4: Removing artifacts...")
    result = collection.update_many(
        { "items.Hospital - ": { "$exists": True } },
        { "$unset": { "items.Hospital - ": "" } }
    )
    
    logger.info(f"✅ Cleaned {result.modified_count} documents")
    logger.info(f"   Removed 'Hospital - ' category from all affected bills")
    
    # Step 5: Verify cleanup
    logger.info("\nStep 5: Verifying cleanup...")
    remaining = collection.count_documents({
        "items.Hospital - ": { "$exists": True }
    })
    
    if remaining == 0:
        logger.info("✅ Verification passed - no artifacts remaining")
    else:
        logger.warning(f"⚠️  {remaining} documents still have 'Hospital - ' category")
    
    logger.info("\n" + "=" * 80)
    logger.info("Cleanup complete!")
    logger.info("=" * 80)
    
    return result.modified_count


def cleanup_unknown_zero_items():
    """
    Alternative cleanup: Remove only UNKNOWN/₹0 items (more conservative).
    
    This approach:
    1. Finds items with name "UNKNOWN" and amount ₹0
    2. Removes only those items using $pull
    3. Removes empty categories after item removal
    
    Returns:
        Number of documents modified
    """
    from app.db.mongo_client import MongoDBClient
    
    logger.info("=" * 80)
    logger.info("PHASE-7: Conservative Artifact Cleanup (UNKNOWN/₹0 items only)")
    logger.info("=" * 80)
    
    db = MongoDBClient(validate_schema=False)
    collection = db.collection
    
    # Step 1: Remove UNKNOWN/₹0 items from "Hospital - " category
    logger.info("\nStep 1: Removing UNKNOWN/₹0 items...")
    result = collection.update_many(
        { 
            "items.Hospital - ": { 
                "$elemMatch": { 
                    "item_name": "UNKNOWN",
                    "final_amount": 0 
                } 
            } 
        },
        { 
            "$pull": { 
                "items.Hospital - ": { 
                    "item_name": "UNKNOWN",
                    "final_amount": 0 
                } 
            } 
        }
    )
    
    logger.info(f"✅ Modified {result.modified_count} documents (removed UNKNOWN items)")
    
    # Step 2: Remove empty "Hospital - " categories
    logger.info("\nStep 2: Removing empty categories...")
    result2 = collection.update_many(
        { "items.Hospital - ": { "$size": 0 } },
        { "$unset": { "items.Hospital - ": "" } }
    )
    
    logger.info(f"✅ Removed {result2.modified_count} empty 'Hospital - ' categories")
    
    logger.info("\n" + "=" * 80)
    logger.info("Conservative cleanup complete!")
    logger.info("=" * 80)
    
    return result.modified_count + result2.modified_count


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Clean up legacy OCR artifacts from MongoDB"
    )
    parser.add_argument(
        "--conservative",
        action="store_true",
        help="Use conservative cleanup (remove only UNKNOWN/₹0 items)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.conservative:
            count = cleanup_unknown_zero_items()
        else:
            count = cleanup_hospital_artifacts()
        
        logger.info(f"\n✅ Successfully cleaned {count} documents")
        
    except Exception as e:
        logger.error(f"\n❌ Cleanup failed: {e}", exc_info=True)
        sys.exit(1)

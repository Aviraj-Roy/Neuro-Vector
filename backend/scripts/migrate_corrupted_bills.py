"""Safe migration utility for legacy corrupted bill documents.

Goals:
- Identify duplicate documents for the same upload_id.
- Identify page-level/intermediate artifacts in main bills collection.
- Archive removable records before deletion.

Usage:
    python backend/scripts/migrate_corrupted_bills.py --dry-run
    python backend/scripts/migrate_corrupted_bills.py --apply
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.db.mongo_client import MongoDBClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_corrupted_bills")


def _is_page_artifact(doc: Dict[str, Any]) -> bool:
    source_pdf = str(doc.get("source_pdf") or "").lower()
    if "_page_" in source_pdf and source_pdf.endswith(".png"):
        return True
    if doc.get("document_type") in {"page", "intermediate", "ocr_page"}:
        return True
    if not doc.get("upload_id"):
        return True
    return False


def _select_keeper(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Keep completed record first; then latest updated; then latest created.
    def score(d: Dict[str, Any]):
        return (
            1 if str(d.get("status") or "").lower() == "completed" else 0,
            str(d.get("updated_at") or ""),
            str(d.get("created_at") or ""),
        )

    return sorted(docs, key=score, reverse=True)[0]


def run_migration(apply: bool) -> None:
    db = MongoDBClient(validate_schema=False)
    col = db.collection
    archive = db.db["bills_archive"]
    migration_id = f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 1) Duplicate upload_id docs (legacy data where _id != upload_id may exist)
    duplicate_groups = list(
        col.aggregate(
            [
                {"$match": {"upload_id": {"$exists": True, "$ne": ""}}},
                {"$group": {"_id": "$upload_id", "ids": {"$push": "$_id"}, "count": {"$sum": 1}}},
                {"$match": {"count": {"$gt": 1}}},
            ]
        )
    )

    duplicates_to_remove: List[Dict[str, Any]] = []
    for group in duplicate_groups:
        upload_id = group["_id"]
        docs = list(col.find({"upload_id": upload_id}))
        keeper = _select_keeper(docs)
        for d in docs:
            if d["_id"] != keeper["_id"]:
                duplicates_to_remove.append(d)

    # 2) Page/intermediate artifacts
    artifact_candidates = [d for d in col.find({}) if _is_page_artifact(d)]

    # Deduplicate combined removal list by _id
    remove_by_id = {}
    for d in duplicates_to_remove + artifact_candidates:
        remove_by_id[str(d["_id"])] = d
    to_remove = list(remove_by_id.values())

    logger.info("Duplicate groups found: %s", len(duplicate_groups))
    logger.info("Artifact candidates found: %s", len(artifact_candidates))
    logger.info("Total docs marked for archive/removal: %s", len(to_remove))

    if not apply:
        logger.info("Dry-run complete. No data changed.")
        return

    for doc in to_remove:
        archived = dict(doc)
        archived["_archived_from_collection"] = col.name
        archived["_migration_id"] = migration_id
        archived["_archived_at"] = datetime.now().isoformat()
        archive.insert_one(archived)
        col.delete_one({"_id": doc["_id"]})

    logger.info("Migration applied. Archived + removed documents: %s", len(to_remove))
    logger.info("Archive collection: %s", archive.name)
    logger.info("Migration ID: %s", migration_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate/cleanup corrupted bill documents safely.")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode (default behavior)")
    args = parser.parse_args()

    apply = bool(args.apply and not args.dry_run)
    run_migration(apply=apply)


if __name__ == "__main__":
    main()


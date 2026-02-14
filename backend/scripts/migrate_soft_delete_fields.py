"""Backfill soft-delete fields on legacy bill documents.

Usage:
    python -m backend.scripts.migrate_soft_delete_fields
"""

from __future__ import annotations

from app.db.mongo_client import MongoDBClient


def main() -> None:
    db = MongoDBClient(validate_schema=False)
    col = db.collection

    result = col.update_many(
        {"is_deleted": {"$exists": False}},
        {"$set": {"is_deleted": False}},
    )
    print(f"Backfilled is_deleted on {result.modified_count} documents")

    result = col.update_many(
        {"deleted_at": {"$exists": False}},
        {"$set": {"deleted_at": None}},
    )
    print(f"Backfilled deleted_at on {result.modified_count} documents")

    result = col.update_many(
        {"deleted_by": {"$exists": False}},
        {"$set": {"deleted_by": None}},
    )
    print(f"Backfilled deleted_by on {result.modified_count} documents")

    result = col.update_many(
        {"delete_mode": {"$exists": False}},
        {"$set": {"delete_mode": None}},
    )
    print(f"Backfilled delete_mode on {result.modified_count} documents")


if __name__ == "__main__":
    main()

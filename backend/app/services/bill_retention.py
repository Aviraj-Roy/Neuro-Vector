from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.config import BILL_RETENTION_CLEANUP_INTERVAL_SECONDS, BILL_RETENTION_DAYS
from app.db.mongo_client import MongoDBClient

logger = logging.getLogger(__name__)

_RETENTION_LOCK = threading.Lock()
_RETENTION_WAKE_EVENT = threading.Event()
_RETENTION_THREAD: Optional[threading.Thread] = None

_DEFAULT_RETENTION_DAYS = BILL_RETENTION_DAYS
_DEFAULT_CLEANUP_INTERVAL_SECONDS = BILL_RETENTION_CLEANUP_INTERVAL_SECONDS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_deleted_at(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_expired_soft_deleted_bill(
    *,
    is_deleted: bool,
    deleted_at: Any,
    now_utc: Optional[datetime] = None,
    retention_days: int = _DEFAULT_RETENTION_DAYS,
) -> bool:
    if not is_deleted:
        return False
    deleted_dt = parse_deleted_at(deleted_at)
    if deleted_dt is None:
        return False
    effective_now = now_utc or _utc_now()
    cutoff = effective_now - timedelta(days=max(0, int(retention_days)))
    return deleted_dt <= cutoff


def cleanup_expired_soft_deleted_bills(
    *,
    db: Optional[MongoDBClient] = None,
    now_utc: Optional[datetime] = None,
    retention_days: int = _DEFAULT_RETENTION_DAYS,
) -> Dict[str, int]:
    mongo = db or MongoDBClient(validate_schema=False)
    effective_now = now_utc or _utc_now()
    retention_days = max(0, int(retention_days))

    stats: Dict[str, int] = {
        "scanned": 0,
        "eligible": 0,
        "deleted": 0,
        "failed": 0,
    }

    cursor = mongo.collection.find(
        {
            "$and": [
                {"upload_id": {"$exists": True, "$ne": ""}},
                {
                    "$or": [
                        {"is_deleted": True},
                        {"deleted_at": {"$exists": True, "$ne": None}},
                    ]
                },
            ]
        },
        {"_id": 1, "upload_id": 1, "is_deleted": 1, "deleted_at": 1},
    )

    for doc in cursor:
        stats["scanned"] += 1
        upload_id = str(doc.get("upload_id") or doc.get("_id") or "").strip()
        if not upload_id:
            continue
        is_deleted = bool(doc.get("is_deleted") is True or doc.get("deleted_at"))
        if not is_expired_soft_deleted_bill(
            is_deleted=is_deleted,
            deleted_at=doc.get("deleted_at"),
            now_utc=effective_now,
            retention_days=retention_days,
        ):
            continue

        stats["eligible"] += 1
        try:
            result = mongo.permanent_delete_upload(upload_id, include_active=False)
            if int(result.get("deleted_count", 0)) > 0:
                stats["deleted"] += 1
                logger.info("Retention cleanup permanently deleted upload_id=%s", upload_id)
            else:
                logger.info("Retention cleanup found nothing to delete for upload_id=%s", upload_id)
        except Exception as exc:
            stats["failed"] += 1
            logger.error("Retention cleanup failed for upload_id=%s: %s", upload_id, exc, exc_info=True)

    return stats


def _retention_worker_loop() -> None:
    interval_seconds = max(60, _DEFAULT_CLEANUP_INTERVAL_SECONDS)
    retention_days = max(0, _DEFAULT_RETENTION_DAYS)
    logger.info(
        "Bill retention worker started (retention_days=%s, interval_seconds=%s)",
        retention_days,
        interval_seconds,
    )
    while True:
        try:
            stats = cleanup_expired_soft_deleted_bills(retention_days=retention_days)
            logger.info(
                "Retention cleanup run complete: scanned=%s eligible=%s deleted=%s failed=%s",
                stats["scanned"],
                stats["eligible"],
                stats["deleted"],
                stats["failed"],
            )
        except Exception as exc:
            logger.error("Retention worker iteration failed: %s", exc, exc_info=True)

        _RETENTION_WAKE_EVENT.wait(timeout=float(interval_seconds))
        _RETENTION_WAKE_EVENT.clear()


def start_bill_retention_worker() -> None:
    global _RETENTION_THREAD
    with _RETENTION_LOCK:
        if _RETENTION_THREAD and _RETENTION_THREAD.is_alive():
            return
        _RETENTION_THREAD = threading.Thread(
            target=_retention_worker_loop,
            daemon=True,
            name="bill-retention-worker",
        )
        _RETENTION_THREAD.start()
    _RETENTION_WAKE_EVENT.set()

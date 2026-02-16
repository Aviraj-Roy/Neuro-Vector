from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List

# Ensure `app` package (backend/app) is importable in test runs.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.bill_retention import (  # noqa: E402
    cleanup_expired_soft_deleted_bills,
    is_expired_soft_deleted_bill,
    parse_deleted_at,
)


def test_is_expired_soft_deleted_bill_true_for_older_than_cutoff():
    now = datetime(2026, 2, 16, 12, 0, 0, tzinfo=timezone.utc)
    deleted_at = now - timedelta(days=31)

    assert is_expired_soft_deleted_bill(
        is_deleted=True,
        deleted_at=deleted_at,
        now_utc=now,
        retention_days=30,
    )


def test_is_expired_soft_deleted_bill_false_for_recent_soft_delete():
    now = datetime(2026, 2, 16, 12, 0, 0, tzinfo=timezone.utc)
    deleted_at = now - timedelta(days=2)

    assert not is_expired_soft_deleted_bill(
        is_deleted=True,
        deleted_at=deleted_at,
        now_utc=now,
        retention_days=30,
    )


def test_parse_deleted_at_supports_iso_and_datetime():
    parsed_iso = parse_deleted_at("2026-01-01T00:00:00+00:00")
    assert parsed_iso is not None
    assert parsed_iso.tzinfo is not None

    parsed_naive_dt = parse_deleted_at(datetime(2026, 1, 1, 0, 0, 0))
    assert parsed_naive_dt is not None
    assert parsed_naive_dt.tzinfo is not None


class _FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def find(self, *_args, **_kwargs):
        return list(self.docs)


class _FakeDB:
    def __init__(self, docs: List[Dict[str, Any]], fail_ids: set[str] | None = None):
        self.collection = _FakeCollection(docs)
        self.fail_ids = fail_ids or set()
        self.deleted_ids: List[str] = []

    def permanent_delete_upload(self, upload_id: str, include_active: bool = False):
        assert include_active is False
        if upload_id in self.fail_ids:
            raise RuntimeError(f"forced failure for {upload_id}")
        self.deleted_ids.append(upload_id)
        return {"upload_id": upload_id, "deleted_count": 1}


def test_cleanup_expired_soft_deleted_bills_is_retry_safe_and_continues_on_failure():
    now = datetime(2026, 2, 16, 12, 0, 0, tzinfo=timezone.utc)
    eligible_id = "a" * 32
    failing_id = "b" * 32
    recent_id = "c" * 32
    docs = [
        {"_id": eligible_id, "upload_id": eligible_id, "is_deleted": True, "deleted_at": now - timedelta(days=40)},
        {"_id": failing_id, "upload_id": failing_id, "is_deleted": True, "deleted_at": now - timedelta(days=45)},
        {"_id": recent_id, "upload_id": recent_id, "is_deleted": True, "deleted_at": now - timedelta(days=5)},
        {"_id": "d" * 32, "upload_id": "d" * 32, "is_deleted": False, "deleted_at": None},
    ]
    fake_db = _FakeDB(docs, fail_ids={failing_id})

    stats = cleanup_expired_soft_deleted_bills(
        db=fake_db,  # type: ignore[arg-type]
        now_utc=now,
        retention_days=30,
    )

    assert stats == {"scanned": 4, "eligible": 2, "deleted": 1, "failed": 1}
    assert fake_db.deleted_ids == [eligible_id]

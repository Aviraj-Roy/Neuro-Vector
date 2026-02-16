from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.mongo_client import MongoDBClient


def _match_query(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for key, value in query.items():
        if key == "$or":
            return any(_match_query(doc, q) for q in value)
        if isinstance(value, dict):
            if "$in" in value and doc.get(key) not in value["$in"]:
                return False
            if "$ne" in value and doc.get(key) == value["$ne"]:
                return False
            if "$exists" in value:
                exists = key in doc
                if bool(value["$exists"]) != exists:
                    return False
        elif doc.get(key) != value:
            return False
    return True


class _FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def find_one_and_update(self, query, update, sort, return_document):
        matched = [d for d in self.docs if _match_query(d, query)]
        if not matched:
            return None

        def _sort_key(doc):
            key = []
            for field, direction in sort:
                raw = doc.get(field) or ""
                key.append(raw if direction == 1 else f"~{raw}")
            return tuple(key)

        target = sorted(matched, key=_sort_key)[0]
        for k, v in (update.get("$set") or {}).items():
            target[k] = v
        for k in (update.get("$unset") or {}).keys():
            target.pop(k, None)
        return target.copy()

    def find(self, query, projection):
        rows = [d for d in self.docs if _match_query(d, query)]
        out = []
        for d in rows:
            obj = {}
            for k, include in projection.items():
                if include and k in d:
                    obj[k] = d[k]
            out.append(obj)
        return out

    def find_one(self, query, projection=None):
        for d in self.docs:
            if _match_query(d, query):
                if not projection:
                    return d.copy()
                out: Dict[str, Any] = {}
                for k, include in projection.items():
                    if include and k in d:
                        out[k] = d[k]
                return out
        return None

    def update_one(self, query, update, upsert=False):
        modified = 0
        for d in self.docs:
            if _match_query(d, query):
                for k, v in (update.get("$set") or {}).items():
                    d[k] = v
                modified += 1
                break

        class _R:
            modified_count = modified
            matched_count = modified

        return _R()


def test_claim_next_pending_job_fifo():
    docs = [
        {
            "_id": "1" * 32,
            "upload_id": "1" * 32,
            "status": "PENDING",
            "queued_at": "2026-02-16T10:00:00",
            "created_at": "2026-02-16T10:00:00",
            "temp_pdf_path": "a.pdf",
        },
        {
            "_id": "2" * 32,
            "upload_id": "2" * 32,
            "status": "PENDING",
            "queued_at": "2026-02-16T10:01:00",
            "created_at": "2026-02-16T10:01:00",
            "temp_pdf_path": "b.pdf",
        },
    ]
    db = object.__new__(MongoDBClient)
    db.collection = _FakeCollection(docs)

    claimed = db.claim_next_pending_job()
    assert claimed is not None
    assert claimed["upload_id"] == "1" * 32
    assert claimed["status"] == "PROCESSING"
    assert claimed["queue_position"] is None
    assert claimed.get("processing_started_at")
    # second row stays pending until next dequeue
    assert docs[1]["status"] == "PENDING"
    assert docs[1]["queue_position"] == 1


def test_claim_next_pending_job_blocks_when_another_processing_exists():
    docs = [
        {
            "_id": "9" * 32,
            "upload_id": "9" * 32,
            "status": "PROCESSING",
            "processing_started_at": "2026-02-16T10:00:00",
            "temp_pdf_path": "x.pdf",
        },
        {
            "_id": "a" * 32,
            "upload_id": "a" * 32,
            "status": "PENDING",
            "queued_at": "2026-02-16T10:01:00",
            "created_at": "2026-02-16T10:01:00",
            "temp_pdf_path": "y.pdf",
        },
    ]
    db = object.__new__(MongoDBClient)
    db.collection = _FakeCollection(docs)

    claimed = db.claim_next_pending_job()
    assert claimed is None
    assert docs[1]["status"] == "PENDING"


def test_recover_stale_processing_jobs_marks_failed():
    stale_started = (datetime.now() - timedelta(hours=2)).isoformat()
    docs = [
        {
            "_id": "3" * 32,
            "upload_id": "3" * 32,
            "status": "PROCESSING",
            "processing_started_at": stale_started,
        },
        {
            "_id": "4" * 32,
            "upload_id": "4" * 32,
            "status": "PROCESSING",
            "processing_started_at": datetime.now().isoformat(),
        },
    ]
    db = object.__new__(MongoDBClient)
    db.collection = _FakeCollection(docs)

    recovered = db.recover_stale_processing_jobs(stale_after_seconds=300)
    assert recovered == 1
    assert docs[0]["status"] == "FAILED"
    assert "Recovered stale processing job after service restart" in docs[0]["error_message"]
    assert docs[0]["completed_at"] is not None
    assert docs[1]["status"] == "PROCESSING"


def test_mark_failed_sets_terminal_fields():
    upload_id = "f" * 32
    docs = [
        {
            "_id": upload_id,
            "upload_id": upload_id,
            "status": "PROCESSING",
            "processing_started_at": "2026-02-16T09:00:00",
        }
    ]
    db = object.__new__(MongoDBClient)
    db.collection = _FakeCollection(docs)

    db.mark_failed(upload_id, "boom")
    assert docs[0]["status"] == "FAILED"
    assert docs[0]["error_message"] == "boom"
    assert docs[0]["completed_at"] is not None

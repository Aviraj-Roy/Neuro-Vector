from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure `app` package (backend/app) is importable in test runs.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes import router


class _FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def sort(self, field: str, direction: int):
        reverse = direction == -1
        self.docs = sorted(self.docs, key=lambda d: d.get(field) or "", reverse=reverse)
        return self

    def __iter__(self):
        return iter(self.docs)


def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for key, cond in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
            continue
        if key == "$and":
            if not all(_matches(doc, sub) for sub in cond):
                return False
            continue
        value = doc.get(key)
        if isinstance(cond, dict):
            if "$exists" in cond:
                exists = key in doc
                if bool(cond["$exists"]) != exists:
                    return False
            if "$ne" in cond:
                if value == cond["$ne"]:
                    return False
            if "$in" in cond:
                if value not in cond["$in"]:
                    return False
        else:
            if value != cond:
                return False
    return True


class FakeMongoDBClient:
    shared_docs: List[Dict[str, Any]] = []
    permanent_delete_calls: List[str] = []

    def __init__(self, validate_schema: bool = False):
        self.validate_schema = validate_schema
        self.collection = self

    # collection methods
    def find(self, query: Dict[str, Any], projection: Dict[str, int]):
        matched = [d.copy() for d in FakeMongoDBClient.shared_docs if _matches(d, query)]
        out: List[Dict[str, Any]] = []
        for d in matched:
            filtered: Dict[str, Any] = {}
            for k, v in projection.items():
                if v and k in d:
                    filtered[k] = d[k]
            if "_id" in d and projection.get("_id", 0):
                filtered["_id"] = d["_id"]
            out.append(filtered)
        return _FakeCursor(out)

    def count_documents(self, query: Dict[str, Any], session=None):
        return sum(1 for d in FakeMongoDBClient.shared_docs if _matches(d, query))

    def update_many(self, query: Dict[str, Any], update: Dict[str, Any], session=None):
        set_data = update.get("$set", {})
        modified = 0
        for d in FakeMongoDBClient.shared_docs:
            if _matches(d, query):
                d.update(set_data)
                modified += 1

        class _Res:
            modified_count = modified

        return _Res()

    def delete_many(self, query: Dict[str, Any]):
        before = len(FakeMongoDBClient.shared_docs)
        FakeMongoDBClient.shared_docs = [d for d in FakeMongoDBClient.shared_docs if not _matches(d, query)]
        deleted = before - len(FakeMongoDBClient.shared_docs)

        class _Res:
            deleted_count = deleted

        return _Res()

    def find_one(self, query: Dict[str, Any], projection: Optional[Dict[str, int]] = None, session=None):
        for d in FakeMongoDBClient.shared_docs:
            if _matches(d, query):
                if not projection:
                    return d.copy()
                out: Dict[str, Any] = {}
                for k, v in projection.items():
                    if v and k in d:
                        out[k] = d[k]
                if "_id" in d:
                    out["_id"] = d["_id"]
                return out
        return None

    # client wrapper methods
    def get_bill(self, bill_id: str):
        for d in FakeMongoDBClient.shared_docs:
            if str(d.get("_id")) == bill_id:
                return d
        return None

    def soft_delete_upload(self, upload_id: str, deleted_by: Optional[str] = None):
        now = datetime.now().isoformat()
        matched = 0
        modified = 0
        deleted_at = None
        for d in FakeMongoDBClient.shared_docs:
            linked = d.get("_id") == upload_id or d.get("upload_id") == upload_id or d.get("parent_upload_id") == upload_id
            if not linked:
                continue
            matched += 1
            is_deleted = bool(d.get("is_deleted") is True or d.get("deleted_at"))
            if is_deleted:
                continue
            d["is_deleted"] = True
            d["deleted_at"] = now
            d["deleted_by"] = deleted_by
            d["delete_mode"] = "temporary"
            d["updated_at"] = now
            deleted_at = now
            modified += 1
        return {
            "upload_id": upload_id,
            "matched_total": matched,
            "modified_count": modified,
            "already_deleted_count": max(0, matched - modified),
            "deleted_at": deleted_at,
        }

    def restore_upload(self, upload_id: str):
        matched = 0
        modified = 0
        now = datetime.now().isoformat()
        for d in FakeMongoDBClient.shared_docs:
            linked = d.get("_id") == upload_id or d.get("upload_id") == upload_id or d.get("parent_upload_id") == upload_id
            if not linked:
                continue
            matched += 1
            is_deleted = bool(d.get("is_deleted") is True or d.get("deleted_at"))
            if not is_deleted:
                continue
            d["is_deleted"] = False
            d["deleted_at"] = None
            d["deleted_by"] = None
            d["delete_mode"] = None
            d["updated_at"] = now
            modified += 1
        return {"upload_id": upload_id, "matched_total": matched, "modified_count": modified}

    def hard_delete_upload(self, upload_id: str, include_active: bool = False):
        matched_total = 0
        deleted_matches = 0
        keep: List[Dict[str, Any]] = []
        for d in FakeMongoDBClient.shared_docs:
            linked = d.get("_id") == upload_id or d.get("upload_id") == upload_id or d.get("parent_upload_id") == upload_id
            if not linked:
                keep.append(d)
                continue
            matched_total += 1
            is_deleted = bool(d.get("is_deleted") is True or d.get("deleted_at"))
            if is_deleted:
                deleted_matches += 1
            if not include_active and not is_deleted:
                keep.append(d)
        deleted_count = len(FakeMongoDBClient.shared_docs) - len(keep)
        FakeMongoDBClient.shared_docs = keep
        return {
            "upload_id": upload_id,
            "matched_total": matched_total,
            "deleted_matches": deleted_matches,
            "deleted_count": deleted_count,
        }

    def permanent_delete_upload(self, upload_id: str, include_active: bool = False):
        FakeMongoDBClient.permanent_delete_calls.append(upload_id)
        result = self.hard_delete_upload(upload_id, include_active=include_active)
        result.update(
            {
                "deleted_file_count": 0,
                "deleted_files": [],
                "failed_file_count": 0,
                "failed_files": [],
            }
        )
        return result


def _build_client(monkeypatch, docs: List[Dict[str, Any]]) -> TestClient:
    import app.db.mongo_client as mongo_client_module

    FakeMongoDBClient.shared_docs = docs
    FakeMongoDBClient.permanent_delete_calls = []
    monkeypatch.setattr(mongo_client_module, "MongoDBClient", FakeMongoDBClient)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_bills_scope_active_excludes_deleted(monkeypatch):
    docs = [
        {
            "_id": "a" * 32,
            "upload_id": "a" * 32,
            "employee_id": "11111111",
            "status": "completed",
            "processing_started_at": "2026-02-14T09:55:00",
            "completed_at": "2026-02-14T10:00:00",
            "updated_at": "2026-02-14T10:00:00",
        },
        {"_id": "b" * 32, "upload_id": "b" * 32, "employee_id": "22222222", "status": "completed", "is_deleted": True, "deleted_at": "2026-02-14T11:00:00", "updated_at": "2026-02-14T11:00:00"},
    ]
    client = _build_client(monkeypatch, docs)

    resp = client.get("/bills?scope=active")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["employee_id"] == "11111111"
    assert rows[0]["is_deleted"] is False
    assert rows[0]["status"] == "COMPLETED"
    assert rows[0]["processing_started_at"] == "2026-02-14T09:55:00"
    assert rows[0]["completed_at"] == "2026-02-14T10:00:00"


def test_get_bills_includes_queue_fields_for_pending(monkeypatch):
    pending_id = "9" * 32
    docs = [
        {
            "_id": pending_id,
            "upload_id": pending_id,
            "employee_id": "10101010",
            "status": "PENDING",
            "queue_position": 3,
            "processing_started_at": None,
            "completed_at": None,
            "updated_at": "2026-02-16T10:00:00",
        }
    ]
    client = _build_client(monkeypatch, docs)

    resp = client.get("/bills?scope=active")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "PENDING"
    assert rows[0]["queue_position"] == 3
    assert rows[0]["processing_started_at"] is None
    assert rows[0]["completed_at"] is None


def test_get_bills_scope_deleted_returns_only_deleted(monkeypatch):
    docs = [
        {"_id": "c" * 32, "upload_id": "c" * 32, "employee_id": "33333333", "status": "processing", "updated_at": "2026-02-14T10:00:00"},
        {"_id": "d" * 32, "upload_id": "d" * 32, "employee_id": "44444444", "status": "processing", "is_deleted": True, "deleted_at": "2026-02-14T11:00:00", "updated_at": "2026-02-14T11:00:00"},
    ]
    client = _build_client(monkeypatch, docs)

    resp = client.get("/bills?scope=deleted")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["employee_id"] == "44444444"
    assert rows[0]["is_deleted"] is True


def test_get_bills_include_deleted_returns_active_and_deleted(monkeypatch):
    docs = [
        {"_id": "aa" * 16, "upload_id": "aa" * 16, "employee_id": "12341234", "status": "PROCESSING", "updated_at": "2026-02-14T10:00:00"},
        {"_id": "bb" * 16, "upload_id": "bb" * 16, "employee_id": "56785678", "status": "COMPLETED", "is_deleted": True, "deleted_at": "2026-02-14T11:00:00", "updated_at": "2026-02-14T11:00:00"},
    ]
    client = _build_client(monkeypatch, docs)

    resp = client.get("/bills?include_deleted=true")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2


def test_soft_delete_flow(monkeypatch):
    bill_id = "e" * 32
    docs = [{"_id": bill_id, "upload_id": bill_id, "employee_id": "55555555", "status": "completed", "updated_at": "2026-02-14T12:00:00"}]
    client = _build_client(monkeypatch, docs)

    resp = client.delete(f"/bills/{bill_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Bill soft-deleted successfully"
    assert body["deleted_at"] is not None

    deleted_view = client.get("/bills?scope=deleted").json()
    assert len(deleted_view) == 1
    assert deleted_view[0]["bill_id"] == bill_id


def test_restore_flow(monkeypatch):
    bill_id = "f" * 32
    docs = [{
        "_id": bill_id,
        "upload_id": bill_id,
        "employee_id": "66666666",
        "status": "completed",
        "is_deleted": True,
        "deleted_at": "2026-02-14T12:30:00",
        "updated_at": "2026-02-14T12:30:00",
    }]
    client = _build_client(monkeypatch, docs)

    resp = client.post(f"/bills/{bill_id}/restore")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["bill"]["is_deleted"] is False
    assert body["bill"]["deleted_at"] is None


def test_permanent_delete_flow(monkeypatch):
    bill_id = "1" * 32
    docs = [{
        "_id": bill_id,
        "upload_id": bill_id,
        "employee_id": "77777777",
        "status": "completed",
        "is_deleted": True,
        "deleted_at": "2026-02-14T13:00:00",
        "updated_at": "2026-02-14T13:00:00",
    }]
    client = _build_client(monkeypatch, docs)

    resp = client.delete(f"/bills/{bill_id}?permanent=true")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Bill permanently deleted"
    assert bill_id in FakeMongoDBClient.permanent_delete_calls

    check = client.get("/bills?scope=deleted")
    assert check.status_code == 200
    assert check.json() == []


def test_filters_combined_with_scope(monkeypatch):
    today = datetime.now().astimezone().replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    docs = [
        {
            "_id": "2" * 32,
            "upload_id": "2" * 32,
            "employee_id": "88888888",
            "status": "processing",
            "hospital_name_metadata": "Apollo Hospital",
            "upload_date": today,
            "updated_at": today,
        },
        {
            "_id": "3" * 32,
            "upload_id": "3" * 32,
            "employee_id": "99999999",
            "status": "processing",
            "hospital_name_metadata": "Narayana Hospital",
            "upload_date": today,
            "is_deleted": True,
            "deleted_at": today,
            "updated_at": today,
        },
    ]
    client = _build_client(monkeypatch, docs)

    resp = client.get("/bills?scope=active&status=PROCESSING&hospital_name=apollo hospital&date_filter=TODAY")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["employee_id"] == "88888888"


def test_invalid_transitions(monkeypatch):
    active_id = "4" * 32
    deleted_id = "5" * 32
    docs = [
        {"_id": active_id, "upload_id": active_id, "employee_id": "12121212", "status": "completed", "updated_at": "2026-02-14T10:00:00"},
        {"_id": deleted_id, "upload_id": deleted_id, "employee_id": "34343434", "status": "completed", "is_deleted": True, "deleted_at": "2026-02-14T10:30:00", "updated_at": "2026-02-14T10:30:00"},
    ]
    client = _build_client(monkeypatch, docs)

    # restore active bill
    assert client.post(f"/bills/{active_id}/restore").status_code == 409
    # soft-delete already deleted should be idempotent
    already_deleted = client.delete(f"/bills/{deleted_id}")
    assert already_deleted.status_code == 200
    assert already_deleted.json()["message"] == "Bill already soft-deleted"
    # permanent delete active completed bill should auto-soft+hard delete
    active_perm = client.delete(f"/bills/{active_id}?permanent=true")
    assert active_perm.status_code == 200
    assert active_perm.json()["message"] == "Bill permanently deleted"
    # permanent delete deleted bill should succeed
    assert client.delete(f"/bills/{deleted_id}?permanent=true").status_code == 200
    # permanent delete non-existent
    missing = client.delete(f"/bills/{'6'*32}?permanent=true")
    assert missing.status_code == 404
    detail = missing.json().get("detail") or {}
    assert detail.get("code") == "BILL_NOT_FOUND"
    assert detail.get("message") == "Bill not found"


def test_permanent_delete_allowed_for_pending_or_processing(monkeypatch):
    pending_id = "7" * 32
    processing_id = "8" * 32
    docs = [
        {"_id": pending_id, "upload_id": pending_id, "employee_id": "56565656", "status": "pending", "updated_at": "2026-02-14T10:00:00"},
        {"_id": processing_id, "upload_id": processing_id, "employee_id": "78787878", "status": "processing", "updated_at": "2026-02-14T10:05:00"},
    ]
    client = _build_client(monkeypatch, docs)

    # permanent delete auto-soft+hard deletes active records
    pending_active_perm = client.delete(f"/bills/{pending_id}?permanent=true")
    assert pending_active_perm.status_code == 200
    assert pending_active_perm.json()["message"] == "Bill permanently deleted"

    processing_active_perm = client.delete(f"/bills/{processing_id}?permanent=true")
    assert processing_active_perm.status_code == 200
    assert processing_active_perm.json()["message"] == "Bill permanently deleted"


def test_repeated_delete_calls_are_safe(monkeypatch):
    bill_id = "c" * 32
    docs = [{"_id": bill_id, "upload_id": bill_id, "employee_id": "90909090", "status": "completed", "updated_at": "2026-02-14T12:00:00"}]
    client = _build_client(monkeypatch, docs)

    first_soft = client.delete(f"/bills/{bill_id}")
    assert first_soft.status_code == 200
    second_soft = client.delete(f"/bills/{bill_id}")
    assert second_soft.status_code == 200
    assert second_soft.json()["message"] == "Bill already soft-deleted"

    first_perm = client.delete(f"/bills/{bill_id}?permanent=true")
    assert first_perm.status_code == 200
    second_perm = client.delete(f"/bills/{bill_id}?permanent=true")
    assert second_perm.status_code == 404


def test_legacy_bill_delete_route_matches_behavior(monkeypatch):
    bill_id = "d" * 32
    docs = [{"_id": bill_id, "upload_id": bill_id, "employee_id": "30303030", "status": "completed", "updated_at": "2026-02-14T12:00:00"}]
    client = _build_client(monkeypatch, docs)

    soft = client.delete(f"/bill/{bill_id}")
    assert soft.status_code == 200
    assert soft.json()["message"] in {"Bill soft-deleted successfully", "Bill already soft-deleted"}

    hard = client.delete(f"/bill/{bill_id}?permanent=true")
    assert hard.status_code == 200
    assert hard.json()["message"] == "Bill permanently deleted"

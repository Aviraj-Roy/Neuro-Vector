from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Dict, List

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

    def limit(self, n: int):
        self.docs = self.docs[:n]
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
            if "$type" in cond:
                if cond["$type"] == "object" and not isinstance(value, dict):
                    return False
        else:
            if value != cond:
                return False
    return True


class _FakeUpdateResult:
    def __init__(self, modified_count: int):
        self.modified_count = modified_count


class _FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def find(self, query: Dict[str, Any], projection: Dict[str, int]):
        matched = [d.copy() for d in self.docs if _matches(d, query)]
        out = []
        for d in matched:
            filtered = {}
            for k, v in projection.items():
                if v and k in d:
                    filtered[k] = d[k]
            if "_id" in d and projection.get("_id", 0):
                filtered["_id"] = d["_id"]
            out.append(filtered)
        return _FakeCursor(out)

    def count_documents(self, query: Dict[str, Any], session=None):
        return sum(1 for d in self.docs if _matches(d, query))

    def update_many(self, query: Dict[str, Any], update: Dict[str, Any], session=None):
        modified = 0
        set_data = update.get("$set", {})
        for d in self.docs:
            if _matches(d, query):
                for k, v in set_data.items():
                    d[k] = v
                modified += 1
        return _FakeUpdateResult(modified)


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def start_transaction(self):
        return self


class _FakeNativeClient:
    def start_session(self):
        return _FakeSession()


class FakeMongoDBClient:
    shared_docs: List[Dict[str, Any]] = []

    def __init__(self, validate_schema: bool = False):
        self.collection = _FakeCollection(FakeMongoDBClient.shared_docs)
        self.client = _FakeNativeClient()

    def get_bill(self, bill_id: str):
        for d in FakeMongoDBClient.shared_docs:
            if str(d.get("_id")) == bill_id:
                return d
        return None

    def soft_delete_upload(self, upload_id: str):
        now = datetime.now().isoformat()
        linked = {"$or": [{"_id": upload_id}, {"upload_id": upload_id}, {"parent_upload_id": upload_id}]}
        active = {"$and": [linked, {"deleted_at": {"$exists": False}}]}
        matched_total = self.collection.count_documents(linked)
        modified = self.collection.update_many(
            active,
            {"$set": {"deleted_at": now, "updated_at": now, "status": "deleted"}},
        ).modified_count
        already_deleted = self.collection.count_documents({"$and": [linked, {"deleted_at": {"$exists": True}}]})
        return {
            "upload_id": upload_id,
            "matched_total": matched_total,
            "modified_count": modified,
            "already_deleted_count": already_deleted,
        }


def _build_client(monkeypatch, docs: List[Dict[str, Any]]) -> TestClient:
    import app.db.mongo_client as mongo_client_module

    FakeMongoDBClient.shared_docs = docs
    monkeypatch.setattr(mongo_client_module, "MongoDBClient", FakeMongoDBClient)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_delete_existing_upload_id(monkeypatch):
    upload_id = "11111111111111111111111111111111"
    docs = [{"_id": upload_id, "upload_id": upload_id, "status": "completed", "items": {}, "grand_total": 10.0}]
    client = _build_client(monkeypatch, docs)

    resp = client.delete(f"/bills/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["upload_id"] == upload_id
    assert body["message"] == "Bill deleted successfully"


def test_delete_same_upload_id_twice_is_idempotent(monkeypatch):
    upload_id = "22222222222222222222222222222222"
    docs = [{"_id": upload_id, "upload_id": upload_id, "status": "completed", "items": {}, "grand_total": 12.0}]
    client = _build_client(monkeypatch, docs)

    first = client.delete(f"/bills/{upload_id}")
    second = client.delete(f"/bills/{upload_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["success"] is True
    assert second.json()["message"] in {"Bill already deleted", "Upload not found or already deleted"}


def test_list_endpoint_excludes_deleted_records(monkeypatch):
    active_id = "33333333333333333333333333333333"
    deleted_id = "44444444444444444444444444444444"
    docs = [
        {
            "_id": active_id,
            "upload_id": active_id,
            "status": "completed",
            "items": {},
            "grand_total": 99.0,
            "updated_at": "2026-02-12T10:00:00",
        },
        {
            "_id": deleted_id,
            "upload_id": deleted_id,
            "status": "completed",
            "items": {},
            "grand_total": 88.0,
            "deleted_at": "2026-02-12T11:00:00",
            "updated_at": "2026-02-12T11:00:00",
        },
    ]
    client = _build_client(monkeypatch, docs)

    resp = client.get("/bills")
    assert resp.status_code == 200
    result_ids = {row["upload_id"] for row in resp.json()}
    assert active_id in result_ids
    assert deleted_id not in result_ids


def test_delete_non_existent_upload_id(monkeypatch):
    upload_id = "55555555555555555555555555555555"
    client = _build_client(monkeypatch, [])

    resp = client.delete(f"/bills/{upload_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["upload_id"] == upload_id
    assert body["message"] == "Upload not found or already deleted"

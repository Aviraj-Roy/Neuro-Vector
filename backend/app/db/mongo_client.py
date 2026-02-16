from __future__ import annotations

import logging
import os
import threading
import atexit
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

load_dotenv()

logger = logging.getLogger(__name__)


class MongoDBClient:
    """MongoDB client wrapper.

    Design requirements:
    - Index creation MUST NOT happen in ingestion/page processing.
      (Indexes are handled by `app/db/init_indexes.py`.)
    - Persistence MUST be bill-scoped: one upload_id -> one document.

    This class uses a singleton MongoClient to avoid reconnect storms.
    """

    _instance = None
    _lock = threading.Lock()
    _client: Optional[MongoClient] = None
    STATUS_UPLOADED = "UPLOADED"
    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"

    @staticmethod
    def _to_utc_datetime(value: Any) -> Optional[datetime]:
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

    @staticmethod
    def _to_iso_or_none(value: Any) -> Optional[str]:
        dt = MongoDBClient._to_utc_datetime(value)
        if dt is not None:
            return dt.isoformat()
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _normalize_status_value(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if raw in {
            MongoDBClient.STATUS_UPLOADED,
            MongoDBClient.STATUS_PENDING,
            MongoDBClient.STATUS_PROCESSING,
            MongoDBClient.STATUS_COMPLETED,
            MongoDBClient.STATUS_FAILED,
        }:
            return raw
        mapping = {
            "UPLOADED": MongoDBClient.STATUS_UPLOADED,
            "PENDING": MongoDBClient.STATUS_PENDING,
            "PROCESSING": MongoDBClient.STATUS_PROCESSING,
            "COMPLETED": MongoDBClient.STATUS_COMPLETED,
            "COMPLETE": MongoDBClient.STATUS_COMPLETED,
            "SUCCESS": MongoDBClient.STATUS_COMPLETED,
            "FAILED": MongoDBClient.STATUS_FAILED,
            "ERROR": MongoDBClient.STATUS_FAILED,
        }
        return mapping.get(raw, raw or MongoDBClient.STATUS_PENDING)

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _now_utc_iso() -> str:
        return MongoDBClient._now_utc().isoformat()

    @classmethod
    def _cleanup(cls):
        """Clean up MongoDB client on interpreter shutdown."""
        try:
            if cls._client is not None:
                cls._client.close()
        except Exception:
            pass
        finally:
            cls._client = None
            cls._instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, validate_schema: bool = False):
        if MongoDBClient._client is not None:
            self.client = MongoDBClient._client
            self.db = self.client[os.getenv("MONGO_DB_NAME", "medical_bills")]
            self.collection = self.db[os.getenv("MONGO_COLLECTION_NAME", "bills")]
            self.validate_schema = validate_schema
            return

        mongo_uri = os.getenv("MONGO_URI")
        db_name = os.getenv("MONGO_DB_NAME", "medical_bills")
        collection_name = os.getenv("MONGO_COLLECTION_NAME", "bills")

        if not mongo_uri:
            raise ValueError("MONGO_URI not found in .env")

        self.client = MongoClient(mongo_uri)
        MongoDBClient._client = self.client

        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.validate_schema = validate_schema

        # Register atexit cleanup exactly once
        atexit.register(MongoDBClient._cleanup)

    def _validate_and_transform(self, bill_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.validate_schema:
            return bill_data

        try:
            from app.db.bill_schema import BillDocument

            doc = BillDocument(**bill_data)
            return doc.to_mongo_dict()
        except Exception as e:
            logger.warning(f"Schema validation failed: {e}. Storing raw data.")
            return bill_data

    def insert_bill(self, bill_data: Dict[str, Any]) -> str:
        """Legacy insert: creates a new document each call."""
        data_to_insert = self._validate_and_transform(bill_data)
        data_to_insert["inserted_at"] = datetime.now().isoformat()
        result = self.collection.insert_one(data_to_insert)
        return str(result.inserted_id)

    def create_upload_record(
        self,
        *,
        upload_id: str,
        original_filename: str,
        file_size_bytes: int,
        hospital_name: str,
        employee_id: str,
        invoice_date: Optional[str] = None,
        source_pdf: Optional[str] = None,
        ingestion_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create exactly one upload-scoped document for a PDF.

        Returns:
            Dict with:
            - upload_id: stable upload identifier
            - created: True if insert happened now, False if request is duplicate
            - status: current status of the existing/new document
        """
        now = self._now_utc_iso()
        source_name = source_pdf or original_filename

        doc: Dict[str, Any] = {
            "_id": upload_id,
            "upload_id": upload_id,
            "status": self.STATUS_PENDING,
            "queue_position": None,
            "retry_count": 0,
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by": None,
            "delete_mode": None,
            "document_type": "bill_upload",
            "created_at": now,
            "upload_date": now,
            "queued_at": now,
            "processing_started_at": None,
            "processing_completed_at": None,
            "completed_at": None,
            "updated_at": now,
            "source_pdf": source_name,
            "original_filename": original_filename,
            "file_size_bytes": int(file_size_bytes or 0),
            "employee_id": str(employee_id),
            # Keep both fields for backward compatibility with existing consumers.
            "hospital_name_metadata": hospital_name,
            "hospital_name": hospital_name,
            "schema_version": 2,
        }
        if invoice_date:
            doc["invoice_date"] = invoice_date
        if ingestion_request_id:
            doc["ingestion_request_id"] = ingestion_request_id

        try:
            self.collection.insert_one(doc)
            return {"upload_id": upload_id, "created": True, "status": self.STATUS_PENDING}
        except DuplicateKeyError:
            existing = None
            if ingestion_request_id:
                existing = self.collection.find_one({"ingestion_request_id": ingestion_request_id})
            if not existing:
                existing = self.collection.find_one({"_id": upload_id})
            if not existing:
                raise
            return {
                "upload_id": str(existing.get("upload_id") or existing.get("_id")),
                "created": False,
                "status": self._normalize_status_value(existing.get("status")),
            }

    def mark_processing(self, upload_id: str) -> bool:
        """Transition uploaded/failed -> processing atomically."""
        now = self._now_utc_iso()
        result = self.collection.update_one(
            {
                "_id": upload_id,
                "status": {"$in": [self.STATUS_PENDING, self.STATUS_UPLOADED, self.STATUS_FAILED, "pending", "uploaded", "failed"]},
            },
            {
                "$set": {
                    "status": self.STATUS_PROCESSING,
                    "updated_at": now,
                    "processing_started_at": now,
                    "queue_position": None,
                    "completed_at": None,
                }
            },
        )
        return result.modified_count == 1

    def enqueue_upload_job(
        self,
        *,
        upload_id: str,
        temp_pdf_path: str,
        hospital_name: str,
        original_filename: str,
    ) -> bool:
        """Queue a bill for strict FIFO processing."""
        now = self._now_utc_iso()
        result = self.collection.update_one(
            {
                "_id": upload_id,
                "status": {"$nin": [self.STATUS_PROCESSING, self.STATUS_COMPLETED, "processing", "completed"]},
            },
            {
                "$set": {
                    "status": self.STATUS_PENDING,
                    "queue_state": "queued",
                    "queued_at": now,
                    "temp_pdf_path": str(temp_pdf_path),
                    "queue_hospital_name": str(hospital_name or "").strip(),
                    "queue_original_filename": str(original_filename or "").strip(),
                    "updated_at": now,
                    "completed_at": None,
                }
            },
            upsert=False,
        )
        if result.modified_count > 0:
            self.recompute_pending_queue_positions()
        return result.modified_count == 1

    def claim_next_pending_job(self) -> Optional[Dict[str, Any]]:
        """Atomically claim oldest pending bill for single-worker processing."""
        owner_id = f"worker-{uuid.uuid4().hex}"
        if not self._acquire_queue_lease(owner_id):
            return None
        try:
            active_processing = self.collection.find_one(
                {
                    "is_deleted": {"$ne": True},
                    "status": {"$in": [self.STATUS_PROCESSING, "processing"]},
                },
                {"_id": 1},
            )
            if active_processing:
                return None

            now = self._now_utc_iso()
            doc = self.collection.find_one_and_update(
                {
                    "is_deleted": {"$ne": True},
                    "status": {"$in": [self.STATUS_PENDING, self.STATUS_UPLOADED, "pending", "uploaded"]},
                    "temp_pdf_path": {"$exists": True, "$ne": ""},
                },
                {
                    "$set": {
                        "status": self.STATUS_PROCESSING,
                        "queue_state": "processing",
                        "processing_started_at": now,
                        "updated_at": now,
                        "queue_position": None,
                        "completed_at": None,
                    },
                    "$unset": {
                        "error_message": "",
                        "processing_failed_at": "",
                    },
                },
                sort=[("created_at", 1), ("queued_at", 1), ("upload_date", 1), ("_id", 1)],
                return_document=ReturnDocument.AFTER,
            )
            self.recompute_pending_queue_positions()
            return doc
        finally:
            self._release_queue_lease(owner_id)

    def _acquire_queue_lease(self, owner_id: str, lease_seconds: int = 60) -> bool:
        """Acquire a short lease to serialize queue claim/reconcile operations."""
        if not hasattr(self, "db") or self.db is None:
            return True
        control = self.db["_queue_control"]
        now = self._now_utc()
        expires_at = now.timestamp() + max(10, int(lease_seconds))
        doc = control.find_one_and_update(
            {
                "_id": "bill_processing_queue_lease",
                "$or": [
                    {"lease_expires_at": {"$lte": now.timestamp()}},
                    {"lease_owner": owner_id},
                    {"lease_expires_at": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "lease_owner": owner_id,
                    "lease_expires_at": expires_at,
                    "updated_at": now.isoformat(),
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return bool(doc and doc.get("lease_owner") == owner_id and float(doc.get("lease_expires_at") or 0) >= now.timestamp())

    def _release_queue_lease(self, owner_id: str) -> None:
        if not hasattr(self, "db") or self.db is None:
            return
        control = self.db["_queue_control"]
        control.update_one(
            {"_id": "bill_processing_queue_lease", "lease_owner": owner_id},
            {
                "$set": {
                    "lease_expires_at": 0.0,
                    "updated_at": self._now_utc_iso(),
                }
            },
            upsert=False,
        )

    def recompute_pending_queue_positions(self) -> int:
        """Persist backend-authoritative FIFO queue positions for pending bills."""
        cursor = self.collection.find(
            {
                "is_deleted": {"$ne": True},
                "status": {"$in": [self.STATUS_PENDING, self.STATUS_UPLOADED, "pending", "uploaded"]},
            },
            {"_id": 1, "queued_at": 1, "created_at": 1, "upload_date": 1},
        )
        docs = list(cursor) if not isinstance(cursor, list) else list(cursor)
        docs.sort(
            key=lambda d: (
                str(d.get("created_at") or ""),
                str(d.get("queued_at") or ""),
                str(d.get("upload_date") or ""),
                str(d.get("_id") or ""),
            )
        )
        now = self._now_utc_iso()
        updates = 0
        for index, doc in enumerate(docs, start=1):
            result = self.collection.update_one(
                {"_id": doc.get("_id")},
                {"$set": {"queue_position": int(index), "updated_at": now}},
                upsert=False,
            )
            updates += int(result.modified_count)

        # Non-pending records should not expose queue position.
        clear_filter = {
            "$or": [
                {"status": {"$in": [self.STATUS_PROCESSING, self.STATUS_COMPLETED, self.STATUS_FAILED, "processing", "completed", "failed"]}},
                {"is_deleted": True},
            ]
        }
        if hasattr(self.collection, "update_many"):
            self.collection.update_many(clear_filter, {"$set": {"queue_position": None}})
        else:
            for doc in self.collection.find(clear_filter, {"_id": 1}):  # type: ignore[attr-defined]
                self.collection.update_one({"_id": doc.get("_id")}, {"$set": {"queue_position": None}}, upsert=False)
        return updates

    def reconcile_queue_state(self, stale_after_seconds: int = 1800) -> Dict[str, int]:
        """Periodic queue reconciliation to enforce single PROCESSING + stale handling."""
        owner_id = f"reconcile-{uuid.uuid4().hex}"
        if not self._acquire_queue_lease(owner_id):
            return {"stale_recovered": 0, "extra_processing_demoted": 0, "queue_repositioned": 0}
        try:
            stale_recovered = self.recover_stale_processing_jobs(stale_after_seconds=stale_after_seconds)

            processing_cursor = self.collection.find(
                {"is_deleted": {"$ne": True}, "status": {"$in": [self.STATUS_PROCESSING, "processing"]}},
                {"_id": 1, "processing_started_at": 1, "updated_at": 1},
            )
            processing_docs = (
                list(processing_cursor)
                if not isinstance(processing_cursor, list)
                else list(processing_cursor)
            )
            processing_docs.sort(
                key=lambda d: (
                    str(d.get("processing_started_at") or ""),
                    str(d.get("updated_at") or ""),
                    str(d.get("_id") or ""),
                )
            )
            extra_processing_demoted = 0
            if len(processing_docs) > 1:
                now = self._now_utc_iso()
                # Keep oldest processing, demote others to pending for retry-safe resume.
                for doc in processing_docs[1:]:
                    result = self.collection.update_one(
                        {"_id": doc.get("_id"), "status": {"$in": [self.STATUS_PROCESSING, "processing"]}},
                        {
                            "$set": {
                                "status": self.STATUS_PENDING,
                                "queue_state": "queued",
                                "queued_at": now,
                                "updated_at": now,
                                "queue_position": None,
                            }
                        },
                        upsert=False,
                    )
                    extra_processing_demoted += int(result.modified_count)

            queue_repositioned = self.recompute_pending_queue_positions()
            return {
                "stale_recovered": int(stale_recovered),
                "extra_processing_demoted": int(extra_processing_demoted),
                "queue_repositioned": int(queue_repositioned),
            }
        finally:
            self._release_queue_lease(owner_id)

    def recover_stale_processing_jobs(self, stale_after_seconds: int = 1800) -> int:
        """Mark stuck processing jobs as failed on service startup."""
        now_dt = self._now_utc()
        now = now_dt.isoformat()
        stale_count = 0
        for doc in self.collection.find(
            {"status": {"$in": [self.STATUS_PROCESSING, "processing"]}, "is_deleted": {"$ne": True}},
            {"_id": 1, "processing_started_at": 1, "retry_count": 1},
        ):
            started_raw = doc.get("processing_started_at")
            if not started_raw:
                started_dt = None
            else:
                try:
                    started_dt = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
                    if started_dt.tzinfo is None:
                        started_dt = started_dt.astimezone()
                    started_dt = started_dt.astimezone(timezone.utc)
                except Exception:
                    started_dt = None
            is_stale = started_dt is None or (now_dt - started_dt).total_seconds() >= stale_after_seconds
            if not is_stale:
                continue
            self.collection.update_one(
                {"_id": doc.get("_id"), "status": {"$in": [self.STATUS_PROCESSING, "processing"]}},
                {
                    "$set": {
                        "status": self.STATUS_FAILED,
                        "queue_state": "failed",
                        "updated_at": now,
                        "processing_failed_at": now,
                        "completed_at": now,
                        "error_message": "Recovered stale processing job after service restart",
                        "queue_position": None,
                    }
                },
                upsert=False,
            )
            stale_count += 1
        if stale_count > 0:
            self.recompute_pending_queue_positions()
        return stale_count

    def mark_failed(self, upload_id: str, error_message: str) -> None:
        """Mark upload as failed with error details."""
        now = self._now_utc_iso()
        self.collection.update_one(
            {"_id": upload_id},
            {
                "$set": {
                    "status": self.STATUS_FAILED,
                    "updated_at": now,
                    "error_message": str(error_message),
                    "processing_failed_at": now,
                    "completed_at": now,
                    "queue_position": None,
                }
            },
        )
        self.recompute_pending_queue_positions()

    def complete_bill(self, upload_id: str, bill_data: Dict[str, Any]) -> str:
        """Finalize one upload-scoped bill document using update_one only."""
        from app.db.artifact_filter import filter_artifact_items, validate_bill_items

        bill_data = filter_artifact_items(bill_data)
        is_valid, error_msg = validate_bill_items(bill_data)
        if not is_valid:
            logger.error(f"Bill validation failed before completion update: {error_msg}")

        data = self._validate_and_transform(bill_data)
        existing_doc = self.collection.find_one(
            {"_id": upload_id},
            {"processing_started_at": 1, "created_at": 1},
        ) or {}
        now_dt = self._now_utc()
        now = now_dt.isoformat()

        update = {
            "$set": {
                "updated_at": now,
                "status": self.STATUS_COMPLETED,
                "processing_completed_at": now,
                "completed_at": now,
                "queue_position": None,
                "page_count": data.get("page_count"),
                "extraction_date": data.get("extraction_date"),
                "header": data.get("header", {}) or {},
                "patient": data.get("patient", {}) or {},
                "items": data.get("items", {}) or {},
                "subtotals": data.get("subtotals", {}) or {},
                "summary": data.get("summary", {}) or {},
                "grand_total": data.get("grand_total", 0.0),
                "raw_ocr_text": data.get("raw_ocr_text"),
                "schema_version": data.get("schema_version", 2),
                # Keep both fields for compatibility.
                "hospital_name_metadata": data.get("hospital_name_metadata"),
                "hospital_name": data.get("hospital_name"),
            }
        }

        started_at = existing_doc.get("processing_started_at") or existing_doc.get("created_at")
        if started_at:
            started_dt = None
            try:
                started_str = str(started_at).replace("Z", "+00:00")
                started_dt = datetime.fromisoformat(started_str)
            except Exception:
                started_dt = None
            if started_dt is not None:
                if started_dt.tzinfo is not None:
                    now_ref = datetime.now(started_dt.tzinfo)
                else:
                    now_ref = now_dt
                duration_seconds = max(0.0, (now_ref - started_dt).total_seconds())
                update["$set"]["processing_time_seconds"] = round(duration_seconds, 3)

        # Promote extracted header billing date to top-level invoice_date for dashboard use.
        # Keep any existing/manual value when extraction does not yield a date.
        extracted_invoice_date = (
            data.get("invoice_date")
            or (data.get("header", {}) or {}).get("billing_date")
        )
        if extracted_invoice_date:
            update["$set"]["invoice_date"] = str(extracted_invoice_date).strip()

        # Preserve ingestion-level metadata if extraction layer provides updates.
        source_pdf = data.get("source_pdf")
        if source_pdf:
            update["$set"]["source_pdf"] = source_pdf

        self.collection.update_one({"_id": upload_id}, update, upsert=False)
        self.recompute_pending_queue_positions()
        return upload_id

    def upsert_bill(self, upload_id: str, bill_data: Dict[str, Any]) -> str:
        """Bill-scoped persistence: one upload_id -> one document.

        Uses:
        - $setOnInsert for immutable metadata
        - $set for computed fields (header, patient, subtotals, summary, grand_total)
        - $addToSet/$each for append-only items (dedupe via stable item_id)

        NOTE: uses `_id == upload_id` to guarantee exactly one doc per upload.

        Schema notes (v2):
        - Payments are NOT stored (removed per choice C to prevent total pollution)
        - Discounts are stored in summary.discounts (not in items or totals)
        - grand_total reflects only billable items
        
        PHASE-7 Guardrail:
        - Filters out legacy OCR artifacts before insertion
        - Prevents "Hospital - / UNKNOWN / ₹0" items from entering DB
        """
        
        # PHASE-7: Filter artifacts before validation/transformation
        from app.db.artifact_filter import filter_artifact_items, validate_bill_items
        
        bill_data = filter_artifact_items(bill_data)
        
        # PHASE-7: Final validation check
        is_valid, error_msg = validate_bill_items(bill_data)
        if not is_valid:
            logger.error(f"⚠️  Bill validation failed: {error_msg}")
            # Continue anyway but log the issue
        
        data = self._validate_and_transform(bill_data)

        header = data.get("header", {}) or {}
        patient = data.get("patient", {}) or {}
        items = data.get("items", {}) or {}
        summary = data.get("summary", {}) or {}

        # Build $addToSet update for each item category only
        # NOTE: Payments are intentionally NOT stored (choice C)
        add_to_set: Dict[str, Any] = {}
        for category, arr in items.items():
            if not isinstance(arr, list):
                continue
            add_to_set[f"items.{category}"] = {"$each": arr}

        now = datetime.now().isoformat()

        update = {
            "$setOnInsert": {
                "_id": upload_id,
                "upload_id": upload_id,
                "created_at": now,
                "source_pdf": data.get("source_pdf"),
                "schema_version": data.get("schema_version", 2),  # Bump to v2
                "is_deleted": False,
                "deleted_at": None,
            },
            "$set": {
                "updated_at": now,
                "page_count": data.get("page_count"),
                "extraction_date": data.get("extraction_date"),
                "header": header,
                "patient": patient,
                "subtotals": data.get("subtotals", {}),
                "summary": summary,  # Contains discounts info
                "grand_total": data.get("grand_total", 0.0),
                "raw_ocr_text": data.get("raw_ocr_text"),
                "status": self._normalize_status_value(data.get("status", self.STATUS_COMPLETED)),
                # Store hospital name metadata for verification (NOT extracted from bill)
                "hospital_name_metadata": data.get("hospital_name_metadata"),
            },
        }

        # Only add $addToSet if there are items to add
        if add_to_set:
            update["$addToSet"] = add_to_set

        self.collection.update_one({"_id": upload_id}, update, upsert=True)
        return upload_id

    def get_bill(self, bill_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a bill by its ID (upload_id or _id).
        
        Args:
            bill_id: The bill identifier (stored as _id in MongoDB)
        
        Returns:
            Bill document if found, None otherwise
            
        Raises:
            ValueError: If bill_id is empty or invalid
            
        Note:
            In this schema, _id == upload_id (see upsert_bill line 132)
        """
        if not bill_id or not isinstance(bill_id, str):
            raise ValueError(f"Invalid bill_id: {bill_id}")
        
        try:
            # Try direct lookup first (string _id)
            bill_doc = self.collection.find_one({"_id": bill_id})
            if bill_doc:
                return bill_doc
            
            # Fallback: try as ObjectId (for legacy documents)
            from bson import ObjectId
            if ObjectId.is_valid(bill_id):
                bill_doc = self.collection.find_one({"_id": ObjectId(bill_id)})
                if bill_doc:
                    return bill_doc
            
            # Not found
            logger.warning(f"Bill not found with ID: {bill_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching bill {bill_id}: {e}")
            return None

    def get_bill_by_id(self, bill_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_bill() for backward compatibility.
        
        Args:
            bill_id: The bill identifier
            
        Returns:
            Bill document if found, None otherwise
        """
        return self.get_bill(bill_id)

    def get_bill_by_upload_id(self, upload_id: str) -> Optional[Dict[str, Any]]:
        return self.collection.find_one({"_id": upload_id})

    def get_bill_by_request_id(self, ingestion_request_id: str) -> Optional[Dict[str, Any]]:
        if not ingestion_request_id:
            return None
        return self.collection.find_one({"ingestion_request_id": ingestion_request_id})

    def save_verification_result(
        self,
        upload_id: str,
        verification_result: Dict[str, Any],
        verification_result_text: str,
        line_items: Optional[list[Dict[str, Any]]] = None,
        format_version: str = "v1",
    ) -> bool:
        """Persist verification output for frontend dashboard consumption."""
        now_dt = datetime.now()
        now = now_dt.isoformat()
        existing_doc = self.collection.find_one(
            {"_id": upload_id},
            {"processing_started_at": 1, "created_at": 1, "upload_date": 1},
        ) or {}

        processing_time_seconds = None
        started_at = (
            existing_doc.get("processing_started_at")
            or existing_doc.get("created_at")
            or existing_doc.get("upload_date")
        )
        if started_at:
            started_dt = None
            try:
                started_str = str(started_at).replace("Z", "+00:00")
                started_dt = datetime.fromisoformat(started_str)
            except Exception:
                started_dt = None
            if started_dt is not None:
                if started_dt.tzinfo is not None:
                    now_ref = datetime.now(started_dt.tzinfo)
                else:
                    now_ref = now_dt
                processing_time_seconds = round(max(0.0, (now_ref - started_dt).total_seconds()), 3)

        set_data: Dict[str, Any] = {
            "verification_status": "completed",
            "verification_result": verification_result or {},
            "verification_result_text": str(verification_result_text or ""),
            "verification_format_version": str(format_version or "v1"),
            "verification_updated_at": now,
            "verification_completed_at": now,
            "updated_at": now,
            # Keep dashboard processing lifecycle aligned with true end-to-end completion.
            "processing_completed_at": now,
            "completed_at": now,
        }
        if line_items is not None:
            set_data["line_items"] = line_items
        if processing_time_seconds is not None:
            set_data["processing_time_seconds"] = processing_time_seconds

        result = self.collection.update_one(
            {"_id": upload_id},
            {"$set": set_data},
            upsert=False,
        )
        return result.modified_count == 1

    def mark_verification_processing(self, upload_id: str) -> bool:
        """Atomically mark verification as processing when not already completed/processing."""
        now = datetime.now().isoformat()
        result = self.collection.update_one(
            {
                "_id": upload_id,
                "verification_status": {"$nin": ["processing", "completed"]},
            },
            {
                "$set": {
                    "verification_status": "processing",
                    "verification_started_at": now,
                    "verification_updated_at": now,
                    "updated_at": now,
                }
            },
            upsert=False,
        )
        return result.modified_count == 1

    def mark_verification_failed(self, upload_id: str, error_message: str) -> bool:
        """Persist verification failure to prevent indefinite dashboard polling."""
        now = datetime.now().isoformat()
        result = self.collection.update_one(
            {"_id": upload_id},
            {
                "$set": {
                    "verification_status": "failed",
                    "verification_error": str(error_message or "Verification failed"),
                    "verification_updated_at": now,
                    "updated_at": now,
                }
            },
            upsert=False,
        )
        return result.modified_count == 1

    def save_line_item_edits(
        self,
        upload_id: str,
        line_item_edits: list[Dict[str, Any]],
        line_items: list[Dict[str, Any]],
        edited_at: str,
        edited_by: Optional[str] = None,
    ) -> bool:
        now = datetime.now().isoformat()
        result = self.collection.update_one(
            {"_id": upload_id},
            {
                "$set": {
                    "line_item_edits": line_item_edits,
                    "line_items": line_items,
                    "line_items_last_edited_at": str(edited_at or now),
                    "line_items_last_edited_by": edited_by,
                    "updated_at": now,
                }
            },
            upsert=False,
        )
        return result.matched_count == 1

    def soft_delete_upload(self, upload_id: str, deleted_by: Optional[str] = None) -> Dict[str, Any]:
        """Soft-delete all records linked to an upload_id.

        Behavior:
        - Idempotent: repeated calls succeed.
        - Marks linked records with is_deleted=true + deleted_at + status=deleted.
        - Attempts transactional execution when supported.
        """
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        linked_filter: Dict[str, Any] = {
            "$or": [
                {"_id": upload_id},
                {"upload_id": upload_id},
                {"parent_upload_id": upload_id},
            ]
        }
        deleted_marker_filter: Dict[str, Any] = {
            "$or": [
                {"is_deleted": True},
                {
                    "$and": [
                        {"deleted_at": {"$exists": True}},
                        {"deleted_at": {"$ne": None}},
                    ]
                },
            ]
        }
        active_filter: Dict[str, Any] = {
            "$and": [
                linked_filter,
                {"is_deleted": {"$ne": True}},
                {
                    "$or": [
                        {"deleted_at": {"$exists": False}},
                        {"deleted_at": None},
                    ]
                },
            ]
        }

        update_doc = {
            "$set": {
                "is_deleted": True,
                "deleted_at": now_dt,
                "deleted_by": deleted_by,
                "delete_mode": "temporary",
                "updated_at": now,
            }
        }

        def _run(session=None) -> Dict[str, Any]:
            matched_total = self.collection.count_documents(linked_filter, session=session)
            modified = self.collection.update_many(active_filter, update_doc, session=session)
            deleted_doc = self.collection.find_one(
                {
                    "$and": [
                        linked_filter,
                        deleted_marker_filter,
                    ]
                },
                {"deleted_at": 1},
                session=session,
            )
            already_deleted = self.collection.count_documents(
                {
                    "$and": [
                        linked_filter,
                        deleted_marker_filter,
                    ]
                },
                session=session,
            )
            return {
                "upload_id": upload_id,
                "deleted_at": (
                    now if int(modified.modified_count) > 0 else self._to_iso_or_none(deleted_doc.get("deleted_at")) if deleted_doc else None
                ),
                "matched_total": int(matched_total),
                "modified_count": int(modified.modified_count),
                "already_deleted_count": int(already_deleted),
            }

        try:
            with self.client.start_session() as session:
                with session.start_transaction():
                    return _run(session=session)
        except Exception as tx_err:
            logger.warning(f"Transaction not available for soft_delete_upload({upload_id}): {tx_err}")
            return _run(session=None)

    def restore_upload(self, upload_id: str) -> Dict[str, Any]:
        """Restore a soft-deleted upload."""
        now = datetime.now().isoformat()
        linked_filter: Dict[str, Any] = {
            "$or": [
                {"_id": upload_id},
                {"upload_id": upload_id},
                {"parent_upload_id": upload_id},
            ]
        }
        deleted_marker_filter: Dict[str, Any] = {
            "$or": [
                {"is_deleted": True},
                {
                    "$and": [
                        {"deleted_at": {"$exists": True}},
                        {"deleted_at": {"$ne": None}},
                    ]
                },
            ]
        }
        deleted_filter: Dict[str, Any] = {
            "$and": [
                linked_filter,
                deleted_marker_filter,
            ]
        }

        result = self.collection.update_many(
            deleted_filter,
            {
                "$set": {
                    "is_deleted": False,
                    "deleted_at": None,
                    "deleted_by": None,
                    "delete_mode": None,
                    "updated_at": now,
                }
            },
        )
        matched_total = self.collection.count_documents(linked_filter)
        return {
            "upload_id": upload_id,
            "matched_total": int(matched_total),
            "modified_count": int(result.modified_count),
        }

    def hard_delete_upload(self, upload_id: str, include_active: bool = False) -> Dict[str, Any]:
        """Permanently delete records linked to an upload_id."""
        linked_filter: Dict[str, Any] = {
            "$or": [
                {"_id": upload_id},
                {"upload_id": upload_id},
                {"parent_upload_id": upload_id},
            ]
        }
        deleted_marker_filter: Dict[str, Any] = {
            "$or": [
                {"is_deleted": True},
                {
                    "$and": [
                        {"deleted_at": {"$exists": True}},
                        {"deleted_at": {"$ne": None}},
                    ]
                },
            ]
        }
        deleted_filter: Dict[str, Any] = {
            "$and": [
                linked_filter,
                deleted_marker_filter,
            ]
        }
        matched_total = self.collection.count_documents(linked_filter)
        deleted_matches = self.collection.count_documents(deleted_filter)
        delete_filter = linked_filter if include_active else deleted_filter
        delete_result = self.collection.delete_many(delete_filter)
        return {
            "upload_id": upload_id,
            "matched_total": int(matched_total),
            "deleted_matches": int(deleted_matches),
            "deleted_count": int(delete_result.deleted_count),
        }

    def _cleanup_upload_files(self, upload_id: str, linked_docs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Delete upload-scoped temporary files/artifacts from local filesystem."""
        candidates: set[Path] = set()
        linked_docs = linked_docs or []

        for doc in linked_docs:
            temp_pdf_path = str(doc.get("temp_pdf_path") or "").strip()
            if temp_pdf_path:
                candidates.add(Path(temp_pdf_path))

        try:
            from app.config import PROCESSED_DIR, UPLOADS_DIR

            for root in (UPLOADS_DIR, PROCESSED_DIR):
                root_path = Path(root)
                if not root_path.exists():
                    continue
                for match in root_path.glob(f"{upload_id}_*"):
                    if match.is_file():
                        candidates.add(match)
        except Exception as e:
            logger.warning("Failed to enumerate upload artifacts for upload_id=%s: %s", upload_id, e)

        deleted_paths: List[str] = []
        failed_paths: List[str] = []

        for path in candidates:
            try:
                path.unlink(missing_ok=True)
                deleted_paths.append(str(path))
            except Exception as e:
                failed_paths.append(str(path))
                logger.warning("Failed to delete artifact file %s for upload_id=%s: %s", path, upload_id, e)

        return {
            "deleted_file_count": len(deleted_paths),
            "deleted_files": deleted_paths,
            "failed_file_count": len(failed_paths),
            "failed_files": failed_paths,
        }

    def permanent_delete_upload(self, upload_id: str, include_active: bool = False) -> Dict[str, Any]:
        """Hard-delete linked records and remove related local upload artifacts."""
        linked_filter: Dict[str, Any] = {
            "$or": [
                {"_id": upload_id},
                {"upload_id": upload_id},
                {"parent_upload_id": upload_id},
            ]
        }
        linked_docs = list(
            self.collection.find(
                linked_filter,
                {"_id": 1, "upload_id": 1, "temp_pdf_path": 1},
            )
        )

        delete_result = self.hard_delete_upload(upload_id, include_active=include_active)
        cleanup_result = self._cleanup_upload_files(upload_id, linked_docs)
        return {
            **delete_result,
            **cleanup_result,
        }

    def get_bills_by_patient_mrn(self, mrn: str) -> List[Dict[str, Any]]:
        return list(self.collection.find({"patient.mrn": mrn}))

    def get_bills_by_patient_name(self, patient_name: str) -> List[Dict[str, Any]]:
        return list(self.collection.find({"patient.name": {"$regex": patient_name, "$options": "i"}}))

    def get_statistics(self) -> Dict[str, Any]:
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_bills": {"$sum": 1},
                    "total_revenue": {"$sum": "$grand_total"},
                    "avg_bill_amount": {"$avg": "$grand_total"},
                }
            }
        ]

        result = list(self.collection.aggregate(pipeline))
        if not result:
            return {"message": "No data available"}
        return result[0]

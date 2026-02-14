from __future__ import annotations

import logging
import os
import threading
import atexit
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient
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
        now = datetime.now().isoformat()
        source_name = source_pdf or original_filename

        doc: Dict[str, Any] = {
            "_id": upload_id,
            "upload_id": upload_id,
            "status": "uploaded",
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by": None,
            "delete_mode": None,
            "document_type": "bill_upload",
            "created_at": now,
            "upload_date": now,
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
            return {"upload_id": upload_id, "created": True, "status": "uploaded"}
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
                "status": str(existing.get("status") or "uploaded"),
            }

    def mark_processing(self, upload_id: str) -> bool:
        """Transition uploaded/failed -> processing atomically."""
        now = datetime.now().isoformat()
        result = self.collection.update_one(
            {
                "_id": upload_id,
                "status": {"$in": ["uploaded", "failed"]},
            },
            {
                "$set": {
                    "status": "processing",
                    "updated_at": now,
                    "processing_started_at": now,
                }
            },
        )
        return result.modified_count == 1

    def mark_failed(self, upload_id: str, error_message: str) -> None:
        """Mark upload as failed with error details."""
        now = datetime.now().isoformat()
        self.collection.update_one(
            {"_id": upload_id},
            {
                "$set": {
                    "status": "failed",
                    "updated_at": now,
                    "error_message": str(error_message),
                    "processing_failed_at": now,
                }
            },
        )

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
        now_dt = datetime.now()
        now = now_dt.isoformat()

        update = {
            "$set": {
                "updated_at": now,
                "status": "completed",
                "processing_completed_at": now,
                "completed_at": now,
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
                "status": data.get("status", "complete"),
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

    def soft_delete_upload(self, upload_id: str, deleted_by: Optional[str] = None) -> Dict[str, Any]:
        """Soft-delete all records linked to an upload_id.

        Behavior:
        - Idempotent: repeated calls succeed.
        - Marks linked records with is_deleted=true + deleted_at + status=deleted.
        - Attempts transactional execution when supported.
        """
        now = datetime.now().isoformat()
        linked_filter: Dict[str, Any] = {
            "$or": [
                {"_id": upload_id},
                {"upload_id": upload_id},
                {"parent_upload_id": upload_id},
            ]
        }
        active_filter: Dict[str, Any] = {
            "$and": [
                linked_filter,
                {"is_deleted": {"$ne": True}},
                {"deleted_at": {"$exists": False}},
            ]
        }

        update_doc = {
            "$set": {
                "is_deleted": True,
                "deleted_at": now,
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
                        {
                            "$or": [
                                {"is_deleted": True},
                                {"deleted_at": {"$exists": True}},
                            ]
                        },
                    ]
                },
                {"deleted_at": 1},
                session=session,
            )
            already_deleted = self.collection.count_documents(
                {
                    "$and": [
                        linked_filter,
                        {
                            "$or": [
                                {"is_deleted": True},
                                {"deleted_at": {"$exists": True}},
                            ]
                        },
                    ]
                },
                session=session,
            )
            return {
                "upload_id": upload_id,
                "deleted_at": (
                    now if int(modified.modified_count) > 0 else deleted_doc.get("deleted_at") if deleted_doc else None
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
        deleted_filter: Dict[str, Any] = {
            "$and": [
                linked_filter,
                {
                    "$or": [
                        {"is_deleted": True},
                        {"deleted_at": {"$exists": True}},
                    ]
                },
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

    def hard_delete_upload(self, upload_id: str) -> Dict[str, Any]:
        """Permanently delete records linked to an upload_id."""
        linked_filter: Dict[str, Any] = {
            "$or": [
                {"_id": upload_id},
                {"upload_id": upload_id},
                {"parent_upload_id": upload_id},
            ]
        }
        deleted_filter: Dict[str, Any] = {
            "$and": [
                linked_filter,
                {
                    "$or": [
                        {"is_deleted": True},
                        {"deleted_at": {"$exists": True}},
                    ]
                },
            ]
        }
        matched_total = self.collection.count_documents(linked_filter)
        deleted_matches = self.collection.count_documents(deleted_filter)
        delete_result = self.collection.delete_many(deleted_filter)
        return {
            "upload_id": upload_id,
            "matched_total": int(matched_total),
            "deleted_matches": int(deleted_matches),
            "deleted_count": int(delete_result.deleted_count),
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

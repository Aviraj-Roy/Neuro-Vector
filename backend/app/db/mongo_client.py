from __future__ import annotations

import logging
import os
import threading
import atexit
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient

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

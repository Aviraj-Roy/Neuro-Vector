from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Dict

# Ensure `app` package (backend/app) is importable in test runs.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.mongo_client import MongoDBClient
from app.extraction.bill_extractor import Candidate, HeaderAggregator
from app.extraction.bill_extractor import extract_bill_data


class _FakeCollection:
    def __init__(self):
        self.last_filter: Dict[str, Any] | None = None
        self.last_update: Dict[str, Any] | None = None

    def update_one(self, filter_doc: Dict[str, Any], update_doc: Dict[str, Any], upsert: bool = False):
        self.last_filter = filter_doc
        self.last_update = update_doc
        return None


def test_header_aggregator_accepts_numeric_billing_date():
    agg = HeaderAggregator()
    accepted = agg.offer(
        Candidate(field="billing_date", value="12/02/2026", score=0.95, page=0)
    )
    assert accepted is True
    result = agg.finalize()
    assert result.get("billing_date") == "12/02/2026"


def test_complete_bill_promotes_header_billing_date_to_invoice_date():
    fake_collection = _FakeCollection()
    db = object.__new__(MongoDBClient)
    db.collection = fake_collection
    db.validate_schema = False

    bill_data = {
        "header": {"billing_date": "12/02/2026"},
        "patient": {"name": "John Doe"},
        "items": {},
        "subtotals": {},
        "summary": {},
        "grand_total": 0.0,
        "schema_version": 2,
    }

    upload_id = "abc123abc123abc123abc123abc123ab"
    db.complete_bill(upload_id, bill_data)

    assert fake_collection.last_filter == {"_id": upload_id}
    assert fake_collection.last_update is not None
    set_doc = fake_collection.last_update.get("$set", {})
    assert set_doc.get("invoice_date") == "12/02/2026"


def test_extract_bill_data_normalizes_invoice_dt_format():
    ocr_result = {
        "raw_text": "",
        "lines": [
            {"text": "Invoice Dt: 14.02.26", "page": 0, "box": [[0, 10], [120, 10], [120, 20], [0, 20]], "confidence": 0.9},
            {"text": "Bill No: BL123456", "page": 0, "box": [[0, 30], [120, 30], [120, 40], [0, 40]], "confidence": 0.9},
            {"text": "S.No", "page": 0, "box": [[0, 90], [40, 90], [40, 100], [0, 100]], "confidence": 0.9},
        ],
        "item_blocks": [],
    }

    result = extract_bill_data(ocr_result)
    assert result["header"]["billing_date"] == "2026-02-14"

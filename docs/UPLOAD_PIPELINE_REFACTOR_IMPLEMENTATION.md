# Upload Pipeline Refactor Implementation (Schema-Locked)

Date: 2026-02-12  
Scope: FastAPI + MongoDB upload/OCR lifecycle refactor with final bill schema compatibility.

## What Was Changed (Code)

1. `backend/app/db/mongo_client.py`
- Added upload lifecycle methods:
  - `create_upload_record(...)` -> single `insert_one` per PDF.
  - `mark_processing(upload_id)` -> atomic `uploaded/failed -> processing`.
  - `complete_bill(upload_id, bill_data)` -> final `update_one` only.
  - `mark_failed(upload_id, error_message)`.
  - `get_bill_by_request_id(ingestion_request_id)`.
- Added idempotent duplicate handling via unique request key (`ingestion_request_id`).
- Preserved existing bill final fields and added optional metadata only (`original_filename`, `file_size_bytes`, `document_type`, `ingestion_request_id`).

2. `backend/app/db/init_indexes.py`
- Added index: `idx_status_updated_at` on `(status, updated_at)`.
- Added unique sparse index: `idx_ingestion_request_id_unique`.

3. `backend/app/services/upload_pipeline.py` (new)
- New canonical upload orchestration service used by API routes.
- Computes file size from original uploaded PDF bytes (not page images).
- Captures original filename immediately.
- Creates Mongo record first (`status=uploaded`), then processes OCR/extraction.
- Handles duplicate/retry submissions idempotently.

4. `backend/app/main.py`
- `process_bill(...)` now operates on an existing upload record.
- Added `original_filename` parameter.
- Enforces lifecycle transition via `mark_processing`.
- Final persistence now uses `complete_bill` (update-only path).
- On exception, marks document `failed`.
- Still aggregates OCR/page output in memory and writes only final bill document.

5. `backend/app/ingestion/pdf_loader.py`
- Added `original_pdf_name` support.
- Enforced page image naming format using original stem:
  - `<original_pdf_name>_page_1.png`
  - `<original_pdf_name>_page_2.png`

6. `backend/app/api/routes.py`
- `POST /upload` now uses canonical `handle_pdf_upload(...)`.
- Added optional `client_request_id` form field for frontend idempotency.
- Upload response now includes `status`, `original_filename`, `file_size_bytes`.
- `GET /status/{upload_id}` includes filename and file size metadata.
- `GET /bills` now fetches only completed bill-level docs:
  - `status=completed`
  - `upload_id exists`
  - `items is object`
  - `grand_total exists`

7. `backend/app/verifier/api.py`
- `POST /upload` also switched to canonical `handle_pdf_upload(...)`.
- Removes duplicated upload/OCR persistence logic across API surfaces.

8. `backend/scripts/migrate_corrupted_bills.py` (new)
- Safe migration utility (dry-run default).
- Finds duplicate `upload_id` docs and page/intermediate artifacts.
- Archives removable docs to `bills_archive` before deletion.

## Root Cause Diagnosis

Frontend retry behavior + multiple upload API surfaces + non-idempotent upload writes can cause multiple inserts for one logical PDF request. If each request independently processes/saves, dashboard sees duplicates and mixed intermediate artifacts.

## Schema Preservation Strategy

Final bill verification contract is preserved:
- `items` and nested item shape remain intact.
- `subtotals`, `grand_total`, `hospital_name`, `upload_id`, `schema_version` remain available.
- No restructuring/renaming of final verification fields.
- Enhancements were additive metadata only.

## Correct Mongo Lifecycle

- Exactly one `insert_one` at upload creation (`uploaded`).
- All subsequent changes use `update_one`:
  - `uploaded -> processing`
  - `processing -> completed` (final aggregated bill)
  - `processing -> failed` (error capture)
- Status transitions are atomic and race-safe.

## Safe Upload Flow

1. Read original `UploadFile` bytes.
2. Capture:
- original filename
- original file size bytes
- hospital name
- idempotency key (`client_request_id` or deterministic fallback hash)
3. Insert one Mongo record immediately (`uploaded`).
4. Run OCR/extraction pipeline.
5. Final update to same document (`completed`) or failure update (`failed`).

## Safe OCR Pipeline

- Page processing is internal only.
- No page-level inserts in main collection.
- Aggregation remains in memory until final single completion update.
- Partial OCR page failures are tolerated by OCR engine loop (failed pages skipped, remaining pages processed).

## Dashboard Query Fix

Dashboard now only reads completed bill-level records, preventing page/intermediate documents from appearing.

## Backward Compatibility Validation Strategy

Recommended validation script/test approach:
1. Export a known pre-refactor final bill JSON (golden sample).
2. Re-run same PDF through new pipeline.
3. Compare locked fields and types:
- `items` category object
- each item `description/amount/category/page`
- `subtotals`, `grand_total`, `hospital_name`, `upload_id`, `schema_version`
4. Fail test on any structural/type drift.

## Migration Plan

Use `backend/scripts/migrate_corrupted_bills.py`:
1. Run dry-run first.
2. Inspect counts.
3. Run `--apply` in maintenance window.
4. Verify archive collection and dashboard output.

## Concurrency Safety

- Unique sparse index on `ingestion_request_id`.
- Duplicate/retry requests return existing upload context instead of inserting new docs.
- Atomic `mark_processing` avoids dual workers processing same upload simultaneously.

## Scale Readiness Notes (10k PDFs/day)

- Lifecycle is worker-friendly (`uploaded/processing/completed/failed`).
- Upload route and processing flow are cleanly separable for future background queue migration.
- Mongo indexes support status/dashboard queries.
- No page-level document fanout into main collection.

## Frontend Changes Required

Yes, small but important changes are recommended:

1. Send `client_request_id` on upload (UUID per user upload action).
- Endpoint: `POST /upload`
- Field: `client_request_id` (form-data)
- Purpose: prevents duplicate bill docs on retries/double-clicks.

2. Use backend `upload_id` as the only bill identity in UI.
- Do not infer identity from filename or row index.

3. Read and display metadata from response/status:
- `original_filename`
- `file_size_bytes`
- `status` (`uploaded`, `processing`, `completed`, `failed`)

4. Dashboard should consume `GET /bills` output as-is.
- It is now filtered server-side to completed bill-level documents.


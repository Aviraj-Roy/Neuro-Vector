# Recent Changes

Date: 2026-02-20

## Scope

This document summarizes the recent updates made across:
- Backend: `Neuro-Vector-Backend`
- Frontend: `../Neuro-Vector-Frontend/frontend`

## Backend Changes

### 1. Tie-up Rate Edit Support (line-item PATCH flow)

File:
- `backend/app/api/routes.py`

What was implemented:
- `LineItemEditInput` supports `tieup_rate` edits.
- Validation allows line-item edit payloads when any of `qty`, `rate`, or `tieup_rate` is provided.
- PATCH persistence stores `tieup_rate` in `line_item_edits`.
- Recompute logic applies edited `tieup_rate` and computes:
  - `amount_to_be_paid = qty * tieup_rate` when both are available.
- Existing qty/rate behavior remains backward compatible.

Tests:
- `backend/tests/test_bill_details_api.py`
- Added tie-up specific cases:
  - tieup-rate-only PATCH payload accepted
  - tieup-rate edit persisted
  - payable recomputed using edited tieup rate

Validation:
- `python -m pytest -q backend/tests/test_bill_details_api.py` passed.

### 2. Discrepancy Flag from DB/Recomputed Data

File:
- `backend/app/api/routes.py`

What was implemented:
- `BillLineItem` includes `discrepancy: Optional[bool]`.
- Added boolean normalizer to safely map bool-like values (`true/false/yes/no/y/n/1/0`).
- Stored line-item normalization includes discrepancy mapping.
- Recomputed line items include discrepancy from verification item, with fallback to source item, preserving explicit `False`.
- Added backfill for stored `line_items`: if discrepancy is missing, fill from matching source `items` entry.

Tests:
- `backend/tests/test_bill_details_api.py`
- Added cases for:
  - stored discrepancy normalization (`True/False/null`)
  - recompute prefers explicit item value and preserves `False`
  - recompute fallback from source item discrepancy
  - stored line-item discrepancy backfill from source item

Validation:
- `python -m pytest -q backend/tests/test_bill_details_api.py` passed (latest run: 19 passed).

## Frontend Changes

### 1. Tie-up Rate Editing + Payload

Files:
- `../Neuro-Vector-Frontend/frontend/src/components/results/CategoryResultTable.jsx`
- `../Neuro-Vector-Frontend/frontend/src/pages/ResultPage.jsx`
- `../Neuro-Vector-Frontend/frontend/src/utils/billEditsStorage.js`
- `../Neuro-Vector-Frontend/frontend/src/utils/verificationResultParser.js`

What was implemented:
- “Edit Tieup Rate” edits `tieupRate` (not billed `rate`).
- Save payload generation supports tieup diffs via `tieup_rate`.
- Original tieup values tracked in UI state (`originalTieupRate`).
- Local storage persists/restores tieup edit state.
- Parser aliases support tieup edit labels.

### 2. Financial Summary Display Updates

File:
- `../Neuro-Vector-Frontend/frontend/src/components/results/FinancialSummaryCard.jsx`

What was implemented:
- Hid `Total Allowed`, `Total Extra`, and `Total Unclassified`.
- Added `Total Amount to be Paid` alongside `Total Billed`.

### 3. Total Amount to be Paid Source of Truth

File:
- `../Neuro-Vector-Frontend/frontend/src/pages/ResultPage.jsx`

What was implemented:
- `Total Amount to be Paid` is computed from table/category row values (`amountToBePaid`), summed across categories.

Validation:
- `cmd /c npm run build` in `../Neuro-Vector-Frontend/frontend` passed after these frontend updates.

## Delete API Compatibility Review

Result:
- No backend changes required for recent frontend delete updates (multi-select + per-bill delete calls).
- Existing endpoints are sufficient:
  - `DELETE /bills/{id}`
  - `DELETE /bill/{id}` (legacy alias)


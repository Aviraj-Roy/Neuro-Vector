# Quick API Reference

## 🚀 Main Endpoint for Frontend

### POST /upload
**Upload and process a medical bill PDF**

```javascript
// JavaScript/React Example
const formData = new FormData();
formData.append('file', pdfFile);  // File object from input
formData.append('hospital_name', selectedHospital);  // String

const response = await fetch('http://localhost:8001/upload', {
  method: 'POST',
  body: formData
});

const result = await response.json();
// result.upload_id - Use this for verification
```

**Response:**
```json
{
  "success": true,
  "upload_id": "abc123...",
  "hospital_name": "Apollo Hospital",
  "message": "Bill processed successfully",
  "page_count": 3,
  "total_items": 15,
  "grand_total": 25000.50
}
```

---

## 🔍 Verify Uploaded Bill

### POST /verify/{upload_id}

```javascript
const uploadId = result.upload_id;  // From upload response
const verifyResponse = await fetch(`http://localhost:8001/verify/${uploadId}`, {
  method: 'POST'
});

const verification = await verifyResponse.json();
```

---

## 🏥 Get Available Hospitals

### GET /tieups

```javascript
const response = await fetch('http://localhost:8001/tieups');
const data = await response.json();
// data.hospitals - Array of hospital names
```

---

## ❤️ Health Check

### GET /health

```javascript
const response = await fetch('http://localhost:8001/health');
const health = await response.json();
```

---

## 🔧 Start Backend Server

```bash
cd c:\Users\USER\Documents\test\Neuro-Vector-Backend
uvicorn backend.app.verifier.api:app --reload --port 8001
```

**Server will run on:** `http://localhost:8001`

**Interactive docs:** `http://localhost:8001/docs`

---

## 📋 Complete Frontend Flow

```javascript
// 1. Upload PDF
const formData = new FormData();
formData.append('file', pdfFile);
formData.append('hospital_name', 'Apollo Hospital');

const uploadRes = await fetch('http://localhost:8001/upload', {
  method: 'POST',
  body: formData
});
const { upload_id } = await uploadRes.json();

// 2. Verify the bill
const verifyRes = await fetch(`http://localhost:8001/verify/${upload_id}`, {
  method: 'POST'
});
const verification = await verifyRes.json();

// 3. Display results
console.log(verification.verification_summary);
```

---

## ⚠️ Important Notes

- **File type:** Only PDF files accepted
- **Hospital name:** Must match exactly with tie-up data
- **CORS:** Already enabled for local development
- **Port:** Backend runs on 8001, frontend can run on any other port
- **MongoDB:** Must be running before starting backend

---

## Bills Dashboard Scopes

### GET /bills
List dashboard bills by scope.

Query params:
- `scope=active|deleted` (default `active`)
- `status=PENDING|PROCESSING|COMPLETED` (optional)
- `hospital_name` (optional, case-insensitive exact match)
- `date_filter=TODAY|YESTERDAY|THIS_MONTH|LAST_MONTH` (optional, server timezone)

### GET /bills/deleted
Shortcut endpoint for deleted scope with same optional filters.

### DELETE /bills/{bill_id}
- Soft delete by default (`permanent=false`)
- Permanent delete with `permanent=true` (only allowed after soft delete)

### POST /bills/{bill_id}/restore
Restore a soft-deleted bill back to active scope.

Example soft delete:
```bash
curl -X DELETE "http://localhost:8001/bills/<bill_id>"
```

Example restore:
```bash
curl -X POST "http://localhost:8001/bills/<bill_id>/restore"
```

Example permanent delete:
```bash
curl -X DELETE "http://localhost:8001/bills/<bill_id>?permanent=true"
```

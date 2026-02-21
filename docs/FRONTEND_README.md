# 🎯 Frontend-Backend Integration - Quick Start

## The API Endpoint You Need

```
POST http://localhost:8001/upload
```

## How to Use It

### JavaScript/React Example

```javascript
const formData = new FormData();
formData.append('file', pdfFile);              // Your PDF file
formData.append('hospital_name', hospitalName); // e.g., "Apollo Hospital"

const response = await fetch('http://localhost:8001/upload', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log('Upload ID:', result.upload_id);
```

### Response You'll Get

```json
{
  "success": true,
  "upload_id": "abc123def456",
  "hospital_name": "Apollo Hospital",
  "message": "Bill processed successfully. Use upload_id to verify.",
  "page_count": 3,
  "total_items": 15,
  "grand_total": 25000.50
}
```

## Start the Backend

**Double-click:** `start_api_server.bat`

**Or run:**
```bash
uvicorn backend.app.verifier.api:app --reload --port 8001
```

## Test It

```bash
python test_upload_api.py
```

## Documentation

- **Quick Reference:** `QUICK_API_REFERENCE.md`
- **Complete Guide:** `API_DOCUMENTATION.md`
- **Full Solution:** `COMPLETE_SOLUTION.md`

## That's It!

Your backend is ready. Just start the server and connect your frontend! 🚀

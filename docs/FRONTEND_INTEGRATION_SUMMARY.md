# Frontend-Backend Integration Summary

## ✅ What Has Been Implemented

### Backend API Enhancements

1. **New Upload Endpoint** (`POST /upload`)
   - Accepts PDF file uploads via multipart/form-data
   - Accepts hospital name as form parameter
   - Processes bill with OCR and extraction
   - Returns upload_id and processing summary
   - Location: `backend/app/verifier/api.py`

2. **CORS Configuration**
   - Enabled cross-origin requests for local development
   - Allows frontend to communicate with backend from different ports
   - Can be configured for production with specific domains

3. **Response Models**
   - `UploadResponse`: Structured response for upload endpoint
   - Includes upload_id, hospital_name, page_count, total_items, grand_total

4. **File Handling**
   - Temporary file management for uploaded PDFs
   - Automatic cleanup after processing
   - Validation for PDF file types

---

## 📡 API Endpoints Available

| Endpoint | Method | Purpose | Frontend Use |
|----------|--------|---------|--------------|
| `/upload` | POST | Upload & process PDF | Primary upload action |
| `/verify/{upload_id}` | POST | Verify processed bill | Get verification results |
| `/health` | GET | Check API status | Health monitoring |
| `/tieups` | GET | List hospitals | Populate hospital dropdown |
| `/tieups/reload` | POST | Reload rate sheets | Admin function |

---

## 🔗 Frontend Integration

### Base URL
```javascript
const API_BASE_URL = 'http://localhost:8001';
```

### Main Upload Flow

```javascript
// 1. Create FormData with PDF and hospital name
const formData = new FormData();
formData.append('file', pdfFile);  // From <input type="file">
formData.append('hospital_name', selectedHospital);  // From dropdown/input

// 2. Upload to backend
const uploadResponse = await fetch(`${API_BASE_URL}/upload`, {
  method: 'POST',
  body: formData
});

const uploadData = await uploadResponse.json();
// uploadData.upload_id - Save this for verification

// 3. Verify the uploaded bill
const verifyResponse = await fetch(
  `${API_BASE_URL}/verify/${uploadData.upload_id}`,
  { method: 'POST' }
);

const verificationData = await verifyResponse.json();
// Display verification results to user
```

---

## 🚀 How to Start the Backend

### Method 1: Double-click the batch file
```
start_api_server.bat
```

### Method 2: Command line
```bash
cd c:\Users\USER\Documents\test\Neuro-Vector-Backend
uvicorn backend.app.verifier.api:app --reload --port 8001
```

### Method 3: Python module
```bash
python -m uvicorn backend.app.verifier.api:app --reload --port 8001
```

**Server will be available at:** `http://localhost:8001`

**Interactive API documentation:** `http://localhost:8001/docs`

---

## 📋 Required Services

Before starting the backend, ensure these are running:

1. **MongoDB**
   - Default: `localhost:27017`
   - Required for storing processed bills

2. **Python Environment**
   - All dependencies installed: `pip install -r backend/requirements.txt`

3. **Ollama** (Optional)
   - For LLM-based verification enhancements
   - Not required for basic functionality

---

## 🏥 Hospital Names

The hospital name must match one of the tie-up rate sheets. Available hospitals:

- Apollo Hospital
- Fortis Hospital
- Manipal Hospital
- Narayana Hospital

You can get the list dynamically via `GET /tieups` endpoint.

---

## 📁 Files Created/Modified

### New Files
1. `API_DOCUMENTATION.md` - Complete API reference with examples
2. `QUICK_API_REFERENCE.md` - Quick reference for common operations
3. `start_api_server.bat` - Windows startup script
4. `FRONTEND_INTEGRATION_SUMMARY.md` - This file

### Modified Files
1. `backend/app/verifier/api.py`
   - Added `/upload` endpoint
   - Added CORS middleware
   - Added file upload handling
   - Added `UploadResponse` model

---

## 🧪 Testing the API

### Using cURL
```bash
# Health check
curl http://localhost:8001/health

# Upload a bill
curl -X POST "http://localhost:8001/upload" \
  -F "file=@Apollo.pdf" \
  -F "hospital_name=Apollo Hospital"

# Verify (replace with actual upload_id)
curl -X POST "http://localhost:8001/verify/abc123..."
```

### Using Postman
1. Create new POST request to `http://localhost:8001/upload`
2. Select Body → form-data
3. Add key `file` (type: File) and select PDF
4. Add key `hospital_name` (type: Text) with value "Apollo Hospital"
5. Send request

### Using Browser (Swagger UI)
1. Navigate to `http://localhost:8001/docs`
2. Find `/upload` endpoint
3. Click "Try it out"
4. Upload file and enter hospital name
5. Execute

---

## 🎯 Frontend Implementation Checklist

- [ ] Set up API base URL configuration
- [ ] Create file upload component with PDF input
- [ ] Create hospital name input/dropdown
- [ ] Implement upload handler with FormData
- [ ] Handle upload response (save upload_id)
- [ ] Implement verification call using upload_id
- [ ] Display verification results
- [ ] Add error handling for failed uploads
- [ ] Add loading states during processing
- [ ] Test with different PDF files

---

## 🔒 Security Notes

### Current Configuration (Development)
- CORS allows all origins (`*`)
- No authentication required
- Suitable for local development only

### Production Recommendations
1. Update CORS to specific frontend domain
2. Add authentication (API keys, JWT, etc.)
3. Add rate limiting
4. Validate file sizes
5. Add virus scanning for uploads
6. Use HTTPS

---

## 📊 Response Examples

### Upload Response
```json
{
  "success": true,
  "upload_id": "a1b2c3d4e5f6",
  "hospital_name": "Apollo Hospital",
  "message": "Bill processed successfully. Use upload_id to verify.",
  "page_count": 3,
  "total_items": 15,
  "grand_total": 25000.50
}
```

### Verification Response
```json
{
  "hospital_name": "Apollo Hospital",
  "verification_summary": {
    "total_bill_amount": 25000.50,
    "total_allowed_amount": 22000.00,
    "total_extra_amount": 3000.50,
    "matched_items": 12,
    "mismatched_items": 3,
    "coverage_percentage": 88.0
  },
  "categories": [...]
}
```

---

## 🐛 Troubleshooting

### Backend won't start
- Check if MongoDB is running
- Verify Python dependencies are installed
- Check if port 8001 is already in use

### CORS errors in frontend
- Verify CORS middleware is added (already done)
- Check browser console for specific error
- Ensure backend is running before frontend requests

### Upload fails
- Verify file is PDF format
- Check file size (very large files may timeout)
- Ensure hospital name is provided
- Check backend logs for errors

### Verification returns 404
- Verify upload_id is correct
- Check if bill was successfully stored in MongoDB
- Use `/health` endpoint to verify system status

---

## 📞 Support

For issues or questions:
1. Check `API_DOCUMENTATION.md` for detailed examples
2. Use Swagger UI at `http://localhost:8001/docs` for interactive testing
3. Check backend logs for error messages
4. Verify all required services are running

---

## 🎉 Quick Start Summary

1. **Start MongoDB** (if not already running)
2. **Start Backend:** Run `start_api_server.bat` or use uvicorn command
3. **Verify Backend:** Open `http://localhost:8001/docs` in browser
4. **Frontend Code:** Use the examples in `API_DOCUMENTATION.md`
5. **Test Upload:** Use Swagger UI or your frontend to upload a PDF

**You're all set! The backend is ready to receive PDF uploads from your frontend.**

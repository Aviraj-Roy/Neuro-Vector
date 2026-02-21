# Medical Bill Verification API Documentation

## Overview

This document provides complete API documentation for the Medical Bill Verification backend system. The API allows you to upload medical bills (PDF), process them with OCR, and verify them against hospital tie-up rates.

## Base URL

When running locally:
```
http://localhost:8001
```

## API Endpoints

### 1. Health Check

**Endpoint:** `GET /health`

**Description:** Check if the API is running and the verifier is initialized.

**Response:**
```json
{
  "status": "healthy",
  "verifier_initialized": true,
  "hospitals_indexed": 5
}
```

---

### 2. Upload and Process Bill (Main Endpoint)

**Endpoint:** `POST /upload`

**Description:** Upload a PDF medical bill and process it with OCR and data extraction.

**Request Type:** `multipart/form-data`

**Parameters:**
- `file` (File, required): PDF file of the medical bill
- `hospital_name` (String, required): Name of the hospital (e.g., "Apollo Hospital", "Fortis Hospital")

**Example using cURL:**
```bash
curl -X POST "http://localhost:8001/upload" \
  -F "file=@/path/to/bill.pdf" \
  -F "hospital_name=Apollo Hospital"
```

**Example using JavaScript (Fetch API):**
```javascript
const formData = new FormData();
formData.append('file', pdfFile); // pdfFile is a File object
formData.append('hospital_name', 'Apollo Hospital');

const response = await fetch('http://localhost:8001/upload', {
  method: 'POST',
  body: formData
});

const result = await response.json();
console.log(result);
```

**Example using Axios:**
```javascript
import axios from 'axios';

const formData = new FormData();
formData.append('file', pdfFile);
formData.append('hospital_name', 'Apollo Hospital');

const response = await axios.post('http://localhost:8001/upload', formData, {
  headers: {
    'Content-Type': 'multipart/form-data'
  }
});

console.log(response.data);
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "upload_id": "a1b2c3d4e5f6g7h8i9j0",
  "hospital_name": "Apollo Hospital",
  "message": "Bill processed successfully. Use upload_id to verify.",
  "page_count": 3,
  "total_items": 15,
  "grand_total": 25000.50
}
```

**Error Responses:**

- **400 Bad Request** - Invalid file type or missing hospital name
```json
{
  "detail": "Only PDF files are accepted"
}
```

- **500 Internal Server Error** - Processing failed
```json
{
  "detail": "Failed to process bill: [error message]"
}
```

---

### 3. Verify Bill from MongoDB

**Endpoint:** `POST /verify/{upload_id}`

**Description:** Verify a previously uploaded bill against tie-up rates.

**Parameters:**
- `upload_id` (Path parameter, required): The upload_id returned from the `/upload` endpoint

**Example:**
```bash
curl -X POST "http://localhost:8001/verify/a1b2c3d4e5f6g7h8i9j0"
```

**Example using JavaScript:**
```javascript
const uploadId = 'a1b2c3d4e5f6g7h8i9j0';
const response = await fetch(`http://localhost:8001/verify/${uploadId}`, {
  method: 'POST'
});

const verificationResult = await response.json();
console.log(verificationResult);
```

**Success Response (200 OK):**
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
  "categories": [
    {
      "category_name": "medicines",
      "items": [
        {
          "item_name": "Paracetamol 500mg",
          "status": "MATCH",
          "bill_amount": 50.00,
          "allowed_amount": 50.00,
          "extra_amount": 0.00,
          "similarity_score": 0.95
        }
      ]
    }
  ]
}
```

---

### 4. List Available Hospitals

**Endpoint:** `GET /tieups`

**Description:** Get a list of all hospitals with loaded tie-up rate sheets.

**Example:**
```bash
curl -X GET "http://localhost:8001/tieups"
```

**Response:**
```json
{
  "hospitals": [
    "Apollo Hospital",
    "Fortis Hospital",
    "Manipal Hospital",
    "Narayana Hospital"
  ],
  "count": 4
}
```

---

### 5. Reload Tie-up Rate Sheets

**Endpoint:** `POST /tieups/reload`

**Description:** Reload tie-up rate sheets from the data directory (admin endpoint).

**Example:**
```bash
curl -X POST "http://localhost:8001/tieups/reload"
```

**Response:**
```json
{
  "success": true,
  "hospitals_loaded": 4,
  "message": "Successfully loaded 4 tie-up rate sheets"
}
```

---

## Complete Frontend Integration Example

### React Component Example

```javascript
import React, { useState } from 'react';
import axios from 'axios';

const BillUploadComponent = () => {
  const [file, setFile] = useState(null);
  const [hospitalName, setHospitalName] = useState('');
  const [uploadResult, setUploadResult] = useState(null);
  const [verificationResult, setVerificationResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const API_BASE_URL = 'http://localhost:8001';

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file || !hospitalName) {
      setError('Please select a file and enter hospital name');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Step 1: Upload and process the bill
      const formData = new FormData();
      formData.append('file', file);
      formData.append('hospital_name', hospitalName);

      const uploadResponse = await axios.post(
        `${API_BASE_URL}/upload`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        }
      );

      setUploadResult(uploadResponse.data);
      console.log('Upload successful:', uploadResponse.data);

      // Step 2: Verify the uploaded bill
      const verifyResponse = await axios.post(
        `${API_BASE_URL}/verify/${uploadResponse.data.upload_id}`
      );

      setVerificationResult(verifyResponse.data);
      console.log('Verification complete:', verifyResponse.data);

    } catch (err) {
      setError(err.response?.data?.detail || err.message);
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>Upload Medical Bill</h2>
      
      <div>
        <label>Hospital Name:</label>
        <input
          type="text"
          value={hospitalName}
          onChange={(e) => setHospitalName(e.target.value)}
          placeholder="e.g., Apollo Hospital"
        />
      </div>

      <div>
        <label>Select PDF:</label>
        <input
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
        />
      </div>

      <button onClick={handleUpload} disabled={loading}>
        {loading ? 'Processing...' : 'Upload and Verify'}
      </button>

      {error && <div style={{ color: 'red' }}>{error}</div>}

      {uploadResult && (
        <div>
          <h3>Upload Result</h3>
          <p>Upload ID: {uploadResult.upload_id}</p>
          <p>Pages: {uploadResult.page_count}</p>
          <p>Total Items: {uploadResult.total_items}</p>
          <p>Grand Total: ₹{uploadResult.grand_total}</p>
        </div>
      )}

      {verificationResult && (
        <div>
          <h3>Verification Result</h3>
          <p>Total Bill Amount: ₹{verificationResult.verification_summary.total_bill_amount}</p>
          <p>Allowed Amount: ₹{verificationResult.verification_summary.total_allowed_amount}</p>
          <p>Extra Amount: ₹{verificationResult.verification_summary.total_extra_amount}</p>
          <p>Coverage: {verificationResult.verification_summary.coverage_percentage}%</p>
        </div>
      )}
    </div>
  );
};

export default BillUploadComponent;
```

---

## Running the Backend Server

### Option 1: Using uvicorn directly
```bash
cd c:\Users\USER\Documents\test\Neuro-Vector-Backend
uvicorn backend.app.verifier.api:app --reload --port 8001 --host 0.0.0.0
```

### Option 2: Using Python module
```bash
cd c:\Users\USER\Documents\test\Neuro-Vector-Backend
python -m uvicorn backend.app.verifier.api:app --reload --port 8001 --host 0.0.0.0
```

### Option 3: Direct execution
```bash
cd c:\Users\USER\Documents\test\Neuro-Vector-Backend\backend
python -m app.verifier.api
```

---

## Environment Setup

Make sure you have the following services running:

1. **MongoDB** - For storing processed bills
2. **Ollama** (optional) - For LLM-based verification
3. **Python dependencies** - Install via `pip install -r requirements.txt`

---

## CORS Configuration

The API is configured to accept requests from any origin (`allow_origins=["*"]`). 

**For production**, update the CORS settings in `backend/app/verifier/api.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],  # Specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Available Hospitals

The system supports the following hospitals (based on tie-up rate sheets in `backend/data/tieups/`):

- Apollo Hospital
- Fortis Hospital
- Manipal Hospital
- Narayana Hospital
- (Add more as JSON files are added to the tieups directory)

---

## Error Handling

All endpoints return standard HTTP status codes:

- **200 OK** - Request successful
- **400 Bad Request** - Invalid input (missing file, wrong format, etc.)
- **404 Not Found** - Resource not found (e.g., upload_id doesn't exist)
- **422 Unprocessable Entity** - Invalid data format
- **500 Internal Server Error** - Server-side processing error

Error responses include a `detail` field with a descriptive message:

```json
{
  "detail": "Error description here"
}
```

---

## Interactive API Documentation

Once the server is running, you can access interactive API documentation at:

- **Swagger UI:** http://localhost:8001/docs
- **ReDoc:** http://localhost:8001/redoc

These interfaces allow you to test all endpoints directly from your browser.

---

## Quick Start Guide

1. **Start MongoDB:**
   ```bash
   # Make sure MongoDB is running on localhost:27017
   ```

2. **Start the Backend API:**
   ```bash
   cd c:\Users\USER\Documents\test\Neuro-Vector-Backend
   uvicorn backend.app.verifier.api:app --reload --port 8001
   ```

3. **Test the API:**
   ```bash
   # Health check
   curl http://localhost:8001/health
   
   # Upload a bill
   curl -X POST "http://localhost:8001/upload" \
     -F "file=@Apollo.pdf" \
     -F "hospital_name=Apollo Hospital"
   ```

4. **Use from Frontend:**
   - Set API base URL to `http://localhost:8001`
   - Use the `/upload` endpoint with FormData
   - Use the returned `upload_id` to verify the bill

---

## Notes

- The system processes PDFs locally using OCR (PaddleOCR)
- All data is stored in MongoDB
- Verification uses semantic matching against hospital tie-up rates
- The upload endpoint handles the entire processing pipeline automatically
- CORS is enabled for local development

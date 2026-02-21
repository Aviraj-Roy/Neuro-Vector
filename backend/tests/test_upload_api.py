"""
Test script to verify the API upload endpoint is working correctly.

Usage:
    python test_upload_api.py
"""

import requests
import os
from pathlib import Path

# Configuration
API_BASE_URL = "http://localhost:8001"
BACKEND_DIR = Path(__file__).parent / "backend"
ROOT_DIR = Path(__file__).parent

def test_health_check():
    """Test if the API is running."""
    print("🔍 Testing health check endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API is healthy!")
            print(f"   - Status: {data['status']}")
            print(f"   - Verifier initialized: {data['verifier_initialized']}")
            print(f"   - Hospitals indexed: {data['hospitals_indexed']}")
            return True
        else:
            print(f"❌ Health check failed with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {API_BASE_URL}")
        print("   Make sure the backend server is running:")
        print("   uvicorn backend.app.verifier.api:app --reload --port 8001")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_list_hospitals():
    """Test listing available hospitals."""
    print("\n🏥 Testing hospital list endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/tieups")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {data['count']} hospitals:")
            for hospital in data['hospitals']:
                print(f"   - {hospital}")
            return data['hospitals']
        else:
            print(f"❌ Failed to get hospitals: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error: {e}")
        return []


def test_upload_bill(pdf_path: str, hospital_name: str):
    """Test uploading a bill."""
    print(f"\n📤 Testing upload endpoint...")
    print(f"   PDF: {pdf_path}")
    print(f"   Hospital: {hospital_name}")
    
    if not os.path.exists(pdf_path):
        print(f"❌ PDF file not found: {pdf_path}")
        return None
    
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (os.path.basename(pdf_path), f, 'application/pdf')}
            data = {'hospital_name': hospital_name}
            
            print("   Uploading... (this may take a minute)")
            response = requests.post(
                f"{API_BASE_URL}/upload",
                files=files,
                data=data,
                timeout=120  # 2 minute timeout for OCR processing
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Upload successful!")
            print(f"   - Upload ID: {result['upload_id']}")
            print(f"   - Pages: {result['page_count']}")
            print(f"   - Total Items: {result['total_items']}")
            print(f"   - Grand Total: ₹{result['grand_total']}")
            return result['upload_id']
        else:
            print(f"❌ Upload failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ Upload timed out (processing took too long)")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_verify_bill(upload_id: str):
    """Test verifying a bill."""
    print(f"\n🔍 Testing verification endpoint...")
    print(f"   Upload ID: {upload_id}")
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/verify/{upload_id}",
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            summary = result.get('verification_summary', {})
            print(f"✅ Verification successful!")
            print(f"   - Total Bill Amount: ₹{summary.get('total_bill_amount', 0)}")
            print(f"   - Allowed Amount: ₹{summary.get('total_allowed_amount', 0)}")
            print(f"   - Extra Amount: ₹{summary.get('total_extra_amount', 0)}")
            print(f"   - Coverage: {summary.get('coverage_percentage', 0)}%")
            print(f"   - Matched Items: {summary.get('matched_items', 0)}")
            print(f"   - Mismatched Items: {summary.get('mismatched_items', 0)}")
            return True
        else:
            print(f"❌ Verification failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Medical Bill Verification API - Test Suite")
    print("=" * 60)
    
    # Test 1: Health check
    if not test_health_check():
        print("\n⚠️  API is not running. Please start the backend server first.")
        return
    
    # Test 2: List hospitals
    hospitals = test_list_hospitals()
    if not hospitals:
        print("\n⚠️  No hospitals found. Verification may not work.")
    
    # Test 3: Upload a bill (if test PDF exists)
    test_pdfs = [
        (ROOT_DIR / "Apollo.pdf", "Apollo Hospital"),
        (ROOT_DIR / "M_Bill.pdf", "Manipal Hospital"),
        (ROOT_DIR / "Apollo Bill.pdf", "Apollo Hospital"),
    ]
    
    upload_id = None
    for pdf_path, hospital in test_pdfs:
        if pdf_path.exists():
            upload_id = test_upload_bill(str(pdf_path), hospital)
            if upload_id:
                break
    
    if not upload_id:
        print("\n⚠️  No test PDF found. Skipping upload test.")
        print("   Available test PDFs:")
        for pdf_path, _ in test_pdfs:
            print(f"   - {pdf_path}")
        return
    
    # Test 4: Verify the uploaded bill
    test_verify_bill(upload_id)
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    print("\nYou can now use the API from your frontend:")
    print(f"   Base URL: {API_BASE_URL}")
    print(f"   Upload endpoint: POST {API_BASE_URL}/upload")
    print(f"   Verify endpoint: POST {API_BASE_URL}/verify/{{upload_id}}")
    print(f"   Interactive docs: {API_BASE_URL}/docs")


if __name__ == "__main__":
    main()

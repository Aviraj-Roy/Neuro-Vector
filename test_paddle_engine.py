import os
import json
from app.ocr.paddle_engine import run_ocr

# 1. Define the path to your image
# Make sure this matches the output folder from your previous PDF step
image_path = "uploads/medical_bill-2_page_1.png"

def test_ocr_processing():
    print(f"--- Starting OCR Test ---")
    
    # 2. Check if the file actually exists before running
    if not os.path.exists(image_path):
        print(f"ERROR: File not found at {os.path.abspath(image_path)}")
        print("Please check if your 'pdf_to_images' function ran correctly first.")
        return

    try:
        # 3. Run the OCR function
        print(f"Processing image: {image_path}...")
        result = run_ocr(image_path)

        # 4. Display the results
        print("\n" + "="*30)
        print("1. FULL EXTRACTED TEXT:")
        print("="*30)
        if result["raw_text"].strip():
            print(result["raw_text"])
        else:
            print("[No text detected in image]")

        print("\n" + "="*30)
        print("2. LINE-BY-LINE DATA (First 5 lines):")
        print("="*30)
        # Showing just the first 5 to keep the terminal clean
        for i, line in enumerate(result["lines"][:5]):
            print(f"Line {i+1}: Text='{line['text']}' | Confidence={line['confidence']:.2f}")
        
        if len(result["lines"]) > 5:
            print(f"... and {len(result['lines']) - 5} more lines.")

    except Exception as e:
        print(f"An unexpected error occurred during the test: {e}")

if __name__ == "__main__":
    test_ocr_processing()
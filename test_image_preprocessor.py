from app.ocr.image_preprocessor import preprocess_image

processed_path = preprocess_image("uploads/medical_bill-2_page_1.png")
print("Processed image saved at:", processed_path)

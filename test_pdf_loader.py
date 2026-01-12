from app.ingestion.pdf_loader import pdf_to_images

image_paths = pdf_to_images("medical_bill-2.pdf")
print(image_paths)

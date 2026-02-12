"""PDF to Image Conversion.

Converts PDF pages to PNG images using pdf2image.
Uses absolute paths to avoid CWD-dependent failures.
"""

import os
import re
from pathlib import Path
from typing import List
from pdf2image import convert_from_path

POPPLER_PATH = r"C:\poppler\Library\bin"


def _sanitize_stem(name: str) -> str:
    stem = re.sub(r"\s+", "_", (name or "").strip())
    stem = re.sub(r"[^A-Za-z0-9._-]", "", stem)
    return stem or "uploaded_bill"


def pdf_to_images(pdf_path: str, output_dir: str = None, original_pdf_name: str | None = None) -> List[str]:
    """Convert PDF to images with absolute path handling.
    
    Args:
        pdf_path: The file path to the source PDF document.
        output_dir: The directory where the resulting image files will be saved.
                   Defaults to backend/uploads (absolute path).
    
    Returns:
        List[str]: The ABSOLUTE file paths of all the PNG images created.
        
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        RuntimeError: If PDF conversion fails
    """
    # Validate input PDF exists
    pdf_path_obj = Path(pdf_path).resolve()
    if not pdf_path_obj.exists():
        raise FileNotFoundError(
            f"❌ PDF File Not Found\n"
            f"{'='*80}\n"
            f"Path: {pdf_path}\n"
            f"Absolute Path: {pdf_path_obj}\n"
            f"Exists: False\n\n"
            f"Fix:\n"
            f"  1. Verify the PDF file exists\n"
            f"  2. Check the file path is correct\n"
            f"  3. Ensure you have read permissions\n"
            f"{'='*80}"
        )
    
    # Get absolute output directory
    if output_dir is None:
        from app.config import get_uploads_dir
        output_dir = get_uploads_dir()  # Returns absolute path
    else:
        # Ensure output_dir is absolute
        output_dir = str(Path(output_dir).resolve())
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Convert PDF to images
        images = convert_from_path(
            pdf_path=str(pdf_path_obj),  # Use absolute path
            poppler_path=POPPLER_PATH
        )
    except Exception as e:
        raise RuntimeError(
            f"❌ PDF Conversion Failed\n"
            f"{'='*80}\n"
            f"PDF: {pdf_path_obj}\n"
            f"Error: {type(e).__name__}: {str(e)}\n\n"
            f"Possible Causes:\n"
            f"  1. Poppler not installed or not in PATH\n"
            f"  2. Corrupted PDF file\n"
            f"  3. Insufficient memory\n\n"
            f"Fix:\n"
            f"  1. Install Poppler: https://github.com/oschwartz10612/poppler-windows/releases\n"
            f"  2. Verify PDF opens in a PDF reader\n"
            f"  3. Check available system memory\n"
            f"{'='*80}"
        ) from e
    
    # Save images and collect absolute paths
    image_paths = []
    if original_pdf_name:
        base_name = _sanitize_stem(os.path.splitext(original_pdf_name)[0])
    else:
        base_name = _sanitize_stem(os.path.splitext(os.path.basename(str(pdf_path_obj)))[0])
    
    for i, image in enumerate(images):
        # Use absolute path for image file
        image_path = os.path.join(output_dir, f"{base_name}_page_{i + 1}.png")
        image_path_abs = str(Path(image_path).resolve())
        
        try:
            image.save(image_path_abs, "PNG")
            image_paths.append(image_path_abs)  # Return absolute path
        except Exception as e:
            raise RuntimeError(
                f"❌ Failed to Save Image\n"
                f"{'='*80}\n"
                f"Image Path: {image_path_abs}\n"
                f"Error: {type(e).__name__}: {str(e)}\n\n"
                f"Fix:\n"
                f"  1. Check write permissions for {output_dir}\n"
                f"  2. Ensure sufficient disk space\n"
                f"{'='*80}"
            ) from e
    
    return image_paths


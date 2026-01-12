import os
import cv2


def preprocess_image(image_path: str, output_dir: str = "uploads/processed") -> str:
    """
    Preprocess an image for OCR:
    - Convert to grayscale
    - Apply adaptive thresholding

    Args:
        image_path (str): Path to input image
        output_dir (str): Directory to store processed image

    Returns:
        str: Path to processed image
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    processed = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2
    )

    filename = os.path.basename(image_path)
    processed_path = os.path.join(output_dir, filename)

    cv2.imwrite(processed_path, processed)

    return processed_path
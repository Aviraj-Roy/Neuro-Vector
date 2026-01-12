from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='en')

def run_ocr(img_paths):
    """
    img_paths: either a single image path (str) or a list of image paths
    Returns combined OCR results across all pages/images.
    """
    if isinstance(img_paths, str):
        img_paths = [img_paths]

    all_lines = []
    raw_text_list = []

    for img_path in img_paths:
        results = ocr.predict(img_path)

        if not results:
            continue

        # Loop over all pages (usually 1 per image)
        for res in results:
            rec_texts = res.get("rec_texts", [])
            rec_scores = res.get("rec_scores", [])
            rec_polys = res.get("rec_polys", [])

            for i in range(len(rec_texts)):
                text = rec_texts[i]
                score = rec_scores[i] if i < len(rec_scores) else 0.0
                box = rec_polys[i].tolist() if i < len(rec_polys) else []

                all_lines.append({
                    "text": text,
                    "confidence": score,
                    "box": box
                })
                raw_text_list.append(text)
                print(f"Detected: {text} | Confidence: {score:.2f}")

    return {
        "raw_text": "\n".join(raw_text_list),
        "lines": all_lines
    }

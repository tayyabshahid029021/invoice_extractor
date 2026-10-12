"""Upload handling: turn a PDF or image into plain text, one visual line per row.

PDFs with a text layer are read directly with pdfplumber. Scanned PDFs and images
are OCR'd with RapidOCR (ONNX runtime, pip only, no system Tesseract needed).
"""
from __future__ import annotations

import io
from functools import lru_cache

import numpy as np
from PIL import Image, ImageOps

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}
MIN_PDF_TEXT_CHARS = 25


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _group_lines(result) -> str:
    """RapidOCR returns text boxes. Group boxes that share a baseline into lines."""
    if not result:
        return ""
    boxes = []
    for box, text, _score in result:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append({"x": min(xs), "cy": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys), "text": text})
    boxes.sort(key=lambda b: b["cy"])
    med_h = float(np.median([b["h"] for b in boxes])) or 10.0
    lines: list[list[dict]] = []
    for b in boxes:
        if lines and abs(b["cy"] - np.mean([x["cy"] for x in lines[-1]])) < 0.55 * med_h:
            lines[-1].append(b)
        else:
            lines.append([b])
    return "\n".join("  ".join(t["text"] for t in sorted(ln, key=lambda t: t["x"])) for ln in lines)


def ocr_image(img: Image.Image) -> str:
    img = ImageOps.exif_transpose(img).convert("RGB")
    # Upscale small images, OCR accuracy drops on tiny text.
    if max(img.size) < 1400:
        scale = 1400 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    result, _ = _ocr_engine()(np.array(img))
    return _group_lines(result)


def _pdf_text_layer(data: bytes) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _pdf_ocr(data: bytes) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    texts = []
    for i in range(len(pdf)):
        pil = pdf[i].render(scale=2.5).to_pil()
        texts.append(ocr_image(pil))
    return "\n".join(texts)


def render_preview(data: bytes, filename: str) -> Image.Image | None:
    """First page as an image for the UI."""
    ext = _ext(filename)
    try:
        if ext in PDF_EXTS:
            import pypdfium2 as pdfium

            return pdfium.PdfDocument(data)[0].render(scale=1.4).to_pil()
        return Image.open(io.BytesIO(data))
    except Exception:
        return None


def _ext(filename: str) -> str:
    return "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""


def extract_text(data: bytes, filename: str) -> tuple[str, str]:
    """Return (text, method) where method is pdf_text, pdf_ocr or image_ocr."""
    ext = _ext(filename)
    if ext in PDF_EXTS:
        text = _pdf_text_layer(data)
        if len(text.strip()) >= MIN_PDF_TEXT_CHARS:
            return text, "pdf_text"
        return _pdf_ocr(data), "pdf_ocr"
    if ext in IMAGE_EXTS:
        return ocr_image(Image.open(io.BytesIO(data))), "image_ocr"
    raise ValueError(f"Unsupported file type: {ext or 'unknown'}. Upload a PDF, PNG or JPG.")

from unittest import mock

import api_v1
from api_v1 import process_single_resume


def test_docx_paragraph_and_table(make_docx):
    data = make_docx(["Experienced in Python"], table_cells=["Docker", "AWS"])
    r = process_single_resume(data, "cv.docx", ["python", "docker", "aws", "java"])
    assert r["status"] == "success"
    assert r["matched_skills"] == ["aws", "docker", "python"]
    assert r["score"] == 3


def test_text_pdf(make_pdf):
    text = "Senior engineer with Python and SQL experience. " * 3
    r = process_single_resume(make_pdf(text), "cv.pdf", ["python", "sql", "rust"])
    assert r["status"] == "success"
    assert r["matched_skills"] == ["python", "sql"]


def test_scanned_pdf_falls_back_to_ocr(make_pdf):
    blank = make_pdf("x")  # < 50 chars of text -> OCR path
    with mock.patch.object(api_v1, "convert_from_bytes", return_value=["img"]) as conv, \
         mock.patch.object(api_v1.pytesseract, "image_to_string", return_value="Skilled in Docker"):
        r = process_single_resume(blank, "scan.pdf", ["docker"])
    conv.assert_called_once()
    assert r["status"] == "success" and r["matched_skills"] == ["docker"]


def test_image_uses_ocr():
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
    with mock.patch.object(api_v1.pytesseract, "image_to_string", return_value="Kubernetes dev"):
        r = process_single_resume(buf.getvalue(), "cv.png", ["kubernetes"])
    assert r["matched_skills"] == ["kubernetes"]


def test_unsupported_extension():
    assert process_single_resume(b"x", "cv.txt", ["a"])["status"] == "error"


def test_missing_extension():
    assert process_single_resume(b"x", "noext", ["a"])["status"] == "error"


def test_corrupt_pdf_returns_error_without_leaking_details():
    r = process_single_resume(b"not a pdf", "bad.pdf", ["python"])
    assert r["status"] == "error"
    assert r["error"] == "Could not process this file."

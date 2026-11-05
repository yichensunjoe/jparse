"""Exercise the unpacked interpreter, Java extractor and live desktop API.

Only a freshly generated, synthetic PDF is used. This script is run by CI with
JPARSE_DATA_DIR pointing at a temporary directory and the packaged Python.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

import fitz

if sys.platform == "win32":
    assert Path(sys.executable).with_name("msvcp140.dll").is_file(), "Bundled VC++ runtime is missing"

parser = argparse.ArgumentParser()
parser.add_argument("--project", type=Path, required=True)
parser.add_argument("--port", type=int, default=18765)
parser.add_argument("--offline-only", action="store_true")
args = parser.parse_args()
sys.path.insert(0, str(args.project))
from src.opendataloader_extractor import extract_pdf_structure

root = Path(os.environ["JPARSE_DATA_DIR"])
inbox = root / "inbox"
inbox.mkdir(parents=True, exist_ok=True)

if os.environ.get("JPARSE_PADDLE_PYTHON"):
    from PIL import Image, ImageDraw, ImageFont
    from src.bitmap_figure_translator import run_paddle_ocr

    image = Image.new("RGB", (950, 150), "white")
    font_path = Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf"
    ImageDraw.Draw(image).text((30, 35), "REACTOR COOLING VALVE", fill="black",
                               font=ImageFont.truetype(str(font_path), 48))
    image_path = root / "jparse-ocr-smoke.png"
    image.save(image_path)
    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        words = " ".join(item.text for item in run_paddle_ocr(image_path)).upper()
        assert "REACTOR" in words, f"Bundled offline OCR failed: {words}"
    finally:
        image_path.unlink(missing_ok=True)
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline
    print("Bundled offline bitmap OCR passed", flush=True)

pdf = inbox / ".jparse-smoke.pdf"
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), "JParse smoke test. This document was generated for a local PDF extraction test.")
page.insert_text((72, 98), "The reactor operates safely with a reliable cooling system and protective controls.")
page.insert_text((72, 124), "This synthetic English text verifies the desktop application's real processing pipeline.")
doc.save(pdf)
doc.close()
result = extract_pdf_structure(pdf)
assert result.pages, "OpenDataLoader produced no pages"
text = " ".join(str(item.to_dict()) for page in result.pages for item in page.elements)
assert "reactor" in text.lower(), "OpenDataLoader did not extract the synthetic text"
print("Local Java/PDF extraction passed", flush=True)

if not args.offline_only:
    pdf_bytes = pdf.read_bytes()
    pdf.unlink()
    boundary = "JParseSmokeBoundary20261105"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="pipelineMode"\r\n\r\nauto\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="service"\r\n\r\nbing\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="jparse-smoke.pdf"\r\n'
        'Content-Type: application/pdf\r\n\r\n'
    ).encode("ascii") + pdf_bytes + f"\r\n--{boundary}--\r\n".encode("ascii")
    base = f"http://127.0.0.1:{args.port}"
    request = Request(base + "/api/upload", data=body,
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(request, timeout=30) as response:
        task_id = json.load(response)["task"]["id"]
    deadline = time.monotonic() + 420
    task = None
    while time.monotonic() < deadline:
        with urlopen(base + "/api/tasks", timeout=10) as response:
            tasks = json.load(response)
        task = next(item for item in tasks if item["id"] == task_id)
        if task["status"] in ("completed", "failed"):
            break
        time.sleep(2)
    assert task and task["status"] == "completed", f"Desktop PDF task failed or timed out: {task}"
    names = [item["name"] for item in task["output_files"]]
    assert any(name.endswith("中文精译版.pdf") for name in names), names
    assert any(name.endswith("双语对照版.pdf") for name in names), names
    mono = next(item for item in task["output_files"] if item["name"].endswith("中文精译版.pdf"))
    with fitz.open(mono["path"]) as translated:
        assert len(translated) > 0, "The translated PDF has no pages"
        translated_text = "".join(page.get_text() for page in translated)
        assert any("\u4e00" <= char <= "\u9fff" for char in translated_text), "No Chinese text in translated PDF"
    assert (root / "processed" / "jparse-smoke.pdf").is_file(), "Original was not archived"
    print("Desktop upload, Bing translation, PDF delivery and archival passed:", names, flush=True)

    # A normal PDF dropped into the actual inbox must be processed automatically.
    (inbox / "watcher-smoke.pdf").write_bytes(pdf_bytes)
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        if (root / "processed" / "watcher-smoke.pdf").exists():
            break
        if (root / "failed" / "watcher-smoke.pdf").exists():
            raise AssertionError("Inbox watcher failed to process its PDF")
        time.sleep(2)
    assert (root / "processed" / "watcher-smoke.pdf").is_file(), "Inbox PDF was not processed"
    assert (root / "outbox" / "watcher-smoke-中文精译版.pdf").is_file()
    print("Inbox watcher processed and archived the PDF", flush=True)

    # Image-only scans are not silently marked successful if extraction found
    # no OCR text. The original must be retained in failed/.
    import io
    from PIL import Image
    picture = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(picture, format="PNG")
    scan_doc = fitz.open()
    scan_page = scan_doc.new_page()
    scan_page.insert_image(scan_page.rect, stream=picture.getvalue())
    scan_page.insert_text((50, 50), "1")  # A page number is not an OCR layer.
    scan = inbox / "image-only-scan.pdf"
    scan_doc.save(scan)
    scan_doc.close()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if (root / "failed" / scan.name).exists() or (root / "processed" / scan.name).exists():
            break
        time.sleep(2)
    assert (root / "failed" / scan.name).is_file(), "Unrecognized scan was not retained as a failure"
    assert not (root / "processed" / scan.name).exists(), "Unrecognized scan was incorrectly archived as success"
    print("Image-only scan was safely rejected and retained", flush=True)

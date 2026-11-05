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
pdf = inbox / "jparse-smoke.pdf"
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

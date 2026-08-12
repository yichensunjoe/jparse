#!/usr/bin/env python3
"""PaddleOCR worker for the scanned-book page-faithful route.

Runs as a separate process under the PaddleOCR virtualenv interpreter.
Protocol:
- stdin:  one JSON line: {"pages": ["/abs/page-001.jpg", ...]}
- stdout: one JSON line per page, in input order:
          {"index": 0, "ok": true, "text": "line1\\nline2"}
          {"index": 1, "ok": false, "error": "..."}
- exit 0 after the whole batch; non-zero exit means the batch failed as a whole.

The parent (scan_html_renderer) keeps Tesseract as a fallback engine; this
worker only exists for ocr_engine="paddleocr".
"""

import json
import sys
import time


def _build_ocr():
    from paddleocr import PaddleOCR

    return PaddleOCR(
        # PP-OCRv5 mobile: measured ~4x faster than the v6 medium models on
        # Apple Silicon CPU with a negligible quality gap for page scans.
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        # Page-faithful mode already preserves layout; orientation and
        # unwarping modules only add latency on top of the scanned pages.
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _recognize_page(ocr, image_path: str) -> str:
    # Concurrent workers occasionally get a silent empty result from a
    # predict call; retrying empty pages makes that self-healing.
    for attempt in range(3):
        results = ocr.predict(image_path)
        lines = []
        for result in results:
            for text in result.get("rec_texts", []) or []:
                if text:
                    lines.append(text)
        if lines:
            return "\n".join(lines)
        time.sleep(0.5)
    return "" 


def _emit(record):
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError) as exc:
        _emit({"index": 0, "ok": False, "error": "无效的批次输入: %s" % exc})
        return 2
    pages = payload.get("pages") or []
    if not pages:
        return 2

    try:
        ocr = _build_ocr()
    except Exception as exc:  # noqa: BLE001 - report model init failure to parent
        _emit({"index": 0, "ok": False, "error": "模型加载失败: %s" % str(exc)[:500]})
        return 3

    for index, page in enumerate(pages):
        try:
            text = _recognize_page(ocr, str(page))
            _emit({"index": index, "ok": True, "text": text})
        except Exception as exc:  # noqa: BLE001 - isolate single-page failures
            _emit({"index": index, "ok": False, "error": str(exc)[:500]})
    return 0


if __name__ == "__main__":
    sys.exit(main())

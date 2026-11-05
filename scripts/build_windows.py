"""Build a self-extracting, per-user JParse Windows x64 executable.

Run on Windows with Python 3.12, pip, a JRE in JAVA_HOME, and .NET Framework.
The executable contains a portable interpreter and does not require Python on
end-user machines. Only source files and public runtime assets are packaged.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "windows-exe"
RUNTIME = BUILD / "runtime"
OUTPUT = ROOT / "dist" / "JParse-Windows-x64.exe"
PYTHON_VERSION = "3.12.10"
MAGIC = b"JPARSE-EXE-V1!!!"


def run(*args: str, **kwargs) -> None:
    print("+", *args, flush=True)
    subprocess.run(args, check=True, **kwargs)


def main() -> None:
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise SystemExit("Build on Windows x64 using Python 3.12.")
    jre = Path(os.environ.get("JAVA_HOME", ""))
    if not (jre / "bin" / "java.exe").is_file():
        raise SystemExit("JAVA_HOME must point to a Windows Java runtime.")
    shutil.rmtree(BUILD, ignore_errors=True)
    RUNTIME.mkdir(parents=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    python_dir = RUNTIME / "python"
    python_dir.mkdir()
    ocr_python_dir = RUNTIME / "ocr-python"
    ocr_python_dir.mkdir()
    python_zip = BUILD / "python-embed.zip"
    url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
    print("Downloading", url, flush=True)
    urllib.request.urlretrieve(url, python_zip)
    with zipfile.ZipFile(python_zip) as archive:
        archive.extractall(python_dir)
        archive.extractall(ocr_python_dir)
    # The Python embeddable ZIP includes vcruntime140*.dll but not the C++
    # standard library required by native wheels such as ONNX Runtime.
    # Include the installed Microsoft redistributable DLLs app-locally, so a
    # clean Windows machine need not install the VC++ redistributable itself.
    system32 = Path(os.environ["WINDIR"]) / "System32"
    msvc = list(system32.glob("msvcp140*.dll"))
    if not msvc:
        raise SystemExit("Microsoft VC++ runtime DLLs are unavailable on the build machine.")
    for dll in msvc + [system32 / "concrt140.dll", system32 / "vcomp140.dll"]:
        if dll.is_file():
            shutil.copy2(dll, python_dir / dll.name)
            shutil.copy2(dll, ocr_python_dir / dll.name)
    for interpreter in (python_dir, ocr_python_dir):
        (interpreter / "python312._pth").write_text(
            "python312.zip\n.\nLib\\site-packages\nimport site\n", encoding="ascii"
        )
    site_packages = python_dir / "Lib" / "site-packages"
    run(sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
        "--target", str(site_packages), "-c", str(ROOT / "scripts" / "constraints-windows.txt"),
        "-r", str(ROOT / "scripts" / "requirements-windows.txt"))
    run(sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
        "--target", str(ocr_python_dir / "Lib" / "site-packages"),
        "-r", str(ROOT / "scripts" / "requirements-windows-ocr.txt"))
    run(str(python_dir / "python.exe"), "-X", "utf8", "-c",
        "from pdf2zh.pdf2zh import main; "
        "from tencentcloud.tmt.v20180321.models import TextTranslateRequest; "
        "print('Bundled pdf2zh imports verified')")
    project = RUNTIME / "project"
    project.mkdir()
    shutil.copytree(ROOT / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "config.json", project / "config.json")
    shutil.copytree(jre, RUNTIME / "jre")

    # Download only the public layout model and Chinese font. The PDF input is
    # never involved. Copy them into the EXE so end users need not fetch them.
    helper = BUILD / "fetch-assets.py"
    helper.write_text(
        "from babeldoc.assets.assets import get_doclayout_onnx_model_path, get_font_and_metadata\n"
        "from pathlib import Path\nimport shutil, sys\n"
        "out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)\n"
        "shutil.copy2(get_doclayout_onnx_model_path(), out / 'layout.onnx')\n"
        "for name in ('SourceHanSerifCN-Regular.ttf', 'SourceHanSerifCN-Bold.ttf', "
        "'SourceHanSansCN-Regular.ttf', 'SourceHanSansCN-Bold.ttf'):\n"
        "    shutil.copy2(get_font_and_metadata(name)[0], out / name)\n",
        encoding="utf-8",
    )
    run(str(python_dir / "python.exe"), str(helper), str(RUNTIME / "models"))

    # Resolve the exact OCR models used by bitmap_figure_translator at build
    # time. No end-user image or PDF is sent to these model hosts.
    ocr_env = os.environ.copy()
    ocr_env["PADDLE_PDX_CACHE_HOME"] = str(RUNTIME / "ocr-models")
    ocr_env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    run(str(ocr_python_dir / "python.exe"), "-c",
        "from paddleocr import PaddleOCR; "
        "PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, "
        "use_textline_orientation=False, lang='en', enable_mkldnn=False)", env=ocr_env)

    payload = BUILD / "runtime.zip"
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as archive:
        for path in sorted(RUNTIME.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(RUNTIME).as_posix())
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    stub = BUILD / "launcher.exe"
    run(str(compiler), "/nologo", "/target:winexe", "/platform:x64", f"/out:{stub}",
        "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", "/r:System.IO.Compression.dll",
        "/r:System.IO.Compression.FileSystem.dll", str(ROOT / "scripts" / "windows_launcher.cs"))
    digest = hashlib.sha256()
    with OUTPUT.open("wb") as target, stub.open("rb") as src:
        shutil.copyfileobj(src, target)
        with payload.open("rb") as src_payload:
            for chunk in iter(lambda: src_payload.read(1024 * 1024), b""):
                target.write(chunk)
                digest.update(chunk)
        target.write(digest.digest())
        target.write(struct.pack("<Q", payload.stat().st_size))
        target.write(MAGIC)
    print(f"Built {OUTPUT} ({OUTPUT.stat().st_size:,} bytes; payload SHA256 {digest.hexdigest()})", flush=True)


if __name__ == "__main__":
    main()

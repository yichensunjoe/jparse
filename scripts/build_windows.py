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
    python_zip = BUILD / "python-embed.zip"
    url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
    print("Downloading", url, flush=True)
    urllib.request.urlretrieve(url, python_zip)
    with zipfile.ZipFile(python_zip) as archive:
        archive.extractall(python_dir)
    (python_dir / "python312._pth").write_text(
        "python312.zip\n.\nLib\\site-packages\nimport site\n", encoding="ascii"
    )
    site_packages = python_dir / "Lib" / "site-packages"
    run(sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
        "--target", str(site_packages), "-r", str(ROOT / "scripts" / "requirements-windows.txt"))
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
        "shutil.copy2(get_font_and_metadata('SourceHanSerifCN-Regular.ttf')[0], out / 'SourceHanSerifCN-Regular.ttf')\n",
        encoding="utf-8",
    )
    run(str(python_dir / "python.exe"), str(helper), str(RUNTIME / "models"))

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

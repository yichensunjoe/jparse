"""Resource paths shared by source and packaged desktop installations."""

import os
from pathlib import Path
import hashlib
import urllib.request


def font_directory() -> Path:
    configured = os.environ.get("JPARSE_FONT_DIR")
    return Path(configured) if configured else Path.home() / ".cache/babeldoc/fonts"


def local_urlopen(url, timeout):
    """Loopback traffic must never be sent through a system HTTP proxy."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(url, timeout=timeout)


def normalized_data_path(value: str) -> str:
    return os.path.normcase(str(Path(value).expanduser().resolve()))


def packaged_port() -> int:
    runtime = os.environ.get("JPARSE_RUNTIME_ID")
    if not runtime:
        return 8765
    data = normalized_data_path(os.environ.get("JPARSE_DATA_DIR", ""))
    digest = hashlib.sha256((runtime + "\0" + data).encode("utf-8")).digest()
    return 20000 + int.from_bytes(digest[:4], "big") % 40000


def identity_matches(identity: dict) -> bool:
    runtime = os.environ.get("JPARSE_RUNTIME_ID")
    if not runtime:
        return True
    data = os.environ.get("JPARSE_DATA_DIR", "")
    remote_data = identity.get("data_dir")
    return (identity.get("runtime_id") == runtime and isinstance(remote_data, str)
            and normalized_data_path(remote_data) == normalized_data_path(data))


def mark_active_runtime(port: int) -> None:
    runtime = os.environ.get("JPARSE_RUNTIME_ID")
    data = os.environ.get("JPARSE_DATA_DIR")
    if not runtime or not data:
        return
    root = Path(data)
    root.mkdir(parents=True, exist_ok=True)
    for name, content in ((".port-" + runtime, str(port)), (".active-runtime", runtime)):
        temp = root / (name + ".%d.tmp" % os.getpid())
        try:
            temp.write_text(content, encoding="utf-8")
            os.replace(str(temp), str(root / name))
        finally:
            temp.unlink(missing_ok=True)

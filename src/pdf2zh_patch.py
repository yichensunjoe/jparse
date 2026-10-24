"""Patch module to fix paragraph truncation bugs in pdf2zh translation engines."""

import html
import logging
import os
from pathlib import Path
import re
import sqlite3
from typing import List, Optional

logger = logging.getLogger("pdf2zh_patch")


def split_into_chunks(text: str, max_len: int = 800) -> List[str]:
    """Split long text into safe chunks without breaking formula tags {v\\d+} or sentences.

    Args:
        text: Input string.
        max_len: Maximum character length per chunk.

    Returns:
        List of chunks, each <= max_len (unless an atomic token exceeds max_len).
    """
    if not text or len(text) <= max_len:
        return [text] if text else []

    # Protect formula placeholders {v\\d+} and reference markers
    tokens = re.split(r"(\{v\d+\})", text)
    pieces: List[str] = []
    for token in tokens:
        if not token:
            continue
        if re.match(r"^\{v\d+\}$", token):
            pieces.append(token)
        else:
            # Split by sentence boundaries, newlines, or numbered list indicators (e.g., " 1. ", " 2. ")
            sub_parts = re.split(r"((?<=[.!?;\n])\s+|\s+(?=\d+\.\s+))", token)
            for sp in sub_parts:
                if sp:
                    pieces.append(sp)

    chunks: List[str] = []
    cur = ""
    for p in pieces:
        if len(cur) + len(p) <= max_len:
            cur += p
        else:
            if cur:
                chunks.append(cur)
            if len(p) > max_len:
                # Force split at whitespace if a single sentence is huge
                words = p.split(" ")
                sub = ""
                for w in words:
                    if len(sub) + len(w) + 1 <= max_len:
                        sub = (sub + " " + w).strip()
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = w
                cur = sub
            else:
                cur = p
    if cur:
        chunks.append(cur)
    return chunks


def smart_join_translated(chunks: List[str]) -> str:
    """Seamlessly join translated chunks with proper CJK and Latin spacing.

    Args:
        chunks: List of translated chunks.

    Returns:
        Combined string.
    """
    if not chunks:
        return ""
    res = chunks[0].strip()
    for c in chunks[1:]:
        c_clean = c.strip()
        if not c_clean:
            continue
        if not res:
            res = c_clean
            continue
        last_char = res[-1]
        first_char = c_clean[0]

        # Natural CJK join rules
        if last_char in "。；！？":
            res += c_clean
        elif ("\u4e00" <= last_char <= "\u9fff" or last_char in "，、：）”’") and (
            "\u4e00" <= first_char <= "\u9fff" or first_char in "（“‘"
        ):
            res += c_clean
        elif "\u4e00" <= last_char <= "\u9fff" and "\u4e00" <= first_char <= "\u9fff":
            res += c_clean
        else:
            res += " " + c_clean
    return res


def clean_truncated_cache(cache_db_path: Optional[Path] = None) -> int:
    """Remove truncated cache entries from pdf2zh SQLite database.

    Args:
        cache_db_path: Path to cache.v1.db. Defaults to ~/.cache/pdf2zh/cache.v1.db.

    Returns:
        Number of removed cache rows.
    """
    if cache_db_path is None:
        cache_db_path = Path.home() / ".cache/pdf2zh/cache.v1.db"
    cache_db_path = Path(cache_db_path)
    if not cache_db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(str(cache_db_path))
        cur = conn.cursor()
        # Find entries where original_text was > 800 chars and thus truncated by Bing/Google
        cur.execute(
            "DELETE FROM _translationcache WHERE (translate_engine = 'bing' AND LENGTH(original_text) > 800) "
            "OR (translate_engine = 'google' AND LENGTH(original_text) > 3000)"
        )
        deleted_count = cur.rowcount
        conn.commit()
        conn.close()
        logger.info("已从 pdf2zh 缓存数据库清理 %d 条截断残缺记录", deleted_count)
        return deleted_count
    except Exception as e:
        logger.warning("清理 pdf2zh 缓存数据库失败: %s", e)
        return 0


def patch_pdf2zh_translator_file(venv_dir: Optional[Path] = None) -> bool:
    """Patch translator.py in the isolated virtual environment to prevent truncation.

    Replaces naive `text = text[:1000]` with smart chunking and SID session reuse.

    Args:
        venv_dir: Path to pdf2zh venv directory. Defaults to ~/.local/venvs/pdf2zh.

    Returns:
        True if patched or already patched, False otherwise.
    """
    if venv_dir is None:
        venv_dir = Path.home() / ".local/venvs/pdf2zh"
    venv_dir = Path(venv_dir)

    # Locate translator.py
    candidate_paths = list(venv_dir.glob("lib/python*/site-packages/pdf2zh/translator.py"))
    if not candidate_paths:
        logger.warning("未找到 %s 下的 translator.py", venv_dir)
        return False

    target_file = candidate_paths[0]
    content = target_file.read_text(encoding="utf-8")

    # Check if already patched
    if "LITEPARSE_CHUNK_PATCH_V1" in content:
        logger.debug("pdf2zh translator.py 已经包含 LITEPARSE_CHUNK_PATCH_V1 补丁")
        return True

    # Replacement code for BingTranslator
    old_bing_block = (
        "    def do_translate(self, text):\n"
        "        text = text[:1000]  # bing translate max length\n"
        "        url, ig, iid, key, token = self.find_sid()\n"
        "        response = self.session.post(\n"
        "            f\"{url}ttranslatev3?IG={ig}&IID={iid}\",\n"
        "            data={\n"
        "                \"fromLang\": self.lang_in,\n"
        "                \"to\": self.lang_out,\n"
        "                \"text\": text,\n"
        "                \"token\": token,\n"
        "                \"key\": key,\n"
        "            },\n"
        "            headers=self.headers,\n"
        "        )\n"
        "        response.raise_for_status()\n"
        "        return response.json()[0][\"translations\"][0][\"text\"]"
    )

    new_bing_block = (
        "    # LITEPARSE_CHUNK_PATCH_V1: Smart chunking and cached SID to prevent truncation\n"
        "    def _find_sid_cached(self):\n"
        "        if hasattr(self, '_cached_sid') and self._cached_sid:\n"
        "            return self._cached_sid\n"
        "        self._cached_sid = self.find_sid()\n"
        "        return self._cached_sid\n"
        "\n"
        "    def _do_translate_single(self, text):\n"
        "        if not text:\n"
        "            return ''\n"
        "        for attempt in range(2):\n"
        "            try:\n"
        "                url, ig, iid, key, token = self._find_sid_cached()\n"
        "                response = self.session.post(\n"
        "                    f\"{url}ttranslatev3?IG={ig}&IID={iid}\",\n"
        "                    data={\n"
        "                        \"fromLang\": self.lang_in,\n"
        "                        \"to\": self.lang_out,\n"
        "                        \"text\": text[:1000],\n"
        "                        \"token\": token,\n"
        "                        \"key\": key,\n"
        "                    },\n"
        "                    headers=self.headers,\n"
        "                    timeout=20,\n"
        "                )\n"
        "                response.raise_for_status()\n"
        "                return response.json()[0][\"translations\"][0][\"text\"]\n"
        "            except Exception:\n"
        "                self._cached_sid = None\n"
        "                if attempt == 1:\n"
        "                    raise\n"
        "\n"
        "    def do_translate(self, text):\n"
        "        if len(text) <= 800:\n"
        "            return self._do_translate_single(text)\n"
        "        # Multi-chunk translation without dropping any paragraph content\n"
        "        tokens = re.split(r'(\\{v\\d+\\})', text)\n"
        "        pieces = []\n"
        "        for t in tokens:\n"
        "            if not t:\n"
        "                continue\n"
        "            if re.match(r'^\\{v\\d+\\}$', t):\n"
        "                pieces.append(t)\n"
        "            else:\n"
        "                sub_parts = re.split(r'((?<=[.!?;\\n])\\s+|\\s+(?=\\d+\\.\\s+))', t)\n"
        "                pieces.extend([p for p in sub_parts if p])\n"
        "        chunks, cur = [], ''\n"
        "        for p in pieces:\n"
        "            if len(cur) + len(p) <= 800:\n"
        "                cur += p\n"
        "            else:\n"
        "                if cur:\n"
        "                    chunks.append(cur)\n"
        "                if len(p) > 800:\n"
        "                    words = p.split(' ')\n"
        "                    sub = ''\n"
        "                    for w in words:\n"
        "                        if len(sub) + len(w) + 1 <= 800:\n"
        "                            sub = (sub + ' ' + w).strip()\n"
        "                        else:\n"
        "                            if sub:\n"
        "                                chunks.append(sub)\n"
        "                            sub = w\n"
        "                    cur = sub\n"
        "                else:\n"
        "                    cur = p\n"
        "        if cur:\n"
        "            chunks.append(cur)\n"
        "        translated = [self._do_translate_single(c) for c in chunks]\n"
        "        if not translated:\n"
        "            return ''\n"
        "        res = translated[0].strip()\n"
        "        for c in translated[1:]:\n"
        "            c_clean = c.strip()\n"
        "            if not c_clean:\n"
        "                continue\n"
        "            if not res:\n"
        "                res = c_clean\n"
        "                continue\n"
        "            lc, fc = res[-1], c_clean[0]\n"
        "            if lc in '。；！？':\n"
        "                res += c_clean\n"
        "            elif ('\\u4e00' <= lc <= '\\u9fff' or lc in '，、：）”') and ('\\u4e00' <= fc <= '\\u9fff' or fc in '（“'):\n"
        "                res += c_clean\n"
        "            elif '\\u4e00' <= lc <= '\\u9fff' and '\\u4e00' <= fc <= '\\u9fff':\n"
        "                res += c_clean\n"
        "            else:\n"
        "                res += ' ' + c_clean\n"
        "        return res"
    )

    if old_bing_block not in content:
        # Fallback check if simple replacement works
        logger.warning("未能精确匹配原版 BingTranslator.do_translate 代码块，检查是否已被修改")
        return False

    patched_content = content.replace(old_bing_block, new_bing_block)
    target_file.write_text(patched_content, encoding="utf-8")
    logger.info("已成功对 %s 应用 LITEPARSE_CHUNK_PATCH_V1 补丁", target_file)
    return True


def ensure_pdf2zh_environment_ready(venv_dir: Optional[Path] = None) -> None:
    """Ensure pdf2zh environment has clean cache and non-truncating translator."""
    patch_pdf2zh_translator_file(venv_dir)
    clean_truncated_cache()

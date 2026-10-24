"""Unit tests for pdf2zh truncation patch and cache management."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.pdf2zh_patch import (
    clean_truncated_cache,
    smart_join_translated,
    split_into_chunks,
)


class TestPdf2zhPatch(unittest.TestCase):
    """Test smart chunking, CJK joining, and cache cleaner."""

    def test_split_into_chunks_short_text(self):
        short = "This is a short text."
        chunks = split_into_chunks(short, max_len=800)
        self.assertEqual(chunks, [short])

    def test_split_into_chunks_empty(self):
        self.assertEqual(split_into_chunks("", 800), [])

    def test_split_into_chunks_preserves_formulas(self):
        # Long text with multiple formulas
        sentence = "This section analyzes parameter {v0} and temperature {v1} under high pressure. "
        text = sentence * 25  # ~2000 chars
        chunks = split_into_chunks(text, max_len=800)
        self.assertTrue(len(chunks) >= 3)

        for c in chunks:
            self.assertLessEqual(len(c), 800)
            # Ensure no formula tag is broken like "{v" or "0}"
            self.assertEqual(c.count("{v"), c.count("}"))

    def test_split_into_chunks_numbered_list(self):
        ref_text = (
            "1. Ming, Y.; Shen, H. Dynamic analysis. Nucl. Eng. Des. 2024. "
            "2. Yang, J.; Duan, Y. Operating performance. J. Therm. Sci. 2024. "
            "3. Zhang, R.; Wang, X. Thermodynamic analysis. Energies 2024. "
        ) * 10
        chunks = split_into_chunks(ref_text, max_len=500)
        for c in chunks:
            self.assertLessEqual(len(c), 500)
        rejoined = "".join(chunks)
        self.assertEqual(len(rejoined.split()), len(ref_text.split()))

    def test_smart_join_translated_cjk(self):
        chunk1 = "本研究探讨了标准尺寸和混合尺寸单元通道配置在不同冷热流体热阻比下的应用。"
        chunk2 = "结果表明，混合尺寸单元通道配置未能增强换热。"
        joined = smart_join_translated([chunk1, chunk2])
        # After Chinese period '。', no space should be added
        self.assertEqual(joined, chunk1 + chunk2)

    def test_smart_join_translated_latin(self):
        c1 = "Figure 1 illustrates"
        c2 = "the overall schematic."
        joined = smart_join_translated([c1, c2])
        self.assertEqual(joined, "Figure 1 illustrates the overall schematic.")

    def test_clean_truncated_cache(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE _translationcache (
                id INTEGER PRIMARY KEY,
                translate_engine TEXT,
                translate_engine_params TEXT,
                original_text TEXT,
                translation TEXT
            )
            """
        )
        # Normal row
        cur.execute(
            "INSERT INTO _translationcache VALUES (1, 'bing', '{}', 'short text', '短文本')"
        )
        # Truncated row (>800 chars)
        cur.execute(
            "INSERT INTO _translationcache VALUES (2, 'bing', '{}', ?, '截断译文')",
            ("long text " * 100,)
        )
        conn.commit()
        conn.close()

        deleted = clean_truncated_cache(db_path)
        self.assertEqual(deleted, 1)

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT id FROM _translationcache")
        remaining = [r[0] for r in cur.fetchall()]
        conn.close()
        db_path.unlink()

        self.assertEqual(remaining, [1])


if __name__ == "__main__":
    unittest.main()

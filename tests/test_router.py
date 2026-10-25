"""Unit tests for Smart Layout Router and Dual-Track Pipelines."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from src.router import probe_pdf_document_type, route_and_process_pdf
from src.vector_pdf_renderer import get_pdf2zh_binary


class TestSmartRouterClassification(unittest.TestCase):
    """验证智能探针能够准确区分现代矢量学术论文与历史打字机扫描件。"""

    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.scanned_pdf = self.project_root / "processed" / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.pdf"
        self.scanned_cf_pdf = self.project_root / "processed" / "ORNL-CF-58-10-37.pdf"
        self.vector_pche = Path("/Users/joe/ai/reasonix/projects/active/P077-核能文章写作项目/references/pdfs_2024_2026/EN01_MDPI_PCHE_Review_2025.pdf")
        self.vector_asme = self.project_root / "processed" / "ASME QME-1-2025-E.pdf"

    def test_probe_identifies_historical_scans(self):
        if self.scanned_pdf.exists():
            doc_type = probe_pdf_document_type(self.scanned_pdf)
            self.assertEqual(doc_type, "scanned", f"Expected '{self.scanned_pdf.name}' to be classified as scanned")

        if self.scanned_cf_pdf.exists():
            doc_type = probe_pdf_document_type(self.scanned_cf_pdf)
            self.assertEqual(doc_type, "scanned", f"Expected '{self.scanned_cf_pdf.name}' to be classified as scanned")

    def test_probe_identifies_modern_vector_papers(self):
        if self.vector_pche.exists():
            doc_type = probe_pdf_document_type(self.vector_pche)
            self.assertEqual(doc_type, "vector", f"Expected '{self.vector_pche.name}' to be classified as vector")

        if self.vector_asme.exists():
            doc_type = probe_pdf_document_type(self.vector_asme)
            self.assertEqual(doc_type, "vector", f"Expected '{self.vector_asme.name}' to be classified as vector")

    def test_pdf2zh_binary_exists_and_executable(self):
        binary = get_pdf2zh_binary()
        self.assertTrue(binary.exists())
        self.assertTrue(binary.is_file())


class TestRouterDispatchLogic(unittest.TestCase):
    """验证路由器的分发逻辑与策略覆盖。"""

    @patch("src.router.process_vector_pdf_with_pdf2zh")
    @patch("src.router.process_pdf_to_insitu_html")
    def test_force_pipeline_vector(self, mock_insitu, mock_vector):
        mock_vector.return_value = [Path("outbox/test-mono.pdf")]
        res = route_and_process_pdf(
            pdf_path=Path("fake.pdf"),
            outbox_dir=Path("outbox"),
            config={"force_pipeline": "vector", "pdf2zh_service": "bing"}
        )
        mock_vector.assert_called_once()
        mock_insitu.assert_not_called()
        self.assertEqual(len(res), 1)

    @patch("src.router.process_vector_pdf_with_pdf2zh")
    @patch("src.router.process_scanned_pdf_to_hd_pdf")
    def test_force_pipeline_scanned(self, mock_hd_scan, mock_vector):
        mock_hd_scan.return_value = [
            Path("outbox/fake-中文精译版.pdf"),
            Path("outbox/fake-双语对照版.pdf"),
            Path("outbox/fake.原位双层版.html"),
        ]
        res = route_and_process_pdf(
            pdf_path=Path("fake.pdf"),
            outbox_dir=Path("outbox"),
            config={"force_pipeline": "scanned"}
        )
        mock_hd_scan.assert_called_once()
        mock_vector.assert_not_called()
        self.assertEqual(len(res), 3)

    @patch("src.router.process_vector_pdf_with_pdf2zh")
    @patch("src.router.process_pdf_to_insitu_html")
    def test_force_pipeline_insitu_legacy(self, mock_insitu, mock_vector):
        mock_insitu.return_value = Path("outbox/fake.原位双层版.html")
        with patch.object(Path, "replace"):
            res = route_and_process_pdf(
                pdf_path=Path("fake.pdf"),
                outbox_dir=Path("outbox"),
                config={"force_pipeline": "insitu_legacy"}
            )
        mock_insitu.assert_called_once()
        mock_vector.assert_not_called()
        self.assertEqual(len(res), 1)


class TestWatcherDualTrackIntegration(unittest.TestCase):
    """验证 Watcher 与双轨路由器的集成及配置解析。"""

    def test_watcher_config_dual_track_mode(self):
        from src.watcher import Config, ConfigError
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d in ("inbox", "outbox", "processing", "processed", "failed", "logs"):
                (root / d).mkdir()

            cfg_file = root / "config.json"

            # Valid config
            cfg_file.write_text(json.dumps({
                "inbox": "inbox", "outbox": "outbox", "processing": "processing",
                "processed": "processed", "failed": "failed", "logs": "logs",
                "dual_track_mode": "auto", "pdf2zh_service": "bing"
            }))
            cfg = Config(cfg_file)
            self.assertEqual(cfg.dual_track_mode, "auto")
            self.assertEqual(cfg.pdf2zh_service, "bing")

            # Invalid dual_track_mode
            cfg_file.write_text(json.dumps({
                "inbox": "inbox", "outbox": "outbox", "processing": "processing",
                "processed": "processed", "failed": "failed", "logs": "logs",
                "dual_track_mode": "invalid_mode"
            }))
            with self.assertRaises(ConfigError):
                Config(cfg_file)

    @patch("src.router.route_and_process_pdf")
    def test_watcher_process_routes_when_enabled(self, mock_route):
        from src.watcher import Config, Watcher
        import tempfile
        import json
        import logging

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d in ("inbox", "outbox", "processing", "processed", "failed", "logs"):
                (root / d).mkdir()

            fake_pdf = root / "inbox" / "paper.pdf"
            fake_pdf.write_bytes(b"%PDF-1.4 test")

            cfg_file = root / "config.json"
            cfg_file.write_text(json.dumps({
                "inbox": "inbox", "outbox": "outbox", "processing": "processing",
                "processed": "processed", "failed": "failed", "logs": "logs",
                "dual_track_mode": "auto", "pdf2zh_service": "bing"
            }))
            cfg = Config(cfg_file)
            logger = logging.getLogger("test_watcher_dual")
            watcher = Watcher(cfg, logger)

            mock_route.return_value = [root / "outbox" / "paper-mono.pdf"]
            watcher.process(fake_pdf)

            mock_route.assert_called_once_with(
                pdf_path=fake_pdf,
                outbox_dir=cfg.outbox,
                config={"force_pipeline": "auto", "pdf2zh_service": "bing", "upstream_extractor": "opendataloader"}
            )
            # Original file should be archived into processed
            self.assertFalse(fake_pdf.exists())
            self.assertTrue((root / "processed" / "paper.pdf").exists())


if __name__ == "__main__":
    unittest.main()

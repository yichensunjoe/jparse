"""Unit tests for bitmap figure in-place translation module."""

import io
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import numpy as np
from PIL import Image, ImageDraw

from src.bitmap_figure_translator import (
    OCRItem,
    TextGroup,
    apply_bitmap_figure_translations,
    group_ocr_items,
    is_diagram_candidate,
    is_math_variable,
    render_translated_diagram,
    sample_background_and_text_color,
    translate_groups,
)


class TestBitmapFigureTranslator(unittest.TestCase):
    """Test suite for bitmap diagram recognition, filtering, and inpainting."""

    def test_is_math_variable(self):
        """Mathematical variables, subscripts, and formulas must be preserved."""
        variables = ["x1", "x2", "y1", "y_1", "x_i", "w_n", "X3", "z", "keff", "flux_1", "y = f(z)", "42", "100%"]
        for var in variables:
            self.assertTrue(is_math_variable(var), f"Expected '{var}' to be treated as a math variable")

        labels = ["NN model", "training dataset", "core input parameters", "Input layer", "Hidden layer", "Output layer"]
        for lbl in labels:
            self.assertFalse(is_math_variable(lbl), f"Expected '{lbl}' to NOT be treated as a math variable")

    def test_is_diagram_candidate(self):
        """Candidate gate must reject empty/pure math images and accept diagrams."""
        self.assertFalse(is_diagram_candidate([], 800, 600))

        # Only math variables
        math_items = [
            OCRItem(text="x1", box=[10, 10, 30, 30], score=0.99),
            OCRItem(text="y1", box=[100, 10, 120, 30], score=0.99),
        ]
        self.assertFalse(is_diagram_candidate(math_items, 800, 600))

        # Diagram with translatable text
        diag_items = [
            OCRItem(text="training", box=[10, 10, 80, 30], score=0.99),
            OCRItem(text="dataset", box=[10, 35, 80, 55], score=0.99),
            OCRItem(text="NN model", box=[100, 10, 180, 30], score=0.99),
        ]
        self.assertTrue(is_diagram_candidate(diag_items, 800, 600))

    def test_group_ocr_items(self):
        """Vertically adjacent text lines should be grouped into cohesive phrases."""
        items = [
            OCRItem(text="core input", box=[14, 234, 111, 260], score=0.99),
            OCRItem(text="parameters", box=[14, 263, 111, 284], score=0.99),
            OCRItem(text="outputs", box=[343, 247, 413, 273], score=0.99),
        ]
        groups = group_ocr_items(items)
        texts = [g.source_text for g in groups]
        self.assertIn("core input parameters", texts)
        self.assertIn("outputs", texts)

    def test_sample_background_and_text_color(self):
        """Sampling around box perimeter should extract the container background."""
        # Create an image with an orange container (248, 203, 173) and black text
        img = Image.new("RGB", (200, 100), (248, 203, 173))
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 40, 150, 60], fill=(0, 0, 0))

        arr = np.array(img)
        bg_col, text_col = sample_background_and_text_color(arr, [50, 40, 150, 60])
        self.assertEqual(bg_col, (248, 203, 173))
        self.assertEqual(text_col, (0, 0, 0))

    def test_translate_groups_domain_terms(self):
        """Domain terms should resolve instantly via dictionary."""
        groups = [
            TextGroup(source_text="core input parameters", box=[0, 0, 10, 10], sub_boxes=[]),
            TextGroup(source_text="NN model", box=[0, 0, 10, 10], sub_boxes=[]),
            TextGroup(source_text="Input layer", box=[0, 0, 10, 10], sub_boxes=[]),
            TextGroup(source_text="x1", box=[0, 0, 10, 10], sub_boxes=[], is_variable=True),
        ]
        res = translate_groups(groups, service="bing")
        self.assertEqual(res[0].translated, "堆芯输入参数")
        self.assertEqual(res[1].translated, "NN 模型")
        self.assertEqual(res[2].translated, "输入层")
        self.assertEqual(res[3].translated, "")  # Variable skipped

    def test_render_translated_diagram(self):
        """Clean erasure and Chinese text redraw on PIL image."""
        img = Image.new("RGB", (300, 200), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Draw a blue box with dark text
        draw.rectangle([50, 50, 250, 150], fill=(157, 195, 230))
        draw.rectangle([80, 80, 220, 120], fill=(0, 0, 0))  # text placeholder

        group = TextGroup(
            source_text="outputs",
            box=[80, 80, 220, 120],
            sub_boxes=[[80, 80, 220, 120]],
            translated="输出",
        )
        out_img = render_translated_diagram(img, [group])
        self.assertEqual(out_img.size, (300, 200))
        # The central region should no longer be black
        out_arr = np.array(out_img)
        center_color = out_arr[100, 70]  # Just left of text inside box
        # Should be blue container color
        self.assertAlmostEqual(center_color[0], 157, delta=10)
        self.assertAlmostEqual(center_color[1], 195, delta=10)
        self.assertAlmostEqual(center_color[2], 230, delta=10)


if __name__ == "__main__":
    unittest.main()

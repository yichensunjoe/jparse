"""Run platform tests with the embedded interpreter's isolated sys.path."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
suite = unittest.defaultTestLoader.loadTestsFromNames(
    ["tests.test_windows_packaging", "tests.test_windows_support"]
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tistory_newsroom.config import load_local_env


class LocalEnvTest(unittest.TestCase):
    def test_loads_missing_variables_without_overriding_existing_values(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"EXISTING_KEY": "keep"}, clear=True):
            root = Path(directory)
            (root / ".env").write_text("GEMINI_API_KEY='test-key'\nEXISTING_KEY=replace\n# note\n", encoding="utf-8")
            load_local_env(root)
            self.assertEqual(os.environ["GEMINI_API_KEY"], "test-key")
            self.assertEqual(os.environ["EXISTING_KEY"], "keep")

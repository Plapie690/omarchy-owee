"""Manifest compatibility with the marketplace's portable Quattro contract."""
import json
from pathlib import Path
import unittest


class ManifestContractTests(unittest.TestCase):
    def test_default_section_is_portable_to_marketplace(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / 'manifest.json').read_text())
        # The installed shell has extra sections, but the marketplace accepts only these.
        self.assertIn(manifest.get('barWidget', {}).get('defaultSection'),
                      (None, 'left', 'center', 'right'))

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.cohort_coverage_monitor.services.catalog_reader import read_catalog_exposomes


class TestCatalogReader(unittest.TestCase):
    """Locks in the fix for the always-zero exposome count.

    Real manifests key availability under top-level "layers" (per
    webapp/public/data/v1/pe/lima/lima_distritos/manifest.json), not under
    "spatial_indicators.indicators" -- that key is indexed by exposome_id and
    describes resolution/methodology, never an availability flag.
    """

    def test_counts_from_top_level_layers(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            catalog_path = base / "catalog.json"
            catalog_path.write_text(json.dumps({
                "cities": [
                    {"slug": "lima", "center": [-76.91, -12.045], "data_url": "/data/v1/pe/lima/lima_distritos/manifest.json"},
                ]
            }))

            manifest_dir = base / "data" / "v1" / "pe" / "lima" / "lima_distritos"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").write_text(json.dumps({
                "layers": {
                    "air_quality_pm25": {"available": True},
                    "alan": {"available": True},
                    "wildfire": {"available": False},
                },
                # Present in real manifests, must be ignored for counting.
                "spatial_indicators": {"pm25": {"layer_id": "air_quality_pm25"}},
            }))

            result = read_catalog_exposomes(catalog_path, base)

        self.assertEqual(result["lima"]["available_count"], 2)
        self.assertEqual(result["lima"]["expected_count"], 3)
        self.assertEqual(result["lima"]["available_list"], ["air_quality_pm25", "alan"])
        self.assertEqual(result["lima"]["center"], [-76.91, -12.045])


if __name__ == "__main__":
    unittest.main()

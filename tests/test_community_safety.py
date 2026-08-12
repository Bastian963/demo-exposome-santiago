"""Contract tests for the Argentina SAT community-safety layer."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.community_safety import (  # noqa: E402
    RAW_RELATIVE,
    YEARS,
    _normalise,
    build_community_safety_layer,
)


class CommunitySafetyTest(unittest.TestCase):
    def test_normalise_matches_accents_and_punctuation(self) -> None:
        self.assertEqual(_normalise("José C. Paz"), "jose c paz")
        self.assertEqual(_normalise("Comuna 08"), "comuna 08")

    @unittest.skipUnless(
        (REPO_ROOT / RAW_RELATIVE / "sat/csv/sat_propiedad_2017_2024.csv").exists(),
        "DNEC raw source is local-only",
    )
    def test_builds_complete_amba_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            csv_path, geojson_path, metadata_path = build_community_safety_layer(
                out_dir=Path(temp), cache_dir=Path(temp) / "cache"
            )
            frame = pd.read_csv(csv_path)
            self.assertEqual(len(frame), 55)
            self.assertFalse(frame["spatial_id"].duplicated().any())
            required = {
                "crime_property_rate_100k",
                "crime_robbery_rate_100k",
                "crime_theft_rate_100k",
                "crime_vehicle_rate_100k",
                "crime_public_space_pct",
                "crime_firearm_pct",
                *{
                    f"{metric}_{year}"
                    for metric in (
                        "crime_property_rate_100k",
                        "crime_robbery_rate_100k",
                        "crime_theft_rate_100k",
                        "crime_vehicle_rate_100k",
                        "crime_public_space_pct",
                        "crime_firearm_pct",
                    )
                    for year in YEARS
                },
            }
            self.assertTrue(required.issubset(frame.columns))
            self.assertFalse(frame[list(required)].isna().any().any())
            self.assertTrue(geojson_path.is_file())
            self.assertTrue(metadata_path.is_file())
            conservation = pd.read_csv(Path(temp) / "diagnostics/community_safety_conservation_by_year.csv")
            self.assertEqual(set(conservation["year"]), set(YEARS))
            self.assertTrue((conservation["source_events"] == conservation["mapped_events"] + conservation["unmapped_events"]).all())


if __name__ == "__main__":
    unittest.main()

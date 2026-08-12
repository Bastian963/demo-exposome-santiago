"""Contract tests for internal Argentina SAT mortality comparators."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.argentina_outcomes import (  # noqa: E402
    _source_records,
    build_argentina_outcome_comparator,
)
from exposome.community_safety import RAW_RELATIVE, YEARS  # noqa: E402
from exposome.layers import build_master_manifest  # noqa: E402
from exposome.studies import load_study  # noqa: E402


class ArgentinaOutcomeComparatorTests(unittest.TestCase):
    def test_comparators_are_not_master_inputs(self) -> None:
        manifest = build_master_manifest(
            load_study("buenos_aires_amba"),
            layer_ids=("suicide_mortality", "road_traffic_mortality"),
        )
        self.assertEqual(manifest["layers"], [])

    @unittest.skipUnless((ROOT / RAW_RELATIVE / "sat/csv/sat_suicidios_2017_2024.csv").exists(), "DNEC raw sources are local-only")
    def test_count_rules_follow_source_manuals(self) -> None:
        raw = ROOT / RAW_RELATIVE
        suicides = _source_records("suicide_mortality", raw)
        roads = _source_records("road_traffic_mortality", raw)
        self.assertEqual(len(suicides), suicides["tipo_persona_id"].nunique())
        self.assertTrue(roads["tipo_persona"].eq("Víctima").all())
        self.assertGreater(len(roads), 0)

    @unittest.skipUnless((ROOT / RAW_RELATIVE / "sat/csv/sat_suicidios_2017_2024.csv").exists(), "DNEC raw sources are local-only")
    def test_outputs_are_complete_aggregate_and_conserved(self) -> None:
        forbidden = ("latitud", "longitud", "calle", "id_hecho", "tipo_persona_id", "_sexo", "_edad")
        with tempfile.TemporaryDirectory() as temp:
            for kind, prefix in (("suicide_mortality", "suicide"), ("road_traffic_mortality", "road_traffic")):
                target = Path(temp) / kind
                csv_path, geojson_path, metadata_path = build_argentina_outcome_comparator(kind, out_dir=target)
                frame = pd.read_csv(csv_path)
                self.assertEqual(len(frame), 55)
                self.assertFalse(frame["spatial_id"].duplicated().any())
                self.assertFalse(frame.isna().any().any())
                self.assertIn(f"{prefix}_mortality_rate_100k", frame.columns)
                self.assertTrue({f"{prefix}_death_count_{year}" for year in YEARS}.issubset(frame.columns))
                payload_columns = [column for column in frame.columns if column not in {"spatial_id", "spatial_name"}]
                self.assertFalse(any(token in column.lower() for column in payload_columns for token in forbidden))
                conservation = pd.read_csv(target / "diagnostics" / f"{kind}_conservation_by_year.csv")
                self.assertEqual(set(conservation["year"]), set(YEARS))
                for measure in ("rows", "persons", "events"):
                    self.assertTrue((conservation[f"source_{measure}"] == conservation[f"mapped_{measure}"] + conservation[f"unmapped_{measure}"]).all())
                self.assertTrue(geojson_path.is_file())
                self.assertTrue(metadata_path.is_file())
                web = target / "web" / f"{kind}.geojson"
                self.assertTrue(web.is_file())
                web_frame = __import__("geopandas").read_file(web)
                self.assertFalse(any("count" in column for column in web_frame.columns))
                self.assertFalse(any("person" in column for column in web_frame.columns))
                for start in range(2017, 2023):
                    self.assertIn(
                        f"{prefix}_mortality_rate_100k_{start}_{start + 2}",
                        web_frame.columns,
                    )


if __name__ == "__main__":
    unittest.main()

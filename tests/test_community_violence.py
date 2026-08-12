from __future__ import annotations

import sys
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.community_violence import (  # noqa: E402
    YEARS,
    _metric_annual_counts,
    _metric_codes_for_year,
    _normalise_code,
)


class CommunityViolenceTests(unittest.TestCase):
    def test_normalise_code_preserves_hierarchy(self) -> None:
        self.assertEqual(_normalise_code("1.0"), "1")
        self.assertEqual(_normalise_code("11_1"), "11_1")

    def test_sexual_codes_follow_documented_taxonomy_eras(self) -> None:
        self.assertEqual(_metric_codes_for_year("violence_sexual_victim_rate_100k", 2022), ("10", "11"))
        self.assertEqual(
            _metric_codes_for_year("violence_sexual_victim_rate_100k", 2023),
            ("10", "11_1", "11_2", "11_3", "11_4", "11_5"),
        )

    def test_top_level_codes_do_not_double_count_children(self) -> None:
        units = []
        for number in range(1, 16):
            units.append({"spatial_id": f"caba_comuna_{number}", "spatial_name": f"Comuna {number}"})
        for number in range(40):
            units.append({"spatial_id": f"pba_{number:05d}", "spatial_name": f"Partido {number}"})
        units_gdf = gpd.GeoDataFrame(units)
        rows = []
        for unit in units:
            is_caba = unit["spatial_id"].startswith("caba_")
            for year in YEARS:
                sexual_codes = ("10", "11", "11_1") if year <= 2022 else (
                    "10", "11", "11_1", "11_2", "11_3", "11_4", "11_5"
                )
                for code in ("1", "2", "5", "17", *sexual_codes):
                    off_policy_duplicate = (
                        (year <= 2022 and code == "11_1")
                        or (year >= 2023 and code == "11")
                    )
                    rows.append(
                        {
                            "provincia_nombre": "Ciudad Autónoma de Buenos Aires" if is_caba else "Buenos Aires",
                            "departamento_nombre": unit["spatial_name"],
                            "anio": year,
                            "codigo_delito_snic_id": code,
                            "cantidad_victimas": 100 if off_policy_duplicate else 1,
                            "cantidad_hechos": 100 if off_policy_duplicate else 1,
                        }
                    )
        for year in YEARS:
            for code in ("1", "2", "5", "10", "11", "17"):
                rows.append(
                    {
                        "provincia_nombre": "Buenos Aires",
                        "departamento_nombre": "Fuera de AMBA",
                        "anio": year,
                        "codigo_delito_snic_id": code,
                        "cantidad_victimas": 10_000,
                        "cantidad_hechos": 10_000,
                    }
                )
        annual = _metric_annual_counts(pd.DataFrame(rows), units_gdf)
        self.assertEqual(len(annual), 55 * len(YEARS))
        early = annual[annual["year"] <= 2022]
        late = annual[annual["year"] >= 2023]
        self.assertTrue((early["violence_sexual_victim_count"] == 2).all())
        self.assertTrue((late["violence_sexual_victim_count"] == 6).all())


if __name__ == "__main__":
    unittest.main()

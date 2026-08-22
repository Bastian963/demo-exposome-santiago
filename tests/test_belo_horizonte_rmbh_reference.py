from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "migrations" / "build_belo_horizonte_rmbh_reference.py"
SPEC = importlib.util.spec_from_file_location("build_belo_horizonte_rmbh_reference", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _square(index: int) -> Polygon:
    west = float(index)
    return Polygon([(west, 0), (west + 0.8, 0), (west + 0.8, 0.8), (west, 0.8)])


class BeloHorizonteReferenceTests(unittest.TestCase):
    def _membership(self) -> gpd.GeoDataFrame:
        records = []
        for index in range(34):
            records.append(
                {
                    "cd_catmetrop": "04501",
                    "nm_catmetrop": "Região Metropolitana de Belo Horizonte",
                    "cd_mun": str(3100000 + index),
                    "nm_mun": f"Municipio {index}",
                    "geometry": _square(index),
                }
            )
        records.append(
            {
                "cd_catmetrop": "04502",
                "nm_catmetrop": "Colar Metropolitano de Belo Horizonte",
                "cd_mun": "3199999",
                "nm_mun": "Outside RMBH",
                "geometry": _square(35),
            }
        )
        return gpd.GeoDataFrame(records, crs="EPSG:4326")

    def _municipalities(self) -> gpd.GeoDataFrame:
        records = [
            {"CD_MUN": str(3100000 + index), "NM_MUN": f"Municipio {index}", "geometry": _square(index)}
            for index in range(34)
        ]
        records.append({"CD_MUN": "3199999", "NM_MUN": "Outside RMBH", "geometry": _square(35)})
        return gpd.GeoDataFrame(records, crs="EPSG:4326")

    def test_builds_exact_rmbh_and_excludes_colar(self) -> None:
        result = MODULE.build_reference(self._membership(), self._municipalities())

        self.assertEqual(len(result), 34)
        self.assertEqual(result["unit_id"].tolist()[0], "3100000")
        self.assertNotIn("3199999", set(result["unit_id"]))
        self.assertEqual(set(result["unit_type"]), {"municipio"})
        self.assertTrue(result.geometry.is_valid.all())

    def test_rejects_incomplete_official_membership(self) -> None:
        membership = self._membership().iloc[:-2].copy()
        with self.assertRaisesRegex(ValueError, "Expected 34 official RMBH"):
            MODULE.build_reference(membership, self._municipalities())

    def test_rejects_member_not_present_in_mesh(self) -> None:
        municipalities = self._municipalities().iloc[:-2].copy()
        with self.assertRaisesRegex(ValueError, "absent from MG municipal mesh"):
            MODULE.build_reference(self._membership(), municipalities)

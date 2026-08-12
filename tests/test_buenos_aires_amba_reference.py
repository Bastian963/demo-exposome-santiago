from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial import load_spatial_units  # noqa: E402
from exposome.studies import load_study  # noqa: E402


class BuenosAiresAmbaReferenceTests(unittest.TestCase):
    def test_reference_has_55_units_with_unique_ids_and_names(self) -> None:
        context = load_study("buenos_aires_amba", repo_root_path=ROOT)
        units = load_spatial_units(context)

        self.assertEqual(len(units), 55)
        self.assertFalse(units["spatial_id"].duplicated().any())
        self.assertFalse(units["spatial_name"].duplicated().any())

        comuna_ids = units["spatial_id"].str.fullmatch(r"caba_comuna_\d{2}")
        partido_ids = units["spatial_id"].str.fullmatch(r"pba_\d{5}")
        self.assertEqual(comuna_ids.sum(), 15)
        self.assertEqual(partido_ids.sum(), 40)

    def test_gran_la_plata_partidos_are_included(self) -> None:
        context = load_study("buenos_aires_amba", repo_root_path=ROOT)
        units = load_spatial_units(context)
        names = set(units["spatial_name"])
        for expected in ("La Plata", "Berisso", "Ensenada"):
            self.assertIn(expected, names)

    def test_comuna_names_use_composite_rule_with_truncation(self) -> None:
        context = load_study("buenos_aires_amba", repo_root_path=ROOT)
        units = load_spatial_units(context)
        by_id = dict(zip(units["spatial_id"], units["spatial_name"]))

        # Comuna 2 has a single barrio: no truncation, no trailing count.
        self.assertEqual(by_id["caba_comuna_02"], "Comuna 2 · Recoleta")
        # Comuna 1 has 6 barrios: "first two + N" truncation.
        self.assertEqual(by_id["caba_comuna_01"], "Comuna 1 · Constitucion, San Telmo +4")

    def test_names_are_source_faithful(self) -> None:
        # Partido names use IGN's own spelling verbatim (accented); comuna
        # names use GCBA's own barrios spelling verbatim (mostly unaccented,
        # but not stripped -- e.g. "Nuñez" keeps its ñ). Both render fine in
        # the webapp's VT323 body font (see build_buenos_aires_amba_reference.py).
        context = load_study("buenos_aires_amba", repo_root_path=ROOT)
        units = load_spatial_units(context)
        names = set(units["spatial_name"])
        for expected in ("José C. Paz", "Lanús", "Morón", "Ituzaingó"):
            self.assertIn(expected, names)
        by_id = dict(zip(units["spatial_id"], units["spatial_name"]))
        self.assertEqual(by_id["caba_comuna_13"], "Comuna 13 · Belgrano, Nuñez +1")

    def test_all_units_within_location_bbox(self) -> None:
        context = load_study("buenos_aires_amba", repo_root_path=ROOT)
        units = load_spatial_units(context)
        bbox = context.location.bbox
        minx, miny, maxx, maxy = units.total_bounds
        self.assertGreaterEqual(minx, bbox.west)
        self.assertGreaterEqual(miny, bbox.south)
        self.assertLessEqual(maxx, bbox.east)
        self.assertLessEqual(maxy, bbox.north)

    def test_reference_metadata_records_provenance(self) -> None:
        path = (
            ROOT / "data" / "reference" / "ar" / "buenos_aires_amba" / "buenos_aires_amba" / "metadata.json"
        )
        metadata = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["unit_count"], 55)
        self.assertEqual(metadata["n_comunas"], 15)
        self.assertEqual(metadata["n_partidos"], 40)


if __name__ == "__main__":
    unittest.main()

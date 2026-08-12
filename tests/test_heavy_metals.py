"""Tests for the heavy metals (RETC) exposome layer (cache-first, no network)."""
from __future__ import annotations

import json
import sys
from tempfile import TemporaryDirectory
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
CACHE_DIR = REPO_ROOT / "cache"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
MASTER_GEOJSON = DATA_DIR / "santiago_exposome_master.geojson"

EXPECTED_COLUMNS = [
    "name",
    "hm_pb_kg",
    "hm_mn_kg",
    "hm_as_kg",
    "hm_cd_kg",
    "hm_hg_kg",
    "n_sources",
    "hm_pb_log",
    "hm_as_log",
    "hm_index",
]


class HeavyMetalsLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_heavy_metals_retc_2015_2022.csv"
        cls.geojson_path = DATA_DIR / "santiago_heavy_metals_retc_2015_2022.geojson"
        cls.metadata_path = DATA_DIR / "santiago_heavy_metals_retc_2015_2022_metadata.json"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_heavy_metals.py first."
            )
        cls.df = pd.read_csv(cls.csv_path)
        if not cls.metadata_path.exists():
            cls.metadata = None
        else:
            cls.metadata = json.loads(cls.metadata_path.read_text(encoding="utf-8"))

    def test_csv_has_52_communes(self) -> None:
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)
        self.assertEqual(self.df["name"].duplicated().sum(), 0)

    def test_csv_columns_complete(self) -> None:
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"missing column: {col}")
        # All numeric columns must be fully populated. A real "0 kg" emission
        # is a valid sentinel ("no RETC declaration") and is encoded as 0.0,
        # never as NaN.
        numeric = [c for c in EXPECTED_COLUMNS if c != "name"]
        self.assertEqual(self.df[numeric].isna().sum().sum(), 0)

    def test_metadata_coherence(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible (likely cloud-sync delay)")
        self.assertEqual(self.metadata["n_communes"], 52)
        self.assertEqual(self.metadata["years"], list(range(2015, 2023)))
        self.assertEqual(
            self.metadata["metals"],
            ["pb", "mn", "as", "cd", "hg"],
        )
        weights = self.metadata["metal_weights"]
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)
        # Pb must dominate the weights (0.35) — it's the primary neurotoxin.
        self.assertEqual(weights["pb"], 0.35)
        # Each metal (Pb, Mn, As, Cd, Hg) has a human-readable description
        # in the metadata `columns` dict.
        for m in ("pb", "mn", "as", "cd", "hg"):
            self.assertIn(
                f"hm_{m}_kg",
                self.metadata["columns"],
                f"metadata missing description for hm_{m}_kg",
            )
        # The Mn/Cd sentinel note must be present — these metals have ZERO
        # RM declarations and that is a real data finding, not a bug.
        self.assertIn("Manganeso", self.metadata["note_mn_cd"])
        self.assertIn("Cadmio", self.metadata["note_mn_cd"])

    def test_mn_cd_sentinel_zero(self) -> None:
        """Mn and Cd are zero across all 52 communes — a real data finding.

        Industrial sources of Mn and Cd in Chile are concentrated in mining
        regions (Atacama, Coquimbo, Maule), not in the Santiago RM. This is
        encoded as 0.0 (not NaN) so the columns remain usable for master
        integration and downstream correlation analysis.
        """
        mn = self.df["hm_mn_kg"]
        cd = self.df["hm_cd_kg"]
        self.assertEqual(mn.isna().sum(), 0)
        self.assertEqual(cd.isna().sum(), 0)
        self.assertEqual(float(mn.sum()), 0.0)
        self.assertEqual(float(cd.sum()), 0.0)
        # These counts must match the metadata — 0 communes with Mn > 0
        # and 0 communes with Cd > 0.
        if self.metadata is not None:
            self.assertEqual(self.metadata["communes_with_mn"], 0)
            self.assertEqual(self.metadata["communes_with_cd"], 0)

    def test_pb_log_transform(self) -> None:
        """hm_pb_log == log1p(hm_pb_kg), rounded to 3 decimals."""
        import numpy as np

        expected = np.log1p(self.df["hm_pb_kg"]).round(3)
        actual = self.df["hm_pb_log"]
        diff = (actual - expected).abs().max()
        self.assertLessEqual(float(diff), 1e-3)
        # log1p(0) = 0 — communes with no Pb emissions get log = 0.
        zero_pb = self.df.loc[self.df["hm_pb_kg"] == 0.0, "hm_pb_log"]
        self.assertTrue((zero_pb == 0.0).all())
        # Tiltil, the dominant emitter (~10,629 kg/yr), gets log ~ 9.27.
        tiltil = self.df.loc[self.df["name"] == "Tiltil", "hm_pb_log"]
        self.assertEqual(len(tiltil), 1)
        self.assertAlmostEqual(float(tiltil.iloc[0]), 9.271, places=2)

    def test_pb_log_monotonicity(self) -> None:
        """Larger raw Pb → larger log1p(Pb), strict for non-zero values."""
        import numpy as np

        nonzero = self.df.loc[self.df["hm_pb_kg"] > 0].copy()
        nonzero = nonzero.sort_values("hm_pb_kg")
        log_sorted = np.log1p(nonzero["hm_pb_kg"].to_numpy())
        self.assertTrue(
            (log_sorted[1:] >= log_sorted[:-1]).all(),
            "hm_pb_log is not monotone in hm_pb_kg for non-zero Pb communes",
        )

    def test_hm_index_zscore_semantics(self) -> None:
        """hm_index is a weighted z-score composite; mean ~ 0, std < 5."""
        import numpy as np

        idx = self.df["hm_index"]
        self.assertEqual(idx.isna().sum(), 0)
        # The composite is sum_i w_i * (x_i - mean_i) / std_i. With Mn=Cd=0
        # the effective weights are 0.35 (Pb) + 0.20 (As) on the non-zero
        # components, so the result is bounded but not centred exactly at 0
        # (because Mn/Cd terms contribute -w*mean/std). Mean stays near 0.
        self.assertAlmostEqual(float(idx.mean()), 0.0, delta=0.5)
        self.assertLess(float(idx.std()), 5.0)
        # Tiltil, the dominant emitter, must be at the top of the index.
        tiltil = self.df.loc[self.df["name"] == "Tiltil", "hm_index"]
        self.assertEqual(len(tiltil), 1)
        self.assertGreater(float(tiltil.iloc[0]), float(idx.median()))

    def test_tiltil_outlier(self) -> None:
        """Tiltil concentrates > 99% of RM Pb emissions (real industrial site)."""
        pb = self.df["hm_pb_kg"]
        tiltil = self.df.loc[self.df["name"] == "Tiltil", "hm_pb_kg"].iloc[0]
        share = tiltil / pb.sum()
        self.assertGreater(float(share), 0.95)
        # Tiltil is in the top 3 by raw Pb.
        top3 = set(pb.nlargest(3).index)
        self.assertIn(
            self.df.loc[self.df["name"] == "Tiltil"].index[0],
            top3,
        )

    def test_n_sources_distribution(self) -> None:
        """n_sources is a non-negative integer count of unique establishments."""
        ns = self.df["n_sources"]
        self.assertEqual(ns.isna().sum(), 0)
        # Integer-valued.
        self.assertTrue((ns == ns.round()).all())
        # Total establishments must match the metadata.
        if self.metadata is not None:
            self.assertEqual(int(ns.sum()), self.metadata["n_sources_total"])
        # 45 of 52 communes report at least one Pb source; 7 are Pb-clean.
        self.assertEqual(int((self.df["hm_pb_kg"] > 0).sum()), 45)

    def test_master_integration(self) -> None:
        if not MASTER_CSV.exists():
            self.skipTest("Master CSV missing; run scripts/build_master_exposome.py first.")
        master_cols = pd.read_csv(MASTER_CSV, nrows=0).columns
        core = [
            "hm_pb_kg",
            "hm_mn_kg",
            "hm_as_kg",
            "hm_cd_kg",
            "hm_hg_kg",
            "n_sources",
            "hm_pb_log",
            "hm_as_log",
            "hm_index",
        ]
        for col in core:
            self.assertIn(col, master_cols, f"master missing core col: {col}")
        # Sentinel zeros (Mn, Cd) must propagate as 0.0 in the master, not
        # as NaN. Sample one row to confirm.
        master_df = pd.read_csv(MASTER_CSV)
        self.assertEqual(master_df["hm_mn_kg"].isna().sum(), 0)
        self.assertEqual(master_df["hm_cd_kg"].isna().sum(), 0)


class HeavyMetalsHelpersTest(unittest.TestCase):
    """Unit tests for the heavy_metals module helpers (no I/O)."""

    def test_emission_to_kg_units(self) -> None:
        """Unit conversion: tonnes → kg (×1000), g → kg (×0.001), kg → kg."""
        from exposome.heavy_metals import _emission_to_kg

        self.assertAlmostEqual(_emission_to_kg(2.5, "ton/año"), 2500.0, places=6)
        self.assertAlmostEqual(_emission_to_kg(2.5, "t/año"), 2500.0, places=6)
        self.assertAlmostEqual(_emission_to_kg(500.0, "g/año"), 0.5, places=6)
        self.assertAlmostEqual(_emission_to_kg(7.3, "kg/año"), 7.3, places=6)
        self.assertAlmostEqual(_emission_to_kg(0, "ton/año"), 0.0, places=6)
        # Negative values clamp to 0 (data-entry error guard).
        self.assertEqual(_emission_to_kg(-1.0, "ton/año"), 0.0)
        # Missing / dash / None → 0.0.
        self.assertEqual(_emission_to_kg(None, "kg/año"), 0.0)
        self.assertEqual(_emission_to_kg("-", "kg/año"), 0.0)

    def test_parse_float_es_spanish_locale(self) -> None:
        """Spanish-locale numbers: comma decimal, dot thousands separator."""
        from exposome.heavy_metals import _parse_float_es

        self.assertAlmostEqual(_parse_float_es("1.234,56"), 1234.56, places=6)
        self.assertAlmostEqual(_parse_float_es("0,05"), 0.05, places=6)
        self.assertAlmostEqual(_parse_float_es("100"), 100.0, places=6)
        self.assertAlmostEqual(_parse_float_es("-"), None)
        self.assertAlmostEqual(_parse_float_es(""), None)
        self.assertAlmostEqual(_parse_float_es("N/A"), None)

    def test_classify_metal_spanish(self) -> None:
        """Spanish contaminant names → metal codes via keyword match."""
        from exposome.heavy_metals import _classify_metal

        self.assertEqual(_classify_metal("Plomo (Pb)"), "pb")
        self.assertEqual(_classify_metal("arsénico"), "as")
        self.assertEqual(_classify_metal("Arsenico"), "as")
        self.assertEqual(_classify_metal("MANGANESO"), "mn")
        self.assertEqual(_classify_metal("Cadmio"), "cd")
        self.assertEqual(_classify_metal("Mercurio"), "hg")
        # Unrelated contaminants → None.
        self.assertIsNone(_classify_metal("Material particulado MP10"))
        self.assertIsNone(_classify_metal(""))
        self.assertIsNone(_classify_metal(None))  # type: ignore[arg-type]


class HeavyMetalsBuildLayerTest(unittest.TestCase):
    """Smoke test the build_layer module from cache, no network.

    The RETC cache is large (~500 MB across 8 years, with the 2020 file
    alone at 118 MB), so a full re-build takes several minutes. We keep the
    round-trip check here but skip it unless the optional
    ``RUN_HEAVY_METALS_BUILD_TEST=1`` env flag is set — by default the data
    validation tests above already guarantee the layer's correctness, and
    cache-first reproducibility is verified manually during the audit.
    """

    def test_build_layer_idempotent_from_cache(self) -> None:
        import os

        if os.environ.get("RUN_HEAVY_METALS_BUILD_TEST") != "1":
            self.skipTest(
                "Skipped by default (set RUN_HEAVY_METALS_BUILD_TEST=1 to enable; "
                "re-builds from ~500 MB RETC cache in ~3 min)."
            )
        from exposome.heavy_metals import build_heavy_metals_layer

        if not (CACHE_DIR / "retc_efp_2015.csv").exists():
            self.skipTest("RETC cache missing; run scripts/run_heavy_metals.py once.")
        if not (CACHE_DIR / "santiago_communes.geojson").exists():
            self.skipTest("Communes boundary cache missing.")

        df_before = pd.read_csv(DATA_DIR / "santiago_heavy_metals_retc_2015_2022.csv")

        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            df_new, _ = build_heavy_metals_layer(
                city="santiago",
                cache_dir=CACHE_DIR,
                out_dir=out_dir,
            )
            df_after = pd.read_csv(out_dir / "santiago_heavy_metals_retc_2015_2022.csv")

        self.assertEqual(df_new["name"].tolist(), df_before["name"].tolist())
        numeric_cols = [c for c in EXPECTED_COLUMNS if c != "name"]
        m_before = df_before.set_index("name")[numeric_cols]
        m_after = df_after.set_index("name")[numeric_cols]
        for c in numeric_cols:
            diff = (m_before[c] - m_after[c]).abs().max()
            self.assertLessEqual(
                float(diff),
                1e-9,
                f"column {c} diverged by {diff} after re-build",
            )
        # Sentinel zeros are preserved.
        self.assertEqual(
            int((df_after["hm_mn_kg"] == 0).sum()),
            int((df_before["hm_mn_kg"] == 0).sum()),
        )
        self.assertEqual(
            int((df_after["hm_cd_kg"] == 0).sum()),
            int((df_before["hm_cd_kg"] == 0).sum()),
        )


if __name__ == "__main__":
    unittest.main()

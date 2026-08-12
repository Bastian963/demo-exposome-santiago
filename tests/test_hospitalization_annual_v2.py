from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pandas as pd

from exposome.hospitalization_annual_v2 import (
    AnnualExposureSpec,
    _diagnostic_numeric_array,
    _fixed_effect_design,
    _poisson_deviance_terms,
    _validate_annual_artifact,
    attach_socioeconomic_and_joint_scores,
    bayesian_tasks,
    build_timed_frame,
    estimability,
    exposure_specs,
    load_analysis_config,
    validate_analysis_config,
)
from exposome.hospitalization_annual_v2_runner import (
    _finalization_preflight,
    run_finalize_phase,
    status_phase,
)
from exposome.inference_run_state import InferenceStateError


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config/analyses/hospitalization_annual_v2.yaml"


class AnnualHospitalizationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_analysis_config(CONFIG_PATH)

    def test_config_prespecifies_eight_component_mixture(self) -> None:
        specs = exposure_specs(self.config, include_sensitivities=True)
        self.assertEqual(len([spec for spec in specs if spec.core_mixture]), 8)
        self.assertEqual(
            {spec.id for spec in specs if spec.direction == -1},
            {"green", "wind", "green_landsat"},
        )
        self.assertEqual(len(bayesian_tasks(self.config)), 142)

    def test_scope_cannot_enable_webapp(self) -> None:
        invalid = json.loads(json.dumps(self.config))
        invalid["scope"]["webapp"] = True
        with self.assertRaisesRegex(ValueError, "offline-only"):
            validate_analysis_config(invalid)

    def test_annual_manifest_hash_and_identity_are_enforced(self) -> None:
        spec = AnnualExposureSpec(
            id="pm25",
            layer="pm25",
            column="pm25_pop_weighted",
            direction=1,
            expected_years=(2015,),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annual = root / "annual.csv"
            manifest = root / "manifest.json"
            frame = pd.DataFrame(
                {
                    "spatial_id": np.arange(52) + 13101,
                    "spatial_name": [f"c{i}" for i in range(52)],
                    "year": 2015,
                    "pm25_pop_weighted": np.linspace(10, 20, 52),
                }
            )
            frame.to_csv(annual, index=False)
            digest = hashlib.sha256(annual.read_bytes()).hexdigest()
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "study_id": "santiago_communes",
                        "layer_id": "pm25",
                        "year": 2015,
                        "annual_table": "annual.csv",
                        "sha256": digest,
                        "n_rows": 52,
                    }
                ),
                encoding="utf-8",
            )
            validated, provenance = _validate_annual_artifact(
                annual, manifest, spec, 2015, "santiago_communes"
            )
            self.assertEqual(len(validated), 52)
            self.assertEqual(provenance["n_complete"], 52)
            frame.loc[0, "pm25_pop_weighted"] = 99
            frame.to_csv(annual, index=False)
            with self.assertRaisesRegex(ValueError, "sha256"):
                _validate_annual_artifact(
                    annual, manifest, spec, 2015, "santiago_communes"
                )

    def _synthetic_exposures(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        ids = [str(13101 + index) for index in range(52)]
        rows = []
        core = [spec for spec in exposure_specs(self.config) if spec.core_mixture]
        for year in range(2016, 2020):
            for index, spatial_id in enumerate(ids):
                row = {
                    "spatial_id": spatial_id,
                    "spatial_name": f"commune-{index}",
                    "year": year,
                }
                for position, spec in enumerate(core):
                    row[spec.id] = index * (position + 1) + (year - 2015) ** 2
                rows.append(row)
        master = pd.DataFrame(
            {
                "spatial_id": ids,
                "spatial_name": [f"commune-{index}" for index in range(52)],
                "nse_index_pca": np.linspace(-2, 2, 52),
                "nse_index": np.linspace(-1.8, 1.9, 52),
                "nse_quintil": np.repeat(np.arange(1, 6), [11, 10, 10, 10, 11]),
            }
        )
        return pd.DataFrame(rows), master

    def test_burden_orients_protective_components_and_adds_deprivation(self) -> None:
        exposures, master = self._synthetic_exposures()
        panel, scaling = attach_socioeconomic_and_joint_scores(
            exposures, master, self.config
        )
        self.assertFalse(panel["environmental_burden"].isna().any())
        self.assertTrue(panel["double_burden"].between(0, 1).all())
        self.assertEqual(scaling["components"]["green"]["direction"], -1)
        high_nse = panel.loc[panel["spatial_id"] == "13152", "deprivation_z"].iloc[0]
        low_nse = panel.loc[panel["spatial_id"] == "13101", "deprivation_z"].iloc[0]
        self.assertLess(high_nse, low_nse)

    def test_lag_one_alignment_and_fe_design_do_not_duplicate_static_main_effects(self) -> None:
        exposures, master = self._synthetic_exposures()
        panel, _ = attach_socioeconomic_and_joint_scores(exposures, master, self.config)
        outcomes = pd.DataFrame(
            [
                {
                    "spatial_id": row.spatial_id,
                    "spatial_name": row.spatial_name,
                    "year": year,
                    "outcome": "cardiovascular",
                    "observed": 10 + index,
                    "expected": 10.0,
                }
                for year in range(2017, 2021)
                for index, row in enumerate(master.itertuples(index=False))
            ]
        )
        frame = build_timed_frame(
            panel,
            outcomes,
            exposure="environmental_burden",
            outcome="cardiovascular",
            timing="lag1",
            outcome_years=[2017, 2018, 2019, 2020],
        )
        self.assertTrue((frame["outcome_year"] == frame["exposure_year"] + 1).all())
        ok, reason = estimability(frame, self.config["screening"])
        self.assertTrue(ok, reason)
        design = _fixed_effect_design(frame, include_interaction=True)
        self.assertIn("exposure_within_z", design)
        self.assertIn("interaction_z", design)
        self.assertNotIn("exposure_between_z", design)
        self.assertNotIn("deprivation_z", design)

    def test_no2_two_year_overlap_is_not_estimable(self) -> None:
        frame = pd.DataFrame(
            {
                "spatial_id": np.tile([str(13101 + i) for i in range(52)], 2),
                "outcome_year": np.repeat([2019, 2020], 52),
                "exposure_within": np.arange(104, dtype=float),
            }
        )
        ok, reason = estimability(frame, self.config["screening"])
        self.assertFalse(ok)
        self.assertIn("years=2", str(reason))

    def test_poisson_deviance_accepts_zero_counts_without_log_zero(self) -> None:
        observed = np.array([0.0, 1.0, 4.0])
        prediction = np.array([0.5, 1.5, 3.0])
        with np.errstate(divide="raise", invalid="raise"):
            terms = _poisson_deviance_terms(observed, prediction)
        self.assertEqual(terms[0], prediction[0])
        self.assertTrue(np.isfinite(terms).all())

    def test_bayesian_diagnostic_normalizes_datatree_dataset_view(self) -> None:
        class DatasetView:
            def to_array(self) -> np.ndarray:
                return np.array([[0.71, 0.83, 0.92]])

        class DataTree:
            dataset = DatasetView()

        values = _diagnostic_numeric_array(DataTree())
        np.testing.assert_allclose(values, [[0.71, 0.83, 0.92]])

    def test_finalize_refuses_an_incomplete_registry_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "screening").mkdir()
            pd.DataFrame(
                [{"status": "ok", "outcome": "cardiovascular"}]
            ).to_csv(output / "screening/screening_results.csv", index=False)
            with self.assertRaisesRegex(InferenceStateError, "Screening registry"):
                _finalization_preflight(
                    output,
                    self.config,
                    "fingerprint",
                    verify_trace_hashes=False,
                )

    def test_finalize_gate_fails_before_any_publication_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            state = {"scientific_fingerprint": "fingerprint"}
            with (
                patch(
                    "exposome.hospitalization_annual_v2_runner.require_prepared_state",
                    return_value=(self.config, state, output),
                ),
                patch(
                    "exposome.hospitalization_annual_v2_runner._finalization_preflight",
                    side_effect=InferenceStateError("142 models required"),
                ),
            ):
                with self.assertRaisesRegex(InferenceStateError, "142 models"):
                    run_finalize_phase(
                        REPO_ROOT, CONFIG_PATH, output_dir=output
                    )
            self.assertFalse((output / "evidence_table.csv").exists())
            self.assertFalse((output / "publication_acceptance.json").exists())

    def test_status_reconstructs_missing_bayesian_summary_from_sidecars(self) -> None:
        tasks = bayesian_tasks(self.config)
        rows = [{**task.as_dict(), "state": "ok", "reason": None} for task in tasks]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "prepared_state.json").write_text("{}", encoding="utf-8")
            state = {"scientific_fingerprint": "fingerprint"}
            with (
                patch(
                    "exposome.hospitalization_annual_v2_runner.require_prepared_state",
                    return_value=(self.config, state, output),
                ),
                patch(
                    "exposome.hospitalization_annual_v2_runner.InferenceRunStore.status_rows",
                    return_value=rows,
                ),
            ):
                result = status_phase(REPO_ROOT, CONFIG_PATH, output_dir=output)
            self.assertTrue(result["prepared_valid"])
            self.assertTrue(result["bayesian"]["reconstructed_from_sidecars"])
            self.assertEqual(result["bayesian"]["complete"], 142)
            self.assertEqual(result["bayesian"]["pending"], 0)


if __name__ == "__main__":
    unittest.main()

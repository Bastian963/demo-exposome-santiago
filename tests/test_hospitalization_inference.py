from __future__ import annotations

from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.config import load_config  # noqa: E402
from exposome.hospitalization_analytics import OUTCOME_PREFIXES  # noqa: E402
from exposome.hospitalization_inference import (  # noqa: E402
    BayesianModelData,
    SpatialGraph,
    _diagnostic_numeric_array,
    apply_multiplicity,
    augment_exposure_matrix,
    bayesian_diagnostics,
    build_pymc_nb_model,
    build_queen_graph,
    classical_correlation_analysis,
    collinearity_diagnostics,
    correlation_estimate,
    extract_loo_result,
    icar_scaling_factor,
    leave_one_out_correlations,
    oriented_exposure_matrix,
    partial_spearman,
    psis_loo_with_exact_refits,
    require_bayesian_dependencies,
    sample_pymc_model,
    summarize_bayesian_effect,
    validate_analysis_inputs,
    validate_inference_config,
)
from exposome.inference_run_state import (  # noqa: E402
    InferenceConfigMismatch,
    InferenceRunStore,
    InferenceStateError,
    ModelTask,
    publication_tasks,
    scientific_fingerprint,
)


class ClassicalInferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rng = np.random.default_rng(431)

    def test_pearson_spearman_kendall_and_log_transform(self) -> None:
        x = np.linspace(-2, 2, 52)
        smr = np.exp(0.7 * x)
        pearson_log, p_log = correlation_estimate("pearson_log_smr", x, smr)
        pearson_raw, _ = correlation_estimate("pearson_raw_smr", x, smr)
        spearman, _ = correlation_estimate("spearman_raw_smr", x, smr)
        kendall, _ = correlation_estimate("kendall_raw_smr", x, smr)
        self.assertAlmostEqual(pearson_log, 1.0, places=12)
        self.assertLess(p_log, 1e-30)
        self.assertLess(pearson_raw, pearson_log)
        self.assertAlmostEqual(spearman, 1.0, places=12)
        self.assertAlmostEqual(kendall, 1.0, places=12)

    def test_negative_control_is_exactly_s00_through_t98(self) -> None:
        prefixes = OUTCOME_PREFIXES["injury_poisoning"]
        self.assertTrue("S00".startswith(prefixes))
        self.assertTrue("T98".startswith(prefixes))
        self.assertFalse("T99".startswith(prefixes))

    def test_partial_spearman_removes_rank_confounding(self) -> None:
        z = np.linspace(-3, 3, 52)
        x = z + self.rng.normal(0, 0.2, len(z))
        y = z + self.rng.normal(0, 0.2, len(z))
        raw, _ = correlation_estimate("spearman_raw_smr", x, y)
        partial, p_value = partial_spearman(x, y, z[:, None])
        self.assertGreater(raw, 0.9)
        self.assertLess(abs(partial), 0.3)
        self.assertGreater(p_value, 0.02)

    def test_holm_and_bh_are_applied_within_method_and_family(self) -> None:
        table = pd.DataFrame(
            {
                "method": ["pearson"] * 7,
                "multiplicity_family": ["confirmatory_chronic"] * 5
                + ["secondary_cross_sectional"] * 2,
                "status": ["ok"] * 7,
                "p_value": [0.001, 0.01, 0.02, 0.2, 0.8, 0.01, 0.03],
            }
        )
        adjusted = apply_multiplicity(table)
        confirmatory = adjusted.iloc[:5]
        secondary = adjusted.iloc[5:]
        self.assertTrue(confirmatory["p_holm"].between(0, 1).all())
        self.assertTrue(confirmatory["q_bh"].between(0, 1).all())
        self.assertTrue(secondary["q_bh"].between(0, 1).all())
        self.assertTrue(secondary["p_holm"].isna().all())

    def test_leave_one_out_flags_an_influential_sign_change(self) -> None:
        x = np.arange(8, dtype=float)
        y = -x.copy()
        y[-1] = 100
        full, _ = correlation_estimate("pearson_raw_smr", x, y)
        influence = leave_one_out_correlations(
            "pearson_raw_smr", x, y, None, [str(value) for value in range(8)], full
        )
        self.assertTrue(influence["sign_changed"].any())
        influential = influence.iloc[influence["delta_from_full"].abs().argmax()]
        self.assertEqual(influential["excluded_spatial_id"], "7")

    def test_orientation_preserves_original_values(self) -> None:
        config = {
            "exposures": [
                {
                    "id": "harm",
                    "source_column": "harm_source",
                    "orientation": 1,
                },
                {
                    "id": "benefit",
                    "source_column": "benefit_source",
                    "orientation": -1,
                },
            ]
        }
        frame = pd.DataFrame(
            {
                "spatial_id": ["1", "2", "3"],
                "spatial_name": ["a", "b", "c"],
                "harm_source": [1.0, 2.0, 3.0],
                "benefit_source": [1.0, 2.0, 3.0],
            }
        )
        oriented, metadata = oriented_exposure_matrix(frame, config)
        self.assertEqual(oriented["benefit__original"].tolist(), [1.0, 2.0, 3.0])
        self.assertGreater(oriented.loc[0, "benefit"], oriented.loc[2, "benefit"])
        self.assertEqual(set(metadata["higher_oriented_value"]), {"greater_burden"})

    def test_collinearity_returns_vif_and_clusters(self) -> None:
        frame = pd.DataFrame(
            {
                "a": np.arange(20, dtype=float),
                "b": np.arange(20, dtype=float) + self.rng.normal(0, 0.01, 20),
                "c": self.rng.normal(size=20),
            }
        )
        matrix, vif, clusters = collinearity_diagnostics(
            frame, ["a", "b", "c"], rho_threshold=0.8
        )
        self.assertEqual(len(matrix), 9)
        self.assertEqual(len(vif), 3)
        self.assertEqual(
            clusters.set_index("exposure").loc["a", "cluster_id"],
            clusters.set_index("exposure").loc["b", "cluster_id"],
        )


class SpatialGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.geometry_path = (
            REPO_ROOT
            / "data/reference/cl/santiago/santiago_communes/spatial_units.geojson"
        )

    def test_real_queen_graph_is_stable_symmetric_connected_and_scaled(self) -> None:
        graph = build_queen_graph(gpd.read_file(self.geometry_path))
        self.assertEqual(len(graph.spatial_ids), 52)
        self.assertEqual(graph.spatial_ids, tuple(sorted(graph.spatial_ids)))
        np.testing.assert_array_equal(graph.adjacency, graph.adjacency.T)
        self.assertTrue((graph.adjacency.sum(axis=1) > 0).all())
        self.assertGreater(graph.scaling_factor, 0)

    def test_scaling_factor_is_invariant_to_node_permutation(self) -> None:
        adjacency = np.zeros((52, 52), dtype=int)
        for index in range(51):
            adjacency[index, index + 1] = adjacency[index + 1, index] = 1
        first = icar_scaling_factor(adjacency)
        permutation = np.random.default_rng(8).permutation(52)
        second = icar_scaling_factor(adjacency[np.ix_(permutation, permutation)])
        self.assertAlmostEqual(first, second, places=9)


class MaterializedIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        resolved = load_config("santiago_communes")
        cls.config = deepcopy(
            resolved["neuro_hospitalizations"]["analysis"]["inference"]
        )
        cls.config["correlations"]["bootstrap_samples"] = 0
        validate_inference_config(cls.config)
        inputs = cls.config["inputs"]
        cls.smr = pd.read_csv(REPO_ROOT / inputs["smr"], dtype={"spatial_id": str})
        raw_exposures = pd.read_csv(
            REPO_ROOT / inputs["exposures"], dtype={"spatial_id": str}
        )
        master = pd.read_csv(REPO_ROOT / inputs["master"], dtype={"spatial_id": str})
        cls.exposures = augment_exposure_matrix(raw_exposures, master)

    def test_main_contract_is_exactly_50_complete_pairs(self) -> None:
        index = validate_analysis_inputs(self.smr, self.exposures, self.config)
        self.assertEqual(len(index), 50)
        self.assertEqual(set(index["n_complete"]), {52})
        self.assertNotIn("2006", " ".join(index["window"]))

    def test_classical_table_has_six_methods_per_pair_and_bounded_q_values(self) -> None:
        table, influence, exclusions = classical_correlation_analysis(
            self.smr, self.exposures, self.config
        )
        self.assertEqual(len(table), 50 * 6)
        self.assertTrue(table["status"].eq("ok").all(), exclusions.to_string(index=False))
        self.assertTrue(table["q_bh"].between(0, 1).all())
        self.assertEqual(len(influence), 50 * 6 * 52)
        self.assertTrue(table["window"].eq("primary_pre_covid_2018_2019").all())


class InferenceRunStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        resolved = load_config("santiago_communes")
        cls.config = deepcopy(
            resolved["neuro_hospitalizations"]["analysis"]["inference"]
        )

    def test_publication_registry_has_exact_prespecified_phase_counts(self) -> None:
        spatial_ids = [str(13101 + value) for value in range(52)]
        tasks = publication_tasks(self.config, spatial_ids)
        counts = pd.Series([task.phase for task in tasks]).value_counts().to_dict()
        self.assertEqual(
            counts,
            {
                "commune-loo": 260,
                "sensitivities": 25,
                "primary": 15,
                "negative-controls": 2,
            },
        )
        self.assertEqual(len({task.model_id for task in tasks}), 302)

    def test_scope_is_explicitly_offline_and_not_published(self) -> None:
        self.assertEqual(str(self.config["protocol_version"]), "1.0")
        self.assertEqual(
            self.config["scope"],
            {
                "product": "offline_data_analysis",
                "webapp": False,
                "exposome_master": False,
                "automated_publish": False,
            },
        )
        validate_inference_config(self.config)

    def test_fingerprint_changes_with_scientific_inputs(self) -> None:
        first = scientific_fingerprint(self.config, {"smr.csv": "a" * 64})
        second = scientific_fingerprint(self.config, {"smr.csv": "b" * 64})
        self.assertNotEqual(first, second)

    def test_psis_loo_adapter_supports_arviz_one_and_legacy_fields(self) -> None:
        current = SimpleNamespace(
            elpd=-12.5,
            se=1.25,
            p=2.5,
            elpd_i=np.array([-4.0, -8.5]),
            pareto_k=np.array([0.2, 0.8]),
        )
        legacy = {
            "elpd_loo": -12.5,
            "se": 1.25,
            "p_loo": 2.5,
            "loo_i": np.array([-4.0, -8.5]),
            "pareto_k": np.array([0.2, 0.8]),
        }
        for result in (extract_loo_result(current), extract_loo_result(legacy)):
            self.assertEqual(result["elpd_loo"], -12.5)
            self.assertEqual(result["p_loo"], 2.5)
            np.testing.assert_array_equal(result["loo_i"], [-4.0, -8.5])
            np.testing.assert_array_equal(result["pareto_k"], [0.2, 0.8])

    def test_exact_reloo_uses_current_arviz_pointwise_fields(self) -> None:
        graph = SpatialGraph(
            spatial_ids=("1", "2"),
            adjacency=np.array([[0, 1], [1, 0]]),
            scaling_factor=1.0,
        )
        data = BayesianModelData(
            spatial_ids=("1", "2"),
            spatial_names=("one", "two"),
            observed=np.array([95, 105]),
            expected=np.array([100.0, 100.0]),
            exposure=np.array([-1.0, 1.0]),
            covariates=np.array([[-1.0], [1.0]]),
            covariate_names=("nse",),
            exposure_mean=0.0,
            exposure_sd=1.0,
            outcome="synthetic",
            exposure_name="pm25_hist",
            window="synthetic",
        )
        loo_result = SimpleNamespace(
            elpd=-5.0,
            se=0.5,
            p=1.0,
            elpd_i=np.array([-2.0, -3.0]),
            pareto_k=np.array([0.8, 0.2]),
        )
        fake_az = SimpleNamespace(loo=lambda *_args, **_kwargs: loo_result)
        refit = SimpleNamespace(
            posterior={
                "mu": np.full((1, 4, 2), 100.0),
                "alpha": np.full((1, 4), 20.0),
            }
        )
        config = {
            "pareto_k_reloo_threshold": 0.7,
            "draws": 4,
            "tune": 4,
            "chains": 1,
            "target_accept": 0.9,
        }
        with (
            patch(
                "exposome.hospitalization_inference.require_bayesian_dependencies",
                return_value=(None, fake_az, None),
            ),
            patch(
                "exposome.hospitalization_inference.build_pymc_nb_model",
                return_value=object(),
            ),
            patch(
                "exposome.hospitalization_inference.sample_pymc_model",
                return_value=refit,
            ),
        ):
            result = psis_loo_with_exact_refits(
                object(),
                data,
                graph,
                config,
                spatial=False,
                include_exposure=True,
                rho_prior=None,
                seed=3,
                progressbar=False,
            )
        self.assertEqual(result["reloo_count"], 1)
        self.assertEqual(result["reloo"][0]["spatial_id"], "1")
        self.assertTrue(np.isfinite(result["elpd_loo"]))

    @unittest.skipUnless(
        importlib.util.find_spec("h5netcdf") is not None,
        "optional NetCDF backend is not installed",
    )
    def test_atomic_trace_sidecar_resume_and_fingerprint_guard(self) -> None:
        import xarray as xr

        posterior = xr.Dataset(
            {"intercept": (("chain", "draw"), np.ones((1, 3)))}
        )
        idata = xr.DataTree.from_dict({"/posterior": posterior})
        task = ModelTask(
            phase="primary",
            model_id="primary-test",
            outcome="cardiovascular",
            exposure="pm25_hist",
            model_name="nb_nonspatial_exposure",
        )
        diagnostics = {
            "diagnostics_passed": True,
            "chains": 1,
            "draws": 3,
            "tune": 2,
            "target_accept": 0.9,
            "attempt": 1,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            store = InferenceRunStore(output_dir, "fingerprint-a")
            store.save_record(
                task,
                idata,
                diagnostics=diagnostics,
                effect=None,
                extras={"test": True},
                required_variables=["intercept"],
            )
            trace = store.trace_path(task)
            self.assertTrue(trace.exists())
            self.assertFalse(trace.with_suffix(".nc.partial").exists())
            trace.with_suffix(".nc.partial").write_text("interrupted")
            record = store.reusable_record(
                task, resume=True, rerun_failed=False
            )
            self.assertEqual(record["status"], "ok")
            self.assertFalse(trace.with_suffix(".nc.partial").exists())
            other = InferenceRunStore(output_dir, "fingerprint-b")
            with self.assertRaises(InferenceConfigMismatch):
                other.reusable_record(task, resume=True, rerun_failed=False)

    def test_orphan_trace_is_never_silently_reused(self) -> None:
        task = ModelTask(
            phase="primary",
            model_id="orphan-test",
            outcome="cardiovascular",
            exposure="pm25_hist",
            model_name="nb_nonspatial_exposure",
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = InferenceRunStore(Path(temporary), "fingerprint")
            trace = store.trace_path(task)
            trace.parent.mkdir(parents=True)
            trace.write_bytes(b"not-a-trace")
            with self.assertRaises(InferenceStateError):
                store.reusable_record(task, resume=True, rerun_failed=False)


@unittest.skipUnless(
    importlib.util.find_spec("pymc") is not None and importlib.util.find_spec("arviz") is not None,
    "optional spatial dependencies are not installed",
)
class BayesianConstructionTest(unittest.TestCase):
    def setUp(self) -> None:
        adjacency = np.zeros((52, 52), dtype=int)
        for index in range(52):
            adjacency[index, (index + 1) % 52] = 1
            adjacency[(index + 1) % 52, index] = 1
        self.graph = SpatialGraph(
            tuple(str(value) for value in range(52)),
            adjacency,
            icar_scaling_factor(adjacency),
        )
        rng = np.random.default_rng(51)
        exposure = np.linspace(-1.5, 1.5, 52)
        expected = np.repeat(100.0, 52)
        mu = expected * np.exp(0.35 * exposure)
        alpha = 20.0
        observed = rng.negative_binomial(alpha, alpha / (alpha + mu))
        self.data = BayesianModelData(
            spatial_ids=self.graph.spatial_ids,
            spatial_names=self.graph.spatial_ids,
            observed=observed,
            expected=expected,
            exposure=exposure,
            covariates=np.column_stack([rng.normal(size=52)]),
            covariate_names=("nse",),
            exposure_mean=0.0,
            exposure_sd=1.0,
            outcome="synthetic",
            exposure_name="known_effect",
            window="synthetic",
        )
        self.config = {
            "coefficient_sd": 0.5,
            "log_alpha_mean": float(np.log(20)),
            "log_alpha_sd": 1.5,
            "spatial_sigma_tail_probability_above_one": 0.01,
            "rho_prior": [0.5, 0.5],
        }

    def test_constructs_nb_bym2_on_52_node_graph(self) -> None:
        model = build_pymc_nb_model(
            self.data,
            self.graph,
            self.config,
            spatial=True,
            include_exposure=True,
        )
        names = {variable.name for variable in model.free_RVs}
        self.assertTrue({"intercept", "beta", "gamma", "alpha", "theta", "phi", "sigma", "rho"}.issubset(names))

    def test_arviz_bfmi_datatree_is_numpy_compatible(self) -> None:
        _, az, _ = require_bayesian_dependencies()
        idata = az.from_dict(
            {
                "sample_stats": {
                    "energy": np.array(
                        [
                            [1.0, 2.0, 1.5, 2.2, 2.8, 2.1, 1.8, 2.4],
                            [0.8, 1.2, 1.7, 1.5, 2.0, 2.3, 2.1, 1.9],
                        ]
                    )
                }
            }
        )
        values = np.asarray(az.bfmi(idata))
        self.assertEqual(values.shape, (1, 2))
        self.assertTrue(np.isfinite(values).all())

    def test_diagnostic_array_accepts_xarray_and_unnamed_dataarray(self) -> None:
        import xarray as xr

        unnamed = xr.DataArray([0.71, 0.83], dims=("chain",))
        named = unnamed.rename("bfmi")
        dataset = named.to_dataset()
        np.testing.assert_allclose(_diagnostic_numeric_array(unnamed), [0.71, 0.83])
        np.testing.assert_allclose(_diagnostic_numeric_array(named), [0.71, 0.83])
        np.testing.assert_allclose(
            _diagnostic_numeric_array(dataset), [[0.71, 0.83]]
        )
        np.testing.assert_allclose(
            _diagnostic_numeric_array(np.array([0.71, 0.83])), [0.71, 0.83]
        )

    @unittest.skipUnless(
        os.environ.get("EXPOSOME_RUN_BAYESIAN_TESTS") == "1",
        "set EXPOSOME_RUN_BAYESIAN_TESTS=1 for reduced MCMC recovery",
    )
    def test_reduced_mcmc_recovers_positive_effect(self) -> None:
        model = build_pymc_nb_model(
            self.data,
            self.graph,
            self.config,
            spatial=True,
            include_exposure=True,
        )
        idata = sample_pymc_model(
            model,
            draws=250,
            tune=250,
            chains=2,
            target_accept=0.95,
            seed=19,
            progressbar=False,
        )
        summary = summarize_bayesian_effect(
            idata, self.data, rope_rr=[0.95, 1.05]
        )
        diagnostics = bayesian_diagnostics(
            idata,
            {
                "max_divergences": 100,
                "max_rhat": 2,
                "min_ess_bulk": 1,
                "min_ess_tail": 1,
                "min_bfmi": 0,
            },
        )
        loo_config = {
            **self.config,
            "draws": 250,
            "tune": 250,
            "chains": 2,
            "target_accept": 0.95,
            # Exercise ArviZ's current pointwise result without adding exact
            # refits to this deliberately reduced construction smoke test.
            "pareto_k_reloo_threshold": 10.0,
        }
        loo = psis_loo_with_exact_refits(
            idata,
            self.data,
            self.graph,
            loo_config,
            spatial=True,
            include_exposure=True,
            rho_prior=None,
            seed=19,
            progressbar=False,
        )
        self.assertGreater(summary["rr_per_sd"], 1.0)
        self.assertGreater(summary["probability_rr_gt_1"], 0.9)
        self.assertIn("max_rhat", diagnostics)
        self.assertEqual(loo["reloo_count"], 0)
        self.assertTrue(np.isfinite(loo["elpd_loo"]))


if __name__ == "__main__":
    unittest.main()

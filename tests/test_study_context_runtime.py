from __future__ import annotations

from unittest.mock import patch
import unittest

from exposome import config
from exposome.settings import resolve_settings
from exposome.studies import load_study


class StudyContextRuntimeTests(unittest.TestCase):
    def test_settings_are_composed_once_and_layer_inputs_are_absolute(self) -> None:
        context = load_study("santiago_communes")
        with patch("exposome.settings.resolve_settings", wraps=resolve_settings) as resolver:
            first = context.settings
            second = context.settings
        self.assertIs(first, second)
        resolver.assert_called_once_with(context)
        inputs = context.layer_inputs("sleep_context")
        self.assertTrue(inputs["master_csv"].is_absolute())

    def test_legacy_loader_reads_injected_resolved_mapping_without_disk_reload(self) -> None:
        context = load_study("buenos_aires_comunas")
        resolved = context.resolved_config(spatial_units=context.spatial_units)
        with config.resolved_config_scope(context.study.id, resolved):
            loaded = config.load_config(context.study.id)
        self.assertEqual(loaded["study_id"], context.study.id)
        self.assertEqual(loaded["crs"]["metric"], context.metric_crs)
        self.assertIsNot(loaded, resolved)
        # Regression: the runner-injected mapping must apply the same
        # post-processing as ``config.load_config``, or layers degrade silently
        # in the runner. Two gaps shipped this way (see incidentes-multiciudad.md):
        #   * ``spatial_units`` dict absent -> greenspace_access/healthcare lose
        #     the per-unit bbox and time out on large rural units.
        #   * ``population.country`` left at the ``CHL`` layer default ->
        #     pop-weighting degenerates to the area mean for non-Chile cities.
        self.assertIsInstance(resolved.get("spatial_units"), dict)
        self.assertEqual(
            resolved["alan"]["population"]["country"], context.location.country_code3
        )
        self.assertNotEqual(resolved["alan"]["population"]["country"], "CHL")

    def test_resolved_config_matches_load_config_on_portable_keys(self) -> None:
        """The runner-injected mapping must not diverge from ``config.load_config``
        on any portable (science-affecting) key.

        The runner injects ``resolved_config`` instead of letting
        ``config.load_config`` resolve the study, so every portable
        post-process (population country, hemisphere summer, healthcare paths,
        spatial_units dict) must be replicated. Whole classes of silent
        degradation shipped from single missing steps -- see
        docs/knowledge/runbooks/incidentes-multiciudad.md. This guard fails if a
        new post-process is added to one path but not the other.
        """
        # Path-mechanism / identity keys that legitimately differ (the runner
        # passes I/O paths as kwargs, not via cfg). NOT science-affecting.
        allow = {
            "aoi_path", "mode", "name", "spatial_unit_type", "spatial_units",
            "spatial_path", "spatial_id_column", "spatial_name_column",
            "crs.geographic", "crs.metric",
        }

        def flat(d: dict, prefix: str = "") -> dict:
            out: dict = {}
            for key, value in (d or {}).items():
                composite = f"{prefix}{key}"
                if isinstance(value, dict):
                    out.update(flat(value, composite + "."))
                else:
                    out[composite] = value
            return out

        def allowed(key: str) -> bool:
            return (
                key in allow
                or key.startswith("outputs.")
                or key.startswith("study_paths.")
            )

        missing = object()
        # A non-native non-Chile study (population + summer + healthcare) and a
        # native non-Chile study (population + summer via the early-return path).
        for study_id in ("buenos_aires_comunas", "caba_native"):
            with self.subTest(study=study_id):
                context = load_study(study_id)
                reference = config.load_config(study_id)
                if context.is_native:
                    injected = context.resolved_config()
                else:
                    injected = context.resolved_config(
                        spatial_units=context.spatial_units
                    )
                flat_ref, flat_run = flat(reference), flat(injected)
                divergent = sorted(
                    key
                    for key in set(flat_ref) | set(flat_run)
                    if flat_ref.get(key, missing) != flat_run.get(key, missing)
                    and not allowed(key)
                )
                self.assertEqual(
                    divergent,
                    [],
                    f"{study_id}: portable keys diverge from config.load_config: "
                    + ", ".join(
                        f"{k} (load_config={flat_ref.get(k, missing)!r} != "
                        f"runner={flat_run.get(k, missing)!r})"
                        for k in divergent
                    ),
                )


if __name__ == "__main__":
    unittest.main()

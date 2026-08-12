from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.distributions import (  # noqa: E402
    ad_ksample,
    count_outliers,
    ecdf_points,
    ks_two_sample,
    robust_scale_double_mad,
    shared_histogram,
    shared_histogram_log,
)


class RobustScaleDoubleMadTests(unittest.TestCase):
    def test_symmetric_data_gives_equal_sigmas(self) -> None:
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])
        scale = robust_scale_double_mad(values, physical_floor=None)
        self.assertEqual(scale.median, 5.0)
        self.assertAlmostEqual(scale.sigma_lower, scale.sigma_upper, places=6)
        self.assertFalse(scale.scale_undefined_lower)
        self.assertFalse(scale.scale_undefined_upper)

    def test_right_skewed_data_has_wider_upper_sigma(self) -> None:
        # Dense cluster near the median plus a long right tail (like ALAN
        # radiance): the whole point of the double-MAD is that the upper
        # sigma should reflect that tail without being dragged down by it
        # being averaged against the tight lower half.
        values = np.concatenate([np.full(20, 10.0) + np.arange(20) * 0.1, [50, 60, 80, 89]])
        scale = robust_scale_double_mad(values, physical_floor=0.0)
        self.assertGreater(scale.sigma_upper, scale.sigma_lower)
        self.assertGreaterEqual(scale.band_low, 0.0)

    def test_physical_floor_clips_band_low(self) -> None:
        values = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 50.0])
        scale = robust_scale_double_mad(values, physical_floor=0.0)
        self.assertGreaterEqual(scale.band_low, 0.0)

    def test_mad_zero_falls_back_to_iqr(self) -> None:
        # More than half the lower side is identical to the median -> MAD=0
        # on that side; IQR fallback should kick in instead of a zero-width
        # (degenerate) band.
        values = np.array([5.0] * 10 + [5.1, 5.2, 20.0, 30.0, 40.0])
        scale = robust_scale_double_mad(values)
        self.assertFalse(scale.scale_undefined_lower)
        self.assertGreater(scale.sigma_lower, 0.0)

    def test_all_identical_values_flags_scale_undefined_both_sides(self) -> None:
        values = np.array([7.0] * 20)
        scale = robust_scale_double_mad(values)
        self.assertTrue(scale.scale_undefined_lower)
        self.assertTrue(scale.scale_undefined_upper)

    def test_empty_array_does_not_raise(self) -> None:
        scale = robust_scale_double_mad(np.array([]))
        self.assertTrue(scale.scale_undefined_lower)
        self.assertTrue(scale.scale_undefined_upper)
        self.assertTrue(np.isnan(scale.median))

    def test_json_serializable(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 100.0])
        scale = robust_scale_double_mad(values)
        json.dumps(scale.to_json())  # must not raise


class CountOutliersTests(unittest.TestCase):
    def test_no_outliers_in_tight_cluster(self) -> None:
        # Symmetric around the median on both sides so neither MAD half
        # degenerates to (near) zero -- a degenerate one-sided MAD from
        # heavy ties at the median is exercised separately below.
        values = np.array([9.9, 9.95, 10.0, 10.05, 10.1])
        scale = robust_scale_double_mad(values, physical_floor=None)
        self.assertEqual(count_outliers(values, scale), 0)

    def test_flags_far_outlier(self) -> None:
        values = np.concatenate([np.full(30, 10.0) + np.linspace(-0.1, 0.1, 30), [1000.0]])
        scale = robust_scale_double_mad(values, physical_floor=None)
        self.assertGreaterEqual(count_outliers(values, scale), 1)

    def test_never_filters_the_sample(self) -> None:
        # count_outliers is purely informational: the input array length is
        # untouched regardless of how many are flagged.
        values = np.array([1.0, 2.0, 3.0, 1000.0])
        original_len = len(values)
        scale = robust_scale_double_mad(values, physical_floor=None)
        count_outliers(values, scale)
        self.assertEqual(len(values), original_len)


class SharedHistogramTests(unittest.TestCase):
    def test_density_integrates_to_approximately_one_including_overflow(self) -> None:
        rng = np.random.default_rng(0)
        city_a = rng.normal(loc=10, scale=2, size=2000)
        city_b = rng.normal(loc=12, scale=3, size=1500)
        result = shared_histogram({"a": city_a, "b": city_b}, max_bins=40)
        widths = np.diff(result.bins)
        for city, n in (("a", city_a.size), ("b", city_b.size)):
            density = np.array(result.density_by_city[city])
            in_range_mass = float(np.sum(density * widths))
            overflow_mass = (
                result.overflow_low_by_city[city] + result.overflow_high_by_city[city]
            ) / n
            self.assertAlmostEqual(in_range_mass + overflow_mass, 1.0, delta=0.05)

    def test_bin_count_is_capped(self) -> None:
        rng = np.random.default_rng(1)
        huge = rng.normal(size=80000)
        result = shared_histogram({"a": huge}, max_bins=60)
        self.assertLessEqual(len(result.bins) - 1, 60)

    def test_extreme_outlier_does_not_collapse_the_main_mass(self) -> None:
        # A single far outlier must not stretch the visible range so much
        # that the dense cluster becomes a single bin.
        values = np.concatenate([np.linspace(9, 11, 500), [10000.0]])
        result = shared_histogram({"a": values}, max_bins=60)
        self.assertLess(result.display_range[1], 1000)
        self.assertGreaterEqual(result.overflow_high_by_city["a"], 1)

    def test_empty_input_does_not_raise(self) -> None:
        result = shared_histogram({})
        self.assertEqual(result.density_by_city, {})


class EcdfPointsTests(unittest.TestCase):
    def test_monotonic_and_bounded(self) -> None:
        rng = np.random.default_rng(2)
        values = rng.normal(size=5000)
        result = ecdf_points(values, max_points=100)
        ys = np.array(result.y)
        self.assertTrue(np.all(np.diff(ys) >= -1e-12))
        self.assertGreater(ys[0], 0.0)
        self.assertAlmostEqual(ys[-1], 1.0, places=6)

    def test_preserves_extremes_when_subsampled(self) -> None:
        values = np.arange(1000, dtype=float)
        result = ecdf_points(values, max_points=50)
        self.assertEqual(result.x[0], 0.0)
        self.assertEqual(result.x[-1], 999.0)

    def test_small_sample_not_subsampled(self) -> None:
        values = np.array([1.0, 2.0, 3.0])
        result = ecdf_points(values, max_points=250)
        self.assertEqual(len(result.x), 3)

    def test_empty_input(self) -> None:
        result = ecdf_points(np.array([]))
        self.assertEqual(result.x, [])
        self.assertEqual(result.y, [])


class KsTwoSampleTests(unittest.TestCase):
    def test_matches_hand_calculable_small_case(self) -> None:
        # F_a jumps at 1,2,3,4,5 (each 0.2); F_b jumps at 3,4,5,6,7.
        # Max gap occurs at x=2: F_a(2)=0.4, F_b(2)=0 -> D=0.4.
        a = np.array([1, 2, 3, 4, 5])
        b = np.array([3, 4, 5, 6, 7])
        result = ks_two_sample(a, b)
        self.assertAlmostEqual(result.d, 0.4, places=6)
        self.assertTrue(0.0 <= result.p <= 1.0)

    def test_identical_samples_give_zero_statistic(self) -> None:
        a = np.array([1.0, 2.0, 3.0, 4.0])
        result = ks_two_sample(a, a.copy())
        self.assertAlmostEqual(result.d, 0.0)
        self.assertAlmostEqual(result.p, 1.0)

    def test_empty_sample_returns_nan(self) -> None:
        result = ks_two_sample(np.array([]), np.array([1.0, 2.0]))
        self.assertTrue(np.isnan(result.d))


class AdKsampleTests(unittest.TestCase):
    def test_returns_none_for_single_sample(self) -> None:
        self.assertIsNone(ad_ksample([np.array([1.0, 2.0, 3.0])]))

    def test_finite_result_for_two_samples(self) -> None:
        rng = np.random.default_rng(3)
        a = rng.normal(size=50)
        b = rng.normal(loc=2, size=50)
        result = ad_ksample([a, b])
        self.assertIsNotNone(result)
        self.assertTrue(np.isfinite(result.a2))
        self.assertTrue(0.0 <= result.p <= 1.0)

    def test_p_capped_flag_on_clearly_identical_distributions(self) -> None:
        rng = np.random.default_rng(4)
        a = rng.normal(size=30)
        b = rng.normal(size=30)
        result = ad_ksample([a, b])
        # Not asserting a specific p here (random), only that the flag is a
        # bool and the result is JSON-serializable.
        self.assertIsInstance(result.p_capped, bool)
        json.dumps(result.to_json())

    def test_cap_side_floor_for_clearly_different(self) -> None:
        # Two well-separated large samples: p is clipped at the table floor,
        # meaning "clearly different" -- the side the renderer must not confuse
        # with the ceiling case.
        rng = np.random.default_rng(7)
        a = rng.normal(loc=0, size=400)
        b = rng.normal(loc=6, size=400)
        result = ad_ksample([a, b])
        self.assertTrue(result.p_capped)
        self.assertEqual(result.p_cap_side, "floor")

    def test_cap_side_ceiling_for_indistinguishable(self) -> None:
        # Two identical small samples: p is clipped at the table ceiling,
        # meaning "indistinguishable" -- the OPPOSITE verdict from the floor.
        a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = ad_ksample([a, a.copy()])
        self.assertEqual(result.p_cap_side, "ceiling")

    def test_degenerate_constant_pooled_sample_returns_none(self) -> None:
        # Both cities report the exact same constant value for every unit
        # (e.g. a boolean flag column) -- scipy itself refuses to run
        # anderson_ksamp on fewer than 2 distinct pooled values; we should
        # return None instead of propagating scipy's ValueError.
        a = np.array([1.0] * 52)
        b = np.array([1.0] * 55)
        self.assertIsNone(ad_ksample([a, b]))

    def test_supports_k_greater_than_two(self) -> None:
        rng = np.random.default_rng(5)
        samples = [rng.normal(size=40), rng.normal(loc=1, size=40), rng.normal(loc=2, size=40)]
        result = ad_ksample(samples)
        self.assertIsNotNone(result)
        self.assertTrue(np.isfinite(result.a2))


class SharedHistogramLogTest(unittest.TestCase):
    def test_bins_are_increasing_and_positive(self) -> None:
        rng = np.random.default_rng(11)
        values = {
            "a": rng.lognormal(mean=1.0, sigma=1.0, size=500),
            "b": rng.lognormal(mean=2.0, sigma=0.8, size=500),
        }
        result = shared_histogram_log(values, max_bins=30)
        self.assertGreaterEqual(len(result.bins), 2)
        self.assertTrue(all(b > 0 for b in result.bins))
        self.assertTrue(all(x < y for x, y in zip(result.bins, result.bins[1:])))

    def test_density_integrates_to_one_in_log_space(self) -> None:
        rng = np.random.default_rng(12)
        values = {"a": rng.lognormal(size=2000), "b": rng.lognormal(mean=1.0, size=2000)}
        result = shared_histogram_log(values, max_bins=40)
        log_edges = np.log10(np.array(result.bins))
        widths = np.diff(log_edges)
        for city, density in result.density_by_city.items():
            integral = float(np.sum(np.array(density) * widths))
            self.assertAlmostEqual(integral, 1.0, places=6, msg=city)

    def test_nonpositive_values_excluded_and_counted(self) -> None:
        values = {"a": np.array([0.0, -1.0, 1.0, 10.0, 100.0])}
        result = shared_histogram_log(values, max_bins=10)
        # Two non-positive values (0 and -1) are excluded from log10 but tallied.
        self.assertEqual(result.n_nonpositive_by_city["a"], 2)
        self.assertTrue(all(b > 0 for b in result.bins))

    def test_all_nonpositive_returns_empty_bins(self) -> None:
        result = shared_histogram_log({"a": np.array([0.0, -3.0, -1.0])}, max_bins=10)
        self.assertEqual(result.bins, [])
        self.assertEqual(result.density_by_city, {})
        self.assertEqual(result.n_nonpositive_by_city["a"], 3)

    def test_json_serializable(self) -> None:
        values = {"a": np.array([1.0, 2.0, 5.0, 9.0, 40.0])}
        json.dumps(shared_histogram_log(values).to_json())


if __name__ == "__main__":
    unittest.main()

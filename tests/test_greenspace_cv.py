"""Tests for greenspace_cv ExG computation.

All tests run offline — no tile downloads or OSM calls. We use synthetic
numpy arrays to verify the ExG formula, Otsu threshold, and green-dominance filter.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.greenspace_cv import _otsu_threshold, detect_vegetation_exg  # noqa: E402


def _solid_rgb(r: int, g: int, b: int, h: int = 64, w: int = 64) -> np.ndarray:
    """Return an HxWx3 uint8 image filled with a single color."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[..., 0] = r
    img[..., 1] = g
    img[..., 2] = b
    return img


def _checkerboard(h: int = 64, w: int = 64) -> np.ndarray:
    """Half green (0,200,0), half grey (128,128,128)."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, : w // 2] = [0, 200, 0]   # left half: green
    img[:, w // 2 :] = [128, 128, 128]  # right half: grey
    return img


class TestOtsuThreshold(unittest.TestCase):
    def test_bimodal_array_returns_value_between_modes(self) -> None:
        low = np.full(500, -0.1)
        high = np.full(500, 0.5)
        x = np.concatenate([low, high])
        thr = _otsu_threshold(x)
        self.assertGreater(thr, -0.1)
        self.assertLess(thr, 0.5)

    def test_empty_array_returns_zero(self) -> None:
        self.assertEqual(_otsu_threshold(np.array([])), 0.0)

    def test_constant_array_returns_finite_value(self) -> None:
        x = np.full(100, 0.3)
        thr = _otsu_threshold(x)
        # Otsu on a constant array has no bimodal structure; result is finite (not NaN/inf)
        self.assertTrue(np.isfinite(thr))


class TestDetectVegetationExg(unittest.TestCase):
    def test_pure_green_image_is_mostly_detected(self) -> None:
        img = _solid_rgb(0, 200, 0)  # saturated green
        mask, thr = detect_vegetation_exg(img)
        # Most pixels should be green
        self.assertGreater(mask.mean(), 0.5)

    def test_grey_image_produces_no_vegetation(self) -> None:
        img = _solid_rgb(128, 128, 128)  # neutral grey, ExG ≈ 0
        mask, thr = detect_vegetation_exg(img)
        # Grey has equal R=G=B so ExG = 0; should be below threshold
        self.assertLess(mask.mean(), 0.1)

    def test_blue_dominant_image_is_not_green(self) -> None:
        img = _solid_rgb(0, 0, 200)  # pure blue — fails G>=R and G>=B
        mask, thr = detect_vegetation_exg(img)
        self.assertEqual(mask.sum(), 0)

    def test_red_dominant_image_is_not_green(self) -> None:
        img = _solid_rgb(200, 0, 0)  # pure red — fails G>=R
        mask, thr = detect_vegetation_exg(img)
        self.assertEqual(mask.sum(), 0)

    def test_checkerboard_detects_only_green_half(self) -> None:
        img = _checkerboard(h=64, w=64)
        mask, thr = detect_vegetation_exg(img)
        left_pct = mask[:, :32].mean()
        right_pct = mask[:, 32:].mean()
        self.assertGreater(left_pct, right_pct)

    def test_threshold_is_above_minimum_floor(self) -> None:
        img = _solid_rgb(0, 200, 0)
        _, thr = detect_vegetation_exg(img, min_threshold=0.05)
        self.assertGreaterEqual(thr, 0.05)

    def test_returns_boolean_mask(self) -> None:
        img = _checkerboard()
        mask, _ = detect_vegetation_exg(img)
        self.assertEqual(mask.dtype, bool)
        self.assertEqual(mask.shape, img.shape[:2])

    def test_exg_formula_values_are_in_expected_range(self) -> None:
        # ExG for pure green (0,1,0) in chromatic space:
        # s = 0+1+0+eps ≈ 1; ExG = 2*(1/1) - 0 - 0 = 2
        # For normalized: ExG ∈ [-1, 2]
        img = _solid_rgb(0, 255, 0)
        a = img.astype(float)
        R, G, B = a[..., 0], a[..., 1], a[..., 2]
        s = R + G + B + 1e-6
        exg = 2 * (G / s) - (R / s) - (B / s)
        self.assertTrue(np.all(exg >= -1.0))
        self.assertTrue(np.all(exg <= 2.0))


if __name__ == "__main__":
    unittest.main()

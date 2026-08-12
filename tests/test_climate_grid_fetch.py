from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from exposome.climate.fetch_grid_openmeteo import ensure_grid_daily
from exposome.climate.fetch_era5land import (
    DEFAULT_BANDS,
    _cache_has_required_values,
    _complete_cached_months,
    _parse_features,
)


class ClimateGridFetchTest(unittest.TestCase):
    def test_existing_cache_avoids_network(self) -> None:
        points = pd.DataFrame(
            {"location_id": [0], "source": ["grid"], "lat": [-34.6], "lon": [-58.4]}
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "climate_heat_grid_daily_2024.csv"
            cache.write_text("location_id,date\n0,2024-01-01\n", encoding="utf-8")
            with patch(
                "exposome.climate.fetch_grid_openmeteo.requests.get",
                side_effect=AssertionError("network should not be used"),
            ):
                result = ensure_grid_daily(points, year=2024, cache_dir=Path(tmp))
        self.assertEqual(result.name, "climate_heat_grid_daily_2024.csv")

    def test_missing_point_columns_fail_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "missing columns"):
                ensure_grid_daily(
                    pd.DataFrame({"location_id": [0]}),
                    year=2024,
                    cache_dir=Path(tmp),
                )

    def test_partial_resume_only_fetches_missing_ids(self) -> None:
        """A pre-existing partial.csv must be resumed, not re-fetched from id 0."""
        points = pd.DataFrame(
            {
                "location_id": [0, 1, 2],
                "source": ["grid", "grid", "grid"],
                "lat": [-34.6, -34.7, -34.8],
                "lon": [-58.4, -58.5, -58.6],
            }
        )

        def fake_get(url, params=None, timeout=None):
            n = len(params["latitude"].split(","))
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status = lambda: None
            response.json.return_value = [
                {
                    "daily": {
                        "time": ["2024-01-01"],
                        "temperature_2m_mean": [10.0],
                        "temperature_2m_max": [15.0],
                        "temperature_2m_min": [5.0],
                        "apparent_temperature_max": [14.0],
                        "precipitation_sum": [0.0],
                    }
                }
                for _ in range(n)
            ]
            return response

        mock_get = MagicMock(side_effect=fake_get)
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            partial = cache_dir / "climate_heat_grid_daily_2024.partial.csv"
            # location_id 0 already fetched in a prior (interrupted) run.
            pd.DataFrame(
                [
                    {
                        "location_id": 0,
                        "source": "grid",
                        "lat": -34.6,
                        "lon": -58.4,
                        "date": "2024-01-01",
                        "temperature_2m_mean": 10.0,
                        "temperature_2m_max": 15.0,
                        "temperature_2m_min": 5.0,
                        "apparent_temperature_max": 14.0,
                        "precipitation_sum": 0.0,
                    }
                ]
            ).to_csv(partial, index=False)

            with patch(
                "exposome.climate.fetch_grid_openmeteo.requests.get", mock_get
            ):
                result = ensure_grid_daily(
                    points,
                    year=2024,
                    cache_dir=cache_dir,
                    chunk_size=2,
                    request_sleep_s=0,
                    retries=1,
                )

            # Only ids 1 and 2 were missing; chunk_size=2 fits them in one
            # request, so the already-done id 0 must not trigger a second call.
            self.assertEqual(mock_get.call_count, 1)
            final = pd.read_csv(result)
            self.assertEqual(set(final["location_id"].unique()), {0, 1, 2})
            self.assertFalse(partial.exists())


class Era5LandCacheTest(unittest.TestCase):
    def test_partial_month_requires_every_day_and_consistent_pixels(self) -> None:
        rows = []
        for day in range(1, 32):
            for pixel_id in ("p1", "p2"):
                rows.append(
                    {
                        "pixel_id": pixel_id,
                        "date": f"2024-01-{day:02d}",
                        **{band: 1.0 for band in DEFAULT_BANDS},
                    }
                )
        self.assertEqual(_complete_cached_months(pd.DataFrame(rows), DEFAULT_BANDS, 2024), {1})
        self.assertEqual(
            _complete_cached_months(pd.DataFrame(rows[:-1]), DEFAULT_BANDS, 2024), set()
        )

    def test_sample_parser_reads_the_band_property(self) -> None:
        rows = _parse_features(
            {
                "features": [
                    {
                        "geometry": {"coordinates": [-46.6, -23.5]},
                        "properties": {
                            "date": "2024-01-01",
                            "temperature_2m": 298.15,
                        },
                    }
                ]
            },
            "temperature_2m",
        )
        self.assertEqual(rows[0]["temperature_2m"], 298.15)

    def test_all_nan_annual_cache_is_rejected(self) -> None:
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")
        invalid = pd.DataFrame(
            {
                "pixel_id": ["p1"] * 12,
                "lon": [-46.6] * 12,
                "lat": [-23.5] * 12,
                "date": dates,
                "temperature_2m_mean": [float("nan")] * 12,
                "temperature_2m_min": [float("nan")] * 12,
                "temperature_2m_max": [float("nan")] * 12,
                "dewpoint_temperature_2m": [float("nan")] * 12,
                "total_precipitation_sum": [float("nan")] * 12,
            }
        )
        self.assertFalse(_cache_has_required_values(invalid, DEFAULT_BANDS))

    def test_complete_annual_cache_is_accepted(self) -> None:
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")
        valid = pd.DataFrame(
            {
                "pixel_id": ["p1"] * 12,
                "lon": [-46.6] * 12,
                "lat": [-23.5] * 12,
                "date": dates,
                "temperature_2m_mean": [20.0] * 12,
                "temperature_2m_min": [15.0] * 12,
                "temperature_2m_max": [25.0] * 12,
                "dewpoint_temperature_2m": [12.0] * 12,
                "total_precipitation_sum": [1.0] * 12,
            }
        )
        self.assertTrue(_cache_has_required_values(valid, DEFAULT_BANDS))


if __name__ == "__main__":
    unittest.main()

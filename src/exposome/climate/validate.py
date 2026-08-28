"""Validate downscaled climate predictions against DMC/SINCA stations.

Metrics:
- Mean Bias Error (MBE)
- Root Mean Square Error (RMSE)
- Mean Absolute Error (MAE)
- R²
- Spatial correlation
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def validate_predictions(
    pred_df: pd.DataFrame,
    obs_df: pd.DataFrame,
    pred_col: str = "tmax_pred",
    obs_col: str = "tmax_obs",
    station_col: str = "station_id",
) -> dict[str, float]:
    """Compute validation metrics.

    Parameters
    ----------
    pred_df, obs_df : pd.DataFrame
        Predictions and observations (aligned by station/date).

    Returns
    -------
    dict
        mbe, rmse, mae, r2, n.
    """
    merged = pred_df.merge(obs_df, on=[station_col, "date"], how="inner")
    y_pred = merged[pred_col]
    y_obs = merged[obs_col]

    mbe = float((y_pred - y_obs).mean())
    rmse = float(np.sqrt(mean_squared_error(y_obs, y_pred)))
    mae = float(mean_absolute_error(y_obs, y_pred))
    r2 = float(r2_score(y_obs, y_pred))

    return {
        "mbe": round(mbe, 3),
        "rmse": round(rmse, 3),
        "mae": round(mae, 3),
        "r2": round(r2, 3),
        "n": len(merged),
    }


def plot_validation_scatter(
    pred_df: pd.DataFrame,
    obs_df: pd.DataFrame,
    out_path: Path,
    pred_col: str = "tmax_pred",
    obs_col: str = "tmax_obs",
) -> None:
    """Generate scatter plot of predicted vs observed."""
    merged = pred_df.merge(obs_df, on=["station_id", "date"], how="inner")
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(merged[obs_col], merged[pred_col], alpha=0.3, s=10)
    ax.plot([merged[obs_col].min(), merged[obs_col].max()],
            [merged[obs_col].min(), merged[obs_col].max()],
            "r--", lw=1)
    ax.set_xlabel("Observed (°C)")
    ax.set_ylabel("Predicted (°C)")
    ax.set_title("Downscaling Validation")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

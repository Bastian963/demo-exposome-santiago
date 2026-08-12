"""Shared statistics for neuro-sanitary ecological outcome comparisons."""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, pearsonr, spearmanr


def residualize(y: pd.Series, covariates: pd.DataFrame) -> pd.Series:
    """Return residuals from a linear model of ``y`` on ``covariates``."""
    mask = y.notna()
    if covariates.empty:
        return y
    for col in covariates.columns:
        mask &= covariates[col].notna()
    out = pd.Series(np.nan, index=y.index, dtype=float)
    if int(mask.sum()) < len(covariates.columns) + 3:
        return out
    X = covariates.loc[mask].astype(float).to_numpy()
    X = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X, y.loc[mask].astype(float).to_numpy(), rcond=None)
    out.loc[mask] = y.loc[mask].astype(float).to_numpy() - X @ beta
    return out


def benjamini_hochberg(p_values: pd.Series) -> pd.Series:
    """Compute Benjamini-Hochberg FDR q-values, preserving input index."""
    p = pd.to_numeric(p_values, errors="coerce")
    q = pd.Series(np.nan, index=p.index, dtype=float)
    valid = p.dropna()
    if valid.empty:
        return q

    ordered = valid.sort_values(kind="mergesort")
    m = float(len(ordered))
    ranks = np.arange(1, len(ordered) + 1, dtype=float)
    raw_q = ordered.to_numpy(dtype=float) * m / ranks
    monotone_q = np.minimum.accumulate(raw_q[::-1])[::-1]
    q.loc[ordered.index] = np.clip(monotone_q, 0.0, 1.0)
    return q


def add_fdr_q_values(
    df: pd.DataFrame,
    p_columns: list[str] | tuple[str, ...] = (
        "spearman_p",
        "pearson_p",
        "kendall_p",
        "partial_spearman_p",
    ),
) -> pd.DataFrame:
    """Add Benjamini-Hochberg q-values for each p-value column."""
    out = df.copy()
    ok = out["status"].eq("ok") if "status" in out.columns else pd.Series(True, index=out.index)
    for p_col in p_columns:
        q_col = p_col.removesuffix("_p") + "_q"
        out[q_col] = np.nan
        if p_col in out.columns:
            out.loc[ok, q_col] = benjamini_hochberg(out.loc[ok, p_col])
    return out


def _safe_corr(
    fn: Callable[[pd.Series, pd.Series], tuple[float, float] | object],
    x: pd.Series,
    y: pd.Series,
) -> tuple[float, float]:
    if len(x) < 3 or x.nunique(dropna=True) < 2 or y.nunique(dropna=True) < 2:
        return np.nan, np.nan
    result = fn(x, y)
    if isinstance(result, tuple):
        stat, pval = result
    else:
        stat = getattr(result, "statistic", np.nan)
        pval = getattr(result, "pvalue", np.nan)
    return float(stat), float(pval)


def compute_exposome_correlations(
    outcome_df: pd.DataFrame,
    master_df: pd.DataFrame,
    exposures: list[str],
    outcomes: list[str],
    covariates: list[str],
    *,
    outcome_rate_col: str,
    fallback_rate_col: str,
) -> pd.DataFrame:
    """Correlate ecological outcome rates with configured exposome features."""
    merged = outcome_df.merge(master_df, on="name", how="inner", validate="many_to_one")
    rows: list[dict[str, object]] = []

    for outcome in outcomes:
        subset = merged[merged["outcome"] == outcome].copy()
        if subset.empty:
            continue
        y = subset[outcome_rate_col]
        if y.isna().all():
            y = subset[fallback_rate_col]
        y_rank = y.rank(method="average")

        for exposure in exposures:
            if exposure not in subset.columns:
                rows.append({"outcome": outcome, "exposure": exposure, "status": "missing_exposure"})
                continue

            x = subset[exposure]
            mask = x.notna() & y.notna()
            if int(mask.sum()) < 10:
                rows.append({"outcome": outcome, "exposure": exposure, "status": f"too_few_pairs:{int(mask.sum())}"})
                continue

            x_valid = x[mask].astype(float)
            y_valid = y[mask].astype(float)
            spearman_rho, spearman_p = _safe_corr(spearmanr, x_valid, y_valid)
            pearson_r, pearson_p = _safe_corr(pearsonr, x_valid, y_valid)
            kendall_tau, kendall_p = _safe_corr(kendalltau, x_valid, y_valid)

            cov_df = subset.loc[mask, covariates].copy()
            x_res = residualize(x_valid.rank(method="average"), cov_df.rank(method="average"))
            y_res = residualize(y_rank[mask].rank(method="average"), cov_df.rank(method="average"))
            partial_mask = x_res.notna() & y_res.notna()
            partial_rho = np.nan
            partial_p = np.nan
            if int(partial_mask.sum()) >= 10:
                partial_rho, partial_p = _safe_corr(
                    spearmanr,
                    x_res[partial_mask],
                    y_res[partial_mask],
                )

            rows.append(
                {
                    "outcome": outcome,
                    "exposure": exposure,
                    "n_pairs": int(mask.sum()),
                    "spearman_rho": round(float(spearman_rho), 4) if pd.notna(spearman_rho) else np.nan,
                    "spearman_p": float(spearman_p) if pd.notna(spearman_p) else np.nan,
                    "pearson_r": round(float(pearson_r), 4) if pd.notna(pearson_r) else np.nan,
                    "pearson_p": float(pearson_p) if pd.notna(pearson_p) else np.nan,
                    "kendall_tau": round(float(kendall_tau), 4) if pd.notna(kendall_tau) else np.nan,
                    "kendall_p": float(kendall_p) if pd.notna(kendall_p) else np.nan,
                    "partial_spearman_rho": round(float(partial_rho), 4) if pd.notna(partial_rho) else np.nan,
                    "partial_spearman_p": float(partial_p) if pd.notna(partial_p) else np.nan,
                    "partial_covariates": ",".join(covariates),
                    "status": "ok",
                }
            )

    return add_fdr_q_values(pd.DataFrame(rows))

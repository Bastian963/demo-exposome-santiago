"""Food insecurity exposome layer (CASEN small-area estimates, 2020 & 2022).

Household experience of moderate-severe food insecurity (SDG indicator
2.1.2), estimated at commune level by MDSF/FAO using the Fay-Herriot
small-area estimation method applied to the FIES scale in CASEN. See
``docs/food_insecurity_methodology.md`` for the full methodology and
``data/raw/casen_food_insecurity/README.md`` for source provenance.

This layer is entirely offline: the source workbooks are versioned in the
repo (small, no API key), so no network access is required to reproduce it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from scipy.stats import spearmanr

from . import boundaries, config, demography

RAW_DIR_NAME = "casen_food_insecurity"
RAW_FILES = {
    2020: "Estimacion_Inseguridad_Alimentaria_Comunal_2020.xlsx",
    2022: "Estimacion_Inseguridad_Alimentaria_Comunal_2022.xlsx",
}

_SAE_TYPE_MAP = {
    "Directa y Sintética (Fay-Herriot)": "directa_sintetica",
    "Sintética": "sintetica",
}

_CORE_COLS = [
    "name",
    "food_insec_2020", "food_insec_ci_low_2020", "food_insec_ci_high_2020",
    "food_insec_sae_type_2020",
    "food_insec_2022", "food_insec_ci_low_2022", "food_insec_ci_high_2022",
    "food_insec_sae_type_2022",
    "food_insec_change",
]


def _read_year(raw_dir: Path, year: int, region_code: int = 13) -> pd.DataFrame:
    """Parse one year's CASEN SAE workbook, filtered to a single region.

    Returns ``[comuna_code, prevalencia_pct, ci_low, ci_high, sae_type]``.
    """
    path = raw_dir / RAW_FILES[year]
    df = pd.read_excel(path, sheet_name=0, header=2)
    df.columns = [
        "comuna_code", "region", "name_raw", "prevalencia",
        "ci_low", "ci_high", "en_muestra", "sae_type_raw",
    ]
    df["comuna_code"] = pd.to_numeric(df["comuna_code"], errors="coerce")
    df = df[df["comuna_code"].notna()].copy()
    df["comuna_code"] = df["comuna_code"].astype(int)
    lo, hi = region_code * 1000, (region_code + 1) * 1000
    df = df[(df["comuna_code"] >= lo) & (df["comuna_code"] < hi)].copy()

    for col in ("prevalencia", "ci_low", "ci_high"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    out = pd.DataFrame({
        "comuna_code": df["comuna_code"].to_numpy(),
        f"food_insec_{year}": (df["prevalencia"] * 100).round(2).to_numpy(),
        f"food_insec_ci_low_{year}": (df["ci_low"] * 100).round(2).to_numpy(),
        f"food_insec_ci_high_{year}": (df["ci_high"] * 100).round(2).to_numpy(),
        f"food_insec_sae_type_{year}": df["sae_type_raw"]
        .map(_SAE_TYPE_MAP)
        .fillna(df["sae_type_raw"])
        .to_numpy(),
    })
    return out.drop_duplicates("comuna_code").reset_index(drop=True)


def build_food_insecurity_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    raw_dir: Path | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the commune-level food insecurity layer and write CSV + GeoJSON + metadata."""
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]
    raw_dir = Path(raw_dir) if raw_dir else repo_root / "data" / "raw" / RAW_DIR_NAME

    region_code = 13
    print(f"Building food insecurity layer for {city} from {raw_dir}")

    # 1. Boundaries (geometry + canonical commune names) + code->name map.
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    code_name = demography.load_comuna_code_name_map(cache_dir, region_code=region_code)

    # 2. Parse both years, keyed by comuna_code (INE CUT).
    y2020 = _read_year(raw_dir, 2020, region_code)
    y2022 = _read_year(raw_dir, 2022, region_code)

    fi = (
        code_name.merge(y2020, on="comuna_code", how="left")
        .merge(y2022, on="comuna_code", how="left")
    )
    fi["food_insec_change"] = (
        fi["food_insec_2022"] - fi["food_insec_2020"]
    ).round(2)

    # 3. Join onto the boundary geometries by canonical name.
    df_bound = gdf_comm[["name"]].copy()
    df_bound["name_key"] = df_bound["name"].str.lower().str.strip()
    fi["name_key"] = fi["name"].str.lower().str.strip()
    df = df_bound.merge(
        fi.drop(columns=["name"]), on="name_key", how="left"
    ).drop(columns="name_key")
    df = df[_CORE_COLS].copy()

    # 4. Validate: exactly N rows, no duplicates, no NaN in core columns.
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df[_CORE_COLS].isna().any().any():
        missing = [c for c in _CORE_COLS if df[c].isna().any()]
        raise ValueError(f"Missing values in core columns: {missing}")

    # 5. Geo version.
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 6. Sanity check: correlation with the socioeconomic layer, if present.
    ses_path = out_dir / "socioeconomic_exposome_rm_santiago.csv"
    ses_check: dict[str, Any] | None = None
    if ses_path.exists():
        ses = pd.read_csv(ses_path)[["name", "nse_index_pca"]]
        merged = df.merge(ses, on="name", how="inner").dropna(
            subset=["food_insec_2022", "nse_index_pca"]
        )
        if len(merged) >= 10:
            rho, pval = spearmanr(merged["food_insec_2022"], merged["nse_index_pca"])
            ses_check = {
                "n_matched": int(len(merged)),
                "spearman_rho": round(float(rho), 4),
                "spearman_p": float(pval),
                "expected_sign": "negative (higher food insecurity <-> lower SES)",
            }

    # 7. Write outputs.
    base_name = "santiago_food_insecurity"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_rows": int(len(df)),
        "columns": df.columns.tolist(),
        "geographic_unit": "comuna (OSM admin_level=8)",
        "source": {
            "publisher": (
                "Ministerio de Desarrollo Social y Familia (MDSF), "
                "División Observatorio Social, con apoyo técnico FAO"
            ),
            "landing_page": (
                "https://observatorio.ministeriodesarrollosocial.gob.cl/"
                "inseguridad-alimentaria-2022"
            ),
            "methodological_note": str(
                raw_dir / "Nota_Metodologica_CASEN_Estimacion_de Inseguridad_Alimentaria_Comunal.pdf"
            ),
            "fao_technical_report": (
                "https://openknowledge.fao.org/items/6d37e6a2-2678-4566-bef3-125159230a60"
            ),
            "years_available": [2020, 2022],
            "years_available_note": "no other years published as of 2026-07-07",
            "indicator": (
                "SDG 2.1.2: prevalence of households in moderate-severe food "
                "insecurity, FIES scale (8 items) fit with a Rasch model, "
                "CASEN survey"
            ),
        },
        "method": (
            "Fay-Herriot small-area estimation: variance-weighted blend of a "
            "direct CASEN estimate and a synthetic estimate (regression on "
            "administrative covariates). Weight trimming (Potter 1993) applied "
            "in two Rasch passes. Confidence intervals from MSE. Regional "
            "benchmarking. Implemented with the R EMDI package. "
            "See docs/food_insecurity_methodology.md for full detail."
        ),
        "sae_inclusion_counts": {
            "2020": {"fay_herriot": 283, "synthetic_only": 41, "communes_in_casen_sample": 324},
            "2022": {"fay_herriot": 306, "synthetic_only": 29, "communes_in_casen_sample": 335},
            "note": "National totals (346 communes); RM (52 communes) has no suppression in either year.",
        },
        "rm_coverage": "all 52 RM communes have a non-missing estimate in both years",
        "relationship_to_food_environment_layer": (
            "food_insecurity measures household experience (demand side, "
            "survey-based); food_environment measures retail supply (OSM). "
            "Kept as separate exposome layers -- see docs/food_insecurity_methodology.md."
        ),
        "socioeconomic_validation": ses_check,
        "outputs": [f"{base_name}.csv", f"{base_name}.geojson"],
    }
    (out_dir / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    if ses_check:
        print(
            f"  Sanity check vs nse_index_pca: rho={ses_check['spearman_rho']} "
            f"(n={ses_check['n_matched']}, expect negative)"
        )
    return df, gdf

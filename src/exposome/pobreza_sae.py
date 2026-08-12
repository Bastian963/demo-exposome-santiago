"""Poverty exposome layer (MDSF official small-area estimates, 2017-2024).

Commune-level income-poverty and multidimensional-poverty (IPM) rates for
the Región Metropolitana de Santiago, from the Ministerio de Desarrollo
Social y Familia's (MDSF) official Small Area Estimation (SAE) series. See
``docs/pobreza_sae_methodology.md`` for the full methodology and
``data/raw/pobreza_sae/README.md`` for source provenance.

This layer is entirely offline: the source workbooks are versioned in the
repo (small, no API key), so no network access is required to reproduce it.

The parsers here (``read_income_year`` / ``read_multi_year``) are also
imported by ``socioeconomic.py`` to source its ``pobreza_pct`` /
``pobreza_multi_pct`` columns from these same official workbooks, replacing
a third-party CSV that was found to mislabel multidimensional-poverty
values as income-poverty (see docs for details).
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

RAW_DIR_NAME = "pobreza_sae"

# (filename, sheet_name, layout) per year. layout "v2017" = 8 columns
# (no population projection, no sample-presence flag); "v2020" = 10
# columns (adds population projection + sample-presence before the
# SAE-type column). Column positions are used, not header text, because
# headers carry footnote markers/newlines that vary release to release.
INCOME_FILES: dict[int, tuple[str, str, str]] = {
    2017: (
        "PLANILLA_Estimaciones_comunales_tasa_pobreza_por_ingresos_multidimensional_2017.xlsx",
        "Ingresos 2017",
        "v2017",
    ),
    2020: (
        "Estimaciones_de_Tasa_de_Pobreza_por_Ingresos_por_Comunas_2020_revisada2022_09.xlsx",
        "Cifras 2020 revisadas en 2022",
        "v2020",
    ),
    2022: (
        "Estimaciones_Tasa_Pobreza_Ingresos_Comunas_2022.xlsx",
        "Estimaciones",
        "v2020",
    ),
    2024: ("SAE_ingresos_2024.xlsx", "Sheet1", "v2020"),
}

MULTI_FILES: dict[int, tuple[str, str, str]] = {
    2017: (
        "PLANILLA_Estimaciones_comunales_tasa_pobreza_por_ingresos_multidimensional_2017.xlsx",
        "Multidimensional 2017",
        "v2017",
    ),
    2022: (
        "Estimaciones_Indice_Pobreza_Multidimensional_Comunas_2022.xlsx",
        "Estimaciones",
        "v2020",
    ),
    2024: ("SAE_multidimensional_2024.xlsx", "Sheet1", "v2020"),
}

_SAE_TYPE_MAP = {
    "Directa y Sintética (Fay-Herriot)": "directa_sintetica",
    "Sintética": "sintetica",
    "SAE": "directa_sintetica",
    "Estimación Sintética": "sintetica",
}

_LAYOUT_COLS = {
    "v2017": ["comuna_code", "region", "name_raw", "n_personas", "pct", "ci_low", "ci_high", "sae_type_raw"],
    "v2020": [
        "comuna_code", "region", "name_raw", "poblacion", "n_personas", "pct",
        "ci_low", "ci_high", "en_muestra", "sae_type_raw",
    ],
}

_CORE_COLS = [
    "name",
    "pobreza_ing_2017", "pobreza_ing_ci_low_2017", "pobreza_ing_ci_high_2017", "pobreza_ing_sae_type_2017",
    "pobreza_ing_2020", "pobreza_ing_ci_low_2020", "pobreza_ing_ci_high_2020", "pobreza_ing_sae_type_2020",
    "pobreza_ing_2022", "pobreza_ing_ci_low_2022", "pobreza_ing_ci_high_2022", "pobreza_ing_sae_type_2022",
    "pobreza_ing_2024", "pobreza_ing_ci_low_2024", "pobreza_ing_ci_high_2024", "pobreza_ing_sae_type_2024",
    "pobreza_ing_change_2017_2022",
    "pobreza_multi_2017", "pobreza_multi_ci_low_2017", "pobreza_multi_ci_high_2017", "pobreza_multi_sae_type_2017",
    "pobreza_multi_2022", "pobreza_multi_ci_low_2022", "pobreza_multi_ci_high_2022", "pobreza_multi_sae_type_2022",
    "pobreza_multi_2024", "pobreza_multi_ci_low_2024", "pobreza_multi_ci_high_2024", "pobreza_multi_sae_type_2024",
    "pobreza_multi_change_2017_2024",
]


def _read_workbook(
    raw_dir: Path,
    files: dict[int, tuple[str, str, str]],
    prefix: str,
    year: int,
    region_code: int,
) -> pd.DataFrame:
    """Parse one MDSF SAE workbook (income or multidimensional) for one year.

    Returns ``[comuna_code, <prefix>_<year>, <prefix>_ci_low_<year>,
    <prefix>_ci_high_<year>, <prefix>_sae_type_<year>]`` and, for the
    "v2020" layout, also ``<prefix>_poblacion_<year>`` (population
    projection used to source ``socioeconomic``'s ``poblacion`` column).
    """
    filename, sheet, layout = files[year]
    path = raw_dir / filename
    df = pd.read_excel(path, sheet_name=sheet, header=2)
    cols = _LAYOUT_COLS[layout]
    df = df.iloc[:, : len(cols)].copy()
    df.columns = cols

    df["comuna_code"] = pd.to_numeric(df["comuna_code"], errors="coerce")
    df = df[df["comuna_code"].notna()].copy()
    df["comuna_code"] = df["comuna_code"].astype(int)
    lo, hi = region_code * 1000, (region_code + 1) * 1000
    df = df[(df["comuna_code"] >= lo) & (df["comuna_code"] < hi)].copy()

    for col in ("pct", "ci_low", "ci_high"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if region_code == 13 and len(df) != 52:
        raise ValueError(
            f"Expected 52 RM communes in {filename}/{sheet} ({year}), got {len(df)}"
        )

    out = pd.DataFrame({
        "comuna_code": df["comuna_code"].to_numpy(),
        f"{prefix}_{year}": (df["pct"] * 100).round(2).to_numpy(),
        f"{prefix}_ci_low_{year}": (df["ci_low"] * 100).round(2).to_numpy(),
        f"{prefix}_ci_high_{year}": (df["ci_high"] * 100).round(2).to_numpy(),
        f"{prefix}_sae_type_{year}": df["sae_type_raw"]
        .map(_SAE_TYPE_MAP)
        .fillna(df["sae_type_raw"])
        .to_numpy(),
    })
    if layout == "v2020":
        out[f"{prefix}_poblacion_{year}"] = pd.to_numeric(
            df["poblacion"], errors="coerce"
        ).to_numpy()
    return out.drop_duplicates("comuna_code").reset_index(drop=True)


def read_income_year(raw_dir: Path, year: int, region_code: int = 13) -> pd.DataFrame:
    """Parse the official income-poverty SAE workbook for ``year``."""
    return _read_workbook(Path(raw_dir), INCOME_FILES, "pobreza_ing", year, region_code)


def read_multi_year(raw_dir: Path, year: int, region_code: int = 13) -> pd.DataFrame:
    """Parse the official multidimensional-poverty (IPM) SAE workbook for ``year``."""
    return _read_workbook(Path(raw_dir), MULTI_FILES, "pobreza_multi", year, region_code)


def build_pobreza_sae_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    raw_dir: Path | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the commune-level poverty SAE layer and write CSV + GeoJSON + metadata."""
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]
    raw_dir = Path(raw_dir) if raw_dir else repo_root / "data" / "raw" / RAW_DIR_NAME

    region_code = 13
    print(f"Building poverty SAE layer for {city} from {raw_dir}")

    # 1. Boundaries (geometry + canonical commune names) + code->name map.
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    code_name = demography.load_comuna_code_name_map(cache_dir, region_code=region_code)

    # 2. Parse every year, keyed by comuna_code (INE CUT), dropping the
    #    auxiliary population columns (only needed by socioeconomic.py).
    pov = code_name.copy()
    for year in sorted(INCOME_FILES):
        yr = read_income_year(raw_dir, year, region_code)
        yr = yr.drop(columns=[c for c in yr.columns if c.endswith(f"poblacion_{year}")])
        pov = pov.merge(yr, on="comuna_code", how="left")
    for year in sorted(MULTI_FILES):
        yr = read_multi_year(raw_dir, year, region_code)
        pov = pov.merge(yr, on="comuna_code", how="left")

    # 3. Change columns — only across internally comparable segments (see
    #    docs/pobreza_sae_methodology.md: SAE estimates are not comparable
    #    across the 2024 canasta básica update).
    pov["pobreza_ing_change_2017_2022"] = (
        pov["pobreza_ing_2022"] - pov["pobreza_ing_2017"]
    ).round(2)
    pov["pobreza_multi_change_2017_2024"] = (
        pov["pobreza_multi_2024"] - pov["pobreza_multi_2017"]
    ).round(2)

    # 4. Join onto the boundary geometries by canonical name.
    df_bound = gdf_comm[["name"]].copy()
    df_bound["name_key"] = df_bound["name"].str.lower().str.strip()
    pov["name_key"] = pov["name"].str.lower().str.strip()
    df = df_bound.merge(
        pov.drop(columns=["name"]), on="name_key", how="left"
    ).drop(columns="name_key")
    df = df[_CORE_COLS].copy()

    # 5. Validate: exactly N rows, no duplicates, no NaN in the required
    #    columns. Confidence-interval bounds are allowed to be missing for
    #    a small number of synthetic-only estimates that the source
    #    workbook does not publish a CI for (e.g. Vitacura, income 2017) --
    #    this is a genuine source-data gap, not a parsing bug.
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    required_cols = [c for c in _CORE_COLS if "_ci_low_" not in c and "_ci_high_" not in c]
    if df[required_cols].isna().any().any():
        missing = [c for c in required_cols if df[c].isna().any()]
        raise ValueError(f"Missing values in required columns: {missing}")

    # 6. Geo version.
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 7. Sanity check: correlation with the socioeconomic layer, if present.
    ses_path = out_dir / "socioeconomic_exposome_rm_santiago.csv"
    ses_check: dict[str, Any] | None = None
    if ses_path.exists():
        ses = pd.read_csv(ses_path)[["name", "nse_index_pca"]]
        merged = df.merge(ses, on="name", how="inner").dropna(
            subset=["pobreza_ing_2024", "nse_index_pca"]
        )
        if len(merged) >= 10:
            rho, pval = spearmanr(merged["pobreza_ing_2024"], merged["nse_index_pca"])
            ses_check = {
                "n_matched": int(len(merged)),
                "spearman_rho": round(float(rho), 4),
                "spearman_p": float(pval),
                "expected_sign": "negative (higher poverty <-> lower SES)",
            }

    # 8. Verification spot-checks (documented, not enforced as hard asserts
    #    here — the notebook / tests assert on these).
    verification = {}
    row = df.loc[df["name"] == "La Pintana"]
    if not row.empty:
        verification["la_pintana"] = {
            "pobreza_ing_2022": float(row["pobreza_ing_2022"].iloc[0]),
            "pobreza_multi_2022": float(row["pobreza_multi_2022"].iloc[0]),
            "pobreza_ing_2024": float(row["pobreza_ing_2024"].iloc[0]),
        }
    row = df.loc[df["name"] == "Vitacura"]
    if not row.empty:
        verification["vitacura"] = {
            "pobreza_ing_2022": float(row["pobreza_ing_2022"].iloc[0]),
            "pobreza_multi_2022": float(row["pobreza_multi_2022"].iloc[0]),
        }

    # 9. Write outputs.
    base_name = "santiago_pobreza_sae"
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
                "División Observatorio Social, con asesoría técnica de CEPAL"
            ),
            "landing_page": (
                "https://observatorio.ministeriodesarrollosocial.gob.cl/pobreza-comunal"
            ),
            "methodological_note": "data/raw/pobreza_sae/Informe_SAE_2020.pdf",
            "years_available": {
                "income": sorted(INCOME_FILES),
                "multidimensional": sorted(MULTI_FILES),
            },
            "years_excluded_note": (
                "2015 excluded: pre-CEPAL-revision poverty line, no parseable "
                "numeric results table in the source PDF. See "
                "data/raw/pobreza_sae/methodology_notes/resultados_pobreza_comunal_2015.md"
            ),
            "indicator": (
                "Income poverty rate and multidimensional poverty index (IPM), "
                "official MDSF small-area estimates (SAE), Fay-Herriot model"
            ),
        },
        "method": (
            "Fay-Herriot small-area estimation: variance-weighted blend of a "
            "direct CASEN estimate and a synthetic estimate (regression on "
            "administrative/census covariates), re-fit independently each "
            "year. Implemented with the R EMDI package since 2020. "
            "See docs/pobreza_sae_methodology.md for full detail."
        ),
        "comparability_caveat": (
            "MDSF states SAE estimates are not comparable across years "
            "(model/covariates re-fit each vintage); 2024 additionally "
            "updates the canasta básica used to define income poverty, "
            "producing a level break independent of any real change. "
            "Change columns are computed only across internally comparable "
            "segments (never crossing the 2024 income break)."
        ),
        "verification": verification,
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

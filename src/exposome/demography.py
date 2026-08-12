"""Chilean census demography layer (Censo 2017 by commune).

Downloads the INE manzana-level microdata RAR, extracts the relevant CSVs,
and aggregates population counts to the commune level for the configured
region. Age groups are scaled so that their sum matches the reported total
population, because raw manzana cells use ``*`` for suppressed small counts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

CENSUS_RAR_URL = "https://redatam-ine.ine.cl/tab/Censo2017_ManzanaEntidad_CSV.rar"
MANZANA_CSV_PATH = "Censo2017_16R_ManzanaEntidad_CSV/Censo2017_Manzanas.csv"
COMUNA_CSV_PATH = "Censo2017_16R_ManzanaEntidad_CSV/Censo2017_Identificación_Geográfica/Microdato_Censo2017-Comunas.csv"

CENSUS_COUNT_COLUMNS = [
    "PERSONAS",
    "HOMBRES",
    "MUJERES",
    "EDAD_0A5",
    "EDAD_6A14",
    "EDAD_15A64",
    "EDAD_65YMAS",
]


def _download_file(url: str, dest: Path, timeout: int = 300) -> None:
    """Download a binary file to ``dest`` using streaming requests."""
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def ensure_census_files(cache_dir: Path) -> tuple[Path, Path]:
    """Download and extract the INE Censo 2017 RAR if needed.

    Returns paths to the manzana CSV and the commune-name CSV. Public so other
    exposome layers (e.g. socioeconomic) can reuse the cached census files.
    """
    import rarfile

    cache_dir = Path(cache_dir)
    rar_path = cache_dir / "censo2017_manzana.rar"
    if not rar_path.exists():
        print(f"  Downloading INE Censo 2017 RAR...")
        _download_file(CENSUS_RAR_URL, rar_path)
        print(f"  Cached {rar_path.name}")

    manzana_path = cache_dir / MANZANA_CSV_PATH
    comuna_path = cache_dir / COMUNA_CSV_PATH

    if not manzana_path.exists() or not comuna_path.exists():
        print("  Extracting census CSVs...")
        rf = rarfile.RarFile(rar_path)
        rf.extract(MANZANA_CSV_PATH, path=cache_dir)
        rf.extract(COMUNA_CSV_PATH, path=cache_dir)

    return manzana_path, comuna_path


# Backwards-compatible private alias.
_ensure_census_files = ensure_census_files


def normalize_comuna_name(names: pd.Series) -> pd.Series:
    """Title-case INE commune names so they match the OSM/boundary names.

    Lowercases common Spanish prepositions/articles so e.g. "CALERA DE TANGO"
    becomes "Calera de Tango".
    """
    return (
        names.astype(str)
        .str.title()
        .str.replace(" De ", " de ")
        .str.replace(" Del ", " del ")
        .str.replace(" La ", " la ")
        .str.replace(" El ", " el ")
        .str.replace(" Y ", " y ")
        .str.strip()
    )


def load_comuna_code_name_map(
    cache_dir: Path,
    region_code: int | None = 13,
) -> pd.DataFrame:
    """Return a ``comuna_code`` → ``name`` mapping from the 2017 Census.

    Names are normalised to match the exposome boundaries. When ``region_code``
    is given, only that region's communes are returned (13 = Metropolitana).
    """
    _, comuna_path = ensure_census_files(Path(cache_dir))
    df = pd.read_csv(comuna_path, sep=";", low_memory=False)
    df = df.rename(columns={"NOM_COMUNA": "name_raw", "COMUNA": "comuna_code"})
    df["comuna_code"] = pd.to_numeric(df["comuna_code"], errors="coerce")
    df = df[df["comuna_code"].notna()].copy()
    df["comuna_code"] = df["comuna_code"].astype(int)
    if region_code is not None:
        lo, hi = region_code * 1000, (region_code + 1) * 1000
        df = df[(df["comuna_code"] >= lo) & (df["comuna_code"] < hi)].copy()
    df["name"] = normalize_comuna_name(df["name_raw"])
    return df[["comuna_code", "name"]].reset_index(drop=True)


def load_region_manzanas(cache_dir: Path, region_code: int = 13) -> pd.DataFrame:
    """Return the raw manzana-level census rows for a single region."""
    manzana_path, _ = ensure_census_files(Path(cache_dir))
    df = pd.read_csv(manzana_path, sep=";", low_memory=False)
    return df[df["REGION"] == region_code].copy()


def _coerce_census_count_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Return ``df`` with census count columns converted to numeric values.

    INE uses ``*`` for suppressed small cells. Those cells are set to NaN before
    aggregation; commune-level components are later scaled back to the official
    total population.
    """
    out = df.copy()
    for col in columns:
        out[col] = pd.to_numeric(out[col].replace("*", np.nan), errors="coerce")
    return out


def _scale_integer_components_to_total(
    components: pd.DataFrame,
    total: pd.Series,
) -> pd.DataFrame:
    """Scale component columns row-wise so integer components sum to ``total``.

    Suppressed census cells make summed components lower than ``PERSONAS``.
    Scaling at the commune level keeps published totals intact while preserving
    the observed component distribution. Largest-remainder rounding guarantees
    exact integer row sums.
    """
    component_cols = list(components.columns)
    counts = components.astype(float).fillna(0.0)
    totals = pd.to_numeric(total, errors="raise").astype(int)
    observed_sum = counts.sum(axis=1)
    if ((observed_sum <= 0) & (totals > 0)).any():
        bad = totals.index[(observed_sum <= 0) & (totals > 0)].tolist()
        raise ValueError(f"Cannot scale suppressed census components with zero observed sum: {bad}")

    scaled = counts.div(observed_sum.replace(0, np.nan), axis=0).mul(totals, axis=0)
    floors = np.floor(scaled).fillna(0).astype(int)
    fractions = (scaled - floors).fillna(0.0)
    result = floors.copy()

    remainders = totals - result.sum(axis=1)
    for idx, remainder in remainders.items():
        remainder = int(remainder)
        if remainder > 0:
            ordered_cols = fractions.loc[idx].sort_values(ascending=False).index[:remainder]
            for col in ordered_cols:
                result.at[idx, col] += 1
        elif remainder < 0:
            ordered_cols = fractions.loc[idx].sort_values(ascending=True).index[:abs(remainder)]
            for col in ordered_cols:
                result.at[idx, col] -= 1

    return result[component_cols].astype(int)


def load_commune_demography(
    cache_dir: Path,
    region_code: int = 13,
) -> pd.DataFrame:
    """Return a DataFrame of commune-level population from the 2017 Census.

    Columns returned:
    - ``name`` : commune name (title-cased, matching the exposome boundaries)
    - ``comuna_code`` : INE commune code
    - ``pop_total``, ``pop_male``, ``pop_female``
    - ``pop_0_14``, ``pop_15_64``, ``pop_65_plus``
    - ``pct_pop_0_14``, ``pct_pop_15_64``, ``pct_pop_65_plus``
    """
    cache_dir = Path(cache_dir)
    df_region = load_region_manzanas(cache_dir, region_code=region_code)
    code_name = load_comuna_code_name_map(cache_dir, region_code=region_code)

    df_region = _coerce_census_count_columns(df_region, CENSUS_COUNT_COLUMNS)

    # Aggregate to commune.
    agg = df_region.groupby("COMUNA").agg(
        pop_total=("PERSONAS", "sum"),
        pop_male=("HOMBRES", "sum"),
        pop_female=("MUJERES", "sum"),
        pop_0_5=("EDAD_0A5", "sum"),
        pop_6_14=("EDAD_6A14", "sum"),
        pop_15_64=("EDAD_15A64", "sum"),
        pop_65_plus=("EDAD_65YMAS", "sum"),
    ).reset_index()

    agg["pop_total"] = agg["pop_total"].astype(int)
    agg["pop_0_14"] = agg["pop_0_5"] + agg["pop_6_14"]

    # Scale sex and age components so they add up to the reported total.
    sex_scaled = _scale_integer_components_to_total(
        agg[["pop_male", "pop_female"]],
        agg["pop_total"],
    )
    agg[["pop_male", "pop_female"]] = sex_scaled

    age_scaled = _scale_integer_components_to_total(
        agg[["pop_0_14", "pop_15_64", "pop_65_plus"]],
        agg["pop_total"],
    )
    agg[["pop_0_14", "pop_15_64", "pop_65_plus"]] = age_scaled

    # Add normalised commune names (matching the exposome boundaries).
    agg["comuna_code"] = agg["COMUNA"].astype(int)
    result = agg.merge(code_name, on="comuna_code", how="left")

    # Percentages.
    for col in ["pop_0_14", "pop_15_64", "pop_65_plus"]:
        pct_col = f"pct_{col}"
        result[pct_col] = (result[col] / result["pop_total"] * 100).round(2)

    out_cols = [
        "name",
        "comuna_code",
        "pop_total",
        "pop_male",
        "pop_female",
        "pop_0_14",
        "pop_15_64",
        "pop_65_plus",
        "pct_pop_0_14",
        "pct_pop_15_64",
        "pct_pop_65_plus",
    ]
    return result[out_cols].copy().reset_index(drop=True)


def _load_commune_geometries(city: str, cache_dir: Path) -> gpd.GeoDataFrame:
    """Load commune geometries in WGS84, reusing local processed layers."""
    from . import boundaries, config

    cfg = config.load_config(city)
    gdf = boundaries.get_communes(
        cfg,
        cache_path=Path(cache_dir) / f"{city}_communes.geojson",
    )
    geographic_crs = cfg["crs"]["geographic"]
    if gdf.crs is None:
        gdf = gdf.set_crs(geographic_crs)
    else:
        gdf = gdf.to_crs(geographic_crs)
    return gdf[["name", "geometry"]].drop_duplicates("name").copy()


def _build_demography_geojson(
    df: pd.DataFrame,
    city: str,
    cache_dir: Path,
) -> gpd.GeoDataFrame:
    """Attach local commune geometries to the demography table."""
    gdf = _load_commune_geometries(city, cache_dir)
    merged = gdf.merge(df, on="name", how="right", validate="one_to_one")
    missing_geometry = merged.loc[merged.geometry.isna(), "name"].tolist()
    if missing_geometry:
        raise ValueError(f"Missing commune geometries for demography layer: {missing_geometry}")
    if merged["name"].duplicated().any():
        dupes = merged.loc[merged["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names in demography GeoJSON: {dupes}")
    return merged.set_geometry("geometry")


def _write_demography_metadata(
    path: Path,
    *,
    city: str,
    region_code: int,
    df: pd.DataFrame,
    outputs: list[str],
    methodology_doc: str,
    figure: str,
) -> None:
    """Write JSON metadata for the demography layer."""
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "geographic_unit": "comuna",
        "region_code": region_code,
        "region_name": "Region Metropolitana de Santiago",
        "expected_communes": 52,
        "n_communes": int(len(df)),
        "data_year": 2017,
        "source": {
            "provider": "Instituto Nacional de Estadisticas de Chile (INE)",
            "dataset": "Censo 2017, microdato de manzanas",
            "url": CENSUS_RAR_URL,
            "archive": Path(urlparse(CENSUS_RAR_URL).path).name,
            "manzana_csv": MANZANA_CSV_PATH,
            "comuna_lookup_csv": COMUNA_CSV_PATH,
        },
        "method": {
            "aggregation": "Manzana-level counts are grouped by INE COMUNA code for region 13 and joined to normalized commune names.",
            "suppression": "INE uses '*' for suppressed small cells. Suppressed cells are treated as missing before commune aggregation.",
            "component_adjustment": "Sex and age-group components are scaled at commune level with largest-remainder integer rounding so each component set sums to pop_total.",
            "age_groups": {
                "pop_0_14": "EDAD_0A5 + EDAD_6A14, scaled to pop_total with other age groups",
                "pop_15_64": "EDAD_15A64, scaled",
                "pop_65_plus": "EDAD_65YMAS, scaled",
            },
        },
        "columns": {
            "name": {"unit": "commune name", "description": "Normalized Santiago commune name"},
            "comuna_code": {"unit": "INE CUT code", "description": "Five-digit INE commune code"},
            "pop_total": {"unit": "persons", "description": "Total population, Censo 2017"},
            "pop_male": {"unit": "persons", "description": "Male population, adjusted for suppressed cells"},
            "pop_female": {"unit": "persons", "description": "Female population, adjusted for suppressed cells"},
            "pop_0_14": {"unit": "persons", "description": "Population aged 0-14, adjusted for suppressed cells"},
            "pop_15_64": {"unit": "persons", "description": "Population aged 15-64, adjusted for suppressed cells"},
            "pop_65_plus": {"unit": "persons", "description": "Population aged 65+, adjusted for suppressed cells"},
            "pct_pop_0_14": {"unit": "percent", "description": "100 * pop_0_14 / pop_total"},
            "pct_pop_15_64": {"unit": "percent", "description": "100 * pop_15_64 / pop_total"},
            "pct_pop_65_plus": {"unit": "percent", "description": "100 * pop_65_plus / pop_total"},
        },
        "limitations": [
            "Census reference is 2017; it is not an intercensal population denominator.",
            "Outputs are aggregated to commune level and do not retain within-commune heterogeneity.",
            "Small-cell suppression in the public manzana table requires commune-level component adjustment.",
            "The layer does not model population change after the 2017 census.",
        ],
        "methodology_doc": methodology_doc,
        "diagnostic_figure": figure,
        "outputs": outputs,
    }
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_demography_figure(gdf: gpd.GeoDataFrame, out_path: Path) -> None:
    """Write a compact diagnostic map for total population and ageing."""
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    plots = [
        ("pop_total", "Poblacion total (Censo 2017)", "viridis", "personas"),
        ("pct_pop_65_plus", "Poblacion 65+ (%)", "magma", "%"),
    ]
    for ax, (column, title, cmap, label) in zip(axes, plots, strict=True):
        gdf.plot(
            column=column,
            ax=ax,
            cmap=cmap,
            legend=True,
            legend_kwds={"label": label, "shrink": 0.65},
            edgecolor="white",
            linewidth=0.3,
        )
        ax.set_title(title, fontsize=12)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def build_demography_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    figures_dir: Path = Path("figures"),
) -> pd.DataFrame:
    """Run the demography pipeline and write CSV, GeoJSON, metadata and figure."""
    # The region code is hardcoded to 13 (Metropolitana) for Santiago; in a
    # generalised pipeline this would come from the city config.
    region_code = 13

    df = load_commune_demography(cache_dir, region_code=region_code)
    gdf = _build_demography_geojson(df, city=city, cache_dir=cache_dir)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{city}_demography"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    metadata_path = out_dir / f"{base_name}_metadata.json"
    figure_path = Path(figures_dir) / f"demography_{city}_2panel.png"

    df.to_csv(csv_path, index=False)
    gdf.to_file(geojson_path, driver="GeoJSON")
    _write_demography_figure(gdf, figure_path)
    _write_demography_metadata(
        metadata_path,
        city=city,
        region_code=region_code,
        df=df,
        outputs=[csv_path.name, geojson_path.name, metadata_path.name],
        methodology_doc="docs/demography_methodology.md",
        figure=figure_path.as_posix(),
    )
    print(f"Wrote {csv_path.name} ({len(df)} rows x {df.shape[1]} cols)")
    print(f"Wrote {geojson_path.name}")
    print(f"Wrote {metadata_path.name}")
    print(f"Wrote {figure_path.name}")
    return df

"""Chilean census demography layer (Censo 2017 by commune).

Downloads the INE manzana-level microdata RAR, extracts the relevant CSVs,
and aggregates population counts to the commune level for the configured
region. Age groups are scaled so that their sum matches the reported total
population, because raw manzana cells use ``*`` for suppressed small counts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

CENSUS_RAR_URL = "https://redatam-ine.ine.cl/tab/Censo2017_ManzanaEntidad_CSV.rar"
MANZANA_CSV_PATH = "Censo2017_16R_ManzanaEntidad_CSV/Censo2017_Manzanas.csv"
COMUNA_CSV_PATH = "Censo2017_16R_ManzanaEntidad_CSV/Censo2017_Identificación_Geográfica/Microdato_Censo2017-Comunas.csv"


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

    # Age columns use '*' for suppressed small counts; coerce to numeric.
    age_cols = ["EDAD_0A5", "EDAD_6A14", "EDAD_15A64", "EDAD_65YMAS"]
    for col in age_cols:
        df_region[col] = pd.to_numeric(
            df_region[col].replace("*", np.nan), errors="coerce"
        )

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

    agg["pop_0_14"] = agg["pop_0_5"] + agg["pop_6_14"]

    # Scale age groups so they add up to the reported total (some manzanas
    # suppress small counts with '*').
    age_sum = agg["pop_0_14"] + agg["pop_15_64"] + agg["pop_65_plus"]
    for col in ["pop_0_14", "pop_15_64", "pop_65_plus"]:
        agg[col] = (agg[col] * agg["pop_total"] / age_sum).round(0).astype(int)

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


def build_demography_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> pd.DataFrame:
    """Run the demography pipeline and write the output CSV."""
    # The region code is hardcoded to 13 (Metropolitana) for Santiago; in a
    # generalised pipeline this would come from the city config.
    region_code = 13

    df = load_commune_demography(cache_dir, region_code=region_code)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{city}_demography.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path.name} ({len(df)} rows x {df.shape[1]} cols)")
    return df

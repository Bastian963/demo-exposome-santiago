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


def _ensure_census_files(cache_dir: Path) -> tuple[Path, Path]:
    """Download and extract the INE Censo 2017 RAR if needed.

    Returns paths to the manzana CSV and the commune-name CSV.
    """
    import rarfile

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
    manzana_path, comuna_path = _ensure_census_files(cache_dir)

    df_manzana = pd.read_csv(manzana_path, sep=";", low_memory=False)
    df_comuna = pd.read_csv(comuna_path, sep=";", low_memory=False)

    # Select the requested region.
    df_region = df_manzana[df_manzana["REGION"] == region_code].copy()

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

    # Add commune names.
    df_comuna = df_comuna.rename(columns={"NOM_COMUNA": "name_raw"})
    result = agg.merge(df_comuna, on="COMUNA", how="left")

    # Normalise commune names to title case for consistency with OSM/boundaries.
    # Lowercase common prepositions so e.g. "Calera De Tango" becomes
    # "Calera de Tango".
    result["name"] = (
        result["name_raw"]
        .astype(str)
        .str.title()
        .str.replace(" De ", " de ")
        .str.replace(" Del ", " del ")
        .str.replace(" La ", " la ")
        .str.replace(" El ", " el ")
        .str.replace(" Y ", " y ")
        .str.strip()
    )
    result["comuna_code"] = result["COMUNA"].astype(int)

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

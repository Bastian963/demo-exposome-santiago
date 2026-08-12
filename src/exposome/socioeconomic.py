"""Socioeconomic (NSE) exposome layer for the Región Metropolitana.

A multidimensional, commune-level socioeconomic index built entirely from open,
no-API-key official sources:

- CASEN 2022 per-capita household income and years of schooling
  (``casen_2022_ingresos.csv`` via ``bastianolea/pobreza_chile``).
- Income-poverty and multidimensional-poverty (IPM) rates with 95% confidence
  intervals, from the MDSF's *official* small-area estimation (SAE) workbooks
  (``data/raw/pobreza_sae/``, see :mod:`exposome.pobreza_sae`), CASEN 2022 vintage.
- Housing materiality and overcrowding from the 2017 Census (INE, manzana level,
  reused via :mod:`exposome.demography`).

Supplementary indicators (added as additional columns, not part of the composite
index):

- Crime rates (per 100k inhabitants) from CEAD via bastianolea/delincuencia_chile.
- Average PAES score (reading + maths, 2024) via bastianolea/puntajes_prueba_paes.
- FONASA tramo A+B coverage (%) via bastianolea/fonasa_beneficiarios.
- Municipal own permanent revenue per capita (IPP, M$) from SINIM
  via bastianolea/sinim_info_municipal.

Two composite indices are produced (both oriented so that *higher = better
socioeconomic position*):

- ``nse_index``     : equal-weight mean of the standardized, sign-oriented
                      components (kept as the canonical column for the master
                      table and the demo document).
- ``nse_index_pca`` : first principal component (numpy SVD) of the same matrix,
                      reported with explained variance and component loadings.
                      The Spearman correlation between the two is exported as a
                      weighting-sensitivity check.

An optional external-validation step compares the PCA index against an
independent official index (e.g. Índice de Prioridad Social RM, JUNAEB IVE) when
a cached source file is configured, following the project's "optional with
graceful skip" convention.

.. note::
   ``pobreza_pct`` / ``pobreza_multi_pct`` were previously sourced from a
   third-party CSV (``bastianolea/pobreza_chile/pobreza_comunal.csv``) that
   was found to carry 2022 *multidimensional* poverty values mislabeled as
   income poverty. They now come directly from the official MDSF SAE
   workbooks via :mod:`exposome.pobreza_sae`. See
   ``docs/pobreza_sae_methodology.md`` for the discovery evidence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr

from . import boundaries, config, demography, pobreza_sae

# Default open-data sources (overridable via the city config).
DEFAULT_SOURCES = {
    "casen_ingresos": (
        "https://raw.githubusercontent.com/bastianolea/pobreza_chile/main/"
        "casen/datos_procesados/casen_2022_ingresos.csv"
    ),
    # Supplementary indicators (bastianolea repos, all official-source derived)
    "crime": (
        "https://github.com/bastianolea/delincuencia_chile/raw/main/"
        "datos/procesados/cead_delincuencia_chile.parquet"
    ),
    "paes": (
        "https://github.com/bastianolea/puntajes_prueba_paes/raw/main/"
        "datos/puntajes_paes_comuna_2024.csv"
    ),
    "fonasa": (
        "https://raw.githubusercontent.com/bastianolea/fonasa_beneficiarios/master/"
        "datos/fonasa_beneficiarios_tramo_edad_sexo.csv"
    ),
    "sinim": (
        "https://github.com/bastianolea/sinim_info_municipal/raw/main/"
        "datos/sinim_2019-2023.parquet"
    ),
}

# CEAD crime-type classification (bastianolea/delincuencia_chile)
_VIOLENT_CRIMES = frozenset({
    "Homicidios", "Femicidios", "Violaciones", "Abusos sexuales", "Acosos sexuales",
    "Robos con violencia o intimidación", "Lesiones graves o gravísimas",
    "Lesiones leves", "Lesiones menos graves", "Violencia intrafamiliar",
})
_PROPERTY_CRIMES = frozenset({
    "Hurtos", "Robo en lugar habitado", "Robo en lugar no habitado",
    "Robo de vehículo motorizado", "Robo violento de vehículo motorizado",
    "Robo por sorpresa", "Robo de objetos de o desde vehículo",
    "Otros robos con fuerza en las cosas", "Robo frustrado",
    "Receptación", "Daños",
})

# Core columns that must be complete (no NaN). Supplementary columns are allowed NaN.
_CORE_COLS = [
    "name", "area_km2", "poblacion", "ingreso", "escolaridad",
    "pobreza_pct", "pobreza_ci_low", "pobreza_ci_high", "pobreza_multi_pct",
    "viv_materialidad_deficitaria_pct", "hacinamiento_phh",
    "nse_index", "nse_index_pca", "nse_quintil",
]

# Index components: (column, orientation). orientation +1 means "higher is a
# better socioeconomic position", -1 means "higher is more deprivation".
INDEX_COMPONENTS: list[tuple[str, int]] = [
    ("ingreso", +1),
    ("escolaridad", +1),
    ("pobreza_pct", -1),
    ("pobreza_multi_pct", -1),
    ("viv_materialidad_deficitaria_pct", -1),
    ("hacinamiento_phh", -1),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _to_num(s: pd.Series) -> pd.Series:
    """Parse a Chilean-formatted numeric series (comma decimal) to float."""
    return pd.to_numeric(
        s.astype(str).str.replace(",", ".", regex=False).str.strip(),
        errors="coerce",
    )


def _rm_filter(codes: pd.Series, region_code: int = 13) -> pd.Series:
    """Boolean mask selecting communes of a region from their 5-digit CUT."""
    lo, hi = region_code * 1000, (region_code + 1) * 1000
    return (codes >= lo) & (codes < hi)


def _download_csv(url: str, dest: Path, timeout: int = 120) -> Path:
    """Download ``url`` to ``dest`` once (cached afterwards)."""
    dest = Path(dest)
    if not dest.exists():
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
    return dest


def _download_parquet(url: str, dest: Path, timeout: int = 240) -> Path:
    """Download a parquet ``url`` to ``dest`` once (cached afterwards)."""
    dest = Path(dest)
    if not dest.exists():
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
    return dest


# --------------------------------------------------------------------------- #
# Fetch functions (all keyed by ``comuna_code`` = INE CUT)
# --------------------------------------------------------------------------- #
def fetch_poverty_income_official(
    raw_dir: Path, year: int = 2022, region_code: int = 13
) -> pd.DataFrame:
    """Official income-poverty SAE rate, 95% CI, and commune population.

    Sourced from the MDSF's own SAE workbooks (``exposome.pobreza_sae``),
    not the third-party CSV formerly used here (see module docstring).
    """
    inc = pobreza_sae.read_income_year(Path(raw_dir), year, region_code)
    return pd.DataFrame(
        {
            "comuna_code": inc["comuna_code"].to_numpy(),
            "poblacion": inc[f"pobreza_ing_poblacion_{year}"]
            .round()
            .astype("Int64")
            .to_numpy(),
            "pobreza_pct": inc[f"pobreza_ing_{year}"].to_numpy(),
            "pobreza_ci_low": inc[f"pobreza_ing_ci_low_{year}"].to_numpy(),
            "pobreza_ci_high": inc[f"pobreza_ing_ci_high_{year}"].to_numpy(),
        }
    )


def fetch_casen_income_education(
    cache_dir: Path, url: str, region_code: int = 13
) -> pd.DataFrame:
    """Per-capita household income (``ytotcor``) and schooling (``esc``)."""
    dest = _download_csv(url, Path(cache_dir) / "ses_casen_ingresos.csv")
    df = pd.read_csv(dest, sep=";", low_memory=False)
    if "nivel" in df.columns:
        df = df[df["nivel"] == "comuna"].copy()
    df["comuna_code"] = pd.to_numeric(df["cut_comuna"], errors="coerce")
    df = df[df["comuna_code"].notna()].copy()
    df["comuna_code"] = df["comuna_code"].astype(int)
    df = df[_rm_filter(df["comuna_code"], region_code)].copy()
    out = pd.DataFrame(
        {
            "comuna_code": df["comuna_code"].to_numpy(),
            "ingreso": _to_num(df["ytotcor"]).round().astype("Int64").to_numpy(),
            "escolaridad": _to_num(df["esc"]).round(2).to_numpy(),
        }
    )
    return out.drop_duplicates("comuna_code").reset_index(drop=True)


def fetch_poverty_multi_official(
    raw_dir: Path, year: int = 2022, region_code: int = 13
) -> pd.DataFrame:
    """Official multidimensional-poverty (IPM) SAE rate.

    Sourced from the MDSF's own SAE workbooks (``exposome.pobreza_sae``),
    not the CASEN direct-survey estimate formerly used here (see module
    docstring) — SAE is the estimator family consistent with the rest of
    the NSE index components.
    """
    multi = pobreza_sae.read_multi_year(Path(raw_dir), year, region_code)
    return pd.DataFrame(
        {
            "comuna_code": multi["comuna_code"].to_numpy(),
            "pobreza_multi_pct": multi[f"pobreza_multi_{year}"].to_numpy(),
        }
    )


def compute_housing_deprivation(
    cache_dir: Path, region_code: int = 13
) -> pd.DataFrame:
    """Aggregate 2017 Census manzana housing indicators to the commune level.

    - ``viv_materialidad_deficitaria_pct`` = share of occupied private dwellings
      with recoverable + irrecoverable building materiality (MATREC + MATIRREC
      over the total materiality-classified dwellings).
    - ``hacinamiento_phh`` = persons per household (a crowding proxy).
    """
    man = demography.load_region_manzanas(cache_dir, region_code=region_code)
    cols = ["MATACEP", "MATREC", "MATIRREC", "PERSONAS", "CANT_HOG"]
    for c in cols:
        man[c] = pd.to_numeric(man[c].replace("*", np.nan), errors="coerce")
    agg = (
        man.groupby("COMUNA")
        .agg(
            matacep=("MATACEP", "sum"),
            matrec=("MATREC", "sum"),
            matirrec=("MATIRREC", "sum"),
            personas=("PERSONAS", "sum"),
            hogares=("CANT_HOG", "sum"),
        )
        .reset_index()
    )
    viv_total = agg["matacep"] + agg["matrec"] + agg["matirrec"]
    agg["viv_materialidad_deficitaria_pct"] = (
        (agg["matrec"] + agg["matirrec"]) / viv_total * 100
    ).round(2)
    agg["hacinamiento_phh"] = (agg["personas"] / agg["hogares"]).round(3)
    agg["comuna_code"] = agg["COMUNA"].astype(int)
    return agg[
        ["comuna_code", "viv_materialidad_deficitaria_pct", "hacinamiento_phh"]
    ].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Supplementary fetch functions (graceful skip on any error)
# --------------------------------------------------------------------------- #
def fetch_crime_counts(
    cache_dir: Path, url: str, region_code: int = 13
) -> pd.DataFrame:
    """Crime counts by commune from CEAD (bastianolea/delincuencia_chile).

    Uses the most recent year available. Returns raw counts; the caller must
    divide by population to get rates per 100k.
    Returns ``[comuna_code, delitos_violentos_n, delitos_propiedad_n]``.
    """
    _empty = pd.DataFrame(
        columns=["comuna_code", "delitos_violentos_n", "delitos_propiedad_n"]
    )
    try:
        dest = _download_parquet(url, Path(cache_dir) / "ses_crime.parquet")
        df = pd.read_parquet(dest)
    except Exception as exc:
        print(f"  [crime] skipped: {exc}")
        return _empty

    df["cut_region"] = pd.to_numeric(df["cut_region"], errors="coerce")
    df = df[df["cut_region"] == region_code].copy()
    if df.empty:
        print(f"  [crime] no rows for region_code={region_code}")
        return _empty

    df["year"] = pd.to_datetime(df["fecha"], errors="coerce").dt.year
    latest = int(df["year"].max())
    df = df[df["year"] == latest].copy()
    print(f"  [crime] using year {latest}, {len(df)} rows")

    df["is_violent"] = df["delito"].isin(_VIOLENT_CRIMES)
    df["is_property"] = df["delito"].isin(_PROPERTY_CRIMES)
    df["cut_comuna"] = pd.to_numeric(df["cut_comuna"], errors="coerce")

    def _agg(g: pd.DataFrame) -> pd.Series:
        return pd.Series({
            "delitos_violentos_n": g.loc[g["is_violent"], "delito_n"].sum(),
            "delitos_propiedad_n": g.loc[g["is_property"], "delito_n"].sum(),
        })

    agg = df.groupby("cut_comuna").apply(_agg, include_groups=False).reset_index()
    agg = agg.rename(columns={"cut_comuna": "comuna_code"})
    agg["comuna_code"] = agg["comuna_code"].astype(int)
    return agg


def fetch_paes_scores(
    cache_dir: Path, url: str, region_code: int = 13
) -> pd.DataFrame:
    """Average PAES score (comprensión lectora + matemática 1) by commune.

    Data from bastianolea/puntajes_prueba_paes (Mineduc, 2024).
    Returns ``[comuna_code, paes_puntaje_promedio]``.
    """
    _empty = pd.DataFrame(columns=["comuna_code", "paes_puntaje_promedio"])
    try:
        dest = _download_csv(url, Path(cache_dir) / "ses_paes.csv")
        df = pd.read_csv(dest, sep=";", low_memory=False)
    except Exception as exc:
        print(f"  [paes] skipped: {exc}")
        return _empty

    df["codigo_region"] = pd.to_numeric(df["codigo_region"], errors="coerce")
    df = df[df["codigo_region"] == region_code].copy()
    if df.empty:
        print(f"  [paes] no rows for region_code={region_code}")
        return _empty

    df["paes_complectora"] = _to_num(df["paes_complectora"])
    df["paes_matematica1"] = _to_num(df["paes_matematica1"])
    df["paes_puntaje_promedio"] = (
        (df["paes_complectora"] + df["paes_matematica1"]) / 2
    ).round(1)
    df["comuna_code"] = pd.to_numeric(df["codigo_comuna"], errors="coerce").astype(int)
    print(f"  [paes] {len(df)} communes in RM")
    return (
        df[["comuna_code", "paes_puntaje_promedio"]]
        .drop_duplicates("comuna_code")
        .reset_index(drop=True)
    )


def fetch_fonasa_coverage(
    cache_dir: Path, url: str, region_code: int = 13
) -> pd.DataFrame:
    """FONASA tramo A+B beneficiaries as % of all FONASA registrants, by commune.

    Tramos A and B are the two lowest income tiers of Chile's public health
    insurance system; high ``pct_fonasa_tramo_a_b`` signals greater vulnerability.
    Data: bastianolea/fonasa_beneficiarios (Fonasa 2023).
    Returns ``[comuna_code, pct_fonasa_tramo_a_b]``.
    """
    _empty = pd.DataFrame(columns=["comuna_code", "pct_fonasa_tramo_a_b"])
    try:
        dest = _download_csv(url, Path(cache_dir) / "ses_fonasa.csv")
        df = pd.read_csv(dest, sep=";", low_memory=False)
    except Exception as exc:
        print(f"  [fonasa] skipped: {exc}")
        return _empty

    df["codigo_region"] = pd.to_numeric(df["codigo_region"], errors="coerce")
    df = df[df["codigo_region"] == region_code].copy()
    if df.empty:
        print(f"  [fonasa] no rows for region_code={region_code}")
        return _empty

    df["beneficiarios"] = pd.to_numeric(df["beneficiarios"], errors="coerce").fillna(0)
    df["comuna_code"] = pd.to_numeric(df["codigo_comuna"], errors="coerce").astype(int)

    total = df.groupby("comuna_code")["beneficiarios"].sum()
    ab = (
        df[df["tramo_fonasa"].isin(["A", "B"])]
        .groupby("comuna_code")["beneficiarios"]
        .sum()
    )
    out = pd.DataFrame({"total": total, "ab": ab}).reset_index()
    out["pct_fonasa_tramo_a_b"] = (out["ab"] / out["total"] * 100).round(2)
    print(f"  [fonasa] {len(out)} communes in RM")
    return (
        out[["comuna_code", "pct_fonasa_tramo_a_b"]]
        .drop_duplicates("comuna_code")
        .reset_index(drop=True)
    )


def fetch_sinim_ipp(
    cache_dir: Path, url: str, region_code: int = 13
) -> pd.DataFrame:
    """SINIM Ingresos Propios Permanentes per Cápita (IPPP, M$/hab), latest year.

    Variable 1262 from bastianolea/sinim_info_municipal (Subdere, 2023).
    Returns ``[comuna_code, ipp_per_capita]``.
    """
    _empty = pd.DataFrame(columns=["comuna_code", "ipp_per_capita"])
    try:
        dest = _download_parquet(url, Path(cache_dir) / "ses_sinim.parquet")
        df = pd.read_parquet(dest)
    except Exception as exc:
        print(f"  [sinim] skipped: {exc}")
        return _empty

    # IPPP = Ingresos Propios Permanentes per Cápita (variable_id 1262, units M$)
    df = df[df["variable_id"].astype(str) == "1262"].copy()
    df = df[df["cut_comuna"].astype(str).str.startswith(str(region_code))].copy()
    if df.empty:
        print(f"  [sinim] no rows for region_code={region_code}")
        return _empty

    latest = int(df["año"].max())
    df = df[df["año"] == latest].copy()
    print(f"  [sinim] IPPP using year {latest}, {len(df)} communes")

    df["comuna_code"] = pd.to_numeric(df["cut_comuna"], errors="coerce").astype(int)
    df["ipp_per_capita"] = pd.to_numeric(df["valor"], errors="coerce").round(3)
    return (
        df[["comuna_code", "ipp_per_capita"]]
        .drop_duplicates("comuna_code")
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------- #
# Composite index
# --------------------------------------------------------------------------- #
def compute_nse_index(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Add ``nse_index``, ``nse_index_pca`` and ``nse_quintil``.

    Returns the augmented DataFrame and a dict of index diagnostics (PC1
    variance explained, loadings, weighting-sensitivity correlation).
    """
    comp_cols = [c for c, _ in INDEX_COMPONENTS]
    df = df.copy()

    # Orient so higher = better SES, then standardize (population std, ddof=0).
    oriented = pd.DataFrame(index=df.index)
    for col, sign in INDEX_COMPONENTS:
        x = df[col].astype(float)
        oriented[col] = sign * (x - x.mean()) / x.std(ddof=0)

    # Equal-weight composite.
    df["nse_index"] = oriented.mean(axis=1).round(3)

    # PCA via SVD on the standardized, oriented matrix (centred).
    X = oriented.to_numpy()
    X = X - X.mean(axis=0)
    _, S, Vt = np.linalg.svd(X, full_matrices=False)
    pc1 = X @ Vt[0]
    loadings_vec = Vt[0]
    # Orient PC1 to correlate positively with income (interpretability).
    if np.corrcoef(pc1, oriented["ingreso"].to_numpy())[0, 1] < 0:
        pc1 = -pc1
        loadings_vec = -loadings_vec
    pc1_z = (pc1 - pc1.mean()) / pc1.std(ddof=0)
    df["nse_index_pca"] = np.round(pc1_z, 3)

    # Quintiles from the robust PCA index (1 = most vulnerable, 5 = most affluent).
    df["nse_quintil"] = pd.qcut(
        df["nse_index_pca"], 5, labels=[1, 2, 3, 4, 5]
    ).astype(int)

    rho, pval = spearmanr(df["nse_index"], df["nse_index_pca"])
    info = {
        "components": comp_cols,
        "pca_variance_explained_pc1": round(float((S[0] ** 2) / (S ** 2).sum()), 4),
        "pca_loadings_pc1": {
            col: round(float(w), 4) for col, w in zip(comp_cols, loadings_vec)
        },
        "weighting_sensitivity_spearman_rho": round(float(rho), 4),
        "weighting_sensitivity_spearman_p": float(pval),
    }
    return df, info


# --------------------------------------------------------------------------- #
# External validation (optional, graceful skip)
# --------------------------------------------------------------------------- #
def validate_against_official(
    df: pd.DataFrame, cfg: dict[str, Any], repo_root: Path
) -> list[dict[str, Any]]:
    """Compare ``nse_index_pca`` against configured official indices.

    Each validation source is a dict in ``cfg['socioeconomic']['validation']
    ['sources']`` with: ``name``, ``path`` (relative to repo root), ``name_col``,
    ``value_col`` and optionally ``sep``, ``sheet`` and ``higher_is_better``.
    Missing/unreadable files are reported as skipped rather than raising.
    """
    ses_cfg = cfg.get("socioeconomic", {}) or {}
    specs = (ses_cfg.get("validation", {}) or {}).get("sources", []) or []
    results: list[dict[str, Any]] = []
    base = df.assign(name_key=df["name"].str.lower().str.strip())

    for spec in specs:
        name = spec.get("name", spec.get("path", "unknown"))
        path = repo_root / spec["path"]
        if not path.exists():
            results.append(
                {"source": name, "status": "skipped", "reason": f"file not found: {spec['path']}"}
            )
            continue
        try:
            if path.suffix.lower() in (".xlsx", ".xls"):
                ext = pd.read_excel(path, sheet_name=spec.get("sheet", 0))
            else:
                ext = pd.read_csv(path, sep=spec.get("sep", ";"), low_memory=False)
            ext = ext.rename(
                columns={spec["name_col"]: "name_raw", spec["value_col"]: "ext_value"}
            )
            ext["name_key"] = (
                demography.normalize_comuna_name(ext["name_raw"]).str.lower().str.strip()
            )
            ext["ext_value"] = _to_num(ext["ext_value"])
            merged = base.merge(
                ext[["name_key", "ext_value"]], on="name_key", how="inner"
            ).dropna(subset=["ext_value", "nse_index_pca"])
            if len(merged) < 10:
                results.append(
                    {"source": name, "status": "skipped", "reason": f"only {len(merged)} communes matched"}
                )
                continue
            sign = 1 if spec.get("higher_is_better", True) else -1
            rho, pval = spearmanr(merged["nse_index_pca"], sign * merged["ext_value"])
            results.append(
                {
                    "source": name,
                    "status": "ok",
                    "n_matched": int(len(merged)),
                    "spearman_rho": round(float(rho), 4),
                    "spearman_p": float(pval),
                    "higher_is_better": bool(spec.get("higher_is_better", True)),
                }
            )
        except Exception as err:  # noqa: BLE001
            results.append({"source": name, "status": "error", "reason": str(err)})
    return results


# --------------------------------------------------------------------------- #
# Layer builder
# --------------------------------------------------------------------------- #
def build_socioeconomic_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    validate: bool = True,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the socioeconomic exposome layer and write CSV + GeoJSON + metadata.

    Returns the commune-level table and its GeoDataFrame.
    """
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]

    ses_cfg = cfg.get("socioeconomic", {}) or {}
    sources = {**DEFAULT_SOURCES, **(ses_cfg.get("sources", {}) or {})}
    region_code = int(ses_cfg.get("region_code", 13))
    poverty_year = int(ses_cfg.get("poverty_year", 2022))
    poverty_raw_dir = Path(
        ses_cfg.get("poverty_raw_dir")
        or repo_root / "data" / "raw" / pobreza_sae.RAW_DIR_NAME
    )

    print(f"Building socioeconomic layer for {city}")

    # 1. Boundaries (geometry + canonical commune names).
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)

    # 2. Fetch core indicators (all keyed by comuna_code = INE CUT).
    print("  Fetching CASEN income + official MDSF SAE poverty + census housing...")
    pov = fetch_poverty_income_official(poverty_raw_dir, poverty_year, region_code)
    inc = fetch_casen_income_education(cache_dir, sources["casen_ingresos"], region_code)
    multi = fetch_poverty_multi_official(poverty_raw_dir, poverty_year, region_code)
    house = compute_housing_deprivation(cache_dir, region_code)
    code_name = demography.load_comuna_code_name_map(cache_dir, region_code=region_code)

    # 3. Merge core indicators and attach canonical commune name.
    ses = (
        code_name.merge(pov, on="comuna_code", how="left")
        .merge(inc, on="comuna_code", how="left")
        .merge(multi, on="comuna_code", how="left")
        .merge(house, on="comuna_code", how="left")
    )

    # 3b. Supplementary indicators (graceful skip if download fails).
    print("  Fetching supplementary indicators (crime, PAES, FONASA, SINIM)...")
    crime = fetch_crime_counts(cache_dir, sources["crime"], region_code)
    paes = fetch_paes_scores(cache_dir, sources["paes"], region_code)
    fonasa = fetch_fonasa_coverage(cache_dir, sources["fonasa"], region_code)
    sinim = fetch_sinim_ipp(cache_dir, sources["sinim"], region_code)

    ses = (
        ses
        .merge(crime, on="comuna_code", how="left")
        .merge(paes, on="comuna_code", how="left")
        .merge(fonasa, on="comuna_code", how="left")
        .merge(sinim, on="comuna_code", how="left")
    )
    # Crime rates per 100k (needs poblacion, which is already in ses from pov).
    if "delitos_violentos_n" in ses.columns:
        pop100k = ses["poblacion"].astype(float) / 100_000
        ses["tasa_delitos_violentos"] = (ses["delitos_violentos_n"] / pop100k).round(1)
        ses["tasa_delitos_propiedad"] = (ses["delitos_propiedad_n"] / pop100k).round(1)
        ses = ses.drop(columns=["delitos_violentos_n", "delitos_propiedad_n"])

    # 4. Composite indices.
    ses, index_info = compute_nse_index(ses)

    # 5. Join indicators onto the boundaries by a lowercased name key.
    df_bound = gdf_comm[["name", "area_km2"]].copy()
    df_bound["name_key"] = df_bound["name"].str.lower().str.strip()
    ses["name_key"] = ses["name"].str.lower().str.strip()
    df = df_bound.merge(
        ses.drop(columns=["name"]), on="name_key", how="left"
    ).drop(columns="name_key")

    supp_cols = [
        c for c in [
            "tasa_delitos_violentos", "tasa_delitos_propiedad",
            "paes_puntaje_promedio", "pct_fonasa_tramo_a_b", "ipp_per_capita",
        ]
        if c in df.columns
    ]
    col_order = _CORE_COLS + supp_cols
    df = df[col_order].copy()
    df["area_km2"] = df["area_km2"].round(2)

    # 6. Validate: exactly N rows, no duplicates, no NaN in core columns.
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df[_CORE_COLS].isna().any().any():
        missing = [c for c in _CORE_COLS if df[c].isna().any()]
        raise ValueError(f"Missing values in core columns: {missing}")
    if supp_cols:
        nan_supp = {c: int(df[c].isna().sum()) for c in supp_cols if df[c].isna().any()}
        if nan_supp:
            print(f"  Note: supplementary columns have NaN in some communes: {nan_supp}")

    # Cast integer columns now that completeness is guaranteed.
    df = df.astype({"poblacion": int, "ingreso": int, "nse_quintil": int})

    # 7. Optional external validation.
    validation_results = (
        validate_against_official(df, cfg, repo_root) if validate else []
    )

    # 8. Geo version.
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 9. Write outputs (keep the historical file name for master/demo compat).
    base_name = "socioeconomic_exposome_rm_santiago"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_rows": int(len(df)),
        "columns": df.columns.tolist(),
        "geographic_unit": "comuna (OSM admin_level=8)",
        "sources": {
            "casen_year": ses_cfg.get("casen_year", 2022),
            "income_education": {
                "vars": {"ytotcor": "ingreso", "esc": "escolaridad"},
                "provider": "CASEN 2022 via bastianolea/pobreza_chile",
                "url": sources["casen_ingresos"],
            },
            "income_poverty_sae": {
                "vars": {
                    "Porcentaje...": "pobreza_pct",
                    "Límite inferior": "pobreza_ci_low",
                    "Límite superior": "pobreza_ci_high",
                    "N proyección poblacional": "poblacion",
                },
                "provider": "MDSF official small-area estimation (SAE), Fay-Herriot",
                "path": str(poverty_raw_dir),
                "year": poverty_year,
                "note": (
                    "Replaces a prior third-party CSV (bastianolea/pobreza_chile/"
                    "pobreza_comunal.csv) found to mislabel 2022 multidimensional "
                    "poverty values as income poverty. See "
                    "docs/pobreza_sae_methodology.md."
                ),
            },
            "multidimensional_poverty": {
                "vars": {"Porcentaje...": "pobreza_multi_pct"},
                "provider": "MDSF official small-area estimation (SAE), Fay-Herriot",
                "path": str(poverty_raw_dir),
                "year": poverty_year,
                "note": (
                    "Replaces a prior CASEN direct-survey estimate "
                    "(bastianolea/pobreza_chile/casen_2022_pobreza.csv); now uses "
                    "the same SAE estimator family as pobreza_pct."
                ),
            },
            "housing": {
                "vars": {
                    "MATREC+MATIRREC / total": "viv_materialidad_deficitaria_pct",
                    "PERSONAS / CANT_HOG": "hacinamiento_phh",
                },
                "provider": "INE Censo 2017 (manzana level)",
            },
            "crime": {
                "vars": {
                    "delito_n (violent categories) / pop * 100k": "tasa_delitos_violentos",
                    "delito_n (property categories) / pop * 100k": "tasa_delitos_propiedad",
                },
                "provider": "CEAD via bastianolea/delincuencia_chile",
                "url": sources["crime"],
                "note": "supplementary column; NaN if download fails",
            },
            "paes": {
                "vars": {
                    "(paes_complectora + paes_matematica1) / 2": "paes_puntaje_promedio",
                },
                "provider": "Mineduc PAES 2024 via bastianolea/puntajes_prueba_paes",
                "url": sources["paes"],
                "note": "supplementary column; NaN if download fails",
            },
            "fonasa": {
                "vars": {
                    "tramo A+B beneficiarios / total": "pct_fonasa_tramo_a_b",
                },
                "provider": "Fonasa 2023 via bastianolea/fonasa_beneficiarios",
                "url": sources["fonasa"],
                "note": "supplementary column; NaN if download fails",
            },
            "sinim": {
                "vars": {
                    "variable_id 1262 (IPPP, M$/hab)": "ipp_per_capita",
                },
                "provider": "Subdere SINIM 2023 via bastianolea/sinim_info_municipal",
                "url": sources["sinim"],
                "note": "supplementary column; NaN if download fails",
            },
        },
        "index": {
            "orientation": "higher = better socioeconomic position",
            "components": [
                {"col": c, "direction": "+" if s > 0 else "-"}
                for c, s in INDEX_COMPONENTS
            ],
            "nse_index": "equal-weight mean of standardized, sign-oriented components",
            "nse_index_pca": "first principal component (numpy SVD), z-scored",
            **index_info,
        },
        "external_validation": validation_results,
        "outputs": [f"{base_name}.csv", f"{base_name}.geojson"],
    }
    (out_dir / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    supp_ok = [c for c in supp_cols if df[c].notna().any()]
    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols; "
          f"supplementary: {supp_ok or 'none'})")
    print(
        f"  PC1 explains {index_info['pca_variance_explained_pc1']:.1%} of variance; "
        f"equal-weight vs PCA Spearman ρ={index_info['weighting_sensitivity_spearman_rho']}"
    )
    for v in validation_results:
        if v["status"] == "ok":
            print(f"  Validation vs {v['source']}: ρ={v['spearman_rho']} (n={v['n_matched']})")
        else:
            print(f"  Validation vs {v['source']}: {v['status']} ({v.get('reason', '')})")
    return df, gdf

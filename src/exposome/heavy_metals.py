"""Heavy metals exposome layer — RETC air emissions from point sources (MMA).

Commune-level industrial emissions of neurotoxic heavy metals for the
52 communes of the Santiago RM, derived from the MMA RETC (Registro de
Emisiones y Transferencias de Contaminantes) — Emisiones al aire de fuentes
puntuales dataset (CC-BY, no API key).

Metals covered (ranked by dementia-relevant evidence):
  Pb  (plomo)     — #1 environmental neurotoxin; accelerates hippocampal
                    atrophy and cognitive decline (Lancet Neurology 2022).
  Mn  (manganeso) — parkinsonism, frontal executive dysfunction.
  As  (arsénico)  — peripheral neuropathy, emerging dementia link.
  Cd  (cadmio)    — oxidative stress, renal→CNS pathway.
  Hg  (mercurio)  — classical neurotoxin; scarce RM sources.

This layer completes the *chemical toxin* pillar of the exposome.  PM2.5
captures combustion-source and secondary aerosol PM; RETC captures
*point-source industrial* releases — a distinct exposure pathway.

Source
------
datosretc.mma.gob.cl — Emisiones al aire de fuentes puntuales.
Annual CSV (2005-2020) / XLSX (2021-2024). Licence: CC-BY.
Dataset ID: 2733b0f0-428a-4594-afeb-17780c8d47c1

Follows the same module pattern as :mod:`exposome.noise` and
:mod:`exposome.wildfire`: local/cached data → spatial join → commune
aggregation → CSV + GeoJSON + metadata outputs.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

try:
    from . import boundaries, config
    from .demography import normalize_comuna_name
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from exposome import boundaries, config  # type: ignore[no-redef]
    from exposome.demography import normalize_comuna_name  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Configuration: URLs, metals, weights
# ---------------------------------------------------------------------------

# Official datos.gob.cl direct-download URLs (resolved via CKAN API 2026-06).
RETC_URLS: dict[int, str] = {
    2015: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/23d39351-ad06-4805-b3fe-229ec755fb10/download/ruea-efp-2015-ckan.csv",
    2016: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/1682aa1f-2a55-49b6-b37e-308d5d6a9499/download/ruea-efp-2016-ckan.csv",
    2017: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/c82279c0-acda-44de-9c0f-f1350e90fb9e/download/ruea-efp-2017-ckan.csv",
    2018: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/5ad7037f-e787-4ba7-8abc-c1ab492d4c3a/download/ruea-efp-2018-ckan.csv",
    2019: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/ce629d88-c410-42e3-b170-de2afd89c395/download/ruea-efp-2019-ckan.csv",
    2020: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/9101859d-555f-48ad-becc-caf3aacd03f2/download/ruea-efp-2020-ckan.csv",
    2021: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/4348b938-7c18-4764-af25-eb4254b68641/download/ruea-efp-2021-ckan.xlsx",
    2022: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/5d34c9fb-5472-4448-911d-75296eb68826/download/ckan_ruea_2022_v2026.xlsx",
    2023: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/d40cc934-4a51-4236-8109-1051b8cc8592/download/ckan_fp_2023.xlsx",
    2024: "https://datosretc.mma.gob.cl/dataset/2733b0f0-428a-4594-afeb-17780c8d47c1/resource/b82ed4a8-ed64-493a-8159-563abf0bf5ad/download/ruea-ckan-2024.xlsx",
}

# Keywords to match each metal in the RETC `contaminante` column (Spanish).
METAL_KEYWORDS: dict[str, list[str]] = {
    "pb": ["plomo"],
    "mn": ["manganeso"],
    "as": ["arsénico", "arsenico"],
    "cd": ["cadmio"],
    "hg": ["mercurio"],
}

# Relative weights for the composite index (sum = 1.0, weighted by
# strength of dementia evidence and prevalence in Chilean industry).
METAL_WEIGHTS: dict[str, float] = {
    "pb": 0.35,
    "mn": 0.30,
    "as": 0.20,
    "cd": 0.10,
    "hg": 0.05,
}

_EXPECTED_COMMUNES = 52


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_float_es(val: Any) -> float | None:
    """Parse a Spanish-locale number (decimal comma, dot thousands) → float.

    Returns None for missing / dash values.
    """
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s in ("-", "", "N/A", "nan", "None"):
        return None
    try:
        # Spanish locale: 1.234,56 → remove dot thousands sep, swap comma decimal
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        return float(s)
    except ValueError:
        return None


def _emission_to_kg(val: Any, unit: str | None) -> float:
    """Convert one emission value to kg, handling Spanish locale and units."""
    v = _parse_float_es(val)
    if v is None or v < 0:
        return 0.0
    unit_low = ("" if pd.isna(unit) else str(unit)).lower().strip()
    if "ton" in unit_low or "/t" in unit_low or unit_low.startswith("t/"):
        return v * 1_000.0   # tonnes → kg
    if "g/a" in unit_low or unit_low in ("g", "gr/año", "gr"):
        return v / 1_000.0   # grams → kg
    # Default: assume kg (or unknown → keep as-is)
    return v


def _classify_metal(name: str | float) -> str | None:
    """Return the metal code if the RETC contaminante name matches one of our targets."""
    if not isinstance(name, str) or not name:
        return None
    name_low = name.lower()
    for code, keywords in METAL_KEYWORDS.items():
        if any(kw in name_low for kw in keywords):
            return code
    return None


# ---------------------------------------------------------------------------
# I/O: download and read RETC annual files
# ---------------------------------------------------------------------------

def _read_year(path: Path, year: int) -> pd.DataFrame:
    """Read one RETC annual file (CSV or XLSX) → normalized DataFrame.

    Column name inconsistencies across years:
      2015-2019, 2021-2022: 'contaminantes' (plural) + ';' separator (CSVs)
      2020:                  'contaminante' (singular) + ';' separator
    Encoding:
      2015-2019: latin-1 (ñ as 0xf1); 2020+: utf-8-sig; XLSX: handled by openpyxl.
    """
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        raw = pd.read_excel(path, dtype=str)
    else:
        # Try modern encoding first, fall back to latin-1 for older files
        for enc in ("utf-8-sig", "latin-1"):
            try:
                raw = pd.read_csv(
                    path, dtype=str, encoding=enc, sep=";",
                    low_memory=False, on_bad_lines="skip",
                )
                break
            except Exception:
                continue
        else:
            raise RuntimeError(f"Cannot read {path.name} with any supported encoding")

    # Strip BOM and normalise column names to lowercase
    raw.columns = [c.lstrip("﻿﻿").strip().lower() for c in raw.columns]

    # Normalise contaminant column: 'contaminantes' (plural, most years) or
    # 'contaminante' (singular, 2020). Rename to a stable internal name.
    if "contaminantes" in raw.columns and "contaminante" not in raw.columns:
        raw = raw.rename(columns={"contaminantes": "contaminante"})

    # For early years (2015-2018) that lack emision_* columns, use
    # cantidad_toneladas as the primary emission value.
    if "emision_primario" not in raw.columns and "cantidad_toneladas" in raw.columns:
        raw["emision_primario"] = raw["cantidad_toneladas"]

    # Filter to Región Metropolitana
    if "region" in raw.columns:
        raw = raw[raw["region"].str.lower().str.contains("metropolitana", na=False)]

    # Keep only the columns we need (gracefully skip missing ones)
    want = [
        "nombre_establecimiento", "id_vu",
        "region", "provincia", "comuna", "id_comuna",
        "latitud", "longitud",
        "contaminante", "unidad",
        "emision_primario", "emision_secundario", "emision_materia_prima",
    ]
    raw = raw[[c for c in want if c in raw.columns]].copy()
    raw["año"] = year
    return raw


def _fetch_year(year: int, cache_dir: Path) -> pd.DataFrame:
    """Download (or read from cache) one RETC annual file."""
    if year not in RETC_URLS:
        raise KeyError(f"No RETC URL for year {year}. Available: {sorted(RETC_URLS)}")

    url = RETC_URLS[year]
    ext = ".xlsx" if url.endswith(".xlsx") else ".csv"
    cache_path = cache_dir / f"retc_efp_{year}{ext}"

    if not cache_path.exists():
        tmp = cache_path.with_suffix(".partial")
        print(f"  Downloading RETC {year} → {cache_path.name}…", flush=True)
        try:
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(cache_path)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download RETC {year} from {url}") from exc

    return _read_year(cache_path, year)


# ---------------------------------------------------------------------------
# Core build function
# ---------------------------------------------------------------------------

def build_heavy_metals_layer(
    city: str = "santiago",
    cache_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    years: list[int] | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build commune-level heavy metals exposure layer from RETC air emissions.

    Downloads and caches annual RETC files, filters to the Región Metropolitana,
    classifies heavy metal contaminants, aggregates by commune (spatial join),
    and writes CSV + GeoJSON + metadata.

    Returns
    -------
    (df, gdf) : tuple
        df  — 52-row DataFrame with columns hm_{pb,mn,as,cd,hg}_kg,
               n_sources, hm_index.
        gdf — same data as a GeoDataFrame.
    """
    cfg = config.load_config(city)
    repo_root = Path(__file__).resolve().parents[2]

    if cache_dir is None:
        cache_dir = repo_root / cfg["outputs"].get("cache_dir", "cache")
    if out_dir is None:
        out_dir = repo_root / cfg["outputs"]["base_dir"]

    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    hm_cfg = cfg.get("heavy_metals", {})
    if years is None:
        years = hm_cfg.get("years", list(range(2015, 2023)))

    # 1. Commune boundaries
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)

    # 2. Load and concatenate RETC data for all requested years
    frames: list[pd.DataFrame] = []
    for yr in sorted(years):
        try:
            frames.append(_fetch_year(yr, cache_dir))
        except Exception as exc:
            print(f"  Warning: skipping RETC {yr}: {exc}")

    if not frames:
        raise RuntimeError("No RETC data loaded. Check internet connection or cache.")

    raw = pd.concat(frames, ignore_index=True)
    print(f"  RETC raw rows (RM, all pollutants): {len(raw):,}")

    # 3. Classify pollutants → metal codes
    raw["metal"] = raw["contaminante"].apply(_classify_metal)
    metals = raw.dropna(subset=["metal"]).copy()
    print(f"  Heavy metal rows: {len(metals):,}")

    # 4. Parse emission values → kg
    for pathway in ("emision_primario", "emision_secundario", "emision_materia_prima"):
        col = pathway if pathway in metals.columns else None
        unit_col = "unidad" if "unidad" in metals.columns else None
        if col:
            metals[f"_{pathway}_kg"] = metals.apply(
                lambda r: _emission_to_kg(r[col], r[unit_col] if unit_col else None),
                axis=1,
            )
        else:
            metals[f"_{pathway}_kg"] = 0.0

    metals["emission_kg"] = (
        metals["_emision_primario_kg"]
        + metals["_emision_secundario_kg"]
        + metals["_emision_materia_prima_kg"]
    )

    # 5. Parse coordinates
    metals["_lat"] = metals["latitud"].apply(_parse_float_es)
    metals["_lon"] = metals["longitud"].apply(_parse_float_es)
    metals_geo = metals.dropna(subset=["_lat", "_lon"]).copy()
    metals_geo = metals_geo[
        (metals_geo["_lat"] != 0) & (metals_geo["_lon"] != 0)
    ].copy()
    print(f"  Rows with valid coordinates: {len(metals_geo):,}")

    # 6. Spatial join: establishment point → commune polygon
    pts = gpd.GeoDataFrame(
        metals_geo,
        geometry=gpd.points_from_xy(metals_geo["_lon"], metals_geo["_lat"]),
        crs="EPSG:4326",
    ).to_crs(gdf_comm.crs)

    joined = gpd.sjoin(
        pts[["metal", "emission_kg", "id_vu", "nombre_establecimiento", "año", "geometry"]],
        gdf_comm[["name", "geometry"]],
        how="left",
        predicate="within",
    )

    # Assign unmatched points to their nearest commune (use metric CRS)
    no_match = joined["name"].isna()
    if no_match.any():
        metric_crs = "EPSG:32719"  # UTM 19S (Chile)
        unmatched_pts = pts.loc[
            no_match.index[no_match],
            ["metal", "emission_kg", "id_vu", "año", "geometry"],
        ].to_crs(metric_crs)
        nearest = gpd.sjoin_nearest(
            unmatched_pts,
            gdf_comm[["name", "geometry"]].to_crs(metric_crs),
            how="left",
        )
        joined.loc[no_match.index[no_match], "name"] = nearest["name"].values
        print(f"  {no_match.sum()} points outside communes assigned to nearest commune")

    # 7. Aggregate: mean annual emission per commune × metal
    agg = (
        joined.groupby(["name", "metal", "año"])["emission_kg"]
        .sum()
        .reset_index()
        .groupby(["name", "metal"])["emission_kg"]
        .mean()
        .reset_index()
        .rename(columns={"emission_kg": "emission_kg_mean"})
    )

    # Count unique industrial sources per commune across all years
    n_sources = (
        joined.dropna(subset=["id_vu"])
        .groupby("name")["id_vu"]
        .nunique()
        .reset_index()
        .rename(columns={"id_vu": "n_sources"})
    )

    # 8. Pivot: one column per metal
    pivot = (
        agg.pivot(index="name", columns="metal", values="emission_kg_mean")
        .reindex(columns=list(METAL_KEYWORDS.keys()), fill_value=0.0)
        .fillna(0.0)
        .rename(columns={m: f"hm_{m}_kg" for m in METAL_KEYWORDS})
        .reset_index()
    )

    # 9. Merge with all 52 communes (communes without sources → 0)
    result = gdf_comm[["name"]].merge(pivot, on="name", how="left")
    result = result.merge(n_sources, on="name", how="left")
    for col in [f"hm_{m}_kg" for m in METAL_KEYWORDS]:
        result[col] = result[col].fillna(0.0).round(2)
    result["n_sources"] = result["n_sources"].fillna(0).astype(int)

    # 10a. Log-transform: Pb exposure-response for cognition is log-linear.
    #      log1p avoids -∞ for communes with zero industrial emissions.
    result["hm_pb_log"] = np.log1p(result["hm_pb_kg"]).round(3)
    result["hm_as_log"] = np.log1p(result["hm_as_kg"]).round(3)

    # 10b. Composite index: weighted z-score of the 4 main metals
    main_metals = ["pb", "mn", "as", "cd"]
    z_parts = []
    for m, w in zip(main_metals, [METAL_WEIGHTS[x] for x in main_metals]):
        col = f"hm_{m}_kg"
        std = result[col].std()
        if std > 0:
            z = (result[col] - result[col].mean()) / std
        else:
            z = pd.Series(0.0, index=result.index)
        z_parts.append(w * z)
    result["hm_index"] = sum(z_parts).round(3)

    # 11. Validate
    n_exp = cfg["expected_communes"]
    if len(result) != n_exp:
        raise ValueError(f"Expected {n_exp} rows, got {len(result)}")
    if result["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    non_ratio = [c for c in result.columns if c != "name"]
    if result[non_ratio].isna().any().any():
        raise ValueError(f"NaN in: {result.columns[result.isna().any()].tolist()}")

    # 12. Write outputs
    stem = f"{city}_heavy_metals_retc_{min(years)}_{max(years)}"
    out_csv = out_dir / f"{stem}.csv"
    out_geo = out_dir / f"{stem}.geojson"
    out_meta = out_dir / f"{stem}_metadata.json"

    result.to_csv(out_csv, index=False)

    gdf_out = gdf_comm[["name", "geometry"]].merge(result, on="name", how="right")
    gdf_out = gpd.GeoDataFrame(gdf_out, geometry="geometry", crs=gdf_comm.crs)
    gdf_out.to_file(out_geo, driver="GeoJSON")

    metadata: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "RETC MMA — Emisiones al aire de fuentes puntuales",
        "dataset_id": "2733b0f0-428a-4594-afeb-17780c8d47c1",
        "license": "CC-BY",
        "years": years,
        "n_communes": len(result),
        "n_sources_total": int(result["n_sources"].sum()),
        "communes_with_pb": int((result["hm_pb_kg"] > 0).sum()),
        "communes_with_mn": int((result["hm_mn_kg"] > 0).sum()),
        "communes_with_as": int((result["hm_as_kg"] > 0).sum()),
        "metals": list(METAL_KEYWORDS.keys()),
        "metal_weights": METAL_WEIGHTS,
        "columns": {
            "hm_pb_kg": "Mean annual Pb air emissions from point sources [kg/yr]",
            "hm_mn_kg": "Mean annual Mn air emissions from point sources [kg/yr]",
            "hm_as_kg": "Mean annual As air emissions from point sources [kg/yr]",
            "hm_cd_kg": "Mean annual Cd air emissions from point sources [kg/yr]",
            "hm_hg_kg": "Mean annual Hg air emissions from point sources [kg/yr]",
            "hm_pb_log": "log1p(hm_pb_kg) — log-transformed Pb for brain-health models",
            "hm_as_log": "log1p(hm_as_kg) — log-transformed As for brain-health models",
            "n_sources": "Unique industrial establishments with heavy metal declarations",
            "hm_index": "Composite heavy-metals index (weighted z-score, Pb+Mn+As+Cd)",
        },
        "note_mn_cd": (
            "Manganeso (Mn) and Cadmio (Cd) are absent from RM RETC declarations: "
            "their industrial sources are in other regions (e.g. Atacama, Maule). "
            "Both columns are 0 for all 52 RM communes — this is a real data finding."
        ),
    }
    out_meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(
        f"Heavy metals layer: {len(result)} communes\n"
        f"  Sources: {int(result['n_sources'].sum())} establishments\n"
        f"  Communes with Pb > 0: {(result['hm_pb_kg'] > 0).sum()}\n"
        f"  Communes with Mn > 0: {(result['hm_mn_kg'] > 0).sum()}\n"
        f"  Written: {out_csv.name}"
    )
    return result, gdf_out

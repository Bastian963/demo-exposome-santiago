"""Export 52 per-commune profiles for on-demand loading.

Each profile is a JSON file at ``webapp/public/data/profiles/{slug}.json``
that contains:

- Basic identifiers (name, slug).
- EBI (score, rank, db, ebi_pca).
- Cluster assignment.
- LISA quadrant.
- All 272 indicators from the master (numeric, rounded to 3 dp).
- DEIS neuro outcomes (mortality + hospitalizations).
- Time-series trends (4 vars × 10 years, when available).

Loaded on-demand when the user clicks a commune.
"""
from __future__ import annotations

import json
import numbers
import sys
import unicodedata
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
DST_DIR = REPO_ROOT / "webapp" / "public" / "data" / "profiles"
DST_DIR.mkdir(parents=True, exist_ok=True)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in s if c.isalnum() or c == "_").strip("_") or "unknown"


def round_floats(obj, decimals: int = 3) -> object:
    if isinstance(obj, numbers.Integral):
        return int(obj)
    if isinstance(obj, numbers.Real):
        value = float(obj)
        if value != value:
            return None
        return round(value, decimals)
    if isinstance(obj, dict):
        return {k: round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, decimals) for v in obj]
    return obj


def main() -> None:
    print("Loading master CSV (272 cols)...")
    master = pd.read_csv(DATA_DIR / "santiago_exposome_master.csv")
    master = master.set_index("name")

    print("Loading EBI sidecar...")
    ebi = pd.read_csv(DATA_DIR / "environmental_burden_index.csv")
    ebi = ebi.set_index("name")

    print("Loading clusters...")
    clusters = pd.read_csv(DATA_DIR / "commune_clusters.csv")
    clusters = clusters.set_index("name")

    print("Loading bivariate LISA...")
    with open(DATA_DIR / "bivariate_lisa.json") as f:
        lisa = json.load(f)
    lisa_ebinse = {n: "NS" for n in master.index}
    lisa_nseebi = {n: "NS" for n in master.index}
    for label, q in (("HH", 1), ("LH", 2), ("LL", 3), ("HL", 4), ("NS", 0)):
        for n in lisa["direction_ebinse"].get(f"members_{label}", []):
            lisa_ebinse[n] = label
        for n in lisa["direction_nseebi"].get(f"members_{label}", []):
            lisa_nseebi[n] = label

    print("Loading DEIS mortality...")
    mort = pd.read_csv(DATA_DIR / "santiago_neuro_mortality_2018_2022.csv")
    mort_dict: dict[str, dict] = {}
    for _, row in mort.iterrows():
        n = row["name"]
        outcome = row["outcome"]
        mort_dict.setdefault(n, {})[
            f"mortality_{outcome}_age_adjusted_per_100k"
        ] = round(float(row["mortality_rate_age_adjusted_per_100k"]), 3)

    print("Loading DEIS hospitalizations...")
    hosp = pd.read_csv(DATA_DIR / "santiago_neuro_hospitalizations_2006_2006.csv")
    hosp_dict: dict[str, dict] = {}
    for _, row in hosp.iterrows():
        n = row["name"]
        outcome = row["outcome"]
        hosp_dict.setdefault(n, {})[
            f"hosp_{outcome}_age_adjusted_per_100k"
        ] = round(float(row["hospital_rate_age_adjusted_per_100k"]), 3)

    print("Loading time-series trends (when present)...")
    trends_csv = DATA_DIR / "time_series_trends.csv"
    trends_dict: dict[str, dict] = {}
    if trends_csv.exists():
        trends = pd.read_csv(trends_csv)
        for _, row in trends.iterrows():
            n = row["name"]
            var = row["variable"]
            val = row.get("sens_slope", None)
            if val is not None and pd.notna(val):
                trends_dict.setdefault(n, {})[var] = round(float(val), 4)

    # Load per-year annual PM2.5 CSVs (when present) and build a
    # timeseries dict: { commune_name: [{year, value}, ...] }
    print("Loading annual PM2.5 timeseries (when present)...")
    pm25_timeseries: dict[str, list] = {}
    for year in range(2015, 2023):
        ann_csv = DATA_DIR / f"santiago_pm25_acag_{year}.csv"
        if not ann_csv.exists():
            continue
        ann = pd.read_csv(ann_csv)
        if "name" not in ann.columns:
            continue
        pm25_col = "pm25_mean" if "pm25_mean" in ann.columns else (
            [c for c in ann.columns if c.startswith("pm25_") and c != "pm25_std"] + [None]
        )[0]
        if not pm25_col or pm25_col not in ann.columns:
            continue
        for _, row in ann.iterrows():
            n = row["name"]
            v = row[pm25_col]
            if pd.notna(v):
                pm25_timeseries.setdefault(n, []).append({
                    "year": year,
                    "value": round(float(v), 3),
                })

    print("Writing 52 profiles...")
    n = 0
    for name in master.index:
        slug = slugify(name)
        # Indicators: all master cols (numeric only).
        ind = master.loc[name]
        indicators = {
            k: round_floats(v, 3)
            for k, v in ind.items()
            if isinstance(v, numbers.Number) and pd.notna(v)
        }
        # EBI subset.
        if name in ebi.index:
            ebi_row = ebi.loc[name]
            ebi_data = {
                "score": round(float(ebi_row.get("ebi_score", 0)), 4),
                "rank": int(ebi_row.get("ebi_rank", 0)),
                "db_score": round(float(ebi_row.get("db_score", 0)), 4),
                "ebi_pca_score": round(float(ebi_row.get("ebi_pca_score", 0)), 4),
                "effective_dose_mean": round(
                    float(ebi_row.get("effective_dose_mean", 0)), 4
                ),
            }
        else:
            ebi_data = {}
        # Cluster.
        if name in clusters.index:
            cluster = {
                "id": int(clusters.loc[name, "cluster_id"]),
                "label": str(clusters.loc[name, "cluster_label"]),
            }
        else:
            cluster = {"id": -1, "label": "unknown"}
        # LISA quadrant (EBI x NSE direction).
        lisa_quad = lisa_ebinse.get(name, "NS")

        profile = {
            "name": name,
            "slug": slug,
            "cluster": cluster,
            "lisa_quadrant": lisa_quad,
            "nse_quintil": int(indicators.get("nse_quintil", 0)),
            "indicators": indicators,
            "ebi": ebi_data,
            "neuro_outcomes": {**mort_dict.get(name, {}), **hosp_dict.get(name, {})},
            "trends": trends_dict.get(name, {}),
            "timeseries": {
                "pm25": pm25_timeseries.get(name, []),
            },
        }
        out = DST_DIR / f"{slug}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, separators=(",", ":"))
        n += 1
    print(f"  Wrote {n} profiles to {DST_DIR}")
    total = sum(p.stat().st_size for p in DST_DIR.glob("*.json"))
    print(f"  Total size: {total / 1024:.1f} KB ({total / n / 1024:.1f} KB avg)")


if __name__ == "__main__":
    main()

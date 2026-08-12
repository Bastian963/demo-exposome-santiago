"""Fase B2: indirect age-standardization of hospital admissions -> observed/expected.

Mirror of build_smr_by_cause.py but for the DEIS hospital-discharge morbidity
table (scripts/run_neuro_hospitalizations.py output). Produces the same schema
(name, outcome, observed, expected, smr, pop_total) so the exposure sweep and NB
regression can consume it unchanged.

IMPORTANT (temporal caveat): only egresos 2006 is on disk. A single historical
year with no antecedent-matched exposure window is a SMOKE TEST of the pipeline,
NOT a valid chronic-exposome morbidity result. The output filename carries the
year span; interpret 2006-only output as a code/plumbing check. The scientifically
valid run needs the 2018-2022 egresos (see the coverage_gap block in the
hospitalization metadata json and docs/methodology_chronic_exposome_mortality.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import demography  # noqa: E402

PROC_DIR = REPO_ROOT / "data" / "processed"
OUT_CSV = PROC_DIR / "analysis" / "santiago_hosp_smr_by_cause.csv"
CACHE_DIR = REPO_ROOT / "cache"
AGE_BINS = ("0_14", "15_64", "65_plus")


def _find_hosp_csv() -> Path:
    candidates = sorted(PROC_DIR.glob("santiago_neuro_hospitalizations_[0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9].csv"))
    if not candidates:
        raise FileNotFoundError(
            "No santiago_neuro_hospitalizations_*.csv found. Run "
            "scripts/run_neuro_hospitalizations.py first."
        )
    return candidates[-1]


def main() -> None:
    hosp_csv = _find_hosp_csv()
    hosp = pd.read_csv(hosp_csv)
    year_start = int(hosp["hospital_year_start"].iloc[0])
    year_end = int(hosp["hospital_year_end"].iloc[0])
    n_years = int(hosp["hospital_n_years"].iloc[0])

    demo = demography.load_commune_demography(CACHE_DIR, region_code=13)
    demo = demo.set_index("name")[["pop_0_14", "pop_15_64", "pop_65_plus", "pop_total"]]

    rows = []
    for outcome, sub in hosp.groupby("outcome"):
        sub = sub.set_index("name")
        ref_rates = {}
        for age_bin in AGE_BINS:
            total_adm = sub[f"hospital_admissions_{age_bin}"].sum()
            total_pop = demo.loc[sub.index, f"pop_{age_bin}"].sum()
            ref_rates[age_bin] = total_adm / (total_pop * n_years)

        for name in sub.index:
            observed = float(sub.loc[name, "hospital_admissions_total"])
            expected = sum(
                ref_rates[age_bin] * demo.loc[name, f"pop_{age_bin}"] * n_years
                for age_bin in AGE_BINS
            )
            rows.append({
                "name": name,
                "outcome": outcome,
                "observed": observed,
                "expected": round(expected, 4),
                "smr": round(observed / expected, 4) if expected > 0 else float("nan"),
                "pop_total": float(demo.loc[name, "pop_total"]),
            })

    out = pd.DataFrame(rows).sort_values(["outcome", "name"]).reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    smoke = " (SINGLE-YEAR SMOKE TEST, not a valid chronic result)" if n_years == 1 else ""
    print(f"Wrote {OUT_CSV} ({len(out)} rows) from {hosp_csv.name}")
    print(f"Hospital window: {year_start}-{year_end}  n_years={n_years}{smoke}\n")
    for outcome in ["all_cause", "cardiovascular", "respiratory",
                    "respiratory_pneumonia", "respiratory_copd"]:
        sub = out[out["outcome"] == outcome]
        if sub.empty:
            continue
        print(f"{outcome:24s} sum(obs)={sub['observed'].sum():>8.0f}  "
              f"sum(exp)={sub['expected'].sum():>8.0f}  "
              f"SMR=[{sub['smr'].min():.2f}, {sub['smr'].max():.2f}]")


if __name__ == "__main__":
    main()

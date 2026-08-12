"""Indirect age-standardization: observed vs expected deaths per commune (Paso 3 prep).

The existing neuro_mortality pipeline produces a DIRECTLY age-adjusted rate
(commune's own age-specific rates weighted by a fixed standard population).
For a Poisson/NB SMR regression we instead need INDIRECT standardization:
apply city-wide reference age-specific rates to each commune's population by
age band to get "expected" deaths, then compare to "observed". This is the
offset= log(expected) used by build_smr_regression.py.

Reuses: santiago_neuro_mortality_2018_2022.csv (observed deaths by age bin,
already built by scripts/run_neuro_mortality.py) + commune demography (same
source the mortality pipeline already uses).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import demography  # noqa: E402

MORT_CSV = REPO_ROOT / "data" / "processed" / "santiago_neuro_mortality_2018_2022.csv"
OUT_CSV = REPO_ROOT / "data" / "processed" / "analysis" / "santiago_mortality_smr_by_cause.csv"
CACHE_DIR = REPO_ROOT / "cache"
AGE_BINS = ("0_14", "15_64", "65_plus")
N_YEARS = 5  # 2018-2022


def main() -> None:
    mort = pd.read_csv(MORT_CSV)
    demo = demography.load_commune_demography(CACHE_DIR, region_code=13)
    demo = demo.set_index("name")[["pop_0_14", "pop_15_64", "pop_65_plus", "pop_total"]]

    rows = []
    for outcome, sub in mort.groupby("outcome"):
        sub = sub.set_index("name")

        # City-wide reference age-specific rate (pooled across all 52 communes).
        ref_rates = {}
        for age_bin in AGE_BINS:
            total_deaths = sub[f"mortality_deaths_{age_bin}"].sum()
            total_pop = demo.loc[sub.index, f"pop_{age_bin}"].sum()
            ref_rates[age_bin] = total_deaths / (total_pop * N_YEARS)

        for name in sub.index:
            observed = float(sub.loc[name, "mortality_deaths_total"])
            expected = sum(
                ref_rates[age_bin] * demo.loc[name, f"pop_{age_bin}"] * N_YEARS
                for age_bin in AGE_BINS
            )
            rows.append(
                {
                    "name": name,
                    "outcome": outcome,
                    "observed": observed,
                    "expected": round(expected, 4),
                    "smr": round(observed / expected, 4) if expected > 0 else float("nan"),
                    "pop_total": float(demo.loc[name, "pop_total"]),
                }
            )

    out = pd.DataFrame(rows).sort_values(["outcome", "name"]).reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    print(f"Wrote {OUT_CSV} ({len(out)} rows)")
    for outcome in ["all_cause", "cardiovascular", "respiratory"]:
        sub = out[out["outcome"] == outcome]
        if sub.empty:
            continue
        print(f"\n{outcome}: sum(observed)={sub['observed'].sum():.0f}  sum(expected)={sub['expected'].sum():.1f}"
              f"  SMR range=[{sub['smr'].min():.2f}, {sub['smr'].max():.2f}]")


if __name__ == "__main__":
    main()

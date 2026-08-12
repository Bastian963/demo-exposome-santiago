# Full-text papers for NotebookLM

> **DO NOT READ THESE PDFS DIRECTLY.**
>
> This folder contains the complete PDF versions of papers used as sources in
> NotebookLM. The structured summaries, methodological notes and syntheses live
> in the conversation with NotebookLM (and, where available, in the sibling
> `*.md` bibliographic cards). Use those for quick reference; use these PDFs only
> as indexed sources inside NotebookLM.

## Folder structure

```
full_papers/
├── climate_heat/      # Temperature, heat waves, cold spells, UHI, ozono+heat
├── air_quality/       # Air pollution, PM, NO2, O3 and cognitive decline / dementia
└── green_space/       # Greenness, NDVI, parks and brain health / dementia
```

## Climate & heat

| File | Title | Authors | Year | DOI |
|------|-------|---------|------|-----|
| `2019_wei_seasonal_temperature_dementia_hospitalizations_newengland.pdf` | Associations between seasonal temperature and dementia-associated hospitalizations in New England | Wei et al. | 2019 | `10.1016/j.envint.2018.12.054` |
| `2023_hou_ambient_temperature_cognitive_function_china.pdf` | Ambient temperatures associated with reduced cognitive function in older adults in China | Hou | 2023 | `10.1038/s41598-023-44776-2` |
| `2023_yan_heat_stress_ozone_bbb_cognitive_impairment.pdf` | Combined exposure of heat stress and ozone enhanced cognitive impairment via neuroinflammation and blood brain barrier disruption in male rats | Yan et al. | 2023 | `10.1016/j.scitotenv.2022.159599` |
| `2024_gao_heat_exposure_dementia_mortality_china.pdf` | Heat Exposure and Dementia-Related Mortality in China | Gao et al. | 2024 | `10.1001/jamanetworkopen.2024.19250` |
| `2024_liu_extreme_temperature_dementia_mortality_china.pdf` | Extreme temperature events and dementia mortality in Chinese adults: a population-based, case-crossover study | Liu et al. | 2024 | `10.1093/ije/dyad119` |

## Air quality

| File | Title | Authors | Year | DOI |
|------|-------|---------|------|-----|
| `2018_cipriani_air_pollution_cognitive_dysfunction.pdf` | Danger in the Air: Air Pollution and Cognitive Dysfunction | Cipriani et al. | 2018 | `10.1177/1533317518777859` |
| `2025_park_air_pollution_alzheimer_dementia.pdf` | Air Pollution as an Environmental Risk Factor for Alzheimer's Disease and Related Dementias | Park et al. | 2025 | (NIHMS preprint / pending DOI) |
| `2025_rogowski_longterm_air_pollution_dementia_metaanalysis.pdf` | Long-term air pollution exposure and incident dementia: a systematic review and meta-analysis | Rogowski | 2025 | `10.1016/S2542-5196(25)00118-4` |

## Green space

| File | Title | Authors | Year | DOI |
|------|-------|---------|------|-----|
| `2021_besser_outdoor_greenspace_alzheimer_rapid_review.pdf` | Outdoor green space exposure and brain health measures related to Alzheimer's disease: a rapid review | Besser | 2021 | `10.1136/bmjopen-2020-043456` |
| `2022_zagnoli_greenness_dementia_metaanalysis.pdf` | Is Greenness Associated with Dementia? A Systematic Review and Dose–Response Meta-analysis | Zagnoli | 2022 | `10.1007/s40572-022-00365-5` |
| `2024_hu_yang_greenspace_cognitive_decline.pdf` | Invited Perspective: More Greenspace, Less Cognitive Decline? Current Evidence and Future Directions | Hu & Yang | 2024 | `10.1289/EHP14915` |
| `2026_wang_greenspace_elderly_health_metaanalysis.pdf` | Association between green space exposure and elderly health: a systematic review and meta-analysis | Wang et al. | 2026 | `10.1186/s12889-025-26137-y` |

## How these papers are used

1. Upload the relevant PDFs to a NotebookLM notebook.
2. Ask NotebookLM synthesis questions (e.g. "What thermal metrics are most
   consistently associated with dementia risk?").
3. Use the answers to inform the design of `src/exposome/climate/metrics.py`,
   the selection of covariates, and the interpretation of results for Santiago.

## Adding new papers

When a new paper arrives:

1. Move the PDF into the appropriate thematic folder.
2. Rename it to `YYYY_firstauthor_short_title.pdf`.
3. Add a row to the table above with the full citation and DOI.
4. Upload the PDF to the active NotebookLM notebook if you want it indexed.

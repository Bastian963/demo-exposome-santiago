# Research Statement
## Bastián Ayala Inostroza

---

My scientific career has been shaped by a fundamental challenge: extracting meaning from vast, heterogeneous, and noisy datasets to understand complex systems. As an astrophysicist, I have spent years developing pipelines to process terabytes of observational data from sky surveys, building statistical models to characterize astronomical populations, and applying machine learning to classify and interpret spatial patterns across cosmic scales. I am now at a transition point where I want to direct these methodological skills toward a problem with immediate human relevance — understanding how our environments shape our brains.

The BrainLat Data Scientist position represents precisely this intersection. The challenge of harmonizing geospatial exposome indicators across Latin American countries is, at its core, a data engineering and statistical inference problem of the kind I have trained for throughout my career — just with a different coordinate system and a different object catalog.

---

## Transferable Technical Expertise

The parallels between large-scale astronomical surveys and large-scale epidemiological and geospatial datasets are deeper than they might initially appear. In astronomy, I worked with survey data characterized by multi-source heterogeneity, inconsistent metadata, varying spatial and temporal resolutions across instruments, and the challenge of linking observations across catalogs using imperfect identifiers. These are structurally identical problems to those encountered when harmonizing census-based socioeconomic indicators across countries with different administrative unit systems, aligning satellite-derived environmental layers with participant residential locations, or integrating data from multiple national health registries.

My experience building reproducible data reduction pipelines — from raw instrument output to science-ready catalogs — translates directly to the geospatial data engineering this position requires: identifying open-access repositories, extracting and aggregating indicators at multiple geographic scales, and building documented, version-controlled workflows. I work routinely in Python (NumPy, pandas, scikit-learn) and R for statistical modeling, and have prior exposure to geospatial data structures through GeoPandas and vector/raster processing libraries.

My statistical training spans parametric and non-parametric methods, Bayesian inference, model comparison, and uncertainty quantification — skills that are directly applicable to the mixed-effects models, survival analysis, and multivariate epidemiological analyses that characterize brain health research. My experience with machine learning in observational settings, including dealing with confounding, class imbalance, and overfitting in high-dimensional data, adds methodological robustness I intend to carry into the exposome context.

---

## Research Vision: Geospatial Exposome in Latin America

My specific interest within the BrainLat research agenda centers on constructing harmonized, multi-country exposome datasets derived from open-access sources — and on using these datasets to investigate environmental and social determinants of brain aging.

Latin America presents a particularly rich and underexplored setting for this work. The region encompasses enormous heterogeneity in urbanization patterns, socioeconomic inequality, environmental conditions, and healthcare access — variability that, if properly captured and harmonized, constitutes a scientific asset. The open-data infrastructure for this region has also matured substantially in the past decade, making it increasingly feasible to build high-quality exposome indicators at the neighborhood or census-block level.

My approach to building this infrastructure would draw on several layers of open-access data. For environmental indicators, **Google Earth Engine** provides programmatic access to decades of satellite imagery from Landsat, Sentinel-2, and MODIS — enabling the derivation of vegetation indices (NDVI), land surface temperature, and urban morphology at the spatial resolution needed to characterize residential environments. Air quality indicators, including NO₂ and PM2.5 estimates, are available at ~3.5 km resolution from **Sentinel-5P (TROPOMI)**, and historical atmospheric reanalysis from **ERA5** allows retrospective exposure estimation.

For social and socioeconomic indicators, **IPUMS International** and country-specific census microdata (INE Chile, IBGE Brazil, INEGI Mexico, DANE Colombia) enable the extraction and harmonization of neighborhood-level variables across different national administrative systems, with **GADM** providing consistent boundary definitions across countries. Infrastructure access — distances to hospitals, schools, pharmacies, and transit — can be derived reproducibly from **OpenStreetMap** using Python's `osmnx` library, enabling comparable network-based metrics across all Latin American countries from a single, unified codebase.

Beyond these conventional sources, I am particularly interested in integrating street-level imagery analysis as an emerging exposome dimension. Computer vision applied to platforms such as **Mapillary** — an open-source street view alternative — allows the extraction of urban quality indicators (tree canopy presence, sidewalk condition, built environment quality) that are not captured in administrative data but are highly relevant to daily environmental experience and mental health. Foundation models such as **CLIP** and **Segment Anything Model (SAM)** make this kind of analysis computationally tractable at city scale, and I see significant potential for incorporating these methods into BrainLat's data infrastructure as a novel research direction.

---

## Motivation and Fit with BrainLat

The epidemiology of brain aging in Latin America remains one of the most scientifically urgent and structurally underserved areas in global health research. Dementia prevalence is rising rapidly across the region, yet most evidence on environmental and social risk factors derives from high-income contexts with limited generalizability. BrainLat's commitment to building research infrastructure grounded in the region's own populations and data positions it to generate evidence that is both scientifically novel and directly relevant to Latin American public health policy.

I am drawn to this mission because it requires exactly the kind of cross-disciplinary, infrastructure-building, data-intensive work I find most intellectually engaging. My astrophysics background offers an unusual vantage point: I am trained to reason carefully about measurement error, selection effects, and the challenge of drawing reliable inference from imperfect observational data — habits of mind that I believe are underrepresented in epidemiological data science and that I can contribute to BrainLat's analytical culture.

I am also deeply committed to open and reproducible science. All workflows I develop would be fully documented, version-controlled, and designed for reuse — priorities that align with BrainLat's role as a regional research platform serving multiple collaborating institutions.

---

## Looking Forward

In my first months at BrainLat, I would prioritize rapidly building fluency in the health and epidemiological domain while contributing immediately to the geospatial data infrastructure. I envision developing a harmonized, open-access exposome database for Latin America — integrating satellite-derived environmental layers, census-based socioeconomic indicators, and infrastructure access metrics at the sub-municipal level — and making this resource available to support BrainLat's ongoing and future studies.

I look forward to contributing to scientific publications, collaborative projects across institutions, and the development of new research questions that bring a rigorous, data-driven perspective to the understanding of brain health across our region.

---

*Word count: ~900 words*

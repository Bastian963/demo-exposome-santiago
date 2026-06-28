"""Fetch Landsat Collection 2 Level-2 Surface Temperature.

High-resolution (30 m) LST for detailed thermal characterization of
urban areas. Used to build "thermal exposure potential" maps.

Limitations:
- Daytime only (~10:30 AM local overpass)
- 16-day revisit, cloud-prone in Santiago winter
- Best used for compositing clear-sky summer scenes
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd

from .. import config, gee

LANDSAT_8 = "LANDSAT/LC08/C02/T1_L2"
LANDSAT_9 = "LANDSAT/LC09/C02/T1_L2"
ST_BAND = "ST_B10"
QA_BAND = "QA_PIXEL"

# Collection 2 scaling: ST = DN * 0.00341802 + 149.0 (Kelvin)
ST_SCALE = 0.00341802
ST_OFFSET = 149.0


def fetch_landsat_lst(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str,
    end: str,
) -> pd.DataFrame:
    """Fetch mean Landsat LST for clear-sky summer scenes.

    Parameters
    ----------
    cfg : dict
        City config.
    regions_fc : ee.FeatureCollection
        Regions for zonal stats.
    start, end : str
        ISO dates (typically Dec-Feb for Santiago summer).

    Returns
    -------
    pd.DataFrame
        Columns: name, landsat_lst_mean_c, landsat_lst_max_c.
    """
    # TODO: implement Landsat LST with QA_PIXEL cloud masking
    raise NotImplementedError("Implement Landsat LST fetch")


def mask_clouds_landsat(img: ee.Image) -> ee.Image:
    """Mask clouds and cloud shadows using QA_PIXEL.

    QA_PIXEL bits (Collection 2):
    - Bit 3: Cloud
    - Bit 4: Cloud Shadow
    - Bit 5: Snow
    We mask out any pixel with cloud or cloud shadow.
    """
    qa = img.select(QA_BAND)
    cloud = qa.bitwiseAnd(1 << 3).eq(0)
    shadow = qa.bitwiseAnd(1 << 4).eq(0)
    return img.updateMask(cloud.And(shadow))

import json
from pathlib import Path
from typing import Dict, List, Tuple

def read_catalog_exposomes(catalog_path: Path, manifests_base_path: Path) -> Dict[str, dict]:
    """
    Reads the catalog and manifests to determine exactly which exposomes are available,
    and extracts the city coordinates.
    Returns a dict mapping city_slug to:
    {
        "available_count": int,
        "expected_count": int,
        "available_list": List[str],
        "center": [lon, lat]
    }
    """
    if not catalog_path.exists():
        return {}

    with catalog_path.open("r", encoding="utf-8") as f:
        catalog = json.load(f)

    results = {}
    for city in catalog.get("cities", []):
        slug = city.get("slug")
        data_url = city.get("data_url")
        if not slug or not data_url:
            continue
        
        center = city.get("center", [0.0, 0.0])
        
        relative_url = data_url.lstrip("/")
        manifest_path = manifests_base_path / relative_url
        
        if not manifest_path.exists():
            results[slug] = {
                "available_count": 0,
                "expected_count": 0,
                "available_list": [],
                "center": center
            }
            continue
            
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        # manifest["layers"] is {layer_id: {"available": bool, ...}} -- the
        # actual per-layer production status. `spatial_indicators` is keyed
        # by exposome_id and describes resolution/methodology, not
        # availability, so it cannot be used to compute this count.
        layers = manifest.get("layers", {})

        available = sorted(
            layer_id for layer_id, layer_data in layers.items()
            if layer_data.get("available") is True
        )

        results[slug] = {
            "available_count": len(available),
            "expected_count": len(layers),
            "available_list": available,
            "center": center
        }
        
    return results

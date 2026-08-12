"""Presentation-ready showcase for CV vs OSM urban greenspace detection."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.gridspec import GridSpec
from scipy import ndimage

from . import config
from .greenspace_cv import (
    _load_osm_green_areas,
    _rasterize_osm_green,
    _tile2deg,
    detect_vegetation_exg,
    fetch_scene,
)

plt.rcParams.update(
    {
        "font.family": "STIXGeneral",
        "figure.dpi": 300,
        "savefig.dpi": 300,
    }
)

CYAN = np.array([0, 210, 255], dtype=np.uint8)
LIME = np.array([170, 255, 0], dtype=np.uint8)
TITLE_GREEN = "#2e7d32"

LOCATIONS: list[dict[str, Any]] = [
    {
        "name": "Parque O'Higgins",
        "comuna": "Santiago",
        "lat": -33.4643,
        "lon": -70.6605,
        "zoom": 18,
        "n_tiles": 3,
        "category": "Parques bien mapeados",
        "blurb": "Gran parque urbano donde OSM ya captura gran parte de la estructura verde.",
    },
    {
        "name": "Parque Bicentenario",
        "comuna": "Vitacura",
        "lat": -33.3996,
        "lon": -70.6020,
        "zoom": 18,
        "n_tiles": 3,
        "category": "Parques bien mapeados",
        "blurb": "Caso de alta visibilidad donde la deteccion CV deberia confirmar el inventario base.",
    },
    {
        "name": "Parque Araucano",
        "comuna": "Las Condes",
        "lat": -33.4030,
        "lon": -70.5745,
        "zoom": 18,
        "n_tiles": 3,
        "category": "Parques bien mapeados",
        "blurb": "Parque consolidado con vegetacion extensa y bordes reconocibles en ambas fuentes.",
    },
    {
        "name": "Cerro Santa Lucia",
        "comuna": "Santiago",
        "lat": -33.4403,
        "lon": -70.6434,
        "zoom": 18,
        "n_tiles": 3,
        "category": "Parques bien mapeados",
        "blurb": "Topografia y arbolado central para comprobar que CV mantiene precision en un cerro-isla.",
    },
    {
        "name": "Parque Forestal",
        "comuna": "Santiago",
        "lat": -33.4354,
        "lon": -70.6416,
        "zoom": 18,
        "n_tiles": 3,
        "category": "Parques bien mapeados",
        "blurb": "Corredor verde lineal donde la deteccion sigue copas y bordes mejor que un poligono simple.",
    },
    {
        "name": "Plaza de Armas",
        "comuna": "Santiago",
        "lat": -33.4372,
        "lon": -70.6506,
        "zoom": 18,
        "n_tiles": 3,
        "category": "OSM submapea",
        "blurb": "Arbolado duro en el casco historico: mucho verde visible pero no siempre representado en OSM.",
    },
    {
        "name": "Plaza Nunoa",
        "comuna": "Nunoa",
        "lat": -33.4556,
        "lon": -70.5979,
        "zoom": 17,
        "n_tiles": 3,
        "category": "OSM submapea",
        "blurb": "Calles arboladas y patios cercanos muestran verde urbano disperso fuera de los parques oficiales.",
    },
    {
        "name": "Barrio La Reina Alta",
        "comuna": "La Reina",
        "lat": -33.4368,
        "lon": -70.5332,
        "zoom": 17,
        "n_tiles": 3,
        "category": "OSM submapea",
        "blurb": "Jardines privados y copas de calle elevan la cobertura real muy por sobre el mapa colaborativo.",
    },
    {
        "name": "Estacion Central Poniente",
        "comuna": "Estacion Central",
        "lat": -33.4649,
        "lon": -70.7061,
        "zoom": 17,
        "n_tiles": 3,
        "category": "OSM submapea",
        "blurb": "Tejido denso con poco verde, util para mostrar que CV aun recupera arbolado residual no mapeado.",
    },
    {
        "name": "Cerro San Cristobal",
        "comuna": "Providencia / Recoleta",
        "lat": -33.4196,
        "lon": -70.6308,
        "zoom": 15,
        "n_tiles": 3,
        "category": "Gran escala",
        "blurb": "Contraste a escala metropolitana donde OSM capta el parque, pero CV revela continuidad vegetal interna.",
    },
]


def _slugify(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def _outline(mask: np.ndarray) -> np.ndarray:
    """Return a one-pixel contour from a boolean mask."""
    mask = mask.astype(bool)
    if mask.size == 0 or not mask.any():
        return np.zeros_like(mask, dtype=bool)
    dilated = ndimage.binary_dilation(mask, iterations=1)
    eroded = ndimage.binary_erosion(mask, iterations=1)
    return dilated & ~eroded


def _overlay_contours(img: np.ndarray, mask: np.ndarray, color: np.ndarray) -> np.ndarray:
    """Overlay a binary contour in RGB space."""
    out = img.copy()
    outline = _outline(mask)
    out[outline] = color
    return out


def _attenuate_image(img: np.ndarray, alpha: float = 0.55) -> np.ndarray:
    base = img.astype(float)
    white = np.full_like(base, 255.0)
    return np.clip(alpha * base + (1.0 - alpha) * white, 0, 255).astype(np.uint8)


def _new_vegetation_overlay(img: np.ndarray, new_mask: np.ndarray) -> np.ndarray:
    out = _attenuate_image(img)
    if new_mask.any():
        out[new_mask] = (0.4 * out[new_mask].astype(float) + 0.6 * LIME.astype(float)).astype(np.uint8)
    out[_outline(new_mask)] = LIME
    return out


def _page_title(loc: dict[str, Any]) -> str:
    return f"{loc['name']} ({loc['comuna']})"


def _clean_mask(mask: np.ndarray, min_blob_px: int) -> np.ndarray:
    """Remove speckle while preserving coherent vegetation patches."""
    opened = ndimage.binary_opening(mask.astype(bool), structure=np.ones((3, 3)))
    labeled, k = ndimage.label(opened)
    if not k:
        return opened
    sizes = ndimage.sum(np.ones_like(labeled), labeled, range(1, k + 1))
    return np.isin(labeled, np.where(sizes >= min_blob_px)[0] + 1)


def _vegetation_indices(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """Compute lightweight RGB-only vegetation indicators for showcase diagnostics."""
    a = rgb.astype(float)
    r_band, g_band, b_band = a[..., 0], a[..., 1], a[..., 2]
    total = r_band + g_band + b_band + 1e-6
    r = r_band / total
    g = g_band / total
    b = b_band / total
    return {
        "R": r_band,
        "G": g_band,
        "B": b_band,
        "exg": 2 * g - r - b,
        "gli": (2 * g_band - r_band - b_band) / (2 * g_band + r_band + b_band + 1e-6),
        "saturation": (a.max(axis=2) - a.min(axis=2)) / (a.max(axis=2) + 1e-6),
    }


def _build_refined_cv_masks(rgb: np.ndarray, cv_cfg: dict[str, Any]) -> dict[str, Any]:
    """Combine strict ExG detection with a more permissive RGB pass.

    The refined mask is still pure CV: it does not borrow OSM geometry.
    OSM is fused later only for the hybrid coverage metric.
    """
    strict_mask, strict_thr = detect_vegetation_exg(
        rgb,
        min_threshold=float(cv_cfg["exg_min_threshold"]),
        min_blob_px=int(cv_cfg["min_blob_px"]),
    )
    idx = _vegetation_indices(rgb)
    relaxed_thr = max(0.12, strict_thr * 0.55)
    relaxed_seed = (
        (idx["exg"] > relaxed_thr)
        & (idx["G"] >= idx["R"] * 0.92)
        & (idx["G"] >= idx["B"] * 0.92)
        & (idx["saturation"] > 0.08)
    )
    relaxed_mask = _clean_mask(relaxed_seed, int(cv_cfg["min_blob_px"]))
    refined_mask = strict_mask | relaxed_mask
    return {
        "strict_mask": strict_mask,
        "relaxed_mask": relaxed_mask,
        "refined_mask": refined_mask,
        "strict_thr": float(strict_thr),
        "relaxed_thr": float(relaxed_thr),
    }


def render_location_page(
    loc: dict[str, Any],
    green_areas: gpd.GeoDataFrame,
    cfg: dict[str, Any],
    cache_dir: Path,
) -> tuple[plt.Figure, dict[str, Any]]:
    """Render a single showcase page and compute page-level metrics."""
    cache_dir = Path(cache_dir)
    cv_cfg = cfg["greenspace"]["cv"]
    z = int(loc.get("zoom", cv_cfg["zoom"]))
    n = int(loc.get("n_tiles", 3))
    tile_cache = cache_dir / "cv_tiles"

    rgb_img, x0, y0 = fetch_scene(
        lat=float(loc["lat"]),
        lon=float(loc["lon"]),
        z=z,
        n=n,
        url_template=cv_cfg["url"],
        cache_dir=tile_cache,
    )
    cv_masks = _build_refined_cv_masks(rgb_img, cv_cfg)
    north, west = _tile2deg(x0, y0, z)
    south, east = _tile2deg(x0 + n, y0 + n, z)
    osm_mask = _rasterize_osm_green(north, west, south, east, x0, y0, z, n, green_areas)
    cv_unmapped_mask = cv_masks["refined_mask"] & ~osm_mask
    hybrid_mask = osm_mask | cv_masks["refined_mask"]

    osm_pct = 100.0 * float(osm_mask.mean())
    cv_strict_pct = 100.0 * float(cv_masks["strict_mask"].mean())
    cv_refined_pct = 100.0 * float(cv_masks["refined_mask"].mean())
    cv_unmapped_pct = 100.0 * float(cv_unmapped_mask.mean())
    hybrid_pct = 100.0 * float(hybrid_mask.mean())
    unmapped_share = 100.0 * float(cv_unmapped_mask.sum()) / float(max(int(cv_masks["refined_mask"].sum()), 1))

    fig = plt.figure(figsize=(8.27, 11.69), constrained_layout=False)
    gs = GridSpec(2, 2, figure=fig, left=0.06, right=0.94, top=0.84, bottom=0.16, wspace=0.05, hspace=0.08)
    axes = [fig.add_subplot(gs[row, col]) for row in range(2) for col in range(2)]
    panel_images = [
        rgb_img,
        _overlay_contours(rgb_img, osm_mask, CYAN),
        _overlay_contours(rgb_img, cv_masks["refined_mask"], LIME),
        _new_vegetation_overlay(rgb_img, cv_unmapped_mask),
    ]
    panel_titles = [
        "Imagen aerea (Esri, ~1 m)",
        "Antes - mapeado en OpenStreetMap",
        "Ahora - CV refinado (ExG + umbral relajado)",
        "Aporte CV fuera de OSM",
    ]
    for ax, img, title in zip(axes, panel_images, panel_titles, strict=True):
        ax.imshow(img)
        ax.set_title(title, fontsize=12, color="#263238", pad=6)
        ax.axis("off")

    fig.text(0.06, 0.94, _page_title(loc), fontsize=19, fontweight="bold", color=TITLE_GREEN, ha="left", va="top")
    fig.text(0.06, 0.905, loc["category"], fontsize=11.5, color="#607d8b", ha="left", va="top")
    fig.text(0.06, 0.88, loc["blurb"], fontsize=11.5, color="#263238", ha="left", va="top")
    footer = (
        f"Verde OSM {osm_pct:.1f}%  ·  CV refinado {cv_refined_pct:.1f}%  ·  Hibrido OSM+CV {hybrid_pct:.1f}%\n"
        f"Aporte CV fuera de OSM: {cv_unmapped_pct:.1f}% del mosaico  ·  {unmapped_share:.1f}% del CV refinado"
    )
    fig.text(
        0.5,
        0.08,
        footer,
        ha="center",
        va="center",
        fontsize=12.2,
        color="#102027",
        bbox={"boxstyle": "round,pad=0.45", "fc": "white", "ec": "#cfd8dc", "lw": 1.2},
        linespacing=1.3,
    )
    fig.text(
        0.06,
        0.03,
        "OSM fija parques formales; el CV refinado agrega arbolado fino y verde visible fuera del mapa colaborativo.",
        fontsize=10.5,
        color="#546e7a",
    )

    stats = {
        "name": loc["name"],
        "comuna": loc["comuna"],
        "category": loc["category"],
        "lat": float(loc["lat"]),
        "lon": float(loc["lon"]),
        "zoom": z,
        "n_tiles": n,
        "threshold_exg": cv_masks["strict_thr"],
        "threshold_relaxed_exg": cv_masks["relaxed_thr"],
        "osm_pct": osm_pct,
        "cv_strict_pct": cv_strict_pct,
        "cv_refined_pct": cv_refined_pct,
        "cv_unmapped_pct": cv_unmapped_pct,
        "hybrid_pct": hybrid_pct,
        "unmapped_share_of_refined_cv": unmapped_share,
        "cv_pct": cv_refined_pct,
        "new_pct": cv_unmapped_pct,
        "outside_pct": unmapped_share,
        "osm_pixels": int(osm_mask.sum()),
        "cv_strict_pixels": int(cv_masks["strict_mask"].sum()),
        "cv_refined_pixels": int(cv_masks["refined_mask"].sum()),
        "cv_unmapped_pixels": int(cv_unmapped_mask.sum()),
        "hybrid_pixels": int(hybrid_mask.sum()),
        "cv_pixels": int(cv_masks["refined_mask"].sum()),
        "new_pixels": int(cv_unmapped_mask.sum()),
    }
    return fig, stats


def _build_cover_page(city: str) -> plt.Figure:
    fig = plt.figure(figsize=(8.27, 11.69))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_facecolor("#f4fbf4")
    fig.text(0.08, 0.82, "Greenspace CV Showcase", fontsize=30, fontweight="bold", color=TITLE_GREEN, ha="left")
    fig.text(0.08, 0.75, city.title(), fontsize=22, color="#1b5e20", ha="left")
    fig.text(
        0.08,
        0.64,
        "OSM para parques formales + CV refinado sobre imagen aerea Esri (~1 m) para verde fino fuera de OSM.",
        fontsize=15,
        color="#263238",
        ha="left",
    )
    fig.text(
        0.08,
        0.54,
        "Cada pagina separa lo que ya esta mapeado por OSM de lo que agrega el CV refinado.\n"
        "La capa hibrida resume verde formal + arbolado fino o jardines que OSM no suele codificar.",
        fontsize=15,
        color="#37474f",
        ha="left",
        linespacing=1.35,
    )
    fig.text(0.08, 0.18, "Bastian Ayala Inostroza", fontsize=16, color="#263238", ha="left")
    fig.text(0.08, 0.14, datetime.now().strftime("%Y-%m-%d"), fontsize=14, color="#546e7a", ha="left")
    return fig


def _build_summary_page(df: pd.DataFrame) -> plt.Figure:
    summary = df.sort_values("cv_unmapped_pct", ascending=True)
    fig = plt.figure(figsize=(8.27, 11.69))
    ax = fig.add_axes([0.13, 0.18, 0.78, 0.62])
    ax.barh(summary["name"], summary["osm_pct"], color="#26c6da", label="OSM formal")
    ax.barh(summary["name"], summary["cv_unmapped_pct"], left=summary["osm_pct"], color="#8bc34a", label="CV fuera de OSM")
    ax.set_xlabel("Cobertura hibrida (% del mosaico)", fontsize=13)
    ax.set_xlim(0, min(100, max(5, float(summary["hybrid_pct"].max()) + 10)))
    ax.grid(axis="x", alpha=0.25)
    ax.tick_params(axis="y", labelsize=11)
    for i, row in enumerate(summary.itertuples(index=False)):
        ax.text(row.hybrid_pct + 1, i, f"{row.hybrid_pct:.1f}%", va="center", fontsize=10.5, color="#263238")
        if row.cv_unmapped_pct > 0.35:
            ax.text(
                row.osm_pct + row.cv_unmapped_pct / 2,
                i,
                f"+{row.cv_unmapped_pct:.1f}",
                va="center",
                ha="center",
                fontsize=9.5,
                color="#102027",
            )
    ax.legend(loc="lower right", frameon=False, fontsize=11)

    fig.text(0.08, 0.92, "Resumen", fontsize=24, fontweight="bold", color=TITLE_GREEN, ha="left")
    fig.text(
        0.08,
        0.865,
        "La barra azul resume vegetacion formal ya mapeada por OSM. El tramo verde cuantifica el aporte extra del CV refinado\n"
        "fuera de OSM, que aparece con fuerza en barrios arbolados y plazas duras, y cae en parques donde OSM ya aporta la semantica.",
        fontsize=13.5,
        color="#37474f",
        ha="left",
        linespacing=1.3,
    )
    fig.text(
        0.08,
        0.09,
        "Nota honesta: el CV refinado sigue siendo RGB puro, asi que puede confundir sombras verdes, pasto sintetico o superficies secas mixtas.\n"
        "Por eso el showcase separa OSM, CV fuera de OSM e hibrido total, en vez de vender el CV como reemplazo del inventario formal.",
        fontsize=11.5,
        color="#546e7a",
        ha="left",
        linespacing=1.25,
    )
    return fig


def build_showcase_pdf(
    city: str = "santiago",
    out_pdf: Path | None = None,
    out_csv: Path | None = None,
    figures_subdir: Path | None = None,
    cache_dir: Path = Path("cache"),
    locations: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """Build the full showcase PDF, per-location PNGs and summary CSV."""
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    figures_dir = Path(cfg["outputs"]["figures_dir"])
    out_pdf = Path(out_pdf) if out_pdf is not None else figures_dir / f"greenspace_cv_showcase_{city}.pdf"
    out_csv = Path(out_csv) if out_csv is not None else Path(cfg["outputs"]["base_dir"]) / f"{city}_greenspace_cv_showcase.csv"
    figures_subdir = Path(figures_subdir) if figures_subdir is not None else figures_dir / "greenspace_cv_showcase"

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    figures_subdir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    active_locations = locations or LOCATIONS
    green_cache = cache_dir / f"{city}_greenspace_osm.geojson"
    green_areas = _load_osm_green_areas(
        cfg["region_query"],
        cfg["greenspace"]["access"]["osm_tags"],
        green_cache,
    )

    rows: list[dict[str, Any]] = []
    with PdfPages(out_pdf) as pdf:
        cover = _build_cover_page(city)
        pdf.savefig(cover, bbox_inches="tight")
        plt.close(cover)

        for loc in active_locations:
            fig, stats = render_location_page(loc, green_areas, cfg, cache_dir)
            rows.append(stats)
            slug = _slugify(loc["name"])
            fig.savefig(figures_subdir / f"{slug}.png", bbox_inches="tight")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        df = pd.DataFrame(rows).sort_values(["category", "cv_unmapped_pct"], ascending=[True, False]).reset_index(drop=True)
        summary = _build_summary_page(df)
        pdf.savefig(summary, bbox_inches="tight")
        plt.close(summary)

    df.to_csv(out_csv, index=False)
    return df

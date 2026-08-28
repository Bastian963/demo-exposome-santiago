"""Network-based healthcare accessibility.

Replaces straight-line (Euclidean) distances with shortest-path distances over
the OpenStreetMap street network. This is still an approximation — it does not
account for traffic, public transport, or one-way streets for pedestrians —
but it is considerably more realistic than Euclidean distance in hilly or
irregular urban layouts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd


def fetch_street_graph(
    region: str,
    cache_path: Path,
    network_type: str = "walk",
    to_crs: str | None = None,
) -> nx.MultiGraph:
    """Download or load a cached OSM street graph for ``region``.

    Returns an undirected, length-weighted MultiGraph suitable for
    shortest-path queries. If ``to_crs`` is provided, the graph is projected
    to that CRS before caching, so node coordinates match the metric CRS used
    by the rest of the pipeline.
    """
    cache_path = Path(cache_path)
    if cache_path.exists():
        print(f"  Loading cached street graph from {cache_path.name}")
        graph = ox.load_graphml(cache_path)
        return graph

    print(f"  Downloading {network_type} street graph for '{region}'...")
    graph = ox.graph_from_place(region, network_type=network_type, simplify=True)

    # Convert to undirected so pedestrian access does not depend on one-way
    # directions. This roughly doubles edge count but keeps queries symmetric.
    graph = ox.convert.to_undirected(graph)

    if to_crs is not None:
        print(f"  Projecting street graph to {to_crs}...")
        graph = ox.project_graph(graph, to_crs=to_crs)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, cache_path)
    return graph


def _prepare_graph(graph: nx.MultiGraph) -> nx.MultiGraph:
    """Ensure every edge has a ``length`` attribute in metres."""
    for _, _, data in graph.edges(data=True):
        if "length" not in data:
            data["length"] = 0.0
    return graph


def nearest_network_distances(
    grid_gdf: gpd.GeoDataFrame,
    facilities_gdf: gpd.GeoDataFrame,
    graph: nx.MultiGraph,
    cfg: dict[str, Any],
    distance_col: str = "nearest_network_m",
    max_snap_distance_m: float = 500.0,
) -> gpd.GeoDataFrame:
    """Return ``grid_gdf`` with a network-distance column to the nearest facility.

    Parameters
    ----------
    grid_gdf : GeoDataFrame
        Grid points in the metric CRS, with a ``name`` column (commune).
    facilities_gdf : GeoDataFrame
        Facility points in the geographic CRS.
    graph : networkx.MultiGraph
        Street graph in the same metric CRS as ``grid_gdf``.
    cfg : dict
        City config (used for CRS lookups).
    distance_col : str
        Name of the output distance column.
    max_snap_distance_m : float
        Grid points whose nearest graph node is farther than this are treated
        as not represented by the street network (NaN). This avoids projecting
        rural interior points to distant roads.

    Returns
    -------
    GeoDataFrame
        ``grid_gdf`` with ``distance_col`` added (NaN for unreachable nodes).
    """
    metric_crs = cfg["crs"]["metric"]
    graph = _prepare_graph(graph)

    grid_metric = grid_gdf.to_crs(metric_crs).copy()
    facilities_metric = facilities_gdf.to_crs(metric_crs).copy()

    if facilities_metric.empty:
        grid_gdf[distance_col] = np.nan
        return grid_gdf

    # Map points to nearest graph nodes.
    grid_nodes = ox.nearest_nodes(
        graph, grid_metric.geometry.x.values, grid_metric.geometry.y.values
    )
    facility_nodes = ox.nearest_nodes(
        graph,
        facilities_metric.geometry.x.values,
        facilities_metric.geometry.y.values,
    )

    # Snap distance: straight-line distance from each grid point to its
    # assigned network node. Points that snap too far are unreliable.
    grid_x = grid_metric.geometry.x.values
    grid_y = grid_metric.geometry.y.values
    node_x = np.array([graph.nodes[n]["x"] for n in grid_nodes])
    node_y = np.array([graph.nodes[n]["y"] for n in grid_nodes])
    snap_dists = np.sqrt((grid_x - node_x) ** 2 + (grid_y - node_y) ** 2)

    # Multi-source Dijkstra from all facility nodes at once.
    lengths = nx.multi_source_dijkstra_path_length(
        graph, sources=facility_nodes.tolist(), weight="length"
    )

    dists = np.array([lengths.get(n, np.nan) for n in grid_nodes], dtype=float)
    # Discard points whose network node is unrealistically far away.
    dists[snap_dists > max_snap_distance_m] = np.nan

    grid_gdf[distance_col] = dists
    return grid_gdf


def network_distance_summary(
    grid_gdf: gpd.GeoDataFrame,
    facilities_gdf: gpd.GeoDataFrame,
    graph: nx.MultiGraph,
    cfg: dict[str, Any],
    prefix: str,
    max_snap_distance_m: float = 500.0,
) -> pd.DataFrame:
    """Compute mean/median/p90 network distance per commune.

    Parameters
    ----------
    grid_gdf : GeoDataFrame
        Grid points in metric CRS with a ``name`` column.
    facilities_gdf : GeoDataFrame
        Facility points in geographic CRS.
    graph : networkx.MultiGraph
        Street graph in metric CRS.
    cfg : dict
        City config.
    prefix : str
        Output prefix, e.g. ``nearest_health_network`` yields
        ``mean_nearest_health_network_m``.
    max_snap_distance_m : float
        See ``nearest_network_distances``.

    Returns
    -------
    pd.DataFrame
        One row per commune with mean, median and p90 network distances.
    """
    distance_col = f"{prefix}_m"
    grid_with_dist = nearest_network_distances(
        grid_gdf,
        facilities_gdf,
        graph,
        cfg,
        distance_col=distance_col,
        max_snap_distance_m=max_snap_distance_m,
    )

    if facilities_gdf.empty:
        out = grid_with_dist.groupby("name").size().rename("n_access_grid").reset_index()
        for col in [f"mean_{prefix}_m", f"median_{prefix}_m", f"p90_{prefix}_m"]:
            out[col] = np.nan
        return out

    valid = grid_with_dist.dropna(subset=[distance_col])
    return valid.groupby("name").agg(
        **{
            f"mean_{prefix}_m": (distance_col, "mean"),
            f"median_{prefix}_m": (distance_col, "median"),
            f"p90_{prefix}_m": (distance_col, lambda x: x.quantile(0.90)),
        }
    ).reset_index()

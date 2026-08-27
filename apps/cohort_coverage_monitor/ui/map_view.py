import pydeck as pdk
import pandas as pd
import streamlit as st
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot
from apps.cohort_coverage_monitor.config import STATUS_COLORS, COLORS

def hex_to_rgb(hex_color: str) -> list:
    hex_color = hex_color.lstrip('#')
    return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)] + [200]

def render_world_map(snapshot: PublicSnapshot):
    # Prepare data
    data = []
    for c in snapshot.cities:
        # Convert status to color
        color_hex = STATUS_COLORS.get(c.status, COLORS["ui_text_muted"])
        color_rgb = hex_to_rgb(color_hex)
        
        data.append({
            "name": c.metro,
            "country": c.country,
            "lat": c.lat,
            "lon": c.lon,
            "participants": c.participants,
            "pct_total": round(c.pct_total, 2),
            "status": c.status,
            "tier": c.publication_tier,
            "exposomes": c.available_exposomes_count,
            "color": color_rgb,
            # base size for pydeck
            "radius": max(c.participants * 20, 10000)
        })
        
    df = pd.DataFrame(data)
    
    # Filter controls above map
    cols = st.columns(3)
    with cols[0]:
        selected_status = st.selectbox("Filtrar por Estado", ["Todos"] + list(STATUS_COLORS.keys()))
    with cols[1]:
        selected_tier = st.selectbox("Filtrar por Tier", ["Todos", "production", "preview", "none"])
    with cols[2]:
        countries = ["Todos"] + sorted(list(set(df["country"].tolist())))
        selected_country = st.selectbox("Filtrar por País", countries)
        
    # Apply filters
    filtered_df = df.copy()
    if selected_status != "Todos":
        filtered_df = filtered_df[filtered_df["status"] == selected_status]
    if selected_tier != "Todos":
        filtered_df = filtered_df[filtered_df["tier"] == selected_tier]
    if selected_country != "Todos":
        filtered_df = filtered_df[filtered_df["country"] == selected_country]
        
    # Define layer
    layer = pdk.Layer(
        "ScatterplotLayer",
        filtered_df,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.8,
        stroked=True,
        filled=True,
        radius_scale=1,
        radius_min_pixels=5,
        radius_max_pixels=50,
        line_width_min_pixels=1,
        get_line_color=[255, 255, 255, 100],
    )
    
    # Tooltip configuration
    tooltip = {
        "html": "<b>{name} ({country})</b><br/>"
                "Participantes (agregados): {participants} ({pct_total}%)<br/>"
                "Estado: {status}<br/>"
                "Tier: {tier}<br/>"
                "Exposomas: {exposomes}",
        "style": {
            "backgroundColor": COLORS["bg_panel"],
            "color": COLORS["ui_text"],
            "border": f"2px solid {COLORS['bg_panel_dark']}",
            "fontFamily": "VT323, monospace",
            "fontSize": "16px"
        }
    }
    
    # Viewport focused on LATAM
    view_state = pdk.ViewState(
        latitude=-15.0,
        longitude=-60.0,
        zoom=2.5,
        pitch=0
    )
    
    # GEMMA's own LATAM view is a flat navy background with cities as points,
    # not a real street/satellite basemap -- so skip pydeck's basemap tiles
    # entirely rather than trying to fake pixel-art terrain it can't render.
    r = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_provider=None,
        parameters={"clearColor": [26 / 255, 28 / 255, 44 / 255, 1]},  # bg_sky
    )

    st.pydeck_chart(r, use_container_width=True)

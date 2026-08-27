import altair as alt
import pandas as pd
import streamlit as st
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot
from apps.cohort_coverage_monitor.services.metrics import get_participants_by_status, get_participants_by_tier
from apps.cohort_coverage_monitor.config import STATUS_COLORS, TIER_COLORS

def render_status_bar_chart(snapshot: PublicSnapshot):
    status_counts = get_participants_by_status(snapshot)
    df = pd.DataFrame(list(status_counts.items()), columns=["Status", "Participants"])
    
    # Map colors
    color_scale = alt.Scale(
        domain=list(STATUS_COLORS.keys()),
        range=list(STATUS_COLORS.values())
    )
    
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("Participants:Q", title="Participantes", axis=alt.Axis(grid=False)),
        y=alt.Y("Status:N", sort=list(STATUS_COLORS.keys()), title=None),
        color=alt.Color("Status:N", scale=color_scale, legend=None),
        tooltip=["Status", "Participants"]
    ).properties(height=250, title="Participantes por Estado Operativo")
    
    st.altair_chart(chart, use_container_width=True)

def render_tier_bar_chart(snapshot: PublicSnapshot):
    tier_counts = get_participants_by_tier(snapshot)
    df = pd.DataFrame(list(tier_counts.items()), columns=["Tier", "Participants"])
    
    color_scale = alt.Scale(
        domain=list(TIER_COLORS.keys()),
        range=list(TIER_COLORS.values())
    )
    
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("Participants:Q", title="Participantes", axis=alt.Axis(grid=False)),
        y=alt.Y("Tier:N", sort=list(TIER_COLORS.keys()), title=None),
        color=alt.Color("Tier:N", scale=color_scale, legend=None),
        tooltip=["Tier", "Participants"]
    ).properties(height=200, title="Participantes por Tier de Publicación")
    
    st.altair_chart(chart, use_container_width=True)

def render_city_ranking(snapshot: PublicSnapshot):
    data = []
    for c in snapshot.cities:
        data.append({
            "City": f"{c.metro} ({c.country})",
            "Participants": c.participants,
            "Status": c.status
        })
    df = pd.DataFrame(data)
    
    color_scale = alt.Scale(
        domain=list(STATUS_COLORS.keys()),
        range=list(STATUS_COLORS.values())
    )
    
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("Participants:Q", title="Participantes", axis=alt.Axis(grid=False)),
        y=alt.Y("City:N", sort="-x", title=None),
        color=alt.Color("Status:N", scale=color_scale, legend=alt.Legend(orient="bottom")),
        tooltip=["City", "Participants", "Status"]
    ).properties(height=400, title="Ciudades por Participantes Agregados")
    
    st.altair_chart(chart, use_container_width=True)

def render_exposome_matrix(snapshot: PublicSnapshot):
    # Prepare data for matrix
    # Columns: Exposomes, Rows: Cities, Cell: available (bool)
    data = []
    all_exposomes = set()
    for c in snapshot.cities:
        all_exposomes.update(c.available_exposomes)
        
    for c in snapshot.cities:
        for exp in all_exposomes:
            data.append({
                "City": c.metro,
                "Exposome": exp,
                "Available": exp in c.available_exposomes
            })
            
    if not data:
        st.info("No hay exposomas disponibles aún.")
        return
        
    df = pd.DataFrame(data)
    
    chart = alt.Chart(df).mark_rect().encode(
        x=alt.X("Exposome:N", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("City:N", title=None),
        color=alt.Color("Available:N", 
                        scale=alt.Scale(domain=[True, False], range=[TIER_COLORS["production"], "#2d3748"]),
                        legend=None),
        tooltip=["City", "Exposome", "Available"]
    ).properties(title="Matriz de Disponibilidad de Exposomas")
    
    st.altair_chart(chart, use_container_width=True)

def render_progress_table(snapshot: PublicSnapshot):
    data = []
    for c in snapshot.cities:
        data.append({
            "Ciudad": c.metro,
            "País": c.country,
            "Participantes": c.participants,
            "Estado": c.status,
            "Tier": c.publication_tier,
            "Exposomas": f"{c.available_exposomes_count} / {c.expected_exposomes_count}" if c.expected_exposomes_count > 0 else "N/A",
            "Siguiente Acción": c.next_action or "-"
        })
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

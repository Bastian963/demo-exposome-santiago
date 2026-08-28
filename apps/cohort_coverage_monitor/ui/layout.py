import streamlit as st
from apps.cohort_coverage_monitor.config import APP_TITLE, APP_SUBTITLE, GEMMA_FULL_NAME
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot
from apps.cohort_coverage_monitor.services.metrics import calculate_summary_metrics
from apps.cohort_coverage_monitor.ui.charts import (
    render_status_bar_chart, 
    render_tier_bar_chart, 
    render_city_ranking, 
    render_exposome_matrix,
    render_progress_table
)
from apps.cohort_coverage_monitor.ui.map_view import render_world_map

def render_header(snapshot: PublicSnapshot):
    st.title(APP_TITLE)
    st.markdown(f"**{APP_SUBTITLE}**")
    st.markdown(f"GEMMA = *{GEMMA_FULL_NAME}*")
    st.markdown(f"*Última actualización (snapshot): {snapshot.updated_at} | Generado: {snapshot.snapshot_generated_at[:10]}*")
    
    st.warning(
        "**Aviso de Privacidad**: Esta aplicación muestra únicamente datos agregados a nivel de área metropolitana. "
        "No contiene, infiere ni expone ubicaciones individuales de los participantes."
    )
    st.markdown("---")

def render_summary_cards(snapshot: PublicSnapshot):
    metrics = calculate_summary_metrics(snapshot)

    cols = st.columns(4)
    with cols[0]:
        st.metric("Total Participantes (Cohorte)", f"{metrics['total_participants']:,}")
        st.metric("Ciudades Publicadas", metrics["published_cities"])

    with cols[1]:
        st.metric("Participantes Priorizados", f"{metrics['priority_participants']:,}")
        st.metric("Ciudades en Ejecución", metrics["running_cities"])

    with cols[2]:
        st.metric("Cobertura Geográfica Priorizada", f"{metrics['priority_coverage_pct']:.1f}%")
        st.metric("Ciudades Pendientes", metrics["remaining_cities"])

    with cols[3]:
        st.metric("Cobertura Visible en GEMMA", f"{metrics['visible_coverage_pct']:.1f}%")
        st.metric("Exposomas Únicos Disponibles", metrics["unique_exposomes_count"])

    st.markdown("---")

def render_methodology():
    st.markdown("## Metodología")
    with st.expander("Ver detalles de cálculo y arquitectura"):
        st.markdown(f"""
        **0. Qué es GEMMA**
        GEMMA ({GEMMA_FULL_NAME}) es la webapp pixel-art de BrainLat donde se publican
        los exposomas urbanos por ciudad. Este monitor es una app aparte: no navega
        exposomas como GEMMA, solo reporta el estado operativo del pipeline que la alimenta.

        **1. Cobertura geográfica priorizada**
        Participantes que viven en una de las 15 áreas metropolitanas priorizadas (n >= 25) dividido por el total de participantes de la cohorte LATAM (2026-07).
        
        **2. Visible en GEMMA**
        Participantes en ciudades cuyo `publication_tier` sea `production` o `preview`, dividido por el total de la cohorte.
        
        **3. Exposomas Disponibles**
        Exposomas únicos realmente publicados y verificables. Se leen del `manifest.json` comprobando que `layer_available` sea `true` y `status` sea `complete`.
        
        **4. Privacidad y Flujo de Datos**
        Esta aplicación no contiene, lee ni expone datos privados. Se basa en un *snapshot público* pregenerado localmente que agrupa participantes por área metropolitana. El repositorio webapp de GEMMA permanece inalterado.
        
        **5. Regeneración del Snapshot**
        Para actualizar los datos, ejecutar localmente:
        `python apps/cohort_coverage_monitor/services/snapshot_builder.py` y luego hacer commit de `cohort_public_snapshot.json`.
        """)

import streamlit as st
import sys
from pathlib import Path

# Fix python path for Streamlit Cloud deployment
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from apps.cohort_coverage_monitor.config import APP_TITLE
from apps.cohort_coverage_monitor.services.snapshot_loader import load_snapshot
from apps.cohort_coverage_monitor.ui.theme import apply_theme
from apps.cohort_coverage_monitor.ui.layout import (
    render_header,
    render_summary_cards,
    render_methodology
)
from apps.cohort_coverage_monitor.ui.map_view import render_world_map
from apps.cohort_coverage_monitor.ui.charts import (
    render_status_bar_chart,
    render_tier_bar_chart,
    render_city_ranking,
    render_exposome_matrix,
    render_progress_table
)

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="🌍"
)

def main():
    apply_theme()
    
    try:
        snapshot = load_snapshot()
    except Exception as e:
        st.error(f"Error cargando el snapshot de datos: {e}")
        st.info("Asegúrese de ejecutar primero 'python apps/cohort_coverage_monitor/services/snapshot_builder.py' localmente.")
        return

    render_header(snapshot)
    render_summary_cards(snapshot)
    
    st.markdown("### Mapa de Cobertura LATAM")
    render_world_map(snapshot)
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        render_status_bar_chart(snapshot)
    with col2:
        render_tier_bar_chart(snapshot)
        
    st.markdown("---")
    
    col3, col4 = st.columns([1, 2])
    with col3:
        render_city_ranking(snapshot)
    with col4:
        render_exposome_matrix(snapshot)
        
    st.markdown("---")
    st.markdown("### Progreso Detallado por Ciudad")
    render_progress_table(snapshot)
    
    st.markdown("---")
    render_methodology()

if __name__ == "__main__":
    main()

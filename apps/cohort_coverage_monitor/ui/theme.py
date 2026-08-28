import streamlit as st
from apps.cohort_coverage_monitor.config import COLORS, PIXEL_FONT, BODY_FONT

def apply_theme():
    """Applies GEMMA's pixel-art theme (fonts, palette, hard edges) to the app shell."""
    custom_css = f"""
    <link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap" rel="stylesheet">
    <style>
        * {{
            border-radius: 0 !important;
        }}
        img, canvas {{
            image-rendering: pixelated;
        }}

        /* Base background and text */
        .stApp {{
            background-color: {COLORS['bg_sky']};
            color: {COLORS['ui_text']};
            font-family: {BODY_FONT};
            font-size: 18px;
        }}

        /* Metric cards styling */
        [data-testid="stMetric"] {{
            background-color: {COLORS['bg_panel']};
            border: 2px solid {COLORS['bg_panel_dark']};
            box-shadow: 0 2px 0 {COLORS['shadow']};
            padding: 0.75rem 1rem;
        }}
        [data-testid="stMetricValue"] {{
            color: {COLORS['ui_accent_2']};
            font-family: {PIXEL_FONT};
            font-size: 1.1rem;
        }}
        [data-testid="stMetricLabel"] {{
            color: {COLORS['ui_text_muted']};
            font-family: {BODY_FONT};
        }}

        /* Headers */
        h1, h2, h3, h4, h5, h6 {{
            color: {COLORS['ui_text']} !important;
            font-family: {PIXEL_FONT};
        }}
        h1 {{ color: {COLORS['ui_accent']} !important; font-size: 1.4rem; }}

        /* DataFrame / Tables */
        .stDataFrame {{
            background-color: {COLORS['bg_panel']};
            border: 2px solid {COLORS['bg_panel_dark']};
        }}

        /* Markdown links */
        a {{
            color: {COLORS['ui_accent']};
        }}

        /* Disable some default padding to make it more compact */
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }}

        /* Custom panels */
        .panel {{
            background-color: {COLORS['bg_panel']};
            border: 2px solid {COLORS['bg_panel_dark']};
            box-shadow: 0 2px 0 {COLORS['shadow']};
            padding: 1rem;
            margin-bottom: 1rem;
        }}

        [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background-color: {COLORS['bg_panel']};
            border: 2px solid {COLORS['bg_panel_dark']};
        }}
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)

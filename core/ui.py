"""Shared UI helpers.

Two functions every page uses:
  - `inject_base_style()` — bumps Streamlit's default font sizes site-wide.
  - `page_header(title, subtitle)` — uniform large navy title + gray subtitle,
    matching the Home page hero.

Both are idempotent — safe to call multiple times.
"""
from __future__ import annotations

import streamlit as st

NAVY = "#1e3a8a"


_BASE_STYLE = """
<style>
    /* Body / paragraph text */
    .stMarkdown p,
    .stMarkdown li,
    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stMarkdownContainer"] li {
        font-size: 1.05rem;
        line-height: 1.55;
    }

    /* Headings */
    h1, h1 span { font-size: 2.4rem !important; line-height: 1.2 !important; }
    h2, h2 span { font-size: 1.9rem !important; line-height: 1.3 !important; }
    h3, h3 span { font-size: 1.4rem !important; line-height: 1.35 !important; }

    /* Captions slightly bigger so they're readable */
    div[data-testid="stCaptionContainer"] p,
    div[data-testid="stCaption"] {
        font-size: 0.9rem !important;
    }

    /* Metrics (st.metric value + label) */
    div[data-testid="stMetricValue"] {
        font-size: 1.7rem !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.95rem !important;
    }

    /* Table / dataframe cells stay default — they're already legible */
</style>
"""


def inject_base_style() -> None:
    """Apply the project-wide typography bump. Call once per page."""
    st.markdown(_BASE_STYLE, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    """Render a consistent page header.

    Navy title (2.8rem) + optional gray subtitle (1.2rem). Matches the
    visual weight of the Home page hero, so every page lines up.
    """
    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            '<p style="margin: 0.5rem 0 0 0; font-size: 1.2rem; color: #475569;">'
            f"{subtitle}</p>"
        )
    st.markdown(
        f"""
        <div style="padding: 1rem 0 0.5rem 0;">
            <h1 style="margin: 0; color: {NAVY}; font-size: 2.8rem; font-weight: 700;
                       letter-spacing: -0.02em;">
                {title}
            </h1>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

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


def render_benchmark_panel(metrics: dict, label: str = "NIFTY 50") -> None:
    """4 metric cards summarizing the strategy's relative performance vs benchmark.

    Pass the dict returned by `core.analytics.benchmark.compute_benchmark_metrics`.
    """
    def _pct(v):
        return f"{v*100:+.2f}%" if v is not None else "—"

    def _num(v, places=3):
        return f"{v:+.{places}f}" if v is not None else "—"

    st.caption(f"Versus {label} (buy & hold over the same window)")
    cols = st.columns(4)
    cols[0].metric(
        f"{label} return",
        _pct(metrics.get("benchmark_total_return")),
        help="What the benchmark returned over the same period.",
    )
    cols[1].metric(
        "Strategy − benchmark",
        _pct(metrics.get("strategy_minus_benchmark")),
        delta=_pct(metrics.get("strategy_minus_benchmark")),
        help="Positive = strategy beat the benchmark. Doesn't account for risk.",
    )
    cols[2].metric(
        "Alpha (annualized)",
        _pct(metrics.get("alpha_annualized")),
        help="CAPM excess return after adjusting for beta. Positive = added value above what the beta exposure would predict.",
    )
    cols[3].metric(
        "Beta",
        _num(metrics.get("beta"), places=2),
        help="Sensitivity to benchmark moves. 1.0 = same vol as benchmark; <1 = less volatile; <0 = inversely correlated.",
    )

    cols2 = st.columns(4)
    cols2[0].metric(
        "Information ratio",
        _num(metrics.get("information_ratio"), places=3),
        help="Annualized excess return per unit of tracking error. >0.5 = decent skill, >1.0 = strong.",
    )
    cols2[1].metric(
        "Tracking error",
        _pct(metrics.get("tracking_error_annualized")),
        help="Annualized stdev of (strategy returns − benchmark returns). How far the strategy deviates from the benchmark.",
    )
    cols2[2].metric(
        f"{label} CAGR",
        _pct(metrics.get("benchmark_cagr")),
    )


def select_strategy_or_preset(
    strategies: list,
    presets: list[dict],
    key: str,
    label: str = "Strategy",
):
    """Render a combined strategy selector (base strategies + custom presets).

    Returns (strategy_cls, initial_params, source_label) where:
      - strategy_cls: the BaseStrategy subclass to instantiate
      - initial_params: dict of starting parameter values for widgets
        (base defaults if a base strategy is picked; preset's saved params
        merged onto base defaults if a preset is picked)
      - source_label: short string describing the selection ("Base" / "Preset · <name>")

    Pages should render param widgets using `strategy_cls.default_params` for
    keys/types and `initial_params[key]` for the starting value.
    """
    strategy_lookup = {c.name: c for c in strategies}
    preset_lookup = {p["id"]: p for p in presets}

    options = [f"base:{c.name}" for c in strategies]
    options.extend([f"preset:{p['id']}" for p in presets])

    def _fmt(opt: str) -> str:
        kind, value = opt.split(":", 1)
        if kind == "base":
            cls = strategy_lookup[value]
            return f"{cls.display_name} (v{cls.version})"
        p = preset_lookup[int(value)]
        base_cls = strategy_lookup.get(p["base_strategy"])
        base_display = base_cls.display_name if base_cls else p["base_strategy"]
        return f"Custom · {p['name']}  (based on {base_display})"

    selected = st.selectbox(label, options=options, format_func=_fmt, key=key)
    kind, value = selected.split(":", 1)

    if kind == "base":
        cls = strategy_lookup[value]
        return cls, dict(cls.default_params), "Base strategy"

    p = preset_lookup[int(value)]
    cls = strategy_lookup.get(p["base_strategy"])
    if cls is None:
        st.error(
            f"Preset '{p['name']}' references base strategy "
            f"'{p['base_strategy']}' which isn't registered."
        )
        st.stop()
    merged = dict(cls.default_params)
    merged.update(p["params"])
    return cls, merged, f"Preset · {p['name']}"

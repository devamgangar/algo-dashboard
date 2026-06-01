"""Strategies page - browse registered strategies.

Reads from the in-memory strategy registry (populated at import time by
core/strategies/__init__.py). To add a strategy, drop a new file under
core/strategies/ with @register_strategy — it will appear here automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `from core...` imports when streamlit runs this page from `pages/`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core.strategies import list_strategies  # noqa: E402

st.set_page_config(page_title="Strategies", layout="wide")
st.session_state["__current_page"] = "strategies"
st.title("Strategies")

strategies = list_strategies()

if not strategies:
    st.warning(
        "No strategies registered. Check that classes under core/strategies/ "
        "are decorated with @register_strategy."
    )
    st.stop()

st.caption(f"{len(strategies)} strategy(ies) registered")

rows = []
for cls in strategies:
    rows.append({
        "Name":          cls.name,
        "Display name":  cls.display_name,
        "Version":       cls.version,
        "Defaults":      ", ".join(f"{k}={v}" for k, v in cls.default_params.items()),
        "Sizing":        f"{cls.sizing.get('type')}={cls.sizing.get('value')}",
    })

st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

st.markdown("---")
st.subheader("Strategy details")

selected_name = st.selectbox(
    "Select a strategy",
    options=[c.name for c in strategies],
    format_func=lambda n: next(c.display_name for c in strategies if c.name == n),
)

selected = next(c for c in strategies if c.name == selected_name)

col1, col2 = st.columns([2, 1])
with col1:
    st.markdown(f"**{selected.display_name}**  (`{selected.name}` v{selected.version})")
    st.write(selected.description or "_No description provided._")
with col2:
    st.markdown("**Default parameters**")
    st.json(selected.default_params)
    st.markdown("**Position sizing**")
    st.json(selected.sizing)

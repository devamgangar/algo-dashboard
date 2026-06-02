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

import traceback  # noqa: E402

from core.strategies import get_strategy, list_strategies  # noqa: E402
from core.ui import inject_base_style, page_header  # noqa: E402
from db import repository as repo  # noqa: E402

st.set_page_config(page_title="Strategies", layout="wide")
st.session_state["__current_page"] = "strategies"
inject_base_style()
page_header(
    "Strategies",
    "Pluggable strategy registry. Drop a file under core/strategies/ with @register_strategy and it shows up here.",
)

strategies = list_strategies()
strategy_lookup = {c.name: c for c in strategies}   # used by preset section below

if not strategies:
    st.warning(
        "No strategies registered. Check that classes under core/strategies/ "
        "are decorated with @register_strategy."
    )
    st.stop()

_n = len(strategies)
st.markdown(f"**{_n} {'strategy' if _n == 1 else 'strategies'} registered**")

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

st.divider()
st.subheader("Strategy details")

selected_name = st.selectbox(
    "Select a strategy",
    options=[c.name for c in strategies],
    format_func=lambda n: next(c.display_name for c in strategies if c.name == n),
)

selected = next(c for c in strategies if c.name == selected_name)

with st.container(border=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"**{selected.display_name}**  (`{selected.name}` v{selected.version})")
        st.write(selected.description or "_No description provided._")
    with col2:
        st.markdown("**Default parameters**")
        st.json(selected.default_params)
        st.markdown("**Position sizing**")
        st.json(selected.sizing)


# ─── Custom presets ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Custom presets")
st.caption(
    "Save a named bundle of parameters as a preset. Presets show up alongside "
    "the base strategies in the Backtest, Sweep, and Forward Testing dropdowns. "
    "Editable at run time — you can still tweak params for a single run without "
    "modifying the saved preset."
)

presets = repo.list_presets()

if presets:
    preset_rows = []
    for p in presets:
        preset_rows.append({
            "ID":              p["id"],
            "Name":            p["name"],
            "Base strategy":   p["base_strategy"],
            "Params":          ", ".join(f"{k}={v}" for k, v in p["params"].items()),
            "Description":     p["description"] or "",
            "Created":         str(p["created_at"])[:19],
        })
    st.dataframe(pd.DataFrame(preset_rows), width="stretch", hide_index=True)

    # Delete preset
    del_col_l, del_col_r = st.columns([2, 1])
    with del_col_l:
        to_delete = st.selectbox(
            "Delete a preset",
            options=["—"] + [f"#{p['id']}: {p['name']}" for p in presets],
            key="preset_delete_select",
        )
    with del_col_r:
        st.write("")
        st.write("")
        if to_delete != "—":
            preset_id_to_delete = int(to_delete.split(":")[0].lstrip("#"))
            confirm = st.checkbox("Confirm delete", key=f"confirm_del_{preset_id_to_delete}")
            if st.button("Delete preset", type="secondary", disabled=not confirm):
                if repo.delete_preset(preset_id_to_delete):
                    st.success(f"Deleted preset #{preset_id_to_delete}.")
                    st.rerun()
                else:
                    st.error("Delete failed.")
else:
    st.info("No custom presets yet. Create one below.")

# Create new preset
with st.expander("Create a new preset", expanded=not presets):
    new_base_name = st.selectbox(
        "Base strategy",
        options=[c.name for c in strategies],
        format_func=lambda n: strategy_lookup[n].display_name,
        key="preset_base",
    )
    new_base_cls = strategy_lookup[new_base_name]

    new_preset_name = st.text_input(
        "Preset name",
        placeholder="e.g., Aggressive SMA on smalls",
        key="preset_name",
        help="Must be unique. Shows up in strategy dropdowns as 'Custom · <name>'.",
    )
    new_preset_desc = st.text_input(
        "Description (optional)", key="preset_desc",
    )

    st.markdown("**Parameters** (start from the base strategy's defaults)")
    preset_p_cols = st.columns(max(1, len(new_base_cls.default_params)))
    new_preset_params: dict = {}
    for i, (pkey, pdefault) in enumerate(new_base_cls.default_params.items()):
        with preset_p_cols[i % len(preset_p_cols)]:
            wkey = f"preset_p_{pkey}"
            if isinstance(pdefault, bool):
                new_preset_params[pkey] = st.checkbox(pkey, value=pdefault, key=wkey)
            elif isinstance(pdefault, int):
                new_preset_params[pkey] = int(
                    st.number_input(pkey, value=pdefault, step=1, key=wkey)
                )
            elif isinstance(pdefault, float):
                new_preset_params[pkey] = float(
                    st.number_input(pkey, value=pdefault, step=0.1, key=wkey)
                )
            else:
                new_preset_params[pkey] = st.text_input(pkey, value=str(pdefault), key=wkey)

    if st.button("Save preset", type="primary", disabled=not new_preset_name):
        try:
            # Validate by trying to instantiate
            new_base_cls(**new_preset_params)
            preset_id = repo.create_preset(
                name=new_preset_name.strip(),
                base_strategy=new_base_name,
                params=new_preset_params,
                description=(new_preset_desc.strip() or None),
            )
            st.success(f"Saved preset #{preset_id}: {new_preset_name}")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to save preset: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


# ─── Inline docs: how to add a brand-new strategy (code path) ───────────────
st.divider()
with st.expander("How to add a brand-new strategy (with custom signal logic)", expanded=False):
    st.markdown("""
Presets let you change **parameters** of existing strategies. To add a strategy with
**new signal logic** (e.g., a totally different entry/exit rule), you write a small
Python file and add it to the repo.

**Three steps:**

**1.** Create `core/strategies/your_strategy.py`:
""")
    st.code(
        '''"""My new strategy — buy on Monday close, exit on Friday close."""
from __future__ import annotations

import pandas as pd

from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy


@register_strategy
class WeeklySwing(BaseStrategy):
    name = "weekly_swing"
    display_name = "Weekly Swing"
    version = "1.0.0"
    description = "Long on Monday close, exit on Friday close."
    default_params = {}
    sizing = {"type": "percent", "value": 0.95}

    def generate_signals(self, ohlcv):
        is_monday = pd.Series(ohlcv.index.weekday == 0, index=ohlcv.index)
        is_friday = pd.Series(ohlcv.index.weekday == 4, index=ohlcv.index)
        return is_monday, is_friday
''',
        language="python",
    )
    st.markdown("""
**2.** Register it by adding one line to `core/strategies/__init__.py`:
""")
    st.code(
        "from core.strategies import your_strategy  # noqa: F401",
        language="python",
    )
    st.markdown("""
**3.** Restart Streamlit. The new strategy appears in every dropdown automatically.

Once registered, you can create custom presets of it in the **Custom presets** section above.

---

**What `generate_signals` must return:** a 2-tuple of boolean pandas Series, both
indexed identically to `ohlcv`. The first is **entries** (True → open a long),
the second is **exits** (True → close the long). Strategies are **long-only** at
the engine level; exits while flat are no-ops.
""")

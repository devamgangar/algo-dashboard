# Algo Trading Dashboard

A multi-page Streamlit dashboard for backtesting, parameter sweeping, and paper-trading equity strategies on Indian markets (NSE / BSE). Persistent run history in SQLite; pluggable strategy framework; sweep heatmaps; forward-testing with daily virtual equity curves.

Built as a learning project with depth: every layer is intentionally separable so the same code can swap data sources (yfinance ↔ Groww), persistence backends (SQLite ↔ Postgres), or backtest engines (vectorbt ↔ backtrader) without rewriting business logic.

> **Live demo:** https://algo-dashboard.streamlit.app
>
>  Algo Trading Dashboard — Streamlit (multi-page) · Python · SQLite/SQLAlchemy · 
  ▎ vectorbt · Plotly
  ▎ Built and deployed a full backtesting + paper-trading platform for Indian equity
  ▎  strategies. Pluggable strategy framework (4 strategies: SMA, RSI, Bollinger, 
  ▎ MACD); RFR-aware risk metrics; parameter-sweep heatmaps with CSV export; 
  ▎ multi-run comparison views with normalized equity curves; daily forward-testing 
  ▎ with scheduled paper-trade ticks. Live: https://algo-dashboard.streamlit.app
  ▎ github.com/devamgangar/algo-dashboard

---

## Status

| Step | Description | Status |
|------|-------------|:------:|
| 1 | Project scaffold, SQLite schema, Streamlit shell | Done |
| 2 | Data layer (yfinance + parquet cache) | Done |
| 3 | Strategy registry + SMA Crossover | Done |
| 4 | Backtest engine (vectorbt wrapper) | Done |
| 5 | DB persistence (SQLAlchemy + repository) | Done |
| 6 | Backtest tab + Results tab (filter, detail, comparison, price-with-signals) | Done |
| 7 | More strategies (RSI Mean Reversion, Bollinger Breakout, MACD Crossover) | Done |
| 8 | Parameter sweeps with heatmap + CSV export | Done |
| 9 | Groww API as second data source | Deferred (yfinance sufficient for equity scope) |
| 10 | Forward testing (paper trading with virtual portfolio + scheduled ticks) | Done |

---

## Tech Stack

| Layer | Technology | Why this choice |
|---|---|---|
| Language | Python 3.11 | First-class data science ecosystem; vectorbt requires it |
| UI | Streamlit (multi-page) | Fastest path from Python code to interactive dashboard; trade-off is single-user runtime |
| Data manipulation | pandas, numpy | Industry standard for time-series and tabular work |
| Data source | yfinance | Free, no auth, decent Indian coverage via `.NS` / `.BO` suffix |
| Cache format | Apache Parquet (via pyarrow) | Columnar + compressed; ~10x smaller than CSV, ~50x faster to read |
| Backtest engine | vectorbt | 100-1000x faster than event-driven engines via numpy/numba vectorization |
| Database | SQLite | Zero-server, file-based, ships with Python; can swap to Postgres later via SQLAlchemy |
| ORM | SQLAlchemy 2.x | Database-agnostic; keeps SQLite-to-Postgres migration cheap |
| Plotting | Plotly | Interactive in Streamlit; native equity / drawdown / heatmap / scatter overlays |
| Config | YAML (PyYAML) | Human-readable defaults outside code |
| Static analysis | Semgrep (MCP) | Catches SQL injection, dynamic imports, unsafe patterns at write time |

---

## Project Layout

```
algo-dashboard/
├── Home.py                       Streamlit entry point
├── pages/
│   ├── 1_Strategies.py           Browse the 4 registered strategies
│   ├── 2_Backtest.py             Configure + run a single backtest; auto-saves to DB
│   ├── 3_Results.py              Filter past runs, detail view, multi-run comparison
│   ├── 4_Forward_Testing.py      Start, monitor, tick paper-trading runs
│   └── 5_Sweep.py                Grid backtests over parameter ranges; heatmap + CSV export
├── core/
│   ├── strategies/
│   │   ├── base.py               BaseStrategy abstract class
│   │   ├── registry.py           @register_strategy decorator + lookup
│   │   ├── sma_crossover.py      Trend-following: SMA fast > SMA slow
│   │   ├── rsi_mean_reversion.py Counter-trend: RSI < 30 → buy, > 70 → exit
│   │   ├── bollinger_breakout.py Volatility: close > upper band → buy
│   │   ├── macd_crossover.py     Momentum: MACD > signal line
│   │   └── __init__.py           Explicit static imports (no dynamic discovery)
│   ├── engine/
│   │   ├── backtest.py           BacktestResult dataclass + run_backtest()
│   │   ├── sweep.py              run_sweep() — cartesian product backtest grid
│   │   └── forward.py            TickResult dataclass for forward runs
│   ├── data/
│   │   ├── loader.py             get_ohlcv() with parquet cache
│   │   └── sources.py            yfinance adapter (Groww adapter slot reserved)
│   └── analytics/
│       ├── metrics.py            Metric metadata + formatting (rupees / %  / ratio)
│       └── plots.py              equity_curve / drawdown / price-with-signals /
│                                 heatmap / comparison-overlay charts
├── db/
│   ├── schema.sql                Full DDL (10 tables, 8 indices)
│   ├── init_db.py                Apply schema (idempotent — CREATE IF NOT EXISTS)
│   ├── inspect.py                CLI: tables, row counts, recent runs
│   ├── models.py                 SQLAlchemy ORM (mirrors schema.sql)
│   ├── session.py                Engine + session ctx mgr; auto-inits DB on import
│   └── repository.py             High-level CRUD for backtests + forward runs
├── services/
│   ├── backtest_service.py       UI ↔ engine ↔ DB orchestration (with run dedup via fingerprint)
│   ├── sweep_service.py          Fetch data once, sweep over param grid
│   └── forward_service.py        Start / tick / stop forward runs; tick_all_active()
├── scripts/
│   └── forward_tick.py           Standalone tick for Windows Task Scheduler / cron
├── data/
│   ├── backtest.db               SQLite database (gitignored; auto-initialized on first launch)
│   └── cache/
│       └── *.parquet             OHLCV cache, one file per (exchange, symbol, interval)
├── tests/
│   ├── smoke_data.py             Cache hit / partial fetch / no-NaN
│   ├── smoke_strategy.py         Registry discovery, instantiation, signal gen
│   ├── smoke_backtest.py         End-to-end backtest pipeline
│   ├── smoke_db.py               Save → list → read-back → integrity check
│   └── profile_imports.py        Diagnostic — times every heavy import individually
├── docs/
│   ├── setup.md                  Full install + run guide (Linux/Mac/Windows + corporate quirks)
│   └── scheduled-forward-tick.md Windows Task Scheduler walkthrough for daily ticks
├── .streamlit/config.toml        Server settings (port 8765, watcher off)
├── config.yaml                   Default capital / costs / RFR / paths
└── requirements.txt
```

---

## Quick start

Full instructions for fresh installs (incl. corporate Windows quirks) live in [`docs/setup.md`](docs/setup.md). The TL;DR:

### Linux / macOS

```bash
cd algo-dashboard
python -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run Home.py
# Browser → http://localhost:8501
```

The DB auto-initializes on first launch — no separate `init_db.py` step needed.

### Windows (PowerShell)

```powershell
cd "C:\path\to\algo-dashboard"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run Home.py
# Browser → http://localhost:8765   (our config.toml uses 8765 — see Gotchas below)
```

For DESCO/corporate environments, see [`docs/setup.md`](docs/setup.md) for AppLocker workarounds and the recommended "venv on C:, project on C:" workflow.

### Verifying the install

```bash
python tests/smoke_data.py        # data layer: cache hit, partial fetch, no NaN
python tests/smoke_strategy.py    # registry: discovery, instantiation, signal gen
python tests/smoke_backtest.py    # full backtest pipeline
python tests/smoke_db.py          # save → list → read-back → integrity check
python db/inspect.py              # DB state: tables + row counts
```

---

## Development log

### Step 1 — Scaffold and database schema

**Built:** project tree, SQLite schema (originally 9 tables / now 10), `init_db.py`, empty Streamlit shell with 4 placeholder tabs, `config.yaml`, `requirements.txt`, `.gitignore`.

**Key schema decisions:**
- Hybrid metrics: high-traffic metrics (Sharpe, Sortino, max DD, CAGR, win rate, total return, num trades) live as columns on `backtest_runs` for fast indexed queries; everything else goes in long-format `run_metrics`. New metrics → new rows, no schema change.
- `JSON` for `params` because parameter schemas vary by strategy; the alternative is EAV (entity-attribute-value) hell.
- `ON DELETE CASCADE` so deleting a run cleanly removes its trades, equity curve, and metrics.
- `code_hash` on `strategies` for reproducibility — detect when a strategy's implementation has drifted from a previous run.

**Tradeoffs:** SQLite over Postgres for zero-server simplicity, Parquet over SQLite rows for time-series, vectorbt over backtrader for vectorization speed, 95% all-in sizing for v1 simplicity (with sizing as a per-strategy attribute for later flexibility).

---

### Step 2 — Data layer with parquet caching

**Built:** `core/data/sources.py` (yfinance adapter), `core/data/loader.py` (`get_ohlcv` with cache orchestration).

**Public API:**
```python
from core.data import get_ohlcv
df = get_ohlcv("RELIANCE", start="2024-01-01", end="2025-12-31", interval="1d")
```

**Cache strategy:** one parquet file per `(exchange, symbol, interval)`. On request, decide whether the requested range is fully in cache (return slice), past cache end (fetch only the tail), or before cache start (re-fetch). Today's bar is always re-fetched in case the market is still updating.

**Problems faced:**
- **yfinance placeholder rows** — NaN OHLC for today-before-close, flat OHLC + zero volume on holidays. Fixed with a `_clean_ohlcv()` filter in `_standardize()` so bad rows never enter the cache.

---

### Step 3 — Strategy registry + SMA Crossover

**Built:** `BaseStrategy` ABC, `@register_strategy` decorator + registry, `SMACrossover` as the first concrete strategy, `tests/smoke_strategy.py`, functional Strategies tab.

**Pattern:**
```python
@register_strategy
class MyStrategy(BaseStrategy):
    name = "my_strategy"
    default_params = {"window": 20}
    sizing = {"type": "percent", "value": 0.95}

    def generate_signals(self, ohlcv) -> tuple[pd.Series, pd.Series]:
        ...
```

Strategies are engine-agnostic — they return plain pandas boolean Series. Only the engine layer knows vectorbt exists.

**Problems faced:**
- **Semgrep blocked dynamic strategy auto-discovery.** Original `__init__.py` used `pkgutil.iter_modules()` + `importlib.import_module(name)` for auto-loading. Even with regex validation + `# nosemgrep`, Semgrep kept flagging dynamic imports. Switched to **explicit static imports** in `__init__.py`: adding a strategy now requires one extra import line, but the active list is auditable from one place.
- **SMA warmup-period false signal (latent).** During the first `slow_window - 1` bars, `slow` is NaN; `fast > slow` evaluates to `False`. On the first valid bar, if `fast > slow`, the crossover detector spuriously fired an entry. Fixed with a `slow_prev_valid = slow.shift(1).notna()` mask.
- **Pandas `FutureWarning` on bool fillna.** `above.shift(1).fillna(False)` triggers a downcasting deprecation. Switched to `shift(1, fill_value=False)`.

---

### Step 4 — Backtest engine

**Built:** `core/engine/backtest.py` with `BacktestResult` dataclass and `run_backtest()` — wraps vectorbt's `Portfolio.from_signals`. Strategy signals are shifted by 1 bar (signal at T → fill at T+1) to avoid lookahead bias. Whole shares only (Indian retail reality).

**Returns a `BacktestResult` containing:**
- `trades` DataFrame (per-event log: one BUY row + one SELL row per round-trip, plus open BUYs)
- `equity_curve` DataFrame (timestamp, equity, cash, position_value, drawdown_pct)
- `summary_metrics` (the indexed columns on `backtest_runs`)
- `extended_metrics` (long-format goes to `run_metrics`)

**Iteration 2:** added `trade_value` column to trades schema; added `duration_days` (days held per round-trip, NULL on BUY rows); added `risk_free_rate` parameter with default **6.5%** (Indian liquid-fund yield as of early 2026). Sharpe/Sortino now use RFR-adjusted excess return. Added `excess_return_vs_rfr` and `return_per_year_in_market` (annualized return only counting in-market bars) to surface "the strategy's edge over cash" and "signal quality vs signal frequency" separately.

**Problems faced:**
- **`pf.sortino_ratio()` doesn't accept `risk_free=`.** vectorbt's Sortino uses the parameter name `required_return` instead. Different name, same concept (minimum acceptable return).
- **Sharpe was misleading when `num_trades == 0`.** Mathematically undefined (div-by-zero); my `_safe_float` coerced NaN/inf to 0, producing a "looks fine" zero. Now explicitly set Sharpe / Sortino / win-rate to `None` when no trades fired.

---

### Step 5 — DB persistence

**Built:** SQLAlchemy ORM models in `db/models.py`, engine + session context manager in `db/session.py` (with `PRAGMA foreign_keys = ON` per connection so cascades fire), repository in `db/repository.py` with `save_result`, `list_runs`, `get_run`, `delete_run`, plus `upsert_strategy` and `list_registered_strategies`.

**Iteration 2:** added `fingerprint` column to `backtest_runs` — SHA-256 over all run inputs (symbol, dates, strategy+version, params, costs, RFR, data source). The service layer checks for existing fingerprint matches before running; same inputs → returns cached run, skips recompute. A `force_rerun=True` parameter bypasses the cache for explicit re-runs (e.g., to pick up yfinance restatements). UI surfaces this as a "Force re-run" checkbox + a "Reused cached run #N" indicator.

**Cloud-readiness fix:** `db/session.py` calls `_ensure_db_initialized()` on import — creates the DB file with the schema applied if missing. Lets the app work on Streamlit Community Cloud without a separate `init_db.py` step.

---

### Step 6 — Backtest tab + Results tab + service layer

**Built:** `services/backtest_service.py` (single `run_and_save` entry point that the UI calls); fully functional Backtest tab with auto-generated parameter form, equity curve + drawdown plots, formatted metric tables; Results tab with strategy/symbol filters, multi-row selection, single-run detail view, multi-run comparison view (side-by-side metrics table + overlaid equity curves + Normalize-to-100 toggle), and per-run delete with confirm-checkbox gate.

**Iteration 2:** filters default to empty (user explicitly opts in); aggregate summary panel above the table (avg / median / % profitable / best / worst across the filtered set); Streamlit `column_config` formatting (percent / rupees / ratios) instead of raw fractions; price-with-signals chart on the Results detail view (close-price line + green BUY triangles + red SELL triangles with hover showing PnL and days held); Backtest tab session lifecycle (results disappear on navigation to another tab, preserved across in-page interactions like expander toggles).

**Problems faced:**
- **Network share (Z:\) killed Streamlit performance.** Tab switches took 10-30 seconds. Root cause: every Python `import` is an SMB round-trip. Profiling (`tests/profile_imports.py`) showed cold imports total ~90 seconds on the network share vs ~4 seconds locally. Lazy-imported vectorbt in the engine + pre-warmed plotly/vectorbt at app startup helped, but the real fix was **moving the project to local C:** — 70x speedup. Now editing on the network share + `robocopy /MIR` to local for execution.
- **Cursor IDE binds port 8501** (Streamlit's default). Browser at `localhost:8501` was serving Cursor's webview instead of our app. Diagnosed via `Get-NetTCPConnection -LocalPort 8501`. Fixed by setting `port = 8765` in `.streamlit/config.toml`.
- **Stale `.pyc` cache on Windows + network share** — Python sometimes loaded old bytecode when source was edited from the Linux side. Fixed via periodic `__pycache__/` wipe; `fileWatcherType = "none"` in config to avoid the watcher hammering the share.

---

### Step 7 — RSI, Bollinger, MACD

**Built:** three new strategies, each following the same `@register_strategy` pattern. RSI uses Wilder smoothing (canonical formulation, matches TradingView); Bollinger Breakout uses 20-period SMA + 2σ bands by default; MACD uses 12/26/9 EMAs.

Each strategy auto-appears in the Backtest tab's strategy dropdown, in the Sweep tab's parameter introspection, and in the Results tab's filter — no additional UI work because the registry is metadata-driven.

**Warmup handling:** SMA / RSI / Bollinger use `.shift(1).notna()` to mask warmup-period false signals. MACD uses positional warmup (`warmup_done.iloc[slow + signal:] = True`) since EMAs don't return NaN — they always have values from bar 0.

**RSI div-by-zero guard:** if all bars in the lookback window were gains (no losses), `avg_loss = 0` would NaN the RSI computation. Replace `0.0` with `pd.NA` before dividing.

---

### Step 8 — Parameter sweeps

**Built:** `core/engine/sweep.py` (cartesian product of `param_grid`, runs `run_backtest` per combo, collects results into a DataFrame), `services/sweep_service.py` (fetch OHLCV once + sweep), `core/analytics/plots.py` `metric_heatmap()` (RdYlGn diverging colorscale centered at 0), and `pages/5_Sweep.py` — per-parameter toggle to enable sweeping with min/max/step inputs, combo-count preview, progress bar during execution, heatmap when exactly 2 dims are swept (line chart when 1, table-only when 3+), top-N ranking table, and CSV export of all combos.

**Sweep results are NOT persisted to the DB** — they're exploratory by nature. The workflow is: sweep to find promising combos, then formally re-run interesting ones via the Backtest tab to save them to the Results history. Avoids cluttering `backtest_runs` with 50+ rows per sweep.

**Constraint violations don't crash the sweep.** SMA with `fast >= slow` raises in the strategy constructor → that combo's row gets NaN metrics + an `error` string. Heatmap renders those cells as transparent gaps; the sweep continues.

---

### Step 9 — Groww API (deferred)

Original plan: add Groww as a second data source. Skipped because:
- Our scope is **equity-only** (no F&O), which is exactly where Groww's value-add over yfinance is concentrated (F&O contracts, expired options, intraday minute data).
- yfinance is sufficient for daily forward testing on equities, which is what we built.
- ₹499/month subscription + auth/TOTP complexity for a feature we don't need.

The architecture supports adding it later — `core/data/loader.py` has a `_SOURCES` dict; adding a `"groww": fetch_groww` entry plus an adapter in `sources.py` is the only change required.

---

### Step 10 — Forward testing

**Built:** `core/engine/forward.py` (TickResult dataclass), `services/forward_service.py` (`start_forward_run`, `tick_forward_run`, `tick_all_active`, `stop_forward_run`), `db/repository.py` forward CRUD, `pages/4_Forward_Testing.py` (start form, runs table, detail view with equity + drawdown plots, manual "Refresh Now" + "Tick all active runs" buttons), and `scripts/forward_tick.py` for scheduled execution.

**Schema changes** (new tables mirror the backtest structure):
- `forward_runs` extended with `exchange`, `interval`, `data_source`, costs, RFR, `start_date`, `last_processed_date`, `error_msg`
- `forward_trades` mirrors `trades` (per-event log)
- `forward_equity_curve` mirrors `equity_curve`
- `forward_signals` removed (was unused — trades + equity_curve cover all needs)

**Tick model: "backtest with a moving end date."** Each tick re-runs the underlying backtest from `start_date` to today, then atomically replaces the stored `forward_trades` + `forward_equity_curve`. Idempotent — no state drift between ticks. Tradeoff: O(days) work per tick, but for daily forward tests on a few years of accumulated history this is sub-second.

**Equity renormalization:** the backtest internally has equity values across the warmup period (bars before `start_date`). Those are filtered out and the remaining series is rescaled so it begins at `initial_capital` on the first forward-window bar. This makes the equity curve cleanly start at ₹1L regardless of warmup behavior.

**Scheduled execution:** `scripts/forward_tick.py` is designed for Windows Task Scheduler. See [`docs/scheduled-forward-tick.md`](docs/scheduled-forward-tick.md) for the full registration walkthrough (`Register-ScheduledTask`, log capture, troubleshooting). Manual ticking via the UI also works.

**UI iteration:** the detail-view metrics were originally a single "Position: LONG 67 shares (₹X)" cell. Split into separate `Position` (LONG / FLAT) + `Shares held` (count) columns. Renamed `Equity` → `Portfolio value` with the return % delta to make total-value vs cash distinction obvious to non-finance readers.

---

## Environment-specific gotchas (Windows + corporate AppLocker)

Documented so they don't have to be re-discovered:

| Symptom | Cause | Fix |
|---|---|---|
| `python -m venv .venv` fails with `[WinError 5] Access is denied` on a network share | Venv creation needs filesystem operations the share doesn't allow | Put venv on local C:, project on C: too if possible |
| `pip install` fails with "This program is blocked by group policy" | AppLocker blocks `.exe` files from user-writable locations; `pip.exe` is collateral damage | Use `python -m pip install ...` (the python interpreter is allowed) |
| `streamlit run Home.py` fails the same way | Same AppLocker rule blocks `streamlit.exe` | `python -m streamlit run Home.py` |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | PowerShell execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force` |
| Browser shows an unrelated page at `localhost:8501` | **Cursor IDE binds port 8501** | We override to **8765** in `.streamlit/config.toml`. Verify with `Get-NetTCPConnection -LocalPort 8501` |
| Tab switches take 10-30 seconds | Project on network share (Z:); every Python import is an SMB round-trip | Move project to local C: (~70x faster); see [`docs/setup.md`](docs/setup.md) for the sync workflow |
| `no such column: backtest_runs.fingerprint` | DB schema is older than code (after a schema iteration) | Wipe `data/backtest.db` and re-launch (auto-inits) |
| Python loads stale code after edits | `__pycache__` not invalidated by network-share timestamp lag | `Get-ChildItem -Recurse -Filter __pycache__ \| Remove-Item -Recurse -Force` |

---

## Roadmap

- [x] Step 1 — Scaffold + SQLite schema
- [x] Step 2 — Data layer with parquet caching
- [x] Step 3 — Strategy registry + SMA Crossover
- [x] Step 4 — Backtest engine with RFR-aware metrics + trade durations
- [x] Step 5 — DB persistence (SQLAlchemy + fingerprint dedup)
- [x] Step 6 — Backtest tab + Results tab (filter / detail / comparison / price-with-signals)
- [x] Step 7 — RSI, Bollinger, MACD strategies
- [x] Step 8 — Parameter sweeps with heatmap + CSV export
- [ ] ~~Step 9 — Groww API as second data source~~ (deferred; yfinance sufficient for equity scope)
- [x] Step 10 — Forward testing with virtual portfolio + scheduled ticks

**Stretch ideas (not in v1 plan):**
- Walk-forward optimization (sweep internals run on rolling train/test windows)
- Multi-symbol portfolios (basket strategies, capital allocation)
- Monte Carlo resampling on trades for confidence intervals on Sharpe / max DD
- Benchmark-relative metrics (alpha / beta / information ratio vs NIFTY 50)
- Survivorship-bias-aware universe (use listing/delisting dates)
- Real broker integration (Zerodha / Groww sandbox for actual paper orders)
- Alembic migrations to evolve the schema without wiping the DB

---

## Documentation

- [`docs/setup.md`](docs/setup.md) — full install + run guide for fresh systems (Linux/Mac/Windows + corporate quirks)
- [`docs/scheduled-forward-tick.md`](docs/scheduled-forward-tick.md) — Windows Task Scheduler walkthrough for daily forward-tick automation
- The schema: [`db/schema.sql`](db/schema.sql) (DDL) and [`db/models.py`](db/models.py) (SQLAlchemy ORM)
- Inline docstrings on every module under `core/`, `services/`, `db/`

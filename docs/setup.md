# Setup — running this project on a fresh system

Walkthrough for installing the dashboard on a Windows, Linux, or Mac machine you've never set up before.

## What you need

| Requirement | Version / notes |
|---|---|
| Python | 3.11 or 3.12 (3.10 should also work) |
| pip | bundled with Python |
| Disk space | ~1 GB (most of it is the venv with vectorbt + numba) |
| RAM | 1 GB free during runs |
| Network | Required for first install (pip) and every backtest (yfinance) |
| Git | Optional, only if cloning from a repo |

## What's in the project folder

```
algo-dashboard/
├── Home.py                     Streamlit entry point
├── pages/                      4 multi-page tabs + Sweep + Forward Testing
├── core/                       strategies, engine, data, analytics
├── db/                         models, init_db, schema.sql, inspect.py
├── services/                   orchestration (UI <-> engine <-> DB)
├── scripts/                    forward_tick.py for scheduled execution
├── tests/                      smoke tests (manual; not pytest yet)
├── docs/                       this doc + the scheduled-tick walkthrough
├── config.yaml                 default capital / costs / RFR
├── requirements.txt            Python dependencies
├── .streamlit/config.toml      server settings (port 8765, watcher off)
└── README.md                   project overview + roadmap
```

These directories get created automatically on first run; **do not copy from another machine:**
- `data/backtest.db` — your local SQLite DB
- `data/cache/*.parquet` — OHLCV cache
- `.venv/` — the virtual environment (always rebuild on each machine)
- `__pycache__/` — Python bytecode (always rebuild)
- `logs/` — if you set up scheduled ticking with logging

## Setup — Linux / Mac

```bash
cd algo-dashboard

# Create + activate venv
python -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Initialize the SQLite DB (creates data/backtest.db with 9 tables)
python db/init_db.py

# Verify with the smoke tests (each runs end-to-end against real yfinance data)
python tests/smoke_data.py
python tests/smoke_strategy.py
python tests/smoke_backtest.py
python tests/smoke_db.py

# Launch the dashboard
streamlit run Home.py
```

Browser opens automatically to `http://localhost:8501`.

## Setup — Windows (PowerShell)

For a vanilla Windows install:

```powershell
cd "C:\path\to\algo-dashboard"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python db\init_db.py
python -m streamlit run Home.py
```

Browser: `http://localhost:8765` (we override the default 8501 in `.streamlit/config.toml` because Cursor IDE binds 8501).

### Corporate Windows quirks (DESCO and similar)

If your project lives on a **network share** (mapped drive like `Z:\`) and the machine has AppLocker / group policy restrictions:

#### 1. Venv on network share fails (`[WinError 5] Access is denied`)

Network shares often deny the filesystem operations `python -m venv` needs. Solution: put the venv on local `C:` while keeping the project on the share.

```powershell
New-Item -ItemType Directory -Force -Path "C:\Users\<you>\venvs" | Out-Null
python -m venv "C:\Users\<you>\venvs\algo-dashboard"
& "C:\Users\<you>\venvs\algo-dashboard\Scripts\Activate.ps1"

# Now navigate to the project on the share
cd "Z:\path\to\algo-dashboard"
```

#### 2. `pip.exe blocked by group policy`

AppLocker can block `.exe` wrappers in user-writable locations. Workaround: invoke pip as a Python module instead.

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Same trick for Streamlit:

```powershell
python -m streamlit run Home.py
```

#### 3. `Activate.ps1 cannot be loaded because running scripts is disabled`

PowerShell execution policy. Allow scripts in the current session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
```

Then re-run the Activate command.

#### 4. Performance is awful on the network share

Reading hundreds of small `.py` files from a network share for every import takes ~30s per Streamlit page-load. Solution: **work on local C: instead.**

```powershell
# Copy project to local disk
robocopy "Z:\Devam proj\algo-dashboard" "C:\Users\<you>\algo-dashboard" /E /XD __pycache__ .venv

# Or set up a one-way sync function in your $PROFILE
function sync-algo {
    robocopy "Z:\Devam proj\algo-dashboard" "C:\Users\<you>\algo-dashboard" /MIR /XD __pycache__ .venv data
}

# Work from there going forward
cd "C:\Users\<you>\algo-dashboard"
```

This drops tab-switch latency from ~30s to under 1s. Keep the network copy as a backup; sync periodically.

## Verify everything works

After `streamlit run Home.py`:

1. **Home tab** loads with project description
2. **Strategies tab** lists 4 strategies (SMA Crossover, RSI Mean Reversion, Bollinger Breakout, MACD Crossover)
3. **Backtest tab**: run defaults (SMA on RELIANCE, last 2y) → metrics + equity curve render
4. **Results tab**: your run shows up; click it for detail view including price-with-signals chart
5. **Sweep tab**: sweep `fast in [10,20,30]` × `slow in [50,100]` → 6-cell heatmap
6. **Forward Testing tab**: start a forward run on RELIANCE → "started" message

If all 6 work, you're good.

## Moving your data to a new machine

The minimum-viable copy is just the **code folder.** Optionally, you can also copy your **runtime data:**

| File / dir | Copy? | Why |
|---|---|---|
| Everything except below | **Yes** | Code, configs, docs |
| `data/backtest.db` | Optional | Your saved backtest + forward-run history. Without it, you start with an empty DB. |
| `data/cache/*.parquet` | Optional | OHLCV cache. Without it, gets rebuilt from yfinance on first request (slower first time only). |
| `.venv/` | **No** | Always rebuild — paths and binaries are machine-specific |
| `__pycache__/` | **No** | Regenerated automatically by Python |
| `logs/` | Optional | Only useful for debugging the forward-tick scheduler |

## Updating to a newer version of the code

Pull the new code (or copy in fresh files). Then:

```bash
# Inside the activated venv
python -m pip install --upgrade -r requirements.txt   # if requirements changed
python db/init_db.py                                  # if schema changed
```

**Heads up on schema changes during dev:** the project uses simple "drop and re-init" rather than migrations for schema changes. Re-running `init_db.py` only adds missing tables — it doesn't apply column changes to existing tables. For a clean upgrade across schema versions:

```bash
# Save existing DB as backup if you care about run history
mv data/backtest.db data/backtest_old.db

# Fresh DB with the new schema
python db/init_db.py
```

For production-grade migrations later, the project is designed to swap in Alembic. Not done yet.

## Optional: enable scheduled forward-test ticks

Once you have at least one forward run created via the UI, you can have it tick automatically every day at 4 PM IST (after Indian market close). See `docs/scheduled-forward-tick.md` for the Windows Task Scheduler walkthrough.

## Common runtime commands

```bash
# Activate venv every session (Linux/Mac)
source .venv/bin/activate

# Activate venv every session (Windows)
& "C:\Users\<you>\venvs\algo-dashboard\Scripts\Activate.ps1"

# Launch dashboard
python -m streamlit run Home.py

# Inspect what's in the DB
python db/inspect.py

# Run a smoke test for sanity
python tests/smoke_db.py

# Tick all active forward runs manually (no scheduler needed)
python scripts/forward_tick.py

# Wipe DB and start over (loses all backtest + forward run history)
rm data/backtest.db   # Linux/Mac
Remove-Item data\backtest.db   # Windows
python db/init_db.py
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: streamlit` | venv not activated | Activate it; check `(.venv)` in your prompt |
| `[WinError 5] Access is denied` on venv | Network share | Create venv on local C: instead |
| `pip.exe blocked by group policy` | AppLocker | Use `python -m pip install ...` |
| `Activate.ps1 cannot be loaded` | PS execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force` |
| Streamlit shows unrelated page | Port conflict (Cursor binds 8501) | Confirm port 8765 (in `.streamlit/config.toml`) or run with `--server.port 8765` |
| Tab switches take 10-30s | Project on network share | Move to local C: |
| `yfinance returned no data for INFOSYS.NS` | Wrong ticker | Use NSE codes — Infosys is `INFY`, not `INFOSYS` |
| `no such column: backtest_runs.fingerprint` | DB schema is older than code | Wipe DB + re-init |
| Backtest succeeds but Results tab is empty | Browser is showing a stale page | Refresh (Ctrl+R / Cmd+R) |
| First Backtest tab visit takes 5-10s | vectorbt cold-loading | Normal, only happens once per Streamlit process |

## Where to learn more

- `README.md` — project overview, status, roadmap, tech stack rationale
- `docs/scheduled-forward-tick.md` — Windows Task Scheduler for automated daily forward ticks
- The schema: `db/schema.sql` (DDL) and `db/models.py` (SQLAlchemy ORM)
- Inline docstrings on every module under `core/` and `services/`

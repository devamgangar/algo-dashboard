-- Algo Trading Dashboard - SQLite schema
-- Idempotent: safe to run multiple times.

PRAGMA foreign_keys = ON;

-- ─── Strategies registry ────────────────────────────────
CREATE TABLE IF NOT EXISTS strategies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    display_name    TEXT    NOT NULL,
    module_path     TEXT    NOT NULL,
    version         TEXT    NOT NULL,
    code_hash       TEXT    NOT NULL,
    default_params  TEXT    NOT NULL,
    params_schema   TEXT,
    description     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);

-- ─── Backtest runs ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id     INTEGER NOT NULL REFERENCES strategies(id),
    symbol          TEXT    NOT NULL,
    exchange        TEXT    NOT NULL DEFAULT 'NSE',
    start_date      DATE    NOT NULL,
    end_date        DATE    NOT NULL,
    interval        TEXT    NOT NULL,
    params          TEXT    NOT NULL,
    initial_capital REAL    NOT NULL,
    commission_bps  REAL    NOT NULL DEFAULT 3.0,
    slippage_bps    REAL    NOT NULL DEFAULT 5.0,
    risk_free_rate  REAL    NOT NULL DEFAULT 0.0,
    fingerprint     TEXT    NOT NULL DEFAULT '',     -- sha256 of all inputs, for dedup
    data_source     TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    error_msg       TEXT,
    -- Summary metrics surfaced as columns for fast listing/sorting
    total_return    REAL,
    cagr            REAL,
    sharpe          REAL,
    sortino         REAL,
    max_drawdown    REAL,
    win_rate        REAL,
    num_trades      INTEGER,
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_runs_strategy    ON backtest_runs(strategy_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_symbol      ON backtest_runs(symbol, start_date);
CREATE INDEX IF NOT EXISTS idx_runs_sharpe      ON backtest_runs(sharpe DESC);
CREATE INDEX IF NOT EXISTS idx_runs_fingerprint ON backtest_runs(fingerprint, started_at DESC);

-- ─── Trades ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    timestamp       TIMESTAMP NOT NULL,
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL,
    qty             INTEGER NOT NULL,
    price           REAL    NOT NULL,
    trade_value     REAL    NOT NULL,
    commission      REAL    NOT NULL,
    slippage_cost   REAL    NOT NULL,
    pnl             REAL,
    duration_days   INTEGER,                         -- NULL on BUY, days held on SELL
    trade_type      TEXT,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id, timestamp);

-- ─── Equity curve (time series per run) ─────────────────
CREATE TABLE IF NOT EXISTS equity_curve (
    run_id          INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    timestamp       TIMESTAMP NOT NULL,
    equity          REAL    NOT NULL,
    cash            REAL    NOT NULL,
    position_value  REAL    NOT NULL,
    drawdown_pct    REAL    NOT NULL,
    PRIMARY KEY (run_id, timestamp)
);

-- ─── Extended metrics (long format) ─────────────────────
CREATE TABLE IF NOT EXISTS run_metrics (
    run_id          INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    metric_name     TEXT    NOT NULL,
    value           REAL    NOT NULL,
    PRIMARY KEY (run_id, metric_name)
);

-- ─── Strategy presets (user-defined param bundles) ──────
-- Each preset = (base strategy name) + (custom params override) + (display name).
-- Appears alongside base strategies in the Backtest/Sweep/Forward dropdowns.
CREATE TABLE IF NOT EXISTS strategy_presets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,    -- "Aggressive SMA on smalls"
    base_strategy   TEXT    NOT NULL,           -- "sma_crossover" (logical ref to strategy registry key)
    params          TEXT    NOT NULL,           -- JSON
    description     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_presets_base ON strategy_presets(base_strategy);

-- ─── Symbol universe ────────────────────────────────────
CREATE TABLE IF NOT EXISTS universe (
    symbol          TEXT    NOT NULL,
    exchange        TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    sector          TEXT,
    industry        TEXT,
    listed_on       DATE,
    delisted_on     DATE,
    is_active       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (symbol, exchange)
);
CREATE INDEX IF NOT EXISTS idx_universe_active ON universe(is_active);

-- ─── Portfolio backtests (one strategy across multiple symbols) ─────
-- A portfolio run applies one strategy to a basket of symbols with a shared
-- cash pool. Each signal triggers a new position sized as N% of current
-- equity (compounding). Cash-constrained: signals are skipped when funds
-- are tied up in existing positions.

CREATE TABLE IF NOT EXISTS portfolio_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id           INTEGER NOT NULL REFERENCES strategies(id),
    universe_label        TEXT    NOT NULL,    -- "NIFTY 50" / custom label
    symbols               TEXT    NOT NULL,    -- JSON array of actual tickers used
    exchange              TEXT    NOT NULL DEFAULT 'NSE',
    interval              TEXT    NOT NULL DEFAULT '1d',
    data_source           TEXT    NOT NULL,
    params                TEXT    NOT NULL,    -- JSON
    initial_capital       REAL    NOT NULL,
    position_size_pct     REAL    NOT NULL,    -- 0.10 = 10% of equity per trade
    commission_bps        REAL    NOT NULL DEFAULT 3.0,
    slippage_bps          REAL    NOT NULL DEFAULT 5.0,
    risk_free_rate        REAL    NOT NULL DEFAULT 0.065,
    start_date            DATE    NOT NULL,
    end_date              DATE    NOT NULL,
    status                TEXT    NOT NULL,
    error_msg             TEXT,
    -- summary metrics (mirror backtest_runs)
    total_return          REAL,
    cagr                  REAL,
    sharpe                REAL,
    sortino               REAL,
    max_drawdown          REAL,
    win_rate              REAL,
    num_trades            INTEGER,
    num_symbols_traded    INTEGER,           -- distinct symbols that had at least one trade
    started_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at           TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pruns_started ON portfolio_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS portfolio_trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_run_id  INTEGER NOT NULL REFERENCES portfolio_runs(id) ON DELETE CASCADE,
    timestamp         TIMESTAMP NOT NULL,
    symbol            TEXT    NOT NULL,
    side              TEXT    NOT NULL,
    qty               INTEGER NOT NULL,
    price             REAL    NOT NULL,
    trade_value       REAL    NOT NULL,
    commission        REAL    NOT NULL,
    slippage_cost     REAL    NOT NULL,
    pnl               REAL,
    duration_days     INTEGER,
    trade_type        TEXT,
    notes             TEXT
);
CREATE INDEX IF NOT EXISTS idx_ptrades_run ON portfolio_trades(portfolio_run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ptrades_sym ON portfolio_trades(portfolio_run_id, symbol);

CREATE TABLE IF NOT EXISTS portfolio_equity_curve (
    portfolio_run_id  INTEGER NOT NULL REFERENCES portfolio_runs(id) ON DELETE CASCADE,
    timestamp         TIMESTAMP NOT NULL,
    equity            REAL    NOT NULL,
    cash              REAL    NOT NULL,
    position_value    REAL    NOT NULL,
    drawdown_pct      REAL    NOT NULL,
    PRIMARY KEY (portfolio_run_id, timestamp)
);

-- ─── Forward testing (paper trading on live yfinance data) ─────────
-- A forward run is essentially "a backtest with a moving end-date." Each
-- daily tick re-runs the backtest from start_date to today and replaces
-- the run's trades / equity curve. Forward trades and equity curve mirror
-- the backtest schema exactly so the same UI helpers work for both.

CREATE TABLE IF NOT EXISTS forward_runs (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id          INTEGER NOT NULL REFERENCES strategies(id),
    symbol               TEXT    NOT NULL,
    exchange             TEXT    NOT NULL DEFAULT 'NSE',
    interval             TEXT    NOT NULL DEFAULT '1d',
    data_source          TEXT    NOT NULL DEFAULT 'yfinance',
    params               TEXT    NOT NULL,
    initial_capital      REAL    NOT NULL,
    commission_bps       REAL    NOT NULL DEFAULT 3.0,
    slippage_bps         REAL    NOT NULL DEFAULT 5.0,
    risk_free_rate       REAL    NOT NULL DEFAULT 0.065,
    start_date           DATE    NOT NULL,
    last_processed_date  DATE,                          -- NULL until first successful tick
    status               TEXT    NOT NULL DEFAULT 'active',
    error_msg            TEXT,
    started_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at           TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fruns_status ON forward_runs(status, started_at DESC);

CREATE TABLE IF NOT EXISTS forward_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    forward_run_id  INTEGER NOT NULL REFERENCES forward_runs(id) ON DELETE CASCADE,
    timestamp       TIMESTAMP NOT NULL,
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL,
    qty             INTEGER NOT NULL,
    price           REAL    NOT NULL,
    trade_value     REAL    NOT NULL,
    commission      REAL    NOT NULL,
    slippage_cost   REAL    NOT NULL,
    pnl             REAL,
    duration_days   INTEGER,
    trade_type      TEXT,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_ftrades_run ON forward_trades(forward_run_id, timestamp);

CREATE TABLE IF NOT EXISTS forward_equity_curve (
    forward_run_id  INTEGER NOT NULL REFERENCES forward_runs(id) ON DELETE CASCADE,
    timestamp       TIMESTAMP NOT NULL,
    equity          REAL    NOT NULL,
    cash            REAL    NOT NULL,
    position_value  REAL    NOT NULL,
    drawdown_pct    REAL    NOT NULL,
    PRIMARY KEY (forward_run_id, timestamp)
);

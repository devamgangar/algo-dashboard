"""High-level CRUD operations for the backtest dashboard.

Streamlit pages and tests call into this module; nobody else should touch
the ORM models or sessions directly. Each function manages its own
session/transaction (one logical unit of work per call).
"""
from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from sqlalchemy import delete, select, text, update

from core.engine import BacktestResult
from core.strategies import get_strategy
from core.strategies.base import BaseStrategy
from db.models import (
    BacktestRun as BacktestRunModel,
    EquityCurve as EquityCurveModel,
    ForwardEquityCurve as ForwardEquityCurveModel,
    ForwardRun as ForwardRunModel,
    ForwardTrade as ForwardTradeModel,
    RunMetric as RunMetricModel,
    Strategy as StrategyModel,
    Trade as TradeModel,
)
from db.session import get_session


def _compute_code_hash(cls: type) -> str:
    """SHA-256 of the source file containing `cls`. Used for drift detection."""
    src_file = inspect.getsourcefile(cls)
    if src_file is None:
        return "unknown"
    with open(src_file, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def upsert_strategy(strategy_cls: type[BaseStrategy]) -> int:
    """Ensure (name, version) is registered. Returns the strategy id.

    If the row already exists, returns its id without modifying anything
    (code_hash drift is NOT updated — we want to preserve the snapshot of
    code that previous runs were executed against).
    """
    with get_session() as session:
        existing = session.execute(
            select(StrategyModel).where(
                StrategyModel.name == strategy_cls.name,
                StrategyModel.version == strategy_cls.version,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id

        new_row = StrategyModel(
            name=strategy_cls.name,
            display_name=strategy_cls.display_name,
            module_path=strategy_cls.__module__,
            version=strategy_cls.version,
            code_hash=_compute_code_hash(strategy_cls),
            default_params=json.dumps(strategy_cls.default_params),
            params_schema=None,
            description=strategy_cls.description,
        )
        session.add(new_row)
        session.flush()
        return new_row.id


def save_result(result: BacktestResult, fingerprint: str = "") -> int:
    """Persist a BacktestResult to the DB. Returns the new run id.

    `fingerprint` is opaque to this function — the service layer computes it
    from all inputs and passes it in. The dedup index (idx_runs_fingerprint)
    lets future runs look up "have I done this exact backtest before?".
    """
    strategy_cls = get_strategy(result.strategy_name)
    strategy_id = upsert_strategy(strategy_cls)

    with get_session() as session:
        now = datetime.utcnow()
        run = BacktestRunModel(
            strategy_id=strategy_id,
            symbol=result.symbol,
            exchange=result.exchange,
            start_date=result.start_date,
            end_date=result.end_date,
            interval=result.interval,
            params=json.dumps(result.strategy_params),
            initial_capital=result.initial_capital,
            commission_bps=result.commission_bps,
            slippage_bps=result.slippage_bps,
            risk_free_rate=result.risk_free_rate,
            fingerprint=fingerprint,
            data_source=result.data_source,
            status="completed",
            error_msg=None,
            total_return=result.summary_metrics.get("total_return"),
            cagr=result.summary_metrics.get("cagr"),
            sharpe=result.summary_metrics.get("sharpe"),
            sortino=result.summary_metrics.get("sortino"),
            max_drawdown=result.summary_metrics.get("max_drawdown"),
            win_rate=result.summary_metrics.get("win_rate"),
            num_trades=result.summary_metrics.get("num_trades"),
            started_at=now,
            finished_at=now,
        )
        session.add(run)
        session.flush()
        run_id = run.id

        if not result.trades.empty:
            session.bulk_insert_mappings(
                TradeModel,
                _trades_df_to_mappings(result.trades, run_id),
            )

        if not result.equity_curve.empty:
            session.bulk_insert_mappings(
                EquityCurveModel,
                _equity_df_to_mappings(result.equity_curve, run_id),
            )

        metric_rows = [
            {"run_id": run_id, "metric_name": name, "value": float(value)}
            for name, value in result.extended_metrics.items()
        ]
        if metric_rows:
            session.bulk_insert_mappings(RunMetricModel, metric_rows)

        return run_id


def _trades_df_to_mappings(trades: pd.DataFrame, run_id: int) -> list[dict[str, Any]]:
    out = []
    for _, t in trades.iterrows():
        out.append({
            "run_id":         run_id,
            "timestamp":      pd.Timestamp(t["timestamp"]).to_pydatetime(),
            "symbol":         t["symbol"],
            "side":           t["side"],
            "qty":            int(t["qty"]),
            "price":          float(t["price"]),
            "trade_value":    float(t["trade_value"]),
            "commission":     float(t["commission"]),
            "slippage_cost":  float(t["slippage_cost"]),
            "pnl":            float(t["pnl"]) if pd.notna(t["pnl"]) else None,
            "duration_days":  int(t["duration_days"]) if pd.notna(t["duration_days"]) else None,
            "trade_type":     t.get("trade_type"),
            "notes":          t.get("notes"),
        })
    return out


def _equity_df_to_mappings(eq: pd.DataFrame, run_id: int) -> list[dict[str, Any]]:
    out = []
    for _, row in eq.iterrows():
        out.append({
            "run_id":         run_id,
            "timestamp":      pd.Timestamp(row["timestamp"]).to_pydatetime(),
            "equity":         float(row["equity"]),
            "cash":           float(row["cash"]),
            "position_value": float(row["position_value"]),
            "drawdown_pct":   float(row["drawdown_pct"]),
        })
    return out


def find_run_by_fingerprint(fingerprint: str) -> Optional[int]:
    """Return the most recent run id matching this fingerprint, or None."""
    if not fingerprint:
        return None
    with get_session() as session:
        return session.execute(
            select(BacktestRunModel.id)
            .where(BacktestRunModel.fingerprint == fingerprint)
            .order_by(BacktestRunModel.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()


def list_runs(limit: int = 20) -> list[dict]:
    """Recent runs, joined to strategy name. Summary only — no trades / equity / metrics."""
    with get_session() as session:
        rows = session.execute(
            select(BacktestRunModel, StrategyModel.name)
            .join(StrategyModel, BacktestRunModel.strategy_id == StrategyModel.id)
            .order_by(BacktestRunModel.started_at.desc())
            .limit(limit)
        ).all()

        return [
            {
                "id":            run.id,
                "strategy":      strategy_name,
                "symbol":        run.symbol,
                "exchange":      run.exchange,
                "start_date":    run.start_date,
                "end_date":      run.end_date,
                "interval":      run.interval,
                "status":        run.status,
                "total_return":  run.total_return,
                "cagr":          run.cagr,
                "sharpe":        run.sharpe,
                "sortino":       run.sortino,
                "max_drawdown":  run.max_drawdown,
                "win_rate":      run.win_rate,
                "num_trades":    run.num_trades,
                "started_at":    run.started_at,
            }
            for run, strategy_name in rows
        ]


def get_run(run_id: int) -> Optional[dict]:
    """Full run including trades DataFrame, equity_curve DataFrame, and all metrics."""
    with get_session() as session:
        row = session.execute(
            select(BacktestRunModel, StrategyModel.name, StrategyModel.version)
            .join(StrategyModel, BacktestRunModel.strategy_id == StrategyModel.id)
            .where(BacktestRunModel.id == run_id)
        ).one_or_none()
        if row is None:
            return None
        run, strategy_name, strategy_version = row

        conn = session.connection()
        trades_df = pd.read_sql_query(
            text(
                "SELECT timestamp, symbol, side, qty, price, trade_value, "
                "commission, slippage_cost, pnl, duration_days, trade_type, notes "
                "FROM trades WHERE run_id = :rid ORDER BY timestamp"
            ),
            conn,
            params={"rid": run_id},
        )
        equity_df = pd.read_sql_query(
            text(
                "SELECT timestamp, equity, cash, position_value, drawdown_pct "
                "FROM equity_curve WHERE run_id = :rid ORDER BY timestamp"
            ),
            conn,
            params={"rid": run_id},
        )

        metric_rows = session.execute(
            select(RunMetricModel).where(RunMetricModel.run_id == run_id)
        ).scalars().all()
        extended_metrics = {m.metric_name: m.value for m in metric_rows}

        return {
            "id":                run.id,
            "strategy_name":     strategy_name,
            "strategy_version":  strategy_version,
            "symbol":            run.symbol,
            "exchange":          run.exchange,
            "start_date":        run.start_date,
            "end_date":          run.end_date,
            "interval":          run.interval,
            "params":            json.loads(run.params),
            "initial_capital":   run.initial_capital,
            "commission_bps":    run.commission_bps,
            "slippage_bps":      run.slippage_bps,
            "risk_free_rate":    run.risk_free_rate,
            "fingerprint":       run.fingerprint,
            "data_source":       run.data_source,
            "status":            run.status,
            "started_at":        run.started_at,
            "finished_at":       run.finished_at,
            "summary_metrics": {
                "total_return": run.total_return,
                "cagr":         run.cagr,
                "sharpe":       run.sharpe,
                "sortino":      run.sortino,
                "max_drawdown": run.max_drawdown,
                "win_rate":     run.win_rate,
                "num_trades":   run.num_trades,
            },
            "extended_metrics":  extended_metrics,
            "trades":            trades_df,
            "equity_curve":      equity_df,
        }


def delete_run(run_id: int) -> bool:
    """Delete a run (cascades to trades, equity_curve, run_metrics)."""
    with get_session() as session:
        result = session.execute(
            delete(BacktestRunModel).where(BacktestRunModel.id == run_id)
        )
        return result.rowcount > 0


# ──────────────────────────────────────────────────────────────────────────
# Forward testing
# ──────────────────────────────────────────────────────────────────────────

def create_forward_run(
    *,
    strategy_name: str,
    symbol: str,
    exchange: str,
    interval: str,
    data_source: str,
    params: dict,
    initial_capital: float,
    commission_bps: float,
    slippage_bps: float,
    risk_free_rate: float,
    start_date,
) -> int:
    """Insert a new forward_runs row. Strategy is upserted if not yet known."""
    strategy_cls = get_strategy(strategy_name)
    strategy_id = upsert_strategy(strategy_cls)

    with get_session() as session:
        row = ForwardRunModel(
            strategy_id=strategy_id,
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            data_source=data_source,
            params=json.dumps(params),
            initial_capital=initial_capital,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            risk_free_rate=risk_free_rate,
            start_date=start_date,
            status="active",
        )
        session.add(row)
        session.flush()
        return row.id


def list_forward_runs(status: Optional[str] = None) -> list[dict]:
    """Forward runs joined to strategy name. Optionally filter by status."""
    with get_session() as session:
        stmt = (
            select(ForwardRunModel, StrategyModel.name)
            .join(StrategyModel, ForwardRunModel.strategy_id == StrategyModel.id)
            .order_by(ForwardRunModel.started_at.desc())
        )
        if status is not None:
            stmt = stmt.where(ForwardRunModel.status == status)
        rows = session.execute(stmt).all()

        out = []
        for r, strategy_name in rows:
            out.append({
                "id":                  r.id,
                "strategy":            strategy_name,
                "symbol":              r.symbol,
                "exchange":            r.exchange,
                "interval":            r.interval,
                "status":              r.status,
                "start_date":          r.start_date,
                "last_processed_date": r.last_processed_date,
                "initial_capital":     r.initial_capital,
                "started_at":          r.started_at,
                "stopped_at":          r.stopped_at,
                "error_msg":           r.error_msg,
            })
        return out


def get_forward_run_detail(forward_run_id: int) -> Optional[dict]:
    """Full forward run incl. trades DataFrame and equity_curve DataFrame."""
    with get_session() as session:
        row = session.execute(
            select(ForwardRunModel, StrategyModel.name, StrategyModel.version)
            .join(StrategyModel, ForwardRunModel.strategy_id == StrategyModel.id)
            .where(ForwardRunModel.id == forward_run_id)
        ).one_or_none()
        if row is None:
            return None
        run, strategy_name, strategy_version = row

        conn = session.connection()
        trades_df = pd.read_sql_query(
            text(
                "SELECT timestamp, symbol, side, qty, price, trade_value, "
                "commission, slippage_cost, pnl, duration_days, trade_type, notes "
                "FROM forward_trades WHERE forward_run_id = :rid ORDER BY timestamp"
            ),
            conn,
            params={"rid": forward_run_id},
        )
        equity_df = pd.read_sql_query(
            text(
                "SELECT timestamp, equity, cash, position_value, drawdown_pct "
                "FROM forward_equity_curve WHERE forward_run_id = :rid ORDER BY timestamp"
            ),
            conn,
            params={"rid": forward_run_id},
        )

        return {
            "id":                  run.id,
            "strategy_name":       strategy_name,
            "strategy_version":    strategy_version,
            "symbol":              run.symbol,
            "exchange":            run.exchange,
            "interval":            run.interval,
            "data_source":         run.data_source,
            "params":              json.loads(run.params),
            "initial_capital":     run.initial_capital,
            "commission_bps":      run.commission_bps,
            "slippage_bps":        run.slippage_bps,
            "risk_free_rate":      run.risk_free_rate,
            "start_date":          run.start_date,
            "last_processed_date": run.last_processed_date,
            "status":              run.status,
            "error_msg":           run.error_msg,
            "started_at":          run.started_at,
            "stopped_at":          run.stopped_at,
            "trades":              trades_df,
            "equity_curve":        equity_df,
        }


def replace_forward_run_data(
    *,
    forward_run_id: int,
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
    last_processed_date,
    error_msg: Optional[str] = None,
) -> None:
    """Atomically replace a forward run's trades + equity curve with fresh data.

    Used by the tick logic: each tick re-runs the underlying backtest and
    overwrites the stored state, so the run's view is always coherent.
    """
    with get_session() as session:
        # Wipe existing
        session.execute(
            delete(ForwardTradeModel).where(ForwardTradeModel.forward_run_id == forward_run_id)
        )
        session.execute(
            delete(ForwardEquityCurveModel).where(ForwardEquityCurveModel.forward_run_id == forward_run_id)
        )

        if not trades.empty:
            session.bulk_insert_mappings(
                ForwardTradeModel,
                _trades_df_to_forward_mappings(trades, forward_run_id),
            )
        if not equity_curve.empty:
            session.bulk_insert_mappings(
                ForwardEquityCurveModel,
                _equity_df_to_forward_mappings(equity_curve, forward_run_id),
            )

        session.execute(
            update(ForwardRunModel)
            .where(ForwardRunModel.id == forward_run_id)
            .values(last_processed_date=last_processed_date, error_msg=error_msg)
        )


def _trades_df_to_forward_mappings(trades: pd.DataFrame, run_id: int) -> list[dict[str, Any]]:
    out = []
    for _, t in trades.iterrows():
        out.append({
            "forward_run_id": run_id,
            "timestamp":      pd.Timestamp(t["timestamp"]).to_pydatetime(),
            "symbol":         t["symbol"],
            "side":           t["side"],
            "qty":            int(t["qty"]),
            "price":          float(t["price"]),
            "trade_value":    float(t["trade_value"]),
            "commission":     float(t["commission"]),
            "slippage_cost":  float(t["slippage_cost"]),
            "pnl":            float(t["pnl"]) if pd.notna(t["pnl"]) else None,
            "duration_days":  int(t["duration_days"]) if pd.notna(t["duration_days"]) else None,
            "trade_type":     t.get("trade_type"),
            "notes":          t.get("notes"),
        })
    return out


def _equity_df_to_forward_mappings(eq: pd.DataFrame, run_id: int) -> list[dict[str, Any]]:
    out = []
    for _, row in eq.iterrows():
        out.append({
            "forward_run_id": run_id,
            "timestamp":      pd.Timestamp(row["timestamp"]).to_pydatetime(),
            "equity":         float(row["equity"]),
            "cash":           float(row["cash"]),
            "position_value": float(row["position_value"]),
            "drawdown_pct":   float(row["drawdown_pct"]),
        })
    return out


def stop_forward_run(forward_run_id: int) -> bool:
    with get_session() as session:
        result = session.execute(
            update(ForwardRunModel)
            .where(ForwardRunModel.id == forward_run_id)
            .values(status="stopped", stopped_at=datetime.utcnow())
        )
        return result.rowcount > 0


def delete_forward_run(forward_run_id: int) -> bool:
    with get_session() as session:
        result = session.execute(
            delete(ForwardRunModel).where(ForwardRunModel.id == forward_run_id)
        )
        return result.rowcount > 0


# ──────────────────────────────────────────────────────────────────────────


def list_registered_strategies() -> list[dict]:
    """Strategies known to the DB (set on first save). May lag the in-memory registry."""
    with get_session() as session:
        rows = session.execute(
            select(StrategyModel).order_by(StrategyModel.id)
        ).scalars().all()
        return [
            {
                "id":              s.id,
                "name":            s.name,
                "display_name":    s.display_name,
                "version":         s.version,
                "code_hash_short": s.code_hash[:16],
                "default_params":  json.loads(s.default_params),
                "description":     s.description,
                "created_at":      s.created_at,
            }
            for s in rows
        ]

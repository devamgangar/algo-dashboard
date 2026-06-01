"""SQLAlchemy ORM models — mirror the DDL in db/schema.sql.

If you add or change a column here, update schema.sql to match (and vice versa).
Drift will surface as INSERT/SELECT errors in smoke_db.py.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Strategy(Base):
    __tablename__ = "strategies"

    id:             Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:           Mapped[str]              = mapped_column(String, unique=True)
    display_name:   Mapped[str]              = mapped_column(String)
    module_path:    Mapped[str]              = mapped_column(String)
    version:        Mapped[str]              = mapped_column(String)
    code_hash:      Mapped[str]              = mapped_column(String)
    default_params: Mapped[str]              = mapped_column(Text)  # JSON string
    params_schema:  Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    description:    Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    created_at:     Mapped[datetime]         = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("name", "version"),)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id:              Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id:     Mapped[int]              = mapped_column(Integer, ForeignKey("strategies.id"))
    symbol:          Mapped[str]              = mapped_column(String)
    exchange:        Mapped[str]              = mapped_column(String, default="NSE")
    start_date:      Mapped[date]             = mapped_column(Date)
    end_date:        Mapped[date]             = mapped_column(Date)
    interval:        Mapped[str]              = mapped_column(String)
    params:          Mapped[str]              = mapped_column(Text)  # JSON string
    initial_capital: Mapped[float]            = mapped_column(Float)
    commission_bps:  Mapped[float]            = mapped_column(Float, default=3.0)
    slippage_bps:    Mapped[float]            = mapped_column(Float, default=5.0)
    risk_free_rate:  Mapped[float]            = mapped_column(Float, default=0.0)
    fingerprint:     Mapped[str]              = mapped_column(String, default="")
    data_source:     Mapped[str]              = mapped_column(String)
    status:          Mapped[str]              = mapped_column(String)
    error_msg:       Mapped[Optional[str]]    = mapped_column(Text, nullable=True)

    # Summary metrics surfaced as columns for fast indexed queries
    total_return:    Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    cagr:            Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    sharpe:          Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    sortino:         Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    max_drawdown:    Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    win_rate:        Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    num_trades:      Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)

    started_at:      Mapped[datetime]         = mapped_column(DateTime, default=datetime.utcnow)
    finished_at:     Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Trade(Base):
    __tablename__ = "trades"

    id:            Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id:        Mapped[int]              = mapped_column(Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"))
    timestamp:     Mapped[datetime]         = mapped_column(DateTime)
    symbol:        Mapped[str]              = mapped_column(String)
    side:          Mapped[str]              = mapped_column(String)
    qty:           Mapped[int]              = mapped_column(Integer)
    price:         Mapped[float]            = mapped_column(Float)
    trade_value:   Mapped[float]            = mapped_column(Float)
    commission:    Mapped[float]            = mapped_column(Float)
    slippage_cost: Mapped[float]            = mapped_column(Float)
    pnl:           Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    duration_days: Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)
    trade_type:    Mapped[Optional[str]]    = mapped_column(String, nullable=True)
    notes:         Mapped[Optional[str]]    = mapped_column(Text, nullable=True)


class EquityCurve(Base):
    __tablename__ = "equity_curve"

    run_id:         Mapped[int]      = mapped_column(Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"), primary_key=True)
    timestamp:      Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    equity:         Mapped[float]    = mapped_column(Float)
    cash:           Mapped[float]    = mapped_column(Float)
    position_value: Mapped[float]    = mapped_column(Float)
    drawdown_pct:   Mapped[float]    = mapped_column(Float)


class RunMetric(Base):
    __tablename__ = "run_metrics"

    run_id:      Mapped[int]   = mapped_column(Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"), primary_key=True)
    metric_name: Mapped[str]   = mapped_column(String, primary_key=True)
    value:       Mapped[float] = mapped_column(Float)


class ForwardRun(Base):
    __tablename__ = "forward_runs"

    id:                  Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id:         Mapped[int]              = mapped_column(Integer, ForeignKey("strategies.id"))
    symbol:              Mapped[str]              = mapped_column(String)
    exchange:            Mapped[str]              = mapped_column(String, default="NSE")
    interval:            Mapped[str]              = mapped_column(String, default="1d")
    data_source:         Mapped[str]              = mapped_column(String, default="yfinance")
    params:              Mapped[str]              = mapped_column(Text)
    initial_capital:     Mapped[float]            = mapped_column(Float)
    commission_bps:      Mapped[float]            = mapped_column(Float, default=3.0)
    slippage_bps:        Mapped[float]            = mapped_column(Float, default=5.0)
    risk_free_rate:      Mapped[float]            = mapped_column(Float, default=0.065)
    start_date:          Mapped[date]             = mapped_column(Date)
    last_processed_date: Mapped[Optional[date]]   = mapped_column(Date, nullable=True)
    status:              Mapped[str]              = mapped_column(String, default="active")
    error_msg:           Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    started_at:          Mapped[datetime]         = mapped_column(DateTime, default=datetime.utcnow)
    stopped_at:          Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ForwardTrade(Base):
    __tablename__ = "forward_trades"

    id:             Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    forward_run_id: Mapped[int]              = mapped_column(Integer, ForeignKey("forward_runs.id", ondelete="CASCADE"))
    timestamp:      Mapped[datetime]         = mapped_column(DateTime)
    symbol:         Mapped[str]              = mapped_column(String)
    side:           Mapped[str]              = mapped_column(String)
    qty:            Mapped[int]              = mapped_column(Integer)
    price:          Mapped[float]            = mapped_column(Float)
    trade_value:    Mapped[float]            = mapped_column(Float)
    commission:     Mapped[float]            = mapped_column(Float)
    slippage_cost:  Mapped[float]            = mapped_column(Float)
    pnl:            Mapped[Optional[float]]  = mapped_column(Float, nullable=True)
    duration_days:  Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)
    trade_type:     Mapped[Optional[str]]    = mapped_column(String, nullable=True)
    notes:          Mapped[Optional[str]]    = mapped_column(Text, nullable=True)


class ForwardEquityCurve(Base):
    __tablename__ = "forward_equity_curve"

    forward_run_id: Mapped[int]      = mapped_column(Integer, ForeignKey("forward_runs.id", ondelete="CASCADE"), primary_key=True)
    timestamp:      Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    equity:         Mapped[float]    = mapped_column(Float)
    cash:           Mapped[float]    = mapped_column(Float)
    position_value: Mapped[float]    = mapped_column(Float)
    drawdown_pct:   Mapped[float]    = mapped_column(Float)

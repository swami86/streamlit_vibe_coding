from __future__ import annotations

import datetime
from collections import deque

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from scipy.optimize import brentq


# ---------------------------------------------------------------------------
# FIFO holdings calculation
# ---------------------------------------------------------------------------

def calculate_fifo_holdings(
    df: pd.DataFrame,
) -> tuple[dict[str, dict], list[str]]:
    """
    Calculate current holdings using FIFO cost basis.

    Returns
    -------
    holdings : dict  {ticker: {quantity, avg_cost, total_cost}}
    errors   : list of error strings for over-sell situations
    """
    lots: dict[str, deque] = {}  # ticker -> deque of [qty, price]
    errors: list[str] = []

    for _, row in df.sort_values("date").iterrows():
        ticker = row["ticker"]
        qty = float(row["quantity"])
        price = float(row["price"])
        txn = row["transaction_type"].lower()

        if ticker not in lots:
            lots[ticker] = deque()

        if txn == "buy":
            lots[ticker].append([qty, price])

        elif txn == "sell":
            total_available = sum(lot[0] for lot in lots[ticker])
            if qty > total_available + 1e-9:
                errors.append(
                    f"Cannot sell {qty:.4f} shares of {ticker}: "
                    f"only {total_available:.4f} available on {row['date'].date()}."
                )
                continue

            remaining = qty
            while remaining > 1e-9 and lots[ticker]:
                lot_qty, lot_price = lots[ticker][0]
                if lot_qty <= remaining + 1e-9:
                    remaining -= lot_qty
                    lots[ticker].popleft()
                else:
                    lots[ticker][0][0] = lot_qty - remaining
                    remaining = 0

    holdings: dict[str, dict] = {}
    for ticker, lot_deque in lots.items():
        if not lot_deque:
            continue
        total_qty = sum(lot[0] for lot in lot_deque)
        total_cost = sum(lot[0] * lot[1] for lot in lot_deque)
        if total_qty > 1e-9:
            holdings[ticker] = {
                "quantity": total_qty,
                "avg_cost": total_cost / total_qty,
                "total_cost": total_cost,
            }

    return holdings, errors


# ---------------------------------------------------------------------------
# yfinance price fetching
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch_current_prices(tickers: tuple[str, ...]) -> dict[str, float | None]:
    """Fetch the latest closing price for each ticker (cached 5 min)."""
    prices: dict[str, float | None] = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if not hist.empty:
                close = hist["Close"].dropna()
                prices[ticker] = float(close.iloc[-1]) if not close.empty else None
            else:
                prices[ticker] = None
        except Exception:
            prices[ticker] = None
    return prices


@st.cache_data(ttl=300, show_spinner=False)
def fetch_daily_changes(tickers: tuple[str, ...]) -> dict[str, dict | None]:
    """
    Fetch today vs previous close for each ticker.
    Returns {ticker: {current, prev_close, change, change_pct}} or None on failure.
    """
    result: dict[str, dict | None] = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                curr = float(hist["Close"].iloc[-1])
                result[ticker] = {
                    "current": curr,
                    "prev_close": prev,
                    "change": curr - prev,
                    "change_pct": (curr - prev) / prev * 100,
                }
            else:
                result[ticker] = None
        except Exception:
            result[ticker] = None
    return result


# ---------------------------------------------------------------------------
# Holdings dataframe
# ---------------------------------------------------------------------------

def build_holdings_dataframe(
    holdings: dict[str, dict],
    prices: dict[str, float | None],
) -> pd.DataFrame:
    """Combine FIFO holdings with current prices into a display dataframe."""
    rows = []
    for ticker, h in holdings.items():
        current_price = prices.get(ticker)
        qty = h["quantity"]
        avg_cost = h["avg_cost"]
        total_cost = h["total_cost"]

        if current_price is not None:
            market_value = qty * current_price
            unrealized_pnl = market_value - total_cost
            unrealized_pnl_pct = (unrealized_pnl / total_cost) * 100 if total_cost else 0.0
        else:
            market_value = None
            unrealized_pnl = None
            unrealized_pnl_pct = None

        rows.append(
            {
                "ticker": ticker,
                "quantity": qty,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Allocation percentage (only for holdings with a fetched price)
    total_value = df["market_value"].sum(skipna=True)
    df["allocation_pct"] = df["market_value"].apply(
        lambda v: (v / total_value * 100) if (total_value and v is not None) else None
    )

    return df.sort_values("market_value", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def calculate_performance_metrics(
    df: pd.DataFrame,
    holdings_df: pd.DataFrame,
) -> dict:
    """
    Calculate lifetime performance metrics.

    total_investment : total cash spent on all Buy transactions
    total_sells      : total cash received from all Sell transactions
    current_value    : sum of current market values of open holdings
    total_return     : total_sells + current_value - total_investment
    total_return_pct : total_return / total_investment * 100
    xirr             : annualized internal rate of return (or None)
    """
    buys = df[df["transaction_type"].str.lower() == "buy"]
    sells = df[df["transaction_type"].str.lower() == "sell"]

    total_investment = (buys["quantity"] * buys["price"]).sum()
    total_sells = (sells["quantity"] * sells["price"]).sum()

    current_value = (
        holdings_df["market_value"].sum(skipna=True)
        if not holdings_df.empty
        else 0.0
    )

    total_return = total_sells + current_value - total_investment
    total_return_pct = (
        total_return / total_investment * 100 if total_investment else 0.0
    )

    xirr_value = _compute_xirr(df, current_value)

    return {
        "total_investment": total_investment,
        "total_sells": total_sells,
        "current_value": current_value,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
        "xirr": xirr_value,
    }


def _compute_xirr(df: pd.DataFrame, current_value: float) -> float | None:
    """Internal XIRR computation using scipy brentq."""
    cashflows: list[tuple[datetime.date, float]] = []

    for _, row in df.iterrows():
        amount = row["quantity"] * row["price"]
        txn = row["transaction_type"].lower()
        date = row["date"].date() if hasattr(row["date"], "date") else row["date"]

        if txn == "buy":
            cashflows.append((date, -amount))
        elif txn == "sell":
            cashflows.append((date, amount))

    if current_value > 0:
        cashflows.append((datetime.date.today(), current_value))

    if not cashflows:
        return None

    has_negative = any(cf[1] < 0 for cf in cashflows)
    has_positive = any(cf[1] > 0 for cf in cashflows)
    if not has_negative or not has_positive:
        return None

    dates = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    t0 = min(dates)
    day_fracs = [(d - t0).days / 365.25 for d in dates]

    # Guard against all-same-date edge case
    if max(day_fracs) < 1e-9:
        return None

    def npv(rate: float) -> float:
        if rate <= -1:
            return float("inf")
        return sum(cf / (1 + rate) ** t for cf, t in zip(amounts, day_fracs))

    try:
        return brentq(npv, -0.9999, 20.0, maxiter=1000, xtol=1e-7)
    except ValueError:
        pass

    # Try narrower bracket if first attempt fails
    try:
        from scipy.optimize import newton
        return newton(npv, 0.1, maxiter=500, tol=1e-7)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Monthly activity for chart
# ---------------------------------------------------------------------------

def build_monthly_activity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate buy/sell amounts by calendar month for charting.
    Returns dataframe with columns: month, buys, sells.
    """
    tmp = df.copy()
    tmp["month"] = tmp["date"].dt.to_period("M").dt.to_timestamp()
    tmp["amount"] = tmp["quantity"] * tmp["price"]

    buys = (
        tmp[tmp["transaction_type"].str.lower() == "buy"]
        .groupby("month")["amount"]
        .sum()
        .rename("buys")
    )
    sells = (
        tmp[tmp["transaction_type"].str.lower() == "sell"]
        .groupby("month")["amount"]
        .sum()
        .rename("sells")
    )

    monthly = pd.concat([buys, sells], axis=1).fillna(0).reset_index()
    monthly.columns = ["month", "buys", "sells"]
    return monthly


# ---------------------------------------------------------------------------
# Portfolio context string for LLM
# ---------------------------------------------------------------------------

def build_portfolio_context(
    transactions_df: pd.DataFrame,
    holdings_df: pd.DataFrame,
    metrics: dict,
) -> str:
    """Produce a compact text summary of the portfolio for LLM context."""
    parts: list[str] = []

    if holdings_df is not None and not holdings_df.empty:
        parts.append("=== CURRENT HOLDINGS ===")
        for _, row in holdings_df.iterrows():
            pnl_str = (
                f"${row['unrealized_pnl']:+,.2f} ({row['unrealized_pnl_pct']:+.1f}%)"
                if row["unrealized_pnl"] is not None
                else "N/A"
            )
            alloc = (
                f"{row['allocation_pct']:.1f}%"
                if row["allocation_pct"] is not None
                else "N/A"
            )
            current_price_str = f"${row['current_price']:.2f}" if row['current_price'] else 'N/A'
            market_value_str = f"${row['market_value']:,.2f}" if row['market_value'] else 'N/A'
            parts.append(
                f"  {row['ticker']}: {row['quantity']:.4f} shares | "
                f"avg cost ${row['avg_cost']:.2f} | "
                f"current {current_price_str} | "
                f"value {market_value_str} | "
                f"unrealized P&L {pnl_str} | allocation {alloc}"
            )

    if metrics:
        parts.append("\n=== PERFORMANCE METRICS ===")
        parts.append(f"  Total Investment:    ${metrics.get('total_investment', 0):,.2f}")
        parts.append(f"  Total Sell Proceeds: ${metrics.get('total_sells', 0):,.2f}")
        parts.append(f"  Current Value:       ${metrics.get('current_value', 0):,.2f}")
        parts.append(
            f"  Total Return:        ${metrics.get('total_return', 0):+,.2f} "
            f"({metrics.get('total_return_pct', 0):+.1f}%)"
        )
        xirr = metrics.get("xirr")
        parts.append(
            f"  XIRR:                {xirr * 100:.1f}%" if xirr is not None else "  XIRR:                N/A"
        )

    if transactions_df is not None and not transactions_df.empty:
        parts.append("\n=== RECENT TRANSACTIONS (last 10) ===")
        for _, row in transactions_df.tail(10).iterrows():
            parts.append(
                f"  {row['date'].strftime('%Y-%m-%d')} "
                f"{row['transaction_type']} "
                f"{row['quantity']:.4f} {row['ticker']} "
                f"@ ${row['price']:.2f}"
            )

    return "\n".join(parts)

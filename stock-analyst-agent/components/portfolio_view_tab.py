from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from utils.llm_agent import GroqAgent
from utils.portfolio_math import (
    build_holdings_dataframe,
    build_portfolio_context,
    calculate_fifo_holdings,
    calculate_performance_metrics,
    fetch_current_prices,
)


def _ensure_portfolio_data() -> bool:
    """
    Compute and cache holdings + metrics in session state if not already done.
    Returns True if data is ready, False if transactions are missing.
    """
    df = st.session_state.get("transactions_df")
    if df is None:
        return False

    if st.session_state.get("holdings_data") is not None:
        return True

    with st.spinner("Computing FIFO holdings and fetching prices…"):
        holdings, errors = calculate_fifo_holdings(df)
        st.session_state.fifo_errors = errors

        tickers = tuple(holdings.keys())
        prices = fetch_current_prices(tickers) if tickers else {}
        st.session_state.current_prices = prices

        holdings_df = build_holdings_dataframe(holdings, prices)
        metrics = calculate_performance_metrics(df, holdings_df)

        st.session_state.holdings_data = holdings_df
        st.session_state.portfolio_metrics = metrics

    return True


def render_portfolio_view_tab() -> None:
    st.header("Consolidated Portfolio View")

    if not _ensure_portfolio_data():
        st.info("Upload a CSV in the **Data Upload** tab to see your portfolio.")
        return

    # Surface FIFO errors
    for err in st.session_state.get("fifo_errors", []):
        st.error(err)

    holdings_df = st.session_state.holdings_data
    metrics = st.session_state.portfolio_metrics

    if holdings_df.empty:
        st.warning("No open positions found. All positions may have been fully sold.")
        return

    # --- Total portfolio value ---
    total_value = metrics.get("current_value", 0.0)
    st.metric("Total Current Portfolio Value", f"${total_value:,.2f}")

    # --- Allocation pie chart ---
    chart_df = holdings_df.dropna(subset=["market_value", "allocation_pct"])
    if not chart_df.empty:
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=chart_df["ticker"],
                    values=chart_df["market_value"],
                    hole=0.42,
                    textinfo="label+percent",
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        "Value: $%{value:,.2f}<br>"
                        "Share: %{percent}<extra></extra>"
                    ),
                )
            ]
        )
        fig.update_layout(
            title="Portfolio Allocation by Current Market Value",
            legend=dict(orientation="v", x=1.02, y=0.5),
            margin=dict(l=20, r=20, t=50, b=20),
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Holdings table ---
    st.subheader("Current Holdings")

    display = holdings_df.copy()
    display["quantity"] = display["quantity"].map("{:,.4f}".format)
    display["avg_cost"] = display["avg_cost"].map("${:,.2f}".format)
    display["current_price"] = display["current_price"].apply(
        lambda v: f"${v:,.2f}" if v is not None else "N/A"
    )
    display["market_value"] = display["market_value"].apply(
        lambda v: f"${v:,.2f}" if v is not None else "N/A"
    )
    display["unrealized_pnl"] = display["unrealized_pnl"].apply(
        lambda v: f"${v:+,.2f}" if v is not None else "N/A"
    )
    display["unrealized_pnl_pct"] = display["unrealized_pnl_pct"].apply(
        lambda v: f"{v:+.2f}%" if v is not None else "N/A"
    )
    display["allocation_pct"] = display["allocation_pct"].apply(
        lambda v: f"{v:.1f}%" if v is not None else "N/A"
    )

    display = display.rename(
        columns={
            "ticker": "Ticker",
            "quantity": "Quantity",
            "avg_cost": "Avg Cost (FIFO)",
            "current_price": "Current Price",
            "market_value": "Market Value",
            "unrealized_pnl": "Unrealized P&L ($)",
            "unrealized_pnl_pct": "Unrealized P&L (%)",
            "allocation_pct": "Allocation",
        }
    )[
        [
            "Ticker",
            "Quantity",
            "Avg Cost (FIFO)",
            "Current Price",
            "Market Value",
            "Unrealized P&L ($)",
            "Unrealized P&L (%)",
            "Allocation",
        ]
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)

    # --- AI portfolio summary ---
    st.subheader("AI Portfolio Health Summary")
    agent = GroqAgent()

    if not agent.is_available:
        st.warning(
            "Groq API key not found. Set `GROQ_API_KEY` in your `.env` file "
            "to enable AI-powered analysis."
        )
        return

    with st.spinner("Generating AI summary…"):
        context = build_portfolio_context(
            st.session_state.transactions_df,
            holdings_df,
            metrics,
        )
        summary = agent.generate_portfolio_summary(context)

    if summary:
        st.info(summary)
    else:
        st.warning("AI summary could not be generated. Check your Groq API key.")

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from utils.portfolio_math import (
    build_holdings_dataframe,
    build_monthly_activity,
    calculate_fifo_holdings,
    calculate_performance_metrics,
    fetch_current_prices,
)


def _ensure_portfolio_data() -> bool:
    df = st.session_state.get("transactions_df")
    if df is None:
        return False
    if st.session_state.get("holdings_data") is not None:
        return True

    with st.spinner("Computing portfolio metrics…"):
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


def render_historical_performance_tab() -> None:
    st.header("Historical Performance")

    if not _ensure_portfolio_data():
        st.info("Upload a CSV in the **Data Upload** tab to see performance metrics.")
        return

    df = st.session_state.transactions_df
    metrics = st.session_state.portfolio_metrics

    # --- Metric cards ---
    col1, col2, col3 = st.columns(3)
    col4, col5, _ = st.columns(3)

    total_inv = metrics.get("total_investment", 0.0)
    total_sells = metrics.get("total_sells", 0.0)
    current_val = metrics.get("current_value", 0.0)
    total_ret = metrics.get("total_return", 0.0)
    total_ret_pct = metrics.get("total_return_pct", 0.0)
    xirr = metrics.get("xirr")

    col1.metric("Total Investment", f"${total_inv:,.2f}")
    col2.metric("Total Sell Proceeds", f"${total_sells:,.2f}")
    col3.metric("Current Portfolio Value", f"${current_val:,.2f}")

    ret_delta = f"{total_ret_pct:+.2f}%"
    col4.metric(
        "Total Return",
        f"${total_ret:+,.2f}",
        delta=ret_delta,
        delta_color="normal",
    )

    xirr_display = f"{xirr * 100:.2f}%" if xirr is not None else "N/A"
    xirr_help = (
        "Annualized internal rate of return over the full transaction timeline."
    )
    col5.metric("XIRR (Annualised Return)", xirr_display, help=xirr_help)

    st.divider()

    # --- Monthly activity chart ---
    st.subheader("Monthly Buy / Sell Activity")
    monthly = build_monthly_activity(df)

    if not monthly.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=monthly["month"],
                y=monthly["buys"],
                name="Buys",
                marker_color="#2ecc71",
            )
        )
        fig.add_trace(
            go.Bar(
                x=monthly["month"],
                y=monthly["sells"],
                name="Sells",
                marker_color="#e74c3c",
            )
        )

        # Cumulative net investment line
        monthly = monthly.sort_values("month")
        monthly["cumulative_net"] = (monthly["buys"] - monthly["sells"]).cumsum()
        fig.add_trace(
            go.Scatter(
                x=monthly["month"],
                y=monthly["cumulative_net"],
                name="Cumulative Net Investment",
                mode="lines+markers",
                line=dict(color="#3498db", width=2),
                yaxis="y2",
            )
        )

        fig.update_layout(
            barmode="group",
            xaxis_title="Month",
            yaxis_title="Amount (USD)",
            yaxis2=dict(
                title="Cumulative Net (USD)",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            legend=dict(orientation="h", y=1.12),
            height=420,
            margin=dict(l=20, r=20, t=40, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Transaction history table ---
    st.subheader("Full Transaction History")
    display = df.copy()
    display["date"] = display["date"].dt.strftime("%Y-%m-%d")
    display["amount"] = display["quantity"] * display["price"]
    display["price"] = display["price"].map("${:,.2f}".format)
    display["amount"] = display["amount"].map("${:,.2f}".format)
    display["quantity"] = display["quantity"].map("{:,.4f}".format)

    display = display.rename(
        columns={
            "ticker": "Ticker",
            "date": "Date",
            "transaction_type": "Type",
            "quantity": "Quantity",
            "price": "Price",
            "amount": "Total Amount",
        }
    )[["Date", "Ticker", "Type", "Quantity", "Price", "Total Amount"]]

    st.dataframe(display, use_container_width=True, hide_index=True)

from __future__ import annotations

import streamlit as st

from utils.data_processing import get_upload_stats, validate_and_clean_csv


def render_data_upload_tab() -> None:
    st.header("Upload Transaction History")
    st.markdown(
        "Upload a CSV file containing your US stock transactions. "
        "The file must have the following columns: "
        "`ticker`, `date`, `transaction_type`, `quantity`, `price`."
    )

    with st.expander("Expected CSV format", expanded=False):
        st.code(
            "ticker,date,transaction_type,quantity,price\n"
            "AAPL,2023-01-10,Buy,10,145.00\n"
            "MSFT,2023-02-15,Buy,5,250.00\n"
            "AAPL,2023-06-20,Sell,3,180.00\n"
            "NVDA,2023-09-01,Buy,4,470.00",
            language="text",
        )

    uploaded_file = st.file_uploader(
        "Choose a CSV file", type=["csv"], key="csv_uploader"
    )

    if uploaded_file is None:
        st.info("Please upload a CSV file to begin.")
        return

    df, errors = validate_and_clean_csv(uploaded_file)

    # Show non-fatal warnings
    for msg in errors:
        if df is not None:
            st.warning(msg)
        else:
            st.error(msg)

    if df is None:
        st.error("Upload failed. Please fix the issues above and re-upload.")
        # Clear any stale session data
        st.session_state.transactions_df = None
        st.session_state.holdings_data = None
        st.session_state.portfolio_metrics = None
        return

    # Persist and invalidate downstream caches on new upload
    if (
        st.session_state.get("transactions_df") is None
        or not df.equals(st.session_state.transactions_df)
    ):
        st.session_state.transactions_df = df
        st.session_state.holdings_data = None
        st.session_state.portfolio_metrics = None
        st.session_state.fifo_errors = []
        st.session_state.current_prices = {}

    st.success("File uploaded and validated successfully.")

    # Upload stats
    stats = get_upload_stats(df)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Transactions", stats["total_transactions"])
    col2.metric("Unique Tickers", stats["unique_tickers"])
    col3.metric("Buy Transactions", stats["buy_count"])
    col4.metric("Sell Transactions", stats["sell_count"])
    col5.metric(
        "Date Range",
        f"{stats['date_range'][0]} → {stats['date_range'][1]}",
    )

    st.subheader("Transaction Data")
    display_df = df.copy()
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
    display_df["price"] = display_df["price"].map("${:,.2f}".format)
    display_df["quantity"] = display_df["quantity"].map("{:,.4f}".format)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

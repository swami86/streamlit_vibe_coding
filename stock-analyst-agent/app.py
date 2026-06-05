from dotenv import load_dotenv

load_dotenv()  # Must run before any other import that reads env vars

import streamlit as st  # noqa: E402

from components.ai_chat_tab import render_ai_chat_tab  # noqa: E402
from components.data_upload_tab import render_data_upload_tab  # noqa: E402
from components.historical_performance_tab import render_historical_performance_tab  # noqa: E402
from components.portfolio_view_tab import render_portfolio_view_tab  # noqa: E402

st.set_page_config(
    page_title="Stock Portfolio Analyst Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Initialise session state keys used across tabs
_defaults = {
    "transactions_df": None,
    "holdings_data": None,
    "portfolio_metrics": None,
    "fifo_errors": [],
    "current_prices": {},
    "chat_history": [],
}
for key, value in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# App header
st.title("📈 US Stock Portfolio Analyst Agent")
st.caption(
    "Upload your transaction history to analyse holdings, performance, "
    "and get AI-powered insights. For informational use only — not financial advice."
)

tab_upload, tab_portfolio, tab_history, tab_chat = st.tabs(
    [
        "Data Upload",
        "Consolidated Portfolio View",
        "Historical Performance",
        "AI Analyst Chat",
    ]
)

with tab_upload:
    render_data_upload_tab()

with tab_portfolio:
    render_portfolio_view_tab()

with tab_history:
    render_historical_performance_tab()

with tab_chat:
    render_ai_chat_tab()

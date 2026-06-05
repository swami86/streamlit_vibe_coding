from __future__ import annotations

import streamlit as st

from utils.llm_agent import GroqAgent
from utils.portfolio_math import (
    build_holdings_dataframe,
    build_portfolio_context,
    calculate_fifo_holdings,
    calculate_performance_metrics,
    fetch_current_prices,
    fetch_daily_changes,
)


_DAILY_KEYWORDS = frozenset(
    ["today", "today's", "down today", "up today", "daily", "day's move", "this session"]
)


def _needs_daily_prices(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _DAILY_KEYWORDS)


def _ensure_portfolio_data() -> bool:
    df = st.session_state.get("transactions_df")
    if df is None:
        return False
    if st.session_state.get("holdings_data") is not None:
        return True

    with st.spinner("Computing portfolio data…"):
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


def _format_daily_changes(changes: dict) -> str:
    lines = []
    for ticker, data in changes.items():
        if data is None:
            lines.append(f"  {ticker}: price data unavailable")
            continue
        direction = "+" if data["change"] >= 0 else ""
        lines.append(
            f"  {ticker}: ${data['current']:.2f} "
            f"({direction}{data['change']:.2f} / {direction}{data['change_pct']:.2f}% "
            f"vs prev close ${data['prev_close']:.2f})"
        )
    return "\n".join(lines)


def render_ai_chat_tab() -> None:
    st.header("AI Analyst Chat")

    if not _ensure_portfolio_data():
        st.info("Upload a CSV in the **Data Upload** tab to enable the AI analyst.")
        return

    agent = GroqAgent()
    if not agent.is_available:
        st.warning(
            "Groq API key not set. Add `GROQ_API_KEY=<your-key>` to your `.env` file "
            "and restart the app to enable the AI analyst."
        )
        return

    st.markdown(
        "Ask anything about your portfolio. The AI analyst is grounded strictly in "
        "your uploaded transaction history and live market data — it will not invent "
        "market news or give financial advice."
    )

    # --- Chat history display ---
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- Chat input ---
    user_input = st.chat_input("Ask your portfolio analyst…")
    if not user_input:
        # Show starter prompts on first load
        if not st.session_state.chat_history:
            st.markdown("**Try asking:**")
            examples = [
                "Summarise my historical trading performance.",
                "Which stocks are driving most of my gains?",
                "Am I over-concentrated in any stock?",
                "Why is my portfolio down today?",
                "What are my worst-performing holdings?",
            ]
            for ex in examples:
                st.markdown(f"- *{ex}*")
        return

    # Append user message to history
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build portfolio context
    context = build_portfolio_context(
        st.session_state.transactions_df,
        st.session_state.holdings_data,
        st.session_state.portfolio_metrics,
    )

    # Optionally enrich with today's price movements
    daily_ctx: str | None = None
    holdings_df = st.session_state.holdings_data
    if _needs_daily_prices(user_input) and not holdings_df.empty:
        tickers = tuple(holdings_df["ticker"].tolist())
        with st.spinner("Fetching today's price movements…"):
            changes = fetch_daily_changes(tickers)
        daily_ctx = _format_daily_changes(changes)

    # Generate AI response
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            response = agent.generate_chat_response(
                user_message=user_input,
                portfolio_context=context,
                chat_history=st.session_state.chat_history[:-1],
                daily_changes_context=daily_ctx,
            )

        if response:
            st.markdown(response)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": response}
            )
        else:
            fallback = "I could not generate a response. Please check your Groq API key and try again."
            st.warning(fallback)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": fallback}
            )

    # Clear chat button
    if st.session_state.chat_history:
        if st.button("Clear Chat History", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

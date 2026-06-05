from __future__ import annotations

import os


class GroqAgent:
    """Thin wrapper around the Groq chat completions API."""

    def __init__(self) -> None:
        self.api_key: str | None = os.environ.get("GROQ_API_KEY")
        self.model: str = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        self.client = None

        if self.api_key:
            try:
                from groq import Groq
                self.client = Groq(api_key=self.api_key)
            except Exception:
                self.client = None

    @property
    def is_available(self) -> bool:
        return self.client is not None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str | None:
        if not self.client:
            return None
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            return content.strip() if content else None
        except Exception as exc:
            return f"[Groq API error: {exc}]"

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def generate_portfolio_summary(self, portfolio_context: str) -> str | None:
        """Return a 2-3 sentence health summary grounded in portfolio_context."""
        if not self.client:
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a concise portfolio analysis assistant. "
                    "Provide factual analysis based ONLY on the data provided. "
                    "This is for informational purposes only and is NOT financial advice."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Based on the portfolio data below, write 2-3 sentences summarising "
                    "portfolio health. Mention concentration risk if any single stock "
                    "exceeds 40% of allocation. Comment on overall unrealized gain/loss. "
                    "Do NOT make buy/sell recommendations.\n\n"
                    f"{portfolio_context}"
                ),
            },
        ]
        return self._call(messages, max_tokens=512)

    def generate_chat_response(
        self,
        user_message: str,
        portfolio_context: str,
        chat_history: list[dict],
        daily_changes_context: str | None = None,
    ) -> str | None:
        """Return an analyst response grounded in portfolio and market data."""
        if not self.client:
            return None

        extra_market = (
            f"\n\n=== TODAY'S PRICE MOVEMENTS ===\n{daily_changes_context}"
            if daily_changes_context
            else ""
        )

        system_prompt = (
            "You are an AI-powered personal US stock portfolio analyst assistant. "
            "Rules you must follow:\n"
            "1. Base ALL analysis strictly on the provided portfolio data and market data.\n"
            "2. Do NOT hallucinate market news, company events, or external factors.\n"
            "3. If you lack sufficient data, say so clearly.\n"
            "4. For questions about today's movement, use the 'TODAY'S PRICE MOVEMENTS' "
            "section if present; otherwise state that intraday data is unavailable.\n"
            "5. End every response with a one-line disclaimer: "
            "'Disclaimer: This is informational only and not financial advice.'\n\n"
            f"Portfolio Context:\n{portfolio_context}{extra_market}"
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]

        # Include last 10 turns for context window efficiency
        for msg in chat_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_message})

        return self._call(messages, max_tokens=1024)

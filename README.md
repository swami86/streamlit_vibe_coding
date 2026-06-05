Stock Portfolio Analyst Agent
An AI-powered Streamlit application for analysing your US stock portfolio from transaction history.

Upload a CSV of your trades and get:

FIFO-based cost basis and current holdings
Unrealized P&L per position with portfolio allocation charts
Lifetime performance metrics including XIRR
An interactive AI analyst chat powered by Groq
Disclaimer: This application is for educational and informational purposes only. It does not constitute financial advice.

Features
Tab	What it does
Data Upload	Upload & validate your transaction CSV; preview cleaned data
Consolidated Portfolio View	FIFO holdings, current prices (yfinance), allocation pie chart, Groq AI summary
Historical Performance	Total investment, sell proceeds, total return, XIRR, monthly activity chart
AI Analyst Chat	Conversational analyst grounded in your portfolio data via Groq LLM
Folder Structure
stock-analyst-agent/
│
├── app.py                          # Streamlit entry point
├── pyproject.toml                  # uv project manifest
├── README.md
├── .env.example                    # Copy to .env and fill in keys
├── .gitignore
│
├── utils/
│   ├── __init__.py
│   ├── data_processing.py          # CSV validation & cleaning
│   ├── portfolio_math.py           # FIFO, XIRR, yfinance, metrics
│   └── llm_agent.py                # Groq client wrapper
│
└── components/
    ├── __init__.py
    ├── data_upload_tab.py
    ├── portfolio_view_tab.py
    ├── historical_performance_tab.py
    └── ai_chat_tab.py
CSV Format
The uploaded file must contain exactly these columns (order does not matter):

Column	Type	Example
ticker	string	AAPL
date	date string	2023-01-10
transaction_type	Buy or Sell (case-insensitive)	Buy
quantity	positive number	10
price	positive number	145.00
Sample CSV
ticker,date,transaction_type,quantity,price
AAPL,2023-01-10,Buy,10,145.00
MSFT,2023-02-15,Buy,5,250.00
AAPL,2023-06-20,Sell,3,180.00
NVDA,2023-09-01,Buy,4,470.00
Setup (uv only)
1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
2. Clone / enter the project directory
cd stock-analyst-agent
3. Create virtual environment and install dependencies
uv sync
This reads pyproject.toml, creates .venv/, and installs all dependencies including uv.lock pinning.

4. Set environment variables
cp .env.example .env
# Edit .env and add your Groq API key
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.1-8b-instant
Get a free API key at https://console.groq.com.

5. Run the app
uv run streamlit run app.py
The app will open at http://localhost:8501.

Adding / upgrading a dependency
uv add <package>          # add new dependency
uv add <package>==x.y.z  # pin version
uv sync                   # update lockfile and venv
FIFO Cost Basis
Positions are tracked using First In, First Out (FIFO):

Each Buy transaction creates a lot: (quantity, price).
Each Sell reduces lots starting from the oldest buy lot.
If a sell quantity exceeds available shares the app shows an error and skips that sell.
Positions fully liquidated are excluded from current holdings.
Average cost basis = remaining cost / remaining quantity.
XIRR Calculation
XIRR (Extended Internal Rate of Return) finds the annualised discount rate r such that the net present value of all cashflows equals zero:

NPV = Σ ( CF_i / (1 + r)^( (d_i - d_0) / 365.25 ) ) = 0
Buy transactions → negative cashflows (money out).
Sell transactions → positive cashflows (money in).
Current portfolio value on today's date → final positive cashflow.
scipy.optimize.brentq is used to solve for r. If a solution cannot be found (e.g. zero time elapsed, no buys, no value) the app displays N/A.

Notes
yfinance prices are cached for 5 minutes to avoid repeated API calls on re-renders.
The AI analyst is explicitly instructed not to hallucinate market news. For "why is my portfolio down today?" it fetches the previous-close vs current-price delta directly from yfinance.
All AI responses include a disclaimer that they are informational only.
The Groq model is configurable via the GROQ_MODEL env var (default: llama-3.1-8b-instant).

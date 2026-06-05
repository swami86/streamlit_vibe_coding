import pandas as pd

REQUIRED_COLUMNS = {"ticker", "date", "transaction_type", "quantity", "price"}
VALID_TRANSACTION_TYPES = {"buy", "sell"}


def validate_and_clean_csv(file) -> tuple[pd.DataFrame | None, list[str]]:
    """
    Validate and clean an uploaded CSV file.
    Returns (cleaned_df, errors). errors is empty on full success.
    """
    errors: list[str] = []

    try:
        df = pd.read_csv(file)
    except Exception as exc:
        return None, [f"Failed to parse CSV: {exc}"]

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return None, [
            f"Missing required columns: {', '.join(sorted(missing))}. "
            "Expected: ticker, date, transaction_type, quantity, price"
        ]

    if df.empty:
        return None, ["The CSV file is empty."]

    # Drop exact duplicate rows
    before = len(df)
    df = df.drop_duplicates()
    if len(df) < before:
        errors.append(f"Removed {before - len(df)} duplicate row(s).")

    # Normalize ticker
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()

    # Normalize and validate transaction_type
    df["transaction_type"] = df["transaction_type"].astype(str).str.strip().str.capitalize()
    invalid_types = df[~df["transaction_type"].str.lower().isin(VALID_TRANSACTION_TYPES)]
    if not invalid_types.empty:
        errors.append(
            f"Removed {len(invalid_types)} row(s) with invalid transaction_type "
            f"(must be 'Buy' or 'Sell'): {invalid_types['transaction_type'].unique().tolist()}"
        )
        df = df[df["transaction_type"].str.lower().isin(VALID_TRANSACTION_TYPES)].copy()

    # Validate quantity
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    bad_qty = df[df["quantity"].isna() | (df["quantity"] <= 0)]
    if not bad_qty.empty:
        errors.append(
            f"Removed {len(bad_qty)} row(s) with invalid quantity (must be a positive number)."
        )
        df = df[df["quantity"].notna() & (df["quantity"] > 0)].copy()

    # Validate price
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    bad_price = df[df["price"].isna() | (df["price"] <= 0)]
    if not bad_price.empty:
        errors.append(
            f"Removed {len(bad_price)} row(s) with invalid price (must be a positive number)."
        )
        df = df[df["price"].notna() & (df["price"] > 0)].copy()

    # Validate dates
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad_dates = df[df["date"].isna()]
    if not bad_dates.empty:
        errors.append(
            f"Removed {len(bad_dates)} row(s) with unparseable date values."
        )
        df = df[df["date"].notna()].copy()

    if df.empty:
        return None, errors + ["No valid rows remain after cleaning."]

    df = df.sort_values("date").reset_index(drop=True)
    return df, errors


def get_upload_stats(df: pd.DataFrame) -> dict:
    """Return summary statistics for a cleaned transaction dataframe."""
    return {
        "total_transactions": len(df),
        "unique_tickers": df["ticker"].nunique(),
        "date_range": (df["date"].min().date(), df["date"].max().date()),
        "buy_count": (df["transaction_type"].str.lower() == "buy").sum(),
        "sell_count": (df["transaction_type"].str.lower() == "sell").sum(),
    }

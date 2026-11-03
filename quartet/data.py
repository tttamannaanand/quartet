"""Free market data, cached on disk so every result can be re-run offline.

Prices and option chains come from Yahoo Finance (via yfinance). Factor returns come
from Kenneth French's data library. Nothing here is committed to git: run
`python -m quartet fetch` to download it.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data"
FRENCH_DAILY = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"


def _path(name: str) -> Path:
    CACHE.mkdir(exist_ok=True)
    return CACHE / name


def prices(ticker: str, start: str = "1999-01-01", refresh: bool = False) -> pd.Series:
    """Daily close adjusted for splits and dividends."""
    p = _path(f"px-{ticker}.csv")
    if p.exists() and not refresh:
        s = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        import yfinance as yf

        df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        s = df["Close"].squeeze("columns").dropna()
        s.name = ticker
        s.to_csv(p)
    s.index = pd.to_datetime(s.index)
    s.name = ticker
    return s


def parse_french(text: str) -> pd.DataFrame:
    """Parse the daily factor CSV: a few lines of notes, a header, YYYYMMDD rows, a footer."""
    rows, cols = [], None
    for line in text.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if cols is None:
            if len(parts) > 1 and parts[0] == "" and "Mkt-RF" in parts:
                cols = parts[1:]
            continue
        if len(parts[0]) == 8 and parts[0].isdigit():
            rows.append([parts[0], *map(float, parts[1:])])
    df = pd.DataFrame(rows, columns=["date", *cols])
    df.index = pd.to_datetime(df.pop("date"), format="%Y%m%d")
    return df / 100.0  # the file is in percent


def french_factors(refresh: bool = False) -> pd.DataFrame:
    """Daily Mkt-RF, SMB, HML and RF as decimals."""
    p = _path("ff3-daily.csv")
    if p.exists() and not refresh:
        return pd.read_csv(p, index_col=0, parse_dates=True)
    with urlopen(FRENCH_DAILY, timeout=60) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    text = z.read(z.namelist()[0]).decode("latin-1")
    df = parse_french(text)
    df.to_csv(p)
    return df


def option_chain(ticker: str = "SPY", refresh: bool = False) -> dict:
    """A snapshot of the option chain: spot, a short rate, and every quote for each expiry."""
    p = _path(f"chain-{ticker}.json")
    if p.exists() and not refresh:
        return json.loads(p.read_text())
    import yfinance as yf

    t = yf.Ticker(ticker)
    spot = float(t.history(period="5d")["Close"].iloc[-1])
    irx = yf.Ticker("^IRX").history(period="5d")["Close"]
    rate = float(irx.iloc[-1]) / 100.0 if len(irx) else 0.04
    today = date.today()
    expiries = []
    for e in t.options:
        days = (date.fromisoformat(e) - today).days
        if not 14 <= days <= 400:
            continue
        ch = t.option_chain(e)
        keep = ["strike", "bid", "ask", "volume", "openInterest"]
        calls = ch.calls[keep].fillna(0).to_dict("list")
        puts = ch.puts[keep].fillna(0).to_dict("list")
        expiries.append({"expiry": e, "days": days, "calls": calls, "puts": puts})
    snap = {"ticker": ticker, "asof": today.isoformat(), "spot": spot, "rate": rate, "expiries": expiries}
    p.write_text(json.dumps(snap))
    return snap


def log_returns(s: pd.Series) -> pd.Series:
    return np.log(s).diff().dropna()

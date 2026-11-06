"""Chapter 1: Fama-French three-factor regression.

    r_fund - rf = alpha + b_mkt (Mkt - rf) + b_smb SMB + b_hml HML + e

If a fund's average return is explained by owning the market, small companies and cheap
"value" companies, alpha shrinks toward zero. Whatever is left is the part the factors
cannot explain. Standard errors use Newey-West so daily autocorrelation doesn't
inflate the t-statistics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class Fit:
    names: list[str]
    coef: np.ndarray
    se: np.ndarray
    r2: float
    n: int

    @property
    def t(self) -> np.ndarray:
        return self.coef / self.se

    def get(self, name: str) -> tuple[float, float]:
        i = self.names.index(name)
        return float(self.coef[i]), float(self.t[i])


def ols_newey_west(y: np.ndarray, X: np.ndarray, names: list[str], lags: int = 5) -> Fit:
    """Least squares with Newey-West (Bartlett kernel) standard errors."""
    n = len(y)
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    u = X * e[:, None]
    S = u.T @ u
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        G = u[lag:].T @ u[:-lag]
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    r2 = 1 - e.var() / y.var()
    return Fit(names, beta, np.sqrt(np.diag(cov)), float(r2), n)


def align(fund: pd.Series, factors: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns of the fund, joined to the factors on shared dates."""
    r = fund.pct_change().dropna().rename("fund")
    df = factors.join(r, how="inner").dropna()
    df["excess"] = df["fund"] - df["RF"]
    return df


def regress(df: pd.DataFrame, factors: list[str]) -> Fit:
    X = np.column_stack([np.ones(len(df)), df[factors].to_numpy()])
    return ols_newey_west(df["excess"].to_numpy(), X, ["alpha", *factors])


MODELS = {
    "CAPM": ["Mkt-RF"],
    "FF3": ["Mkt-RF", "SMB", "HML"],
    "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "FF5 + momentum": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"],
}


def ladder(fund: pd.Series, factors6: pd.DataFrame) -> list[dict]:
    """Alpha as factors are added one model at a time, all on the same dates."""
    df = align(fund, factors6)
    out = []
    for name, cols in MODELS.items():
        fit = regress(df, cols)
        a, t = fit.get("alpha")
        out.append({"model": name, "alpha": a * TRADING_DAYS, "t": t, "r2": fit.r2, "loadings": {c: fit.get(c)[0] for c in cols}})
    return out


def analyse(ticker: str, fund: pd.Series, factors: pd.DataFrame, factors6: pd.DataFrame | None = None) -> dict:
    df = align(fund, factors)
    capm = regress(df, ["Mkt-RF"])
    ff3 = regress(df, ["Mkt-RF", "SMB", "HML"])
    a1, t1 = capm.get("alpha")
    a3, t3 = ff3.get("alpha")
    return {
        "ticker": ticker,
        "start": df.index[0].date().isoformat(),
        "end": df.index[-1].date().isoformat(),
        "days": len(df),
        "capm": {"alpha": a1 * TRADING_DAYS, "t": t1, "beta": capm.get("Mkt-RF")[0], "r2": capm.r2},
        "ff3": {
            "alpha": a3 * TRADING_DAYS,
            "t": t3,
            "mkt": ff3.get("Mkt-RF")[0],
            "smb": ff3.get("SMB")[0],
            "hml": ff3.get("HML")[0],
            "smb_t": ff3.get("SMB")[1],
            "hml_t": ff3.get("HML")[1],
            "r2": ff3.r2,
        },
        # Share of the CAPM alpha that the two extra factors explain away.
        "explained": None if abs(a1) < 1e-12 else 1 - a3 / a1,
        "ladder": ladder(fund, factors6) if factors6 is not None else [],
    }


FUNDS = {
    "SPY": "S&P 500 index fund (sanity check: beta near 1, alpha near 0)",
    "BRK-B": "Berkshire Hathaway, Warren Buffett's company",
    "IWN": "Russell 2000 small-cap value fund",
    "QQQ": "Nasdaq-100 fund (big tech growth)",
    "ARKK": "ARK Innovation, a famous active growth fund",
    "VTV": "Vanguard large-cap value fund",
}

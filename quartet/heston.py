"""Chapter 4: the Heston stochastic volatility model, calibrated to a real option chain.

    dS = (r - q) S dt + sqrt(v) S dW1
    dv = kappa (theta - v) dt + xi sqrt(v) dW2,   corr(dW1, dW2) = rho

Five parameters: v0 (variance today), theta (long-run variance), kappa (how fast variance
returns to theta), xi (volatility of variance) and rho (how price and volatility move
together). Prices come from the characteristic function through Lewis's formula.
The hard part is that many parameter sets fit a chain almost equally well.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import erf, exp, log, sqrt

import numpy as np
from scipy.optimize import brentq, least_squares

NAMES = ("v0", "kappa", "theta", "xi", "rho")
LOWER = np.array([1e-4, 0.05, 1e-4, 0.05, -0.99])
UPPER = np.array([1.0, 15.0, 1.0, 3.0, 0.3])

# Fixed Gauss-Legendre nodes on [0, U] for the pricing integral.
_X, _W = np.polynomial.legendre.leggauss(256)
_U = 250.0
NODES = 0.5 * _U * (_X + 1)
WEIGHTS = 0.5 * _U * _W


@dataclass(frozen=True)
class Params:
    v0: float
    kappa: float
    theta: float
    xi: float
    rho: float

    def array(self) -> np.ndarray:
        return np.array([self.v0, self.kappa, self.theta, self.xi, self.rho])

    @property
    def feller(self) -> bool:
        """2 kappa theta > xi^2 keeps variance away from zero."""
        return 2 * self.kappa * self.theta > self.xi**2


def cf(u: np.ndarray, T: float, p: Params) -> np.ndarray:
    """Characteristic function of ln(S_T / F_T), the 'little trap' form (Albrecher et al.)."""
    iu = 1j * u
    b = p.kappa - p.rho * p.xi * iu
    d = np.sqrt(b * b + p.xi**2 * (iu + u * u))
    g = (b - d) / (b + d)
    e = np.exp(-d * T)
    C = p.kappa * p.theta / p.xi**2 * ((b - d) * T - 2 * np.log((1 - g * e) / (1 - g)))
    D = (b - d) / p.xi**2 * (1 - e) / (1 - g * e)
    return np.exp(C + D * p.v0)


def call_prices(F: float, strikes: np.ndarray, T: float, df: float, p: Params) -> np.ndarray:
    """Lewis (2001): C = DF [F - sqrt(F K) / pi * int Re(e^{iuk} phi(u - i/2)) / (u^2 + 1/4) du], k = ln(F/K)."""
    k = np.log(F / strikes)
    phi = cf(NODES - 0.5j, T, p)
    integrand = np.real(np.exp(1j * np.outer(k, NODES)) * phi) / (NODES**2 + 0.25)
    integral = integrand @ WEIGHTS
    return df * (F - np.sqrt(F * strikes) / np.pi * integral)


def put_prices(F: float, strikes: np.ndarray, T: float, df: float, p: Params) -> np.ndarray:
    return call_prices(F, strikes, T, df, p) - df * (F - strikes)


# ---------- Black-76 helpers (prices on the forward) ----------


def _ncdf(x):
    return 0.5 * (1 + np.vectorize(erf)(np.asarray(x) / sqrt(2)))


def black(F: float, K, T: float, df: float, vol, call) -> np.ndarray:
    K, vol, call = np.asarray(K, float), np.asarray(vol, float), np.asarray(call, bool)
    sd = vol * sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    c = df * (F * _ncdf(d1) - K * _ncdf(d2))
    return np.where(call, c, c - df * (F - K))


def black_vega(F: float, K, T: float, df: float, vol) -> np.ndarray:
    K, vol = np.asarray(K, float), np.asarray(vol, float)
    sd = vol * sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd * sd) / sd
    return df * F * np.exp(-0.5 * d1 * d1) / sqrt(2 * np.pi) * sqrt(T)


def implied_vol(price: float, F: float, K: float, T: float, df: float, call: bool) -> float:
    intrinsic = df * max((F - K) if call else (K - F), 0.0)
    if price <= intrinsic + 1e-10:
        return float("nan")
    f = lambda v: float(black(F, K, T, df, v, call)) - price  # noqa: E731
    try:
        return brentq(f, 1e-4, 5.0, xtol=1e-8)
    except ValueError:
        return float("nan")


# ---------- turning a raw chain into clean quotes ----------


@dataclass
class Slice:
    expiry: str
    T: float
    F: float
    df: float
    strikes: np.ndarray
    is_call: np.ndarray
    mid: np.ndarray
    iv: np.ndarray
    vega: np.ndarray


def clean_chain(snap: dict, min_days: int = 20, max_days: int = 370, band: tuple[float, float] = (0.8, 1.15), max_slices: int = 6) -> list[Slice]:
    """Out-of-the-money quotes with a real bid, within a moneyness band, on a few expiries.

    The forward for each expiry comes from put-call parity near the money, so no
    dividend assumption is needed.
    """
    r = snap["rate"]
    picked = [e for e in snap["expiries"] if min_days <= e["days"] <= max_days]
    if len(picked) > max_slices:
        idx = np.unique(np.linspace(0, len(picked) - 1, max_slices).round().astype(int))
        picked = [picked[i] for i in idx]
    out = []
    for e in picked:
        T = e["days"] / 365.0
        df = exp(-r * T)
        c = {k: v for k, v in zip(e["calls"]["strike"], zip(e["calls"]["bid"], e["calls"]["ask"], strict=True), strict=True)}
        pu = {k: v for k, v in zip(e["puts"]["strike"], zip(e["puts"]["bid"], e["puts"]["ask"], strict=True), strict=True)}
        both = sorted(k for k in set(c) & set(pu) if c[k][0] > 0 and pu[k][0] > 0)
        if len(both) < 5:
            continue
        near = sorted(both, key=lambda k: abs(k - snap["spot"]))[:6]
        F = float(np.median([k + (sum(c[k]) / 2 - sum(pu[k]) / 2) / df for k in near]))
        Ks, calls, mids = [], [], []
        for k in sorted(set(c) | set(pu)):
            if not band[0] <= k / F <= band[1]:
                continue
            is_call = k >= F
            bid, ask = (c if is_call else pu).get(k, (0, 0))
            if bid <= 0.05 or ask <= bid or (ask - bid) / ((ask + bid) / 2) > 0.25:
                continue
            Ks.append(k)
            calls.append(is_call)
            mids.append((bid + ask) / 2)
        if len(Ks) < 8:
            continue
        Ks, calls, mids = np.array(Ks), np.array(calls), np.array(mids)
        iv = np.array([implied_vol(m, F, k, T, df, ic) for m, k, ic in zip(mids, Ks, calls, strict=True)])
        ok = np.isfinite(iv)
        out.append(Slice(e["expiry"], T, F, df, Ks[ok], calls[ok], mids[ok], iv[ok], black_vega(F, Ks[ok], T, df, iv[ok])))
    return out


def model_prices(s: Slice, p: Params) -> np.ndarray:
    c = call_prices(s.F, s.strikes, s.T, s.df, p)
    return np.where(s.is_call, c, c - s.df * (s.F - s.strikes))


def residuals(x: np.ndarray, slices: list[Slice]) -> np.ndarray:
    """Price errors divided by vega: roughly the error in implied-vol units."""
    p = Params(*x)
    return np.concatenate([(model_prices(s, p) - s.mid) / np.maximum(s.vega, 1e-3) for s in slices])


@dataclass
class Calibration:
    params: Params
    rmse_vol_pts: float
    start: Params


def calibrate(slices: list[Slice], starts: int = 24, seed: int = 0) -> list[Calibration]:
    """Fit from many random starting points. Returns every fit, best first."""
    rng = np.random.default_rng(seed)
    n = sum(len(s.strikes) for s in slices)
    fits = []
    for _ in range(starts):
        x0 = np.array(
            [
                rng.uniform(0.005, 0.08),
                rng.uniform(0.3, 8.0),
                rng.uniform(0.01, 0.1),
                rng.uniform(0.2, 1.5),
                rng.uniform(-0.95, -0.3),
            ]
        )
        res = least_squares(residuals, x0, args=(slices,), bounds=(LOWER, UPPER), x_scale="jac", max_nfev=400)
        rmse = float(np.sqrt(np.mean(res.fun**2)) * 100)
        if np.isfinite(rmse):
            fits.append(Calibration(Params(*res.x), rmse, Params(*x0)))
    _ = n
    return sorted(fits, key=lambda f: f.rmse_vol_pts)


def mc_call(S: float, K: float, T: float, r: float, p: Params, steps: int = 200, n: int = 200_000, seed: int = 0) -> tuple[float, float]:
    """Full-truncation Euler Monte Carlo, used only to check the pricing formula."""
    rng = np.random.default_rng(seed)
    dt = T / steps
    lnS = np.full(n, log(S))
    v = np.full(n, p.v0)
    for _ in range(steps):
        z1 = rng.standard_normal(n)
        z2 = p.rho * z1 + sqrt(1 - p.rho**2) * rng.standard_normal(n)
        vp = np.maximum(v, 0)
        lnS += (r - 0.5 * vp) * dt + np.sqrt(vp * dt) * z1
        v += p.kappa * (p.theta - vp) * dt + p.xi * np.sqrt(vp * dt) * z2
    pay = np.exp(-r * T) * np.maximum(np.exp(lnS) - K, 0)
    return float(pay.mean()), float(pay.std() / sqrt(n))


def as_dict(p: Params) -> dict:
    return {**asdict(p), "feller": p.feller, "long_run_vol": sqrt(p.theta), "vol_today": sqrt(p.v0), "half_life_days": log(2) / p.kappa * 365}


def profile(slices: list[Slice], param: str, values, start: Params) -> list[dict]:
    """Fix one parameter at each value and refit the other four. A flat curve means the data can't pin it down."""
    i = NAMES.index(param)
    free = [j for j in range(5) if j != i]
    x = start.array()
    out = []
    for val in values:
        def res(z, val=val):
            full = np.empty(5)
            full[free] = z
            full[i] = val
            return residuals(full, slices)

        fit = least_squares(res, x[free], bounds=(LOWER[free], UPPER[free]), x_scale="jac", max_nfev=400)
        full = np.empty(5)
        full[free] = fit.x
        full[i] = val
        x[free] = fit.x  # warm start the next value
        p = Params(*full)
        out.append(as_dict(p) | {"fixed": float(val), "rmse": float(np.sqrt(np.mean(fit.fun**2)) * 100)})
    return out

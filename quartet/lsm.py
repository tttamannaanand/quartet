"""Chapter 3: Longstaff-Schwartz least-squares Monte Carlo for American options.

An American put can be exercised any day before expiry. Simulate many price paths, then
walk backwards: at each date, regress the discounted future cash flow on the current
price (in-the-money paths only) to estimate the value of holding on. Exercise where the
payoff now beats that estimate. Check the answer against a binomial tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, sqrt

import numpy as np


def _ncdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def bs_put(S: float, K: float, r: float, sigma: float, T: float, q: float = 0.0) -> float:
    d1 = (log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return K * exp(-r * T) * _ncdf(-d2) - S * exp(-q * T) * _ncdf(-d1)


def binomial_american_put(S: float, K: float, r: float, sigma: float, T: float, q: float = 0.0, n: int = 2000) -> float:
    """Cox-Ross-Rubinstein tree, checked for early exercise at every node."""
    dt = T / n
    u = exp(sigma * sqrt(dt))
    d = 1 / u
    p = (exp((r - q) * dt) - d) / (u - d)
    disc = exp(-r * dt)
    j = np.arange(n + 1)
    prices = S * u ** (n - j) * d**j
    v = np.maximum(K - prices, 0.0)
    for step in range(n - 1, -1, -1):
        j = np.arange(step + 1)
        prices = S * u ** (step - j) * d**j
        v = np.maximum(disc * (p * v[:-1] + (1 - p) * v[1:]), K - prices)
    return float(v[0])


def gbm_paths(S: float, r: float, sigma: float, T: float, steps: int, n: int, q: float = 0.0, seed: int = 0) -> np.ndarray:
    """Geometric Brownian motion paths with antithetic variates. Shape (n, steps + 1)."""
    rng = np.random.default_rng(seed)
    half = n // 2
    z = rng.standard_normal((half, steps))
    z = np.vstack([z, -z])
    dt = T / steps
    inc = (r - q - 0.5 * sigma**2) * dt + sigma * sqrt(dt) * z
    logs = np.hstack([np.zeros((len(z), 1)), np.cumsum(inc, axis=1)])
    return S * np.exp(logs)


def _basis(x: np.ndarray, degree: int) -> np.ndarray:
    """Weighted Laguerre polynomials, as in the original paper. x is price / strike."""
    from numpy.polynomial import laguerre

    return np.exp(-x / 2)[:, None] * laguerre.lagvander(x, degree)


@dataclass
class LSMResult:
    price: float
    stderr: float
    european: float
    boundary_t: list[float]
    boundary_s: list[float]
    paths: np.ndarray | None = None  # a small sample of paths, for plotting
    stop: np.ndarray | None = None  # step at which each sampled path exercises (-1 = never)


def lsm_american_put(
    S: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    q: float = 0.0,
    steps: int = 50,
    n: int = 100_000,
    degree: int = 3,
    seed: int = 0,
) -> LSMResult:
    paths = gbm_paths(S, r, sigma, T, steps, n, q, seed)
    dt = T / steps
    disc = exp(-r * dt)
    cash = np.maximum(K - paths[:, -1], 0.0)
    european = float(exp(-r * T) * cash.mean())
    stop = np.where(cash > 0, steps, -1)
    bt, bs = [], []
    grid = np.linspace(0.3 * K, K, 400)
    for t in range(steps - 1, 0, -1):
        cash *= disc  # now valued at date t
        s = paths[:, t]
        itm = s < K
        if itm.sum() < degree + 2:
            continue
        coef, *_ = np.linalg.lstsq(_basis(s[itm] / K, degree), cash[itm], rcond=None)
        hold = _basis(s[itm] / K, degree) @ coef
        now = K - s[itm]
        ex = now > hold
        idx = np.flatnonzero(itm)[ex]
        cash[idx] = now[ex]
        stop[idx] = t
        # Exercise boundary: the highest price at which exercising beats the fitted hold value.
        fitted = _basis(grid / K, degree) @ coef
        lo, hi = s[itm].min(), s[itm].max()
        inside = (grid >= lo) & (grid <= hi)
        better = (K - grid > fitted) & inside
        if better.any():
            bt.append(t * dt)
            bs.append(float(grid[better].max()))
    pv = cash * disc
    keep = np.r_[0:40, n // 2 : n // 2 + 40]  # 40 paths and their antithetic twins
    return LSMResult(float(pv.mean()), float(pv.std() / sqrt(n)), european, bt[::-1], bs[::-1], paths[keep], stop[keep])


def binomial_surface(S: float, K: float, r: float, sigma: float, T: float, q: float = 0.0, n: int = 1000, s_grid=None, t_points: int = 41):
    """American put value V(S, t) on a regular grid, and the exact exercise boundary, from the tree.

    The tree is run once per time slice, starting from each grid price, so every value is
    a proper American price with the remaining time to expiry.
    """
    s_grid = np.linspace(0.5 * K, 1.5 * K, 41) if s_grid is None else np.asarray(s_grid)
    times = np.linspace(0, T, t_points)
    V = np.empty((len(times), len(s_grid)))
    boundary = []
    for i, t in enumerate(times):
        left = T - t
        if left <= 1e-9:
            V[i] = np.maximum(K - s_grid, 0)
            boundary.append(K)
            continue
        steps = max(50, int(n * left / T))
        V[i] = [binomial_american_put(s, K, r, sigma, left, q, steps) for s in s_grid]
        # Critical price: the highest S where exercising now is optimal, by bisection on the tree.
        lo, hi = 0.3 * K, K
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if binomial_american_put(mid, K, r, sigma, left, q, steps) - (K - mid) < 1e-6:
                lo = mid
            else:
                hi = mid
        boundary.append(lo)
    return times, s_grid, V, np.array(boundary)


# The test grid from Longstaff and Schwartz (2001), Table 1: K = 40, r = 6%, no dividends.
PAPER_GRID = [(S, sig, T) for S in (36, 38, 40, 42, 44) for sig in (0.2, 0.4) for T in (1, 2)]

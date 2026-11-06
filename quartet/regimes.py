"""Chapter 2: regime switching with a two-state Gaussian hidden Markov model.

Each day the market is secretly in a calm or a stressed state. Each state has its own
mean and volatility, and the state follows a Markov chain. We fit it by expectation
maximisation (Baum-Welch), written from scratch.

The trap: smoothed probabilities P(state_t | all data) use returns after day t. A
strategy built on them is trading on the future. The honest signal is the filtered
probability P(state_t | data up to t), with parameters fitted only on the past.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HMM:
    pi0: np.ndarray  # starting probabilities, shape (K,)
    A: np.ndarray  # transitions, A[i, j] = P(next = j | now = i)
    mu: np.ndarray
    sd: np.ndarray

    def sorted(self) -> HMM:
        """State 0 is always the calmer (lower volatility) one."""
        o = np.argsort(self.sd)
        return HMM(self.pi0[o], self.A[np.ix_(o, o)], self.mu[o], self.sd[o])

    @property
    def expected_duration(self) -> np.ndarray:
        return 1.0 / (1.0 - np.diag(self.A))


def _density(x: np.ndarray, m: HMM) -> np.ndarray:
    z = (x[:, None] - m.mu) / m.sd
    return np.exp(-0.5 * z * z) / (m.sd * np.sqrt(2 * np.pi)) + 1e-300


def forward(x: np.ndarray, m: HMM) -> tuple[np.ndarray, np.ndarray, float]:
    """Scaled forward pass. Row t is the filtered P(state_t | x_1..x_t)."""
    B = _density(x, m)
    T, K = B.shape
    alpha = np.empty((T, K))
    c = np.empty(T)
    a = m.pi0 * B[0]
    c[0] = a.sum()
    alpha[0] = a / c[0]
    A = m.A
    for t in range(1, T):
        a = (alpha[t - 1] @ A) * B[t]
        c[t] = a.sum()
        alpha[t] = a / c[t]
    return alpha, c, float(np.log(c).sum())


def smooth(x: np.ndarray, m: HMM) -> tuple[np.ndarray, np.ndarray, float]:
    """Forward-backward. Returns smoothed P(state_t | all x), summed transitions, log-likelihood."""
    B = _density(x, m)
    alpha, c, ll = forward(x, m)
    T, K = B.shape
    beta = np.ones((T, K))
    for t in range(T - 2, -1, -1):
        beta[t] = m.A @ (B[t + 1] * beta[t + 1]) / c[t + 1]
    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)
    nb = B[1:] * beta[1:] / c[1:, None]
    xi = m.A * (alpha[:-1].T @ nb)
    return gamma, xi, ll


def initial(x: np.ndarray, k: int = 2) -> HMM:
    s = x.std()
    if k == 2:
        sd = np.array([0.6 * s, 1.8 * s])
    else:
        sd = s * np.geomspace(0.5, 2.5, k)
    stay = 0.97
    A = np.full((k, k), (1 - stay) / max(k - 1, 1))
    np.fill_diagonal(A, stay if k > 1 else 1.0)
    return HMM(pi0=np.full(k, 1 / k), A=A, mu=np.full(k, x.mean()), sd=sd)


def n_params(k: int) -> int:
    """Free parameters: start probabilities, transitions, and a mean and volatility per state."""
    return (k - 1) + k * (k - 1) + 2 * k


def bic(x: np.ndarray, ks=(1, 2, 3, 4)) -> list[dict]:
    """Bayesian information criterion for each number of states. Lower is better."""
    out = []
    for k in ks:
        m, ll = fit(x, start=initial(x, k), iters=300)
        out.append({"states": k, "loglik": ll, "params": n_params(k), "bic": -2 * ll + n_params(k) * np.log(len(x)),
                    "vols": (m.sd * np.sqrt(252)).tolist(), "days": m.expected_duration.tolist() if k > 1 else [float(len(x))]})
    best = min(o["bic"] for o in out)
    for o in out:
        o["delta"] = o["bic"] - best
    return out


def fit(x: np.ndarray, start: HMM | None = None, iters: int = 200, tol: float = 1e-7) -> tuple[HMM, float]:
    """Baum-Welch. Returns the fitted model (calm state first) and its log-likelihood."""
    m = start or initial(x)
    prev = -np.inf
    ll = prev
    for _ in range(iters):
        gamma, xi, ll = smooth(x, m)
        w = gamma.sum(axis=0)
        mu = gamma.T @ x / w
        var = (gamma * (x[:, None] - mu) ** 2).sum(axis=0) / w
        A = xi / xi.sum(axis=1, keepdims=True)
        m = HMM(gamma[0], A, mu, np.sqrt(np.maximum(var, 1e-12)))
        if ll - prev < tol * abs(ll):
            break
        prev = ll
    return m.sorted(), ll


def simulate(m: HMM, T: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    K = len(m.mu)
    s = np.empty(T, dtype=int)
    s[0] = rng.choice(K, p=m.pi0)
    for t in range(1, T):
        s[t] = rng.choice(K, p=m.A[s[t - 1]])
    return rng.normal(m.mu[s], m.sd[s]), s


@dataclass
class Backtest:
    name: str
    cagr: float
    vol: float
    sharpe: float
    max_drawdown: float
    time_invested: float
    switches: int
    equity: pd.Series


def backtest(name: str, r: pd.Series, p_stress: pd.Series, threshold: float = 0.5, cost_bps: float = 5.0) -> Backtest:
    """Hold the index when P(stressed) is below the threshold, cash otherwise.

    The signal at the close of day t sets the position for day t+1, so nothing uses
    a return before it happens (other than what the probabilities themselves leak).
    """
    pos = (p_stress < threshold).astype(float).shift(1).fillna(1.0)
    trades = pos.diff().abs().fillna(0.0)
    simple = np.expm1(r)
    strat = pos * simple - trades * cost_bps / 1e4
    return _stats(name, strat, pos, int(trades.sum()))


def _stats(name: str, daily: pd.Series, pos: pd.Series, switches: int) -> Backtest:
    eq = (1 + daily).cumprod()
    years = len(daily) / 252
    cagr = eq.iloc[-1] ** (1 / years) - 1
    vol = daily.std() * np.sqrt(252)
    dd = (eq / eq.cummax() - 1).min()
    return Backtest(name, float(cagr), float(vol), float(cagr / vol if vol else 0), float(dd), float(pos.mean()), switches, eq)


def buy_and_hold(r: pd.Series) -> Backtest:
    simple = np.expm1(r)
    return _stats("Buy and hold", simple, pd.Series(1.0, index=r.index), 0)


def walk_forward_filtered(r: pd.Series, first_year: int, min_years: int = 5) -> tuple[pd.Series, list[dict]]:
    """Refit every January on data before that year only, then filter forward through it.

    Returns P(stressed) for each day from `first_year` on, and the parameters used each year.
    """
    x_all = r.to_numpy()
    years = sorted(set(r.index.year))
    out = pd.Series(np.nan, index=r.index)
    m = None
    history = []
    for y in years:
        if y < first_year:
            continue
        train = r.index.year < y
        if train.sum() < 252 * min_years:
            continue
        m, _ = fit(x_all[train], start=m, iters=60 if m else 200)
        upto = r.index.year <= y
        alpha, _, _ = forward(x_all[upto], replace(m, pi0=np.array([0.5, 0.5])))
        days = r.index[upto]
        this_year = days.year == y
        out.loc[days[this_year]] = alpha[this_year, 1]
        history.append(
            {
                "year": int(y),
                "calm_vol": float(m.sd[0] * np.sqrt(252)),
                "stress_vol": float(m.sd[1] * np.sqrt(252)),
                "calm_days": float(m.expected_duration[0]),
                "stress_days": float(m.expected_duration[1]),
            }
        )
    return out.dropna(), history

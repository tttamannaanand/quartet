import numpy as np
import pandas as pd
import pytest

from quartet import famafrench as ff
from quartet import heston as h
from quartet import lsm
from quartet import regimes as rg
from quartet.data import parse_french

# ---------- Fama-French ----------


def test_regression_recovers_known_loadings():
    rng = np.random.default_rng(1)
    n = 5000
    f = rng.normal(0, 0.01, (n, 3))
    y = 0.0002 + f @ np.array([1.1, 0.5, -0.3]) + rng.normal(0, 0.004, n)
    fit = ff.ols_newey_west(y, np.column_stack([np.ones(n), f]), ["alpha", "m", "s", "h"])
    assert fit.coef[1:] == pytest.approx([1.1, 0.5, -0.3], abs=0.02)
    assert fit.coef[0] == pytest.approx(0.0002, abs=1e-4)
    assert 0.8 < fit.r2 < 1


def test_alpha_from_a_factor_is_explained_away():
    """A fund that just owns value stocks shows CAPM alpha, but no three-factor alpha."""
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2010-01-01", periods=4000)
    fac = pd.DataFrame(
        {"Mkt-RF": rng.normal(3e-4, 0.01, 4000), "SMB": rng.normal(0, 0.005, 4000), "HML": rng.normal(4e-4, 0.005, 4000), "RF": 0.0},
        index=idx,
    )
    r = fac["Mkt-RF"] + 0.8 * fac["HML"] + rng.normal(0, 0.002, 4000)
    price = pd.Series(np.r_[100, 100 * np.cumprod(1 + r.to_numpy())], index=[idx[0] - pd.Timedelta(days=1), *idx])
    out = ff.analyse("X", price, fac)
    assert out["capm"]["alpha"] > 0.05
    assert abs(out["ff3"]["alpha"]) < 0.02
    assert out["ff3"]["hml"] == pytest.approx(0.8, abs=0.05)


def test_french_file_parser():
    text = "This file was created...\n\n,Mkt-RF,SMB,HML,RF\n19260701,    0.09,   -0.25,   -0.27,    0.01\n19260702,    0.45,   -0.33,   -0.06,    0.01\n\nCopyright 2026\n"
    df = parse_french(text)
    assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert df.iloc[0]["Mkt-RF"] == pytest.approx(0.0009)
    assert len(df) == 2


# ---------- Regimes ----------

TRUE = rg.HMM(np.array([0.5, 0.5]), np.array([[0.99, 0.01], [0.03, 0.97]]), np.array([5e-4, -1e-3]), np.array([0.007, 0.025]))


def test_hmm_recovers_states():
    x, s = rg.simulate(TRUE, 6000, seed=3)
    m, _ = rg.fit(x)
    assert m.sd == pytest.approx(TRUE.sd, rel=0.1)
    gamma, _, _ = rg.smooth(x, m)
    assert ((gamma[:, 1] > 0.5) == (s == 1)).mean() > 0.95


def test_filtered_probabilities_never_see_the_future():
    x, _ = rg.simulate(TRUE, 3000, seed=4)
    early, _, _ = rg.forward(x[:2000], TRUE)
    full, _, _ = rg.forward(x, TRUE)
    assert np.allclose(early, full[:2000])


def test_smoothed_probabilities_do_see_the_future():
    x, _ = rg.simulate(TRUE, 3000, seed=4)
    early, _, _ = rg.smooth(x[:2000], TRUE)
    full, _, _ = rg.smooth(x, TRUE)
    assert not np.allclose(early[-50:], full[1950:2000])


def test_em_never_lowers_likelihood():
    x, _ = rg.simulate(TRUE, 3000, seed=5)
    m = rg.initial(x)
    lls = []
    for _ in range(15):
        m, ll = rg.fit(x, start=m, iters=1)
        lls.append(ll)
    assert all(b >= a - 1e-6 for a, b in zip(lls, lls[1:], strict=False))


# ---------- Longstaff-Schwartz ----------


@pytest.mark.parametrize("S,sig,T", [(36, 0.2, 1), (40, 0.4, 2), (44, 0.2, 2)])
def test_lsm_matches_binomial_tree(S, sig, T):
    tree = lsm.binomial_american_put(S, 40, 0.06, sig, T)
    mc = lsm.lsm_american_put(S, 40, 0.06, sig, T, n=60_000, seed=1)
    assert mc.price == pytest.approx(tree, abs=max(0.04, 4 * mc.stderr))


def test_american_put_is_worth_at_least_european():
    for S in (36, 40, 44):
        assert lsm.binomial_american_put(S, 40, 0.06, 0.2, 1) >= lsm.bs_put(S, 40, 0.06, 0.2, 1) - 1e-9


def test_paper_value():
    # Longstaff and Schwartz (2001), Table 1: S=36, sigma=0.2, T=1 -> finite difference 4.478
    assert lsm.binomial_american_put(36, 40, 0.06, 0.2, 1) == pytest.approx(4.478, abs=0.01)


def test_exercise_boundary_sits_below_the_strike():
    r = lsm.lsm_american_put(36, 40, 0.06, 0.2, 1, n=40_000)
    assert r.boundary_s and all(b < 40 for b in r.boundary_s)


# ---------- Heston ----------

P = h.Params(v0=0.04, kappa=1.5, theta=0.05, xi=0.6, rho=-0.7)


def test_characteristic_function_is_a_martingale():
    # E[S_T / F] = phi(-i) = 1
    assert h.cf(np.array([-1j]), 1.0, P)[0] == pytest.approx(1.0, abs=1e-10)


def test_heston_reduces_to_black_scholes_with_tiny_vol_of_vol():
    p = h.Params(v0=0.04, kappa=2.0, theta=0.04, xi=0.01, rho=0.0)
    K = np.array([80.0, 100.0, 120.0])
    hp = h.call_prices(100.0, K, 1.0, 0.97, p)
    bs = h.black(100.0, K, 1.0, 0.97, 0.2, True)
    assert hp == pytest.approx(bs, abs=2e-3)


def test_heston_matches_monte_carlo():
    for K in (90.0, 100.0, 115.0):
        price = h.call_prices(100 * np.exp(0.03), np.array([K]), 1.0, np.exp(-0.03), P)[0]
        mc, se = h.mc_call(100.0, K, 1.0, 0.03, P, n=100_000)
        assert price == pytest.approx(mc, abs=4 * se + 0.03)


def test_put_call_parity():
    K = np.array([90.0, 110.0])
    c = h.call_prices(100.0, K, 0.5, 0.98, P)
    p = h.put_prices(100.0, K, 0.5, 0.98, P)
    assert c - p == pytest.approx(0.98 * (100 - K))


def test_implied_vol_round_trip():
    price = float(h.black(100.0, 95.0, 0.5, 0.99, 0.23, False))
    assert h.implied_vol(price, 100.0, 95.0, 0.5, 0.99, False) == pytest.approx(0.23, abs=1e-6)


def test_calibration_fits_a_synthetic_chain():
    """Prices made by Heston itself: the fit should be near perfect, even if the parameters differ."""
    slices = []
    for T in (0.1, 0.3, 0.8):
        F, df = 100.0, np.exp(-0.04 * T)
        K = np.linspace(85, 112, 12)
        call = K >= F
        mid = np.where(call, h.call_prices(F, K, T, df, P), h.put_prices(F, K, T, df, P))
        iv = np.array([h.implied_vol(m, F, k, T, df, c) for m, k, c in zip(mid, K, call, strict=True)])
        slices.append(h.Slice(str(T), T, F, df, K, call, mid, iv, h.black_vega(F, K, T, df, iv)))
    best = h.calibrate(slices, starts=4, seed=1)[0]
    assert best.rmse_vol_pts < 0.05


# ---------- additions ----------


def test_parser_reads_a_single_factor_file():
    text = "Momentum notes\n\n,Mom   \n19270103,   0.56\n19270104,  -0.12\n\nCopyright\n"
    df = parse_french(text)
    assert list(df.columns) == ["Mom"]
    assert df.iloc[0, 0] == pytest.approx(0.0056)


def test_bic_prefers_the_true_number_of_states():
    x, _ = rg.simulate(TRUE, 6000, seed=8)
    out = {o["states"]: o["bic"] for o in rg.bic(x, ks=(1, 2, 3))}
    assert out[2] < out[1]
    assert out[2] < out[3]


def test_tree_boundary_sits_below_strike_and_rises_to_it():
    times, s, V, b = lsm.binomial_surface(36, 40, 0.06, 0.2, 1, n=300, t_points=6)
    assert all(x <= 40 + 1e-9 for x in b)
    assert b[-1] == pytest.approx(40)
    assert all(np.diff(b) > -0.05)  # rises toward expiry
    assert np.all(V >= np.maximum(40 - s, 0) - 1e-9)  # never worth less than exercising now


def test_lsm_boundary_agrees_with_the_tree():
    r = lsm.lsm_american_put(36, 40, 0.06, 0.2, 1, n=100_000, seed=3)
    times, _, _, b = lsm.binomial_surface(36, 40, 0.06, 0.2, 1, n=300, t_points=11)
    mid = np.interp(0.5, r.boundary_t, r.boundary_s)
    assert mid == pytest.approx(np.interp(0.5, times, b), abs=1.0)


def test_sampled_paths_exercise_only_in_the_money():
    r = lsm.lsm_american_put(36, 40, 0.06, 0.2, 1, n=20_000, seed=2)
    for p, stop in zip(r.paths, r.stop, strict=True):
        if stop >= 0:
            assert p[stop] < 40

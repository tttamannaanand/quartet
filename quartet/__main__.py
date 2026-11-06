"""Run the four chapters on real data.

    python -m quartet fetch          # download prices, factors and an option chain
    python -m quartet famafrench     # chapter 1
    python -m quartet regimes        # chapter 2
    python -m quartet lsm            # chapter 3
    python -m quartet heston         # chapter 4
    python -m quartet all            # everything, and write web/data/*.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, lsm
from . import famafrench as ff
from . import heston as h
from . import regimes as rg

OUT = Path(__file__).resolve().parent.parent / "web" / "data"


def save(name: str, obj: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1, default=float))


def run_famafrench() -> dict:
    factors = data.french_factors()
    six = data.french_five_mom()
    rows = [ff.analyse(t, data.prices(t), factors, six) | {"about": about} for t, about in ff.FUNDS.items()]
    print(f"\nChapter 1: Fama-French ({factors.index[0].date()} to {factors.index[-1].date()})")
    print(f"  {'fund':6} {'CAPM alpha':>11} {'FF3 alpha':>10} {'t':>6} {'mkt':>5} {'SMB':>6} {'HML':>6} {'R2':>5}")
    for r in rows:
        a, b = r["capm"], r["ff3"]
        print(f"  {r['ticker']:6} {a['alpha']:>10.1%} {b['alpha']:>10.1%} {b['t']:>6.2f} {b['mkt']:>5.2f} {b['smb']:>6.2f} {b['hml']:>6.2f} {b['r2']:>5.2f}")
    print("  alpha as factors are added (CAPM -> FF3 -> FF5 -> FF5 + momentum):")
    for r in rows:
        print(f"  {r['ticker']:6} " + "  ".join(f"{x['alpha']:>6.1%} (t {x['t']:5.2f})" for x in r["ladder"]))
    out = {"factors_end": factors.index[-1].date().isoformat(), "funds": rows}
    save("famafrench", out)
    return out


def run_regimes() -> dict:
    px = data.prices("SPY")
    r = data.log_returns(px)
    first = 2005
    honest, history = rg.walk_forward_filtered(r, first)
    full, _ = rg.fit(r.to_numpy())
    gamma, _, _ = rg.smooth(r.to_numpy(), full)
    cheat = pd.Series(gamma[:, 1], index=r.index).loc[honest.index]
    rr = r.loc[honest.index]
    tests = [rg.buy_and_hold(rr), rg.backtest("Honest: filtered, past-only fit", rr, honest), rg.backtest("Cheating: smoothed, full-sample fit", rr, cheat)]
    print(f"\nChapter 2: regimes on SPY ({rr.index[0].date()} to {rr.index[-1].date()})")
    print(f"  full-sample fit: calm vol {full.sd[0] * np.sqrt(252):.0%}, stressed vol {full.sd[1] * np.sqrt(252):.0%}, "
          f"calm lasts ~{full.expected_duration[0]:.0f} days, stress ~{full.expected_duration[1]:.0f} days")
    for b in tests:
        print(f"  {b.name:38} CAGR {b.cagr:6.1%}  vol {b.vol:5.1%}  return/vol {b.sharpe:5.2f}  max DD {b.max_drawdown:6.1%}  switches {b.switches}")
    bics = rg.bic(r.to_numpy())
    print("  BIC by number of states (lower is better):")
    for o in bics:
        print(f"    {o['states']} states: BIC {o['bic']:9.0f}  (+{o['delta']:5.0f})  vols {', '.join(f'{v:.0%}' for v in o['vols'])}")
    weekly = pd.DataFrame({"price": px.loc[honest.index], "honest": honest, "cheat": cheat}).resample("W-FRI").last().dropna()
    eq = pd.DataFrame({b.name: b.equity for b in tests}).resample("W-FRI").last().dropna()
    out = {
        "start": rr.index[0].date().isoformat(),
        "end": rr.index[-1].date().isoformat(),
        "full_fit": {"calm_vol": full.sd[0] * np.sqrt(252), "stress_vol": full.sd[1] * np.sqrt(252),
                     "calm_mean": full.mu[0] * 252, "stress_mean": full.mu[1] * 252,
                     "calm_days": full.expected_duration[0], "stress_days": full.expected_duration[1]},
        "yearly_fits": history,
        "bic": bics,
        "series": {"dates": [d.date().isoformat() for d in weekly.index], "price": weekly["price"].round(2).tolist(),
                   "honest": weekly["honest"].round(3).tolist(), "cheat": weekly["cheat"].round(3).tolist()},
        "equity": {"dates": [d.date().isoformat() for d in eq.index], **{k: eq[k].round(4).tolist() for k in eq}},
        "backtests": [{k: v for k, v in b.__dict__.items() if k != "equity"} for b in tests],
    }
    save("regimes", out)
    return out


def run_lsm() -> dict:
    rows = []
    t0 = time.time()
    for S, sig, T in lsm.PAPER_GRID:
        res = lsm.lsm_american_put(S, 40, 0.06, sig, T, steps=50 * T, n=100_000, seed=7)
        tree = lsm.binomial_american_put(S, 40, 0.06, sig, T)
        euro = lsm.bs_put(S, 40, 0.06, sig, T)
        rows.append({"S": S, "sigma": sig, "T": T, "lsm": res.price, "se": res.stderr, "tree": tree, "european": euro,
                     "premium": tree - euro, "error": res.price - tree})
    worst = max(abs(r["error"]) for r in rows)
    print(f"\nChapter 3: Longstaff-Schwartz, 20 cases from the paper ({time.time() - t0:.0f}s)")
    print(f"  {'S':>3} {'vol':>4} {'T':>2} {'LSM':>7} {'(se)':>7} {'tree':>7} {'European':>9} {'early ex.':>9}")
    for r in rows:
        print(f"  {r['S']:>3} {r['sigma']:>4} {r['T']:>2} {r['lsm']:>7.3f} {r['se']:>7.3f} {r['tree']:>7.3f} {r['european']:>9.3f} {r['premium']:>9.3f}")
    print(f"  largest gap between LSM and the tree: {worst:.3f}")
    b = lsm.lsm_american_put(36, 40, 0.06, 0.2, 1, steps=100, n=200_000, seed=7)
    times, sgrid, V, crit = lsm.binomial_surface(36, 40, 0.06, 0.2, 1, n=600, s_grid=np.linspace(24, 56, 33), t_points=26)
    ex_frac = float((b.stop[b.stop >= 0] < 100).mean()) if (b.stop >= 0).any() else 0.0
    print(f"  of the sampled in-the-money paths, {ex_frac:.0%} exercise before expiry")
    degree = []
    for d in (1, 2, 3, 4, 5, 6):
        res = lsm.lsm_american_put(36, 40, 0.06, 0.2, 1, n=100_000, degree=d, seed=7)
        degree.append({"degree": d, "price": res.price, "se": res.stderr})
    paths = []
    for n in (1_000, 5_000, 20_000, 100_000):
        vals = [lsm.lsm_american_put(36, 40, 0.06, 0.2, 1, n=n, seed=s).price for s in range(8)]
        paths.append({"paths": n, "mean": float(np.mean(vals)), "spread": float(np.std(vals))})
    out = {"rows": rows, "worst_error": worst, "boundary": {"t": b.boundary_t, "s": b.boundary_s, "S": 36, "K": 40, "sigma": 0.2, "T": 1},
           "degree": degree, "paths": paths,
           "fan": {"t": np.linspace(0, 1, b.paths.shape[1]).round(4).tolist(), "paths": b.paths.round(3).tolist(), "stop": b.stop.tolist(), "steps": 100},
           "surface": {"t": times.round(4).tolist(), "s": sgrid.round(3).tolist(), "v": V.round(4).tolist(), "boundary": crit.round(4).tolist()},
           "tree_ref": lsm.binomial_american_put(36, 40, 0.06, 0.2, 1)}
    save("lsm", out)
    return out


def run_heston() -> dict:
    snap = data.option_chain("SPY")
    slices = h.clean_chain(snap)
    n = sum(len(s.strikes) for s in slices)
    t0 = time.time()
    fits = h.calibrate(slices, starts=24, seed=0)
    best = fits[0]
    near = [f for f in fits if f.rmse_vol_pts <= best.rmse_vol_pts * 1.15]
    print(f"\nChapter 4: Heston on SPY, {snap['asof']} (spot {snap['spot']:.2f}, rate {snap['rate']:.2%})")
    print(f"  {len(slices)} expiries, {n} quotes, 24 random starts ({time.time() - t0:.0f}s)")
    print(f"  best fit: RMSE {best.rmse_vol_pts:.2f} vol points")
    print(f"  {len(near)} of {len(fits)} starts ended within 15% of the best error; distinct answers:")
    seen = []
    for f in near:
        if any(np.allclose(f.params.array(), q, rtol=0.02) for q in seen):
            continue
        seen.append(f.params.array())
        p = f.params
        print(f"    RMSE {f.rmse_vol_pts:.2f}  v0 {p.v0:.4f}  kappa {p.kappa:6.2f}  theta {p.theta:.4f}  xi {p.xi:.2f}  rho {p.rho:+.2f}  Feller {'ok' if p.feller else 'broken'}")
    prof = h.profile(slices, "kappa", [0.5, 1, 2, 3, 5, 8, 10.8, 13, 15], best.params)
    print("  profile: lock kappa, refit the other four")
    for q in prof:
        print(f"    kappa {q['fixed']:5.1f} -> RMSE {q['rmse']:.2f}  xi {q['xi']:.2f}  theta {q['theta']:.4f}  rho {q['rho']:+.2f}  Feller {'ok' if q['feller'] else 'broken'}")
    single = h.clean_chain(snap, min_days=25, max_days=45, max_slices=1)
    prof1 = h.profile(single, "kappa", [0.5, 1, 2, 3, 5, 8, 10.8, 13, 15], best.params) if single else []
    if prof1:
        print(f"  same profile using one {round(single[0].T*365)}-day expiry only")
        for q in prof1:
            print(f"    kappa {q['fixed']:5.1f} -> RMSE {q['rmse']:.2f}  xi {q['xi']:.2f}  theta {q['theta']:.4f}")
    # Model implied-vol surface on a regular grid, between the shortest and longest expiries.
    Ts = np.linspace(min(s.T for s in slices), max(s.T for s in slices), 24)
    ms = np.linspace(0.8, 1.15, 29)
    grid = []
    for T in Ts:
        df = np.exp(-snap["rate"] * T)
        Fg = 1.0
        prices = h.call_prices(Fg, ms, T, df, best.params)
        row = [h.implied_vol(pv if m >= 1 else pv - df * (Fg - m), Fg, m, T, df, m >= 1) for pv, m in zip(prices, ms, strict=True)]
        grid.append([round(v * 100, 3) if np.isfinite(v) else None for v in row])
    smiles = []
    for s in slices:
        model = h.model_prices(s, best.params)
        miv = [h.implied_vol(m, s.F, k, s.T, s.df, c) for m, k, c in zip(model, s.strikes, s.is_call, strict=True)]
        smiles.append({"expiry": s.expiry, "days": round(s.T * 365), "forward": s.F,
                       "moneyness": (s.strikes / s.F).round(4).tolist(), "strike": s.strikes.tolist(),
                       "market": (s.iv * 100).round(2).tolist(), "model": (np.array(miv) * 100).round(2).tolist()})
    out = {"asof": snap["asof"], "spot": snap["spot"], "rate": snap["rate"], "quotes": n,
           "best": h.as_dict(best.params) | {"rmse": best.rmse_vol_pts},
           "fits": [h.as_dict(f.params) | {"rmse": f.rmse_vol_pts} for f in fits],
           "near_best": len(near), "smiles": smiles,
           "surface": {"days": (Ts * 365).round(1).tolist(), "moneyness": ms.round(4).tolist(), "iv": grid}, "profile": prof, "profile_single": prof1,
           "single_days": round(single[0].T * 365) if single else None}
    save("heston", out)
    return out


def main() -> None:
    p = argparse.ArgumentParser(prog="quartet", description="Four quant models on real market data")
    p.add_argument("chapter", choices=["fetch", "famafrench", "regimes", "lsm", "heston", "all"])
    p.add_argument("--refresh", action="store_true", help="download fresh data")
    a = p.parse_args()
    if a.chapter == "fetch" or a.refresh:
        data.french_factors(refresh=True)
        for t in [*ff.FUNDS]:
            data.prices(t, refresh=True)
        data.option_chain("SPY", refresh=True)
        print(f"data saved to {data.CACHE}")
        if a.chapter == "fetch":
            return
    runs = {"famafrench": run_famafrench, "regimes": run_regimes, "lsm": run_lsm, "heston": run_heston}
    for name, fn in runs.items():
        if a.chapter in (name, "all"):
            fn()


if __name__ == "__main__":
    main()

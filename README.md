# Quartet

**Four classic quant models, written from scratch and run on real market data.** Each chapter ends with what broke.

**[Open the interactive page](https://tttamannaanand.github.io/quartet/)**

| # | Model | Question | Data |
|---|---|---|---|
| 1 | Fama-French three-factor regression | How much of a fund's alpha survives once size and value are counted? | Kenneth French Data Library, Yahoo Finance |
| 2 | Regime switching (hidden Markov model) | Is the market calm or stressed, and can you trade on it honestly? | SPY daily, 1999 onward |
| 3 | Longstaff-Schwartz | When should you exercise an American put? | Simulated paths, checked against a binomial tree |
| 4 | Heston stochastic volatility | Can five parameters explain the volatility smile, and are they unique? | Live SPY option chain |

Everything is plain NumPy and SciPy: the Newey-West regression, Baum-Welch EM, forward-backward filter, least-squares Monte Carlo, binomial tree, Heston characteristic function, Lewis pricing formula and calibration. No quant libraries.

## Run it

```bash
pip install numpy scipy pandas yfinance
python -m quartet fetch      # download prices, factors and today's option chain into data/
python -m quartet all        # run the four chapters and write web/data/*.json
python -m http.server -d web 8000
pytest                       # 24 tests
```

Raw market data isn't committed. The results in `web/data/` are from **3 November 2026**; rerun `fetch` to update them.

## 1 · Fama-French: how much alpha survives?

Daily returns regressed on market, size (SMB) and value (HML), with Newey-West standard errors. Alpha is annualised.

| Fund | CAPM alpha | FF3 alpha | t | Market | SMB | HML | R² |
|---|---|---|---|---|---|---|---|
| SPY | −0.2% | −0.1% | −0.31 | 0.98 | −0.14 | 0.01 | 0.97 |
| BRK-B | +3.4% | +2.7% | 0.89 | 0.65 | −0.12 | 0.44 | 0.39 |
| IWN (small value) | +0.6% | −0.8% | −1.17 | 0.99 | 0.84 | 0.56 | 0.96 |
| QQQ | +1.8% | +2.9% | 1.57 | 1.19 | −0.01 | −0.57 | 0.82 |
| ARKK | −1.3% | +2.6% | 0.52 | 1.39 | 1.14 | −0.84 | 0.75 |
| VTV (large value) | −0.6% | −0.5% | −0.62 | 0.90 | −0.10 | 0.35 | 0.95 |

**Adding more factors** (all on the five-factor file, Newey-West t in brackets):

| Fund | CAPM | FF3 | FF5 (+ profitability, investment) | FF5 + momentum |
|---|---|---|---|---|
| SPY | −0.2% (−0.43) | −0.1% (−0.25) | −0.6% (−1.84) | −0.5% (−1.62) |
| BRK-B | +3.4% (1.03) | +2.7% (0.89) | +2.9% (0.95) | +3.0% (0.98) |
| IWN | +0.6% (0.29) | −1.0% (−1.51) | −1.7% (−2.59) | −1.6% (−2.51) |
| QQQ | +1.8% (0.77) | +3.0% (1.61) | **+6.1% (3.57)** | **+6.1% (3.57)** |
| ARKK | −1.3% (−0.19) | +2.5% (0.50) | +5.2% (1.16) | +6.0% (1.36) |
| VTV | −0.6% (−0.49) | −0.4% (−0.55) | −0.9% (−1.16) | −0.7% (−0.97) |

**What broke:** no fund has an alpha with a t-statistic above 2, so none can be told apart from luck. IWN's small CAPM alpha disappears once its size and value tilts are counted. Factors can also *raise* alpha: growth funds (QQQ, ARKK) lean away from value, so their three-factor alpha is higher than their CAPM alpha. SPY is the sanity check: beta 0.98, alpha about equal to its fee. As the brief warned, most of the work was cleaning and aligning data.

Adding profitability, investment and momentum **doesn't always shrink alpha**: QQQ's grows to +6.1% a year with a t of 3.57, because the Nasdaq-100 loads negatively on profitability (−0.41) and investment (−0.43), so the model expected it to do worse. IWN's turns significantly *negative*. With six models on six funds, one or two "significant" results can appear by chance, so they're leads, not proof.

## 2 · Regime switching: calm or stressed?

A two-state Gaussian HMM on SPY daily log returns, fitted by Baum-Welch. The full-sample fit finds calm days with **11%** yearly volatility (lasting about 79 trading days) and stressed spells with **30%** (about 35 days).

The strategy holds SPY when P(stressed) < 50% and cash otherwise, acting the next day, with 0.05% per switch. 2005 to November 2026:

| Strategy | Yearly return | Volatility | Return / vol | Worst drop | Switches |
|---|---|---|---|---|---|
| Buy and hold | 10.8% | 18.9% | 0.57 | −55.2% | 0 |
| **Honest:** filtered probabilities, parameters refitted each January on past data only | 7.5% | 10.6% | 0.70 | −20.5% | 238 |
| **Cheating:** smoothed probabilities, full-sample parameters | 16.3% | 9.6% | 1.70 | −10.0% | 76 |

**What broke:** the cheating version looks brilliant only because smoothed probabilities use returns from after each day. A test proves the filtered probabilities never change when future data is added, and the smoothed ones do. Done honestly, the signal halves volatility and the worst drop but gives up about 3% a year, and it whipsaws: 238 switches against 76.

**How many states?** BIC (lower is better) for 1–4 states on the full sample:

| States | BIC behind the best | Volatility of each state |
|---|---|---|
| 1 | +3,367 | 19% |
| 2 | +683 | 11%, 30% |
| 3 | +95 | 9%, 19%, 47% |
| 4 | best | 8%, 15%, 24%, 61% |

BIC keeps wanting more states: daily returns have fat tails, so each extra volatility level pays for its parameters. Two states is a choice for interpretability, and a test checks that BIC does pick 2 when the data really has 2.

## 3 · Longstaff-Schwartz: when to exercise early

100,000 antithetic paths, 50 steps a year, weighted Laguerre polynomials of degree 3, on the 20 cases from Table 1 of the original paper (strike $40, 6% rates). Each is checked against a 2,000-step binomial tree.

- **Largest gap from the tree: $0.020** across all 20 cases.
- The method lands slightly below the tree in most cases. That's expected: a regression-based exercise rule is never perfect, and any imperfect rule earns less than the best one, so the estimate is biased low.
- Early exercise is worth up to **$1.09** over the European price (stock $36, 20% volatility, 2 years).
- The interactive page shows 80 simulated paths and the point where each one exercises, the exact boundary from the tree, how the price settles as paths go from 1,000 to 100,000, and a **rotatable 3D surface** of the put's value at every stock price and time, with the exercise boundary drawn across it.

## 4 · Heston: random volatility, calibrated to SPY

Calibrated to **497 out-of-the-money SPY quotes across 6 expiries** (24 days to 331 days) on 3 November 2026. The forward for each expiry comes from put-call parity, so no dividend guess is needed. The fit minimises vega-weighted price errors, roughly errors in implied volatility, from 24 random starting points.

| Parameter | Fitted | Meaning |
|---|---|---|
| v0 | 0.0392 | volatility today ≈ 19.8% |
| theta | 0.0419 | long-run volatility ≈ 20.5% |
| kappa | 10.8 | pull back to the long run, half-life ≈ 23 days |
| xi | 2.16 | volatility of volatility |
| rho | −0.73 | prices fall, volatility rises |

Average fit error: **0.59 volatility points**.

The page draws the full **3D implied-volatility surface**: every market quote as a dot, with the fitted Heston surface through them. Drag to rotate.

**What broke:**
- All 24 starts found the same minimum, but it sits in a long, flat valley. **Lock kappa anywhere from 8 to 15 and refit the rest, and the error barely moves (0.59–0.61)**, as long as xi moves with it (1.9 to 2.5). The data pins down the combination, not each number.
- With one 27-day expiry alone it's much worse: every kappa from 1 to 15 fits about equally, and theta runs into its upper limit.
- The fit **breaks the Feller condition** (2κθ < ξ²), so variance can touch zero. That's common for SPY: its steep short-dated smile needs a large xi.
- The shortest expiry fits worst. Far out-of-the-money puts price in more crash risk than Heston can make; models with jumps (like Bates) do better there.

## Tests

24 tests check each piece against something independent:
- regression recovers known loadings, and a fund that only owns value loses its alpha;
- the HMM recovers simulated states, EM never lowers the likelihood, filtered probabilities never see the future, and BIC picks the true number of states;
- Longstaff-Schwartz matches the binomial tree (prices and the exercise boundary), paths only exercise in the money, and the tree matches the paper's 4.478;
- Heston's characteristic function is a martingale, collapses to Black-Scholes when vol-of-vol is tiny, matches Monte Carlo, obeys put-call parity, and calibration refits a synthetic Heston chain.

## Caveats

- Research and learning only; not investment advice. Backtests ignore taxes and use the close price.
- Yahoo Finance data is unofficial and sometimes revised. Option quotes are a single snapshot with bid-ask noise.
- Fund regressions cover each fund's own history (ARKK from 2014, BRK-B from 1999). The factor data ends at the last month Kenneth French has published.

## Layout

```
quartet/data.py         downloading and caching data
quartet/famafrench.py   chapter 1
quartet/regimes.py      chapter 2
quartet/lsm.py          chapter 3
quartet/heston.py       chapter 4
quartet/__main__.py     runs everything and writes web/data
web/                    the interactive page (vanilla JS + SVG; Plotly for the two 3D surfaces)
tests/                  24 tests
```

## Licence

MIT

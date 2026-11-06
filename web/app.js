"use strict";

const NS = "http://www.w3.org/2000/svg";
const $ = (s, r = document) => r.querySelector(s);
const tip = $("#tip");

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
const pct = (x, d = 1) => `${(x * 100).toFixed(d)}%`;
const signed = (x, d = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}%`;
const fix = (x, d = 2) => Number(x).toFixed(d);
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

function showTip(evt, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  const pad = 14;
  let x = evt.clientX + pad;
  let y = evt.clientY + pad;
  const r = tip.getBoundingClientRect();
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
const hideTip = () => (tip.hidden = true);
const width = (host) => Math.max(280, Math.round(host.clientWidth || host.parentElement.clientWidth || 720));

function niceTicks(lo, hi, n = 5) {
  const span = hi - lo || 1;
  const step0 = span / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

/* A line chart with a shared x axis, crosshair tooltip and optional shaded bands. */
function lineChart(host, o) {
  host.innerHTML = "";
  const W = width(host);
  const H = o.height || 300;
  const m = { t: 10, r: o.right ?? 110, b: 26, l: 48 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.label || "chart" }, host);
  const xs = o.xs.map(Number);
  const all = o.series.flatMap((s) => s.ys.filter((v) => v != null && isFinite(v)));
  let lo = o.yMin ?? Math.min(...all);
  let hi = o.yMax ?? Math.max(...all);
  const f = o.logY ? Math.log : (v) => v;
  if (!o.logY) {
    const pad = (hi - lo) * 0.06;
    lo = o.yMin ?? lo - pad;
    hi = o.yMax ?? hi + pad;
  }
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const X = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((f(v) - f(lo)) / (f(hi) - f(lo) || 1)) * (H - m.t - m.b);

  if (o.bands) {
    const g = el("g", {}, svg);
    for (let i = 0; i < xs.length - 1; i++) {
      const p = o.bands[i];
      if (p > 0.02) el("rect", { x: X(xs[i]), y: m.t, width: Math.max(0.6, X(xs[i + 1]) - X(xs[i]) + 0.4), height: H - m.t - m.b, fill: "var(--stress)", "fill-opacity": (p * 0.32).toFixed(3) }, g);
    }
  }
  const ax = el("g", { class: "axis" }, svg);
  const yt = o.logY ? o.logTicks : niceTicks(lo, hi, 5);
  for (const v of yt) {
    if (v < lo || v > hi) continue;
    el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: "gridline" }, ax);
    el("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, ax).textContent = o.yFmt ? o.yFmt(v) : v;
  }
  for (const v of o.xTicks || niceTicks(x0, x1, 6)) {
    el("text", { x: X(+v), y: H - 8, "text-anchor": "middle" }, ax).textContent = o.xFmt ? o.xFmt(+v) : v;
  }
  if (o.refY != null) el("line", { x1: m.l, x2: W - m.r, y1: Y(o.refY), y2: Y(o.refY), class: "baseline", "stroke-dasharray": "4 4" }, svg);

  for (const s of o.series) {
    if (s.dots) {
      const g = el("g", {}, svg);
      s.ys.forEach((v, i) => v != null && isFinite(v) && el("circle", { cx: X(xs[i]), cy: Y(v), r: 3.2, class: "dot-mkt" }, g));
      continue;
    }
    let d = "";
    s.ys.forEach((v, i) => {
      if (v == null || !isFinite(v)) return;
      d += `${d ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`;
    });
    el("path", { d, class: "series", stroke: s.color, "stroke-dasharray": s.dash || "" }, svg);
    if (o.labels !== false && m.r > 20) {
      const last = s.ys.length - 1 - [...s.ys].reverse().findIndex((v) => v != null && isFinite(v));
      el("text", { x: X(xs[last]) + 6, y: Y(s.ys[last]) + 4 + (s.nudge || 0), class: "label" }, svg).textContent = s.name;
    }
  }

  const cross = el("line", { y1: m.t, y2: H - m.b, class: "crosshair", visibility: "hidden" }, svg);
  const marks = o.series.map((s) => el("circle", { r: 4, fill: s.color || "var(--s2)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg));
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, class: "hit" }, svg);
  hit.addEventListener("mousemove", (e) => {
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    let i = 0;
    let best = Infinity;
    xs.forEach((v, j) => {
      const dd = Math.abs(X(v) - p.x);
      if (dd < best) [best, i] = [dd, j];
    });
    cross.setAttribute("x1", X(xs[i]));
    cross.setAttribute("x2", X(xs[i]));
    cross.setAttribute("visibility", "visible");
    o.series.forEach((s, k) => {
      const v = s.ys[i];
      const ok = v != null && isFinite(v);
      marks[k].setAttribute("visibility", ok ? "visible" : "hidden");
      if (ok) {
        marks[k].setAttribute("cx", X(xs[i]));
        marks[k].setAttribute("cy", Y(v));
      }
    });
    showTip(e, o.tip(i));
  });
  hit.addEventListener("mouseleave", () => {
    cross.setAttribute("visibility", "hidden");
    marks.forEach((c) => c.setAttribute("visibility", "hidden"));
    hideTip();
  });
}

function table(host, head, rows, numeric = []) {
  host.innerHTML = `<table><thead><tr>${head.map((h, i) => `<th class="${numeric.includes(i) ? "n" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${r.map((c, i) => `<td class="${numeric.includes(i) ? "n" : ""}">${c}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

function takeaways(host, items) {
  host.innerHTML = `<h4>What broke, and what it means</h4><ul>${items.map((t) => `<li>${t}</li>`).join("")}</ul>`;
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-table]");
  if (!b) return;
  const t = document.getElementById(b.dataset.table);
  const chart = t.previousElementSibling;
  t.hidden = !t.hidden;
  chart.hidden = !t.hidden;
  b.textContent = t.hidden ? "Show as table" : "Show as chart";
});

const yearOf = (iso) => {
  const d = new Date(iso);
  return d.getUTCFullYear() + d.getUTCMonth() / 12 + d.getUTCDate() / 365;
};

/* ---------- Chapter 1 ---------- */
function famaFrench(d) {
  const host = $("#ffChart");
  host.innerHTML = "";
  const funds = d.funds;
  const W = width(host);
  const row = 46;
  const m = { t: W < 560 ? 44 : 30, r: 70, b: 26, l: 60 };
  const H = m.t + m.b + funds.length * row;
  const vals = funds.flatMap((f) => [f.capm.alpha, f.ff3.alpha]);
  const lim = Math.max(0.04, ...vals.map(Math.abs)) * 1.1;
  const X = (v) => m.l + ((v + lim) / (2 * lim)) * (W - m.l - m.r);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Alpha before and after Fama-French" }, host);
  const lg = el("g", { class: "axis" }, svg);
  for (const v of niceTicks(-lim, lim, 6)) {
    el("line", { x1: X(v), x2: X(v), y1: m.t - 6, y2: H - m.b, class: "gridline" }, lg);
    el("text", { x: X(v), y: H - 8, "text-anchor": "middle" }, lg).textContent = `${(v * 100).toFixed(0)}%`;
  }
  el("line", { x1: X(0), x2: X(0), y1: m.t - 6, y2: H - m.b, class: "baseline" }, svg);
  const key = el("g", {}, svg);
  [["CAPM alpha (market only)", "var(--s3)"], ["Fama-French alpha (market, size, value)", "var(--s1)"]].forEach(([t, c], i) => {
    const narrow = W < 560;
    const kx = narrow ? 8 : m.l + i * 250;
    const ky = narrow ? 4 + i * 16 : 4;
    el("rect", { x: kx, y: ky, width: 12, height: 12, rx: 3, fill: c }, key);
    el("text", { x: kx + 18, y: ky + 10, class: "label" }, key).textContent = narrow ? t.split(" (")[0] : t;
  });
  funds.forEach((f, i) => {
    const y = m.t + i * row;
    el("text", { x: m.l - 10, y: y + 22, "text-anchor": "end", class: "label", "font-weight": 600 }, svg).textContent = f.ticker;
    [[f.capm.alpha, "var(--s3)", 4], [f.ff3.alpha, "var(--s1)", 21]].forEach(([v, c, off]) => {
      const a = X(Math.min(0, v));
      const w = Math.max(2, Math.abs(X(v) - X(0)));
      el("rect", { x: a, y: y + off, width: w, height: 15, rx: 3, fill: c }, svg);
    });
    el("text", { x: X(Math.max(0, f.ff3.alpha, f.capm.alpha)) + 6, y: y + 33, class: "label" }, svg).textContent = signed(f.ff3.alpha);
    const hit = el("rect", { x: 0, y, width: W, height: row - 4, class: "hit" }, svg);
    hit.addEventListener("mousemove", (e) =>
      showTip(
        e,
        `<b>${esc(f.ticker)}</b> · ${esc(f.about)}<br>CAPM alpha ${signed(f.capm.alpha)} a year<br>Fama-French alpha ${signed(f.ff3.alpha)} (t = ${fix(f.ff3.t)})<br>Loadings: market ${fix(f.ff3.mkt)}, size ${fix(f.ff3.smb)}, value ${fix(f.ff3.hml)}<br>${f.start.slice(0, 4)}–${f.end.slice(0, 4)}, R² ${fix(f.ff3.r2)}`,
      ),
    );
    hit.addEventListener("mouseleave", hideTip);
  });
  table(
    $("#ffTable"),
    ["Fund", "Years", "CAPM α", "FF3 α", "t", "Market", "Size (SMB)", "Value (HML)", "R²"],
    funds.map((f) => [`<b>${f.ticker}</b> <span class="muted">${esc(f.about)}</span>`, `${f.start.slice(0, 4)}–${f.end.slice(0, 4)}`, signed(f.capm.alpha), signed(f.ff3.alpha), fix(f.ff3.t), fix(f.ff3.mkt), fix(f.ff3.smb), fix(f.ff3.hml), fix(f.ff3.r2)]),
    [2, 3, 4, 5, 6, 7, 8],
  );
  const by = Object.fromEntries(funds.map((f) => [f.ticker, f]));
  const sig = funds.filter((f) => Math.abs(f.ff3.t) > 2);
  const items = [
    sig.length
      ? `Only ${sig.map((f) => f.ticker).join(", ")} kept alpha with a t-statistic above 2.`
      : `<b>No fund keeps statistically significant alpha.</b> Every t-statistic is below 2, so none of these alphas can be told apart from luck.`,
  ];
  if (by.IWN) items.push(`<b>IWN</b> is a small-value index fund. Its CAPM alpha of ${signed(by.IWN.capm.alpha)} turns into ${signed(by.IWN.ff3.alpha)} once size (${fix(by.IWN.ff3.smb)}) and value (${fix(by.IWN.ff3.hml)}) are counted: the "edge" was just the factors.`);
  if (by["BRK-B"]) items.push(`<b>Berkshire</b> leans strongly on value (HML ${fix(by["BRK-B"].ff3.hml)}). Some of Buffett's alpha is the value factor, though ${signed(by["BRK-B"].ff3.alpha)} a year is left, with a t of ${fix(by["BRK-B"].ff3.t)}.`);
  if (by.ARKK) items.push(`Factors can also <i>raise</i> alpha. <b>ARKK</b> goes from ${signed(by.ARKK.capm.alpha)} to ${signed(by.ARKK.ff3.alpha)} once its strong tilts toward small companies (SMB ${fix(by.ARKK.ff3.smb)}) and away from value (HML ${fix(by.ARKK.ff3.hml)}) are counted. Even so, a t of ${fix(by.ARKK.ff3.t)} is nowhere near significant.`);
  if (by.SPY) items.push(`Sanity check: <b>SPY</b> has a market beta of ${fix(by.SPY.ff3.mkt)} and alpha of ${signed(by.SPY.ff3.alpha)}, about its fee. Most of the work was cleaning and lining up the data, as the brief warned.`);
  const last = (f) => f.ladder[f.ladder.length - 1];
  const grew = funds.filter((f) => f.ladder.length && last(f).alpha > f.ladder[1].alpha + 0.01);
  const sigEnd = funds.filter((f) => f.ladder.length && Math.abs(last(f).t) > 2);
  if (grew.length) {
    const g = grew.reduce((a, b2) => (last(b2).alpha > last(a).alpha ? b2 : a));
    items.push(`<b>Adding factors doesn't always shrink alpha.</b> With profitability, investment and momentum added, ${g.ticker}'s alpha <i>grows</i> from ${signed(g.ladder[1].alpha)} to ${signed(last(g).alpha)} a year (t = ${fix(last(g).t)}). Its stocks load negatively on the new factors, so the model expected them to do worse than they did.`);
  }
  if (sigEnd.length) items.push(`In the full six-factor model, ${sigEnd.map((f) => `<b>${f.ticker}</b> (${signed(last(f).alpha)}, t ${fix(last(f).t)})`).join(" and ")} cross the |t| &gt; 2 line. Run six models on six funds and one or two "significant" results can appear by chance, so treat them as leads, not proof.`);
  takeaways($("#ffTake"), items);
}

/* ---------- Chapter 2 ---------- */
function regimes(d) {
  const xs = d.series.dates.map(yearOf);
  const logTicks = [50, 100, 200, 400, 800].filter((v) => v > Math.min(...d.series.price) * 0.8 && v < Math.max(...d.series.price) * 1.3);
  const hint = {
    honest: "Each day uses only returns up to that day, with parameters refitted every January on past years only. This is what you could have traded.",
    cheat: "Each day uses the whole sample, including the future. It looks sharper because it knows how every sell-off ended.",
  };
  const draw = (mode) => {
    $("#rgHint").textContent = hint[mode];
    lineChart($("#rgPrice"), {
      xs,
      label: "SPY price shaded by probability of stress",
      series: [{ name: "SPY", ys: d.series.price, color: "var(--ink)" }],
      bands: d.series[mode],
      logY: true,
      logTicks,
      yFmt: (v) => `$${v}`,
      xFmt: (v) => Math.round(v),
      right: 40,
      tip: (i) => `<b>${d.series.dates[i]}</b><br>SPY $${d.series.price[i]}<br>P(stressed): <b>${pct(d.series[mode][i], 0)}</b> ${mode === "cheat" ? "(uses future data)" : ""}`,
    });
  };
  document.querySelectorAll("[data-mode]").forEach((b) =>
    (b.onclick = () => {
      document.querySelectorAll("[data-mode]").forEach((x) => x.setAttribute("aria-checked", x === b));
      draw(b.dataset.mode);
    }),
  );
  draw(document.querySelector('[data-mode][aria-checked="true"]').dataset.mode);

  const names = d.backtests.map((b) => b.name);
  const colors = ["var(--s3)", "var(--s1)", "var(--stress)"];
  const short = ["Buy and hold", "Honest", "Cheating"];
  const exs = d.equity.dates.map(yearOf);
  lineChart($("#rgEquity"), {
    xs: exs,
    label: "Growth of one dollar",
    series: names.map((n, i) => ({ name: short[i], ys: d.equity[n], color: colors[i], dash: i === 2 ? "5 4" : "" })),
    logY: true,
    logTicks: [0.5, 1, 2, 4, 8, 16, 32],
    yFmt: (v) => `$${v}`,
    xFmt: (v) => Math.round(v),
    right: 90,
    tip: (i) => `<b>${d.equity.dates[i]}</b><br>${names.map((n, k) => `${short[k]}: $${fix(d.equity[n][i])}`).join("<br>")}`,
  });
  table(
    $("#rgTable"),
    ["Strategy", "Yearly return", "Volatility", "Return / vol", "Worst drop", "Time invested", "Switches"],
    d.backtests.map((b) => [b.name, pct(b.cagr), pct(b.vol), fix(b.sharpe), pct(b.max_drawdown), pct(b.time_invested, 0), b.switches]),
    [1, 2, 3, 4, 5, 6],
  );
  const [bh, hon, ch] = d.backtests;
  const f = d.full_fit;
  takeaways($("#rgTake"), [
    `The model finds two clear moods: calm days with ${pct(f.calm_vol, 0)} yearly volatility lasting about ${Math.round(f.calm_days)} trading days, and stressed spells with ${pct(f.stress_vol, 0)} lasting about ${Math.round(f.stress_days)}.`,
    `<b>The trap is real.</b> Using smoothed probabilities, the strategy makes ${pct(ch.cagr)} a year with a worst drop of ${pct(ch.max_drawdown)}. The honest version makes ${pct(hon.cagr)}. The difference is entirely information from the future.`,
    `Honestly done, the signal mostly cuts risk: volatility falls from ${pct(bh.vol)} to ${pct(hon.vol)} and the worst drop from ${pct(bh.max_drawdown)} to ${pct(hon.max_drawdown)}, but it gives up return: ${pct(hon.cagr)} a year against ${pct(bh.cagr)} for simply holding.`,
    `<b>BIC wants more states</b> than the two we used: ${d.bic.map((o) => `${o.states}: +${Math.round(o.delta).toLocaleString()}`).join(", ")} behind the best. Daily returns have fat tails, so each extra volatility level keeps paying for its parameters. Two states is a choice for interpretability, not what the data demands.`,
    `The honest filter switches ${hon.switches} times, against ${ch.switches} for the cheating one: without hindsight it gets whipsawed. Each switch is charged 0.05%.`,
  ]);
}

/* ---------- Chapter 3 ---------- */
function lsmChapter(d) {
  const b = d.boundary;
  lineChart($("#lsBoundary"), {
    xs: b.t,
    label: "Exercise boundary",
    series: [{ name: "Boundary", ys: b.s, color: "var(--s1)" }],
    yMin: 30,
    yMax: 40.5,
    refY: b.K,
    yFmt: (v) => `$${v}`,
    xFmt: (v) => `${Math.round(v * 12)}m`,
    xTicks: [0, 0.25, 0.5, 0.75, 1],
    right: 80,
    height: 260,
    tip: (i) => `<b>${(b.t[i] * 12).toFixed(1)} months in</b><br>Exercise if the stock is below <b>$${fix(b.s[i])}</b>`,
  });
  const host = $("#lsPaths");
  host.innerHTML = "";
  const W = width(host);
  const H = 260;
  const m = { t: 10, r: 20, b: 30, l: 52 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Convergence with more paths" }, host);
  const ys = d.paths.flatMap((p) => [p.mean - 2 * p.spread, p.mean + 2 * p.spread]).concat(d.tree_ref);
  const lo = Math.min(...ys) - 0.02;
  const hi = Math.max(...ys) + 0.02;
  const X = (i) => m.l + ((i + 0.5) / d.paths.length) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - lo) / (hi - lo)) * (H - m.t - m.b);
  const ax = el("g", { class: "axis" }, svg);
  for (const v of niceTicks(lo, hi, 5)) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: "gridline" }, ax);
    el("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, ax).textContent = `$${fix(v)}`;
  }
  el("line", { x1: m.l, x2: W - m.r, y1: Y(d.tree_ref), y2: Y(d.tree_ref), class: "baseline", "stroke-dasharray": "5 4" }, svg);
  d.paths.forEach((p, i) => {
    el("text", { x: X(i), y: H - 10, "text-anchor": "middle", class: "label" }, svg).textContent = W < 520 ? `${p.paths / 1000}k` : `${p.paths.toLocaleString()} paths`;
    el("line", { x1: X(i), x2: X(i), y1: Y(p.mean - 2 * p.spread), y2: Y(p.mean + 2 * p.spread), stroke: "var(--s1)", "stroke-width": 2 }, svg);
    el("circle", { cx: X(i), cy: Y(p.mean), r: 5, fill: "var(--s1)", stroke: "var(--surface)", "stroke-width": 2 }, svg);
    const hit = el("rect", { x: X(i) - 50, y: m.t, width: 100, height: H - m.t - m.b, class: "hit" }, svg);
    hit.addEventListener("mousemove", (e) => showTip(e, `<b>${p.paths.toLocaleString()} paths</b><br>Average price $${fix(p.mean, 3)}<br>Spread across seeds ±$${fix(2 * p.spread, 3)}<br>Binomial tree $${fix(d.tree_ref, 3)}`));
    hit.addEventListener("mouseleave", hideTip);
  });
  table(
    $("#lsTable"),
    ["Stock", "Volatility", "Years", "LSM", "± (std. error)", "Binomial tree", "Gap", "European", "Early-exercise value"],
    d.rows.map((r) => [`$${r.S}`, pct(r.sigma, 0), r.T, fix(r.lsm, 3), fix(r.se, 3), fix(r.tree, 3), fix(r.error, 3), fix(r.european, 3), fix(r.premium, 3)]),
    [1, 2, 3, 4, 5, 6, 7, 8],
  );
  const below = d.rows.filter((r) => r.error < 0).length;
  const deg = d.degree;
  takeaways($("#lsTake"), [
    `Across all 20 cases, Longstaff-Schwartz lands within <b>$${fix(d.worst_error, 3)}</b> of the binomial tree.`,
    `It comes in slightly <i>below</i> the tree in ${below} of 20 cases. That is expected: the regression's exercise rule is never perfect, and any imperfect rule earns a bit less than the best one, so the method is biased low.`,
    `In the path picture, most in-the-money paths stop early, the moment they cross the boundary, rather than waiting for expiry. The boundary rises toward the $40 strike as time runs out, so exercising gets more tempting near the end.`,
    `Being allowed to exercise early is worth a lot when the put is deep in the money: up to $${fix(Math.max(...d.rows.map((r) => r.premium)))} over the European price.`,
    `The choice of regression barely matters past degree 2: prices run from $${fix(deg[0].price, 3)} (degree 1) to $${fix(deg[deg.length - 1].price, 3)} (degree ${deg[deg.length - 1].degree}). Path count matters more; with 1,000 paths the price swings by about ±$${fix(2 * d.paths[0].spread, 2)}.`,
  ]);
}

/* ---------- Chapter 4 ---------- */
function hestonChapter(d) {
  $("#hsSmileTitle").textContent = `Implied volatility: market vs Heston · SPY options on ${d.asof}`;
  const host = $("#hsSmiles");
  host.innerHTML = "";
  for (const s of d.smiles) {
    const box = document.createElement("div");
    box.innerHTML = `<h4>${s.days} days · ${s.expiry}</h4><div class="chart"></div>`;
    host.appendChild(box);
    const all = s.market.concat(s.model).filter(isFinite);
    lineChart(box.querySelector(".chart"), {
      xs: s.moneyness,
      label: `Volatility smile ${s.expiry}`,
      series: [
        { name: "Market", ys: s.market, dots: true, color: "var(--s2)" },
        { name: "Heston", ys: s.model, color: "var(--s1)" },
      ],
      yMin: Math.floor(Math.min(...all) - 1),
      yMax: Math.ceil(Math.max(...all) + 1),
      yFmt: (v) => `${v}%`,
      xFmt: (v) => v.toFixed(2),
      xTicks: [0.8, 0.9, 1.0, 1.1].filter((v) => v >= Math.min(...s.moneyness) - 0.01 && v <= Math.max(...s.moneyness) + 0.01),
      right: 10,
      labels: false,
      height: 220,
      tip: (i) => `<b>Strike $${s.strike[i]}</b> (${(s.moneyness[i] * 100).toFixed(0)}% of forward)<br>Market ${fix(s.market[i], 1)}%<br>Heston ${fix(s.model[i], 1)}%`,
    });
  }
  const b = d.best;
  table(
    $("#hsParams"),
    ["Parameter", "Fitted", "In plain words"],
    [
      ["v0", fix(b.v0, 4), `Volatility today: ${pct(b.vol_today)}`],
      ["theta", fix(b.theta, 4), `Long-run volatility: ${pct(b.long_run_vol)}`],
      ["kappa", fix(b.kappa, 2), `Pull back to long run; half-life ${Math.round(b.half_life_days)} days`],
      ["xi", fix(b.xi, 2), "Volatility of volatility"],
      ["rho", fix(b.rho, 2), "Price falls ⇒ volatility rises"],
      ["Feller", b.feller ? "holds" : "broken", b.feller ? "Variance stays above zero" : "Variance can hit zero"],
      ["Fit error", `${fix(b.rmse, 2)} pts`, `Across ${d.quotes} quotes`],
    ],
    [1],
  );
  const pr = d.profile;
  const ps = d.profile_single;
  lineChart($("#hsProfile"), {
    xs: pr.map((p) => p.fixed),
    label: "Fit error with kappa fixed",
    series: [
      { name: "All expiries", ys: pr.map((p) => p.rmse), color: "var(--s1)" },
      ...(ps.length ? [{ name: `${d.single_days}-day only`, ys: ps.map((p) => p.rmse), color: "var(--s2)", dash: "5 4" }] : []),
    ],
    yMin: 0,
    yFmt: (v) => `${fix(v, 1)}`,
    xFmt: (v) => v,
    xTicks: [0, 5, 10, 15],
    right: 100,
    height: 260,
    tip: (i) => `<b>kappa fixed at ${pr[i].fixed}</b><br>All expiries: error ${fix(pr[i].rmse)} pts, xi ${fix(pr[i].xi)}, theta ${fix(pr[i].theta, 3)}${ps.length ? `<br>${d.single_days}-day only: error ${fix(ps[i].rmse)} pts` : ""}`,
  });
  const flat = pr.filter((p) => p.rmse <= b.rmse * 1.05);
  const pick = (a, k) => [Math.min(...a.map((p) => p[k])), Math.max(...a.map((p) => p[k]))];
  const [klo, khi] = pick(flat, "fixed");
  const [xlo, xhi] = pick(flat, "xi");
  const items = [
    `With ${d.smiles.length} expiries and ${d.quotes} quotes, Heston fits the market to within <b>${fix(b.rmse, 2)} volatility points</b> on average, and all 24 random starts found the same best fit.`,
    `But the minimum is a long, flat valley. Any kappa from ${klo} to ${khi} fits within 5% of the best error, as long as xi moves with it (from ${fix(xlo)} to ${fix(xhi)}). The data pins down the <i>combination</i>, not each number.`,
  ];
  if (ps.length) {
    const [a, z] = pick(ps, "rmse");
    items.push(`With only the ${d.single_days}-day expiry it gets much worse: every kappa from ${ps[0].fixed} to ${ps[ps.length - 1].fixed} fits about equally (error ${fix(a)}–${fix(z)} pts), and theta runs into its limits. One expiry can't tell how fast volatility returns to normal.`);
  }
  const err = d.smiles.map((s) => {
    const e = s.market.map((v, i) => v - s.model[i]).filter(isFinite);
    return { s, rmse: Math.sqrt(e.reduce((a, x) => a + x * x, 0) / e.length) };
  });
  const worst = err.reduce((a, b2) => (b2.rmse > a.rmse ? b2 : a));
  items.push(`The worst fit is the shortest expiry (${worst.s.days} days, ${fix(worst.rmse, 2)} pts): far out-of-the-money puts cost more than Heston can produce. Short-dated crash fear is a known weak spot; models with price jumps (like Bates) handle it better.`);
  items.push(
    b.feller
      ? "The Feller condition holds, so variance stays positive."
      : `The best fit <b>breaks the Feller condition</b> (2κθ = ${fix(2 * b.kappa * b.theta, 3)} &lt; ξ² = ${fix(b.xi ** 2, 3)}), so variance can touch zero. Fits to real SPY chains usually do: the market's steep short-dated smile needs a large xi.`,
  );
  takeaways($("#hsTake"), items);
}


/* ---------- additions: factor ladder, BIC, path fan, 3D surfaces ---------- */
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const CAT = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6"];

function ladderChart(d) {
  const host = $("#ffLadder");
  host.innerHTML = "";
  const funds = d.funds.filter((f) => f.ladder.length);
  const models = funds[0].ladder.map((x) => x.model);
  const W = width(host);
  const H = 320;
  const m = { t: 14, r: W < 520 ? 56 : 80, b: 30, l: 48 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Alpha as factors are added" }, host);
  const vals = funds.flatMap((f) => f.ladder.map((x) => x.alpha));
  const lo = Math.min(0, ...vals) - 0.01;
  const hi = Math.max(...vals) + 0.01;
  const X = (i) => m.l + (i / (models.length - 1)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - lo) / (hi - lo)) * (H - m.t - m.b);
  const ax = el("g", { class: "axis" }, svg);
  for (const v of niceTicks(lo, hi, 5)) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: "gridline" }, ax);
    el("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, ax).textContent = `${Math.round(v * 100)}%`;
  }
  el("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), class: "baseline" }, svg);
  models.forEach((name, i) => {
    el("text", { x: X(i), y: H - 8, "text-anchor": i === 0 ? "start" : i === models.length - 1 ? "end" : "middle" }, ax).textContent = W < 520 ? name.replace("FF5 + momentum", "+Mom") : name;
  });
  // Spread end labels so they don't collide.
  const ends = funds.map((f, k) => ({ k, y: Y(f.ladder[f.ladder.length - 1].alpha) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 13);
  const labelY = Object.fromEntries(ends.map((e) => [e.k, e.y]));
  funds.forEach((f, k) => {
    const color = `var(${CAT[k % CAT.length]})`;
    el("path", { d: f.ladder.map((x, i) => `${i ? "L" : "M"}${X(i)},${Y(x.alpha)}`).join(""), class: "series", stroke: color }, svg);
    f.ladder.forEach((x, i) => {
      const sig = Math.abs(x.t) > 2;
      const c = el("circle", { cx: X(i), cy: Y(x.alpha), r: 5, fill: sig ? color : "var(--surface)", stroke: color, class: "dot-sig" }, svg);
      const hit = el("circle", { cx: X(i), cy: Y(x.alpha), r: 12, class: "hit" }, svg);
      hit.addEventListener("mousemove", (e) => showTip(e, `<b>${esc(f.ticker)}</b> · ${esc(x.model)}<br>Alpha ${signed(x.alpha)} a year<br>t = ${fix(x.t)} ${sig ? "(significant)" : "(could be luck)"}<br>R² ${fix(x.r2)}`));
      hit.addEventListener("mouseleave", hideTip);
      void c;
    });
    el("text", { x: X(models.length - 1) + 8, y: labelY[k] + 4, class: "label" }, svg).textContent = f.ticker;
  });
  table(
    $("#ffLadderTable"),
    ["Fund", ...models.map((x) => `${x} α (t)`), "Momentum loading"],
    funds.map((f) => [`<b>${f.ticker}</b>`, ...f.ladder.map((x) => `${signed(x.alpha)} (${fix(x.t)})`), fix(f.ladder[f.ladder.length - 1].loadings.Mom)]),
    [1, 2, 3, 4, 5],
  );
}

function bicChart(d) {
  const host = $("#rgBic");
  host.innerHTML = "";
  const rows = d.bic;
  const W = width(host);
  const row = 40;
  const m = { t: 6, r: 120, b: 24, l: 70 };
  const H = m.t + m.b + rows.length * row;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "BIC by number of states" }, host);
  const max = Math.max(...rows.map((r) => r.delta));
  const X = (v) => m.l + (v / max) * (W - m.l - m.r);
  rows.forEach((r, i) => {
    const y = m.t + i * row;
    el("text", { x: m.l - 10, y: y + 22, "text-anchor": "end", class: "label", "font-weight": 600 }, svg).textContent = `${r.states} state${r.states > 1 ? "s" : ""}`;
    el("rect", { x: m.l, y: y + 8, width: Math.max(3, X(r.delta) - m.l), height: 20, rx: 4, fill: r.delta === 0 ? "var(--s1)" : "var(--s3)" }, svg);
    el("text", { x: Math.max(m.l + 3, X(r.delta)) + 6, y: y + 22, class: "label" }, svg).textContent = r.delta === 0 ? "best" : `+${Math.round(r.delta).toLocaleString()}`;
    const hit = el("rect", { x: 0, y, width: W, height: row, class: "hit" }, svg);
    hit.addEventListener("mousemove", (e) => showTip(e, `<b>${r.states} state${r.states > 1 ? "s" : ""}</b><br>BIC ${Math.round(r.bic).toLocaleString()} (+${Math.round(r.delta).toLocaleString()} vs best)<br>${r.params} parameters<br>Volatilities: ${r.vols.map((v) => pct(v, 0)).join(", ")}`));
    hit.addEventListener("mouseleave", hideTip);
  });
  el("line", { x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, class: "baseline" }, svg);
  table($("#rgBicTable"), ["States", "Log-likelihood", "Parameters", "BIC", "Behind best", "Volatility of each state"],
    rows.map((r) => [r.states, Math.round(r.loglik).toLocaleString(), r.params, Math.round(r.bic).toLocaleString(), Math.round(r.delta).toLocaleString(), r.vols.map((v) => pct(v, 0)).join(", ")]), [1, 2, 3, 4]);
}

function fanChart(d) {
  const host = $("#lsFan");
  host.innerHTML = "";
  const f = d.fan;
  const sf = d.surface;
  const W = width(host);
  const H = 320;
  const m = { t: 12, r: W < 520 ? 16 : 120, b: 28, l: 48 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Simulated paths and exercise points" }, host);
  const all = f.paths.flat();
  const lo = Math.min(...all) - 1;
  const hi = Math.max(...all) + 1;
  const X = (t) => m.l + t * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - lo) / (hi - lo)) * (H - m.t - m.b);
  const ax = el("g", { class: "axis" }, svg);
  for (const v of niceTicks(lo, hi, 5)) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: "gridline" }, ax);
    el("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, ax).textContent = `$${v}`;
  }
  [0, 0.25, 0.5, 0.75, 1].forEach((t) => (el("text", { x: X(t), y: H - 8, "text-anchor": "middle" }, ax).textContent = `${Math.round(t * 12)}m`));
  el("line", { x1: m.l, x2: W - m.r, y1: Y(40), y2: Y(40), class: "baseline", "stroke-dasharray": "5 4" }, svg);
  let exercised = 0;
  f.paths.forEach((p, k) => {
    const stop = f.stop[k];
    const end = stop >= 0 ? stop : p.length - 1;
    const d2 = p.slice(0, end + 1).map((v, i) => `${i ? "L" : "M"}${X(f.t[i]).toFixed(1)},${Y(v).toFixed(1)}`).join("");
    el("path", { d: d2, fill: "none", stroke: "var(--ink-3)", "stroke-opacity": 0.45, "stroke-width": 1 }, svg);
    if (stop >= 0) {
      if (stop < p.length - 1) exercised++;
      const dot = el("circle", { cx: X(f.t[stop]), cy: Y(p[stop]), r: 3.5, fill: stop < p.length - 1 ? "var(--s2)" : "var(--surface)", stroke: "var(--s2)", "stroke-width": 1.5 }, svg);
      void dot;
    }
  });
  const bd = sf.t.map((t, i) => `${i ? "L" : "M"}${X(t).toFixed(1)},${Y(sf.boundary[i]).toFixed(1)}`).join("");
  el("path", { d: bd, class: "series", stroke: "var(--s1)", "stroke-width": 2.5 }, svg);
  if (m.r > 20) {
    el("text", { x: X(1) + 6, y: Y(40) + 4, class: "label" }, svg).textContent = "Strike $40";
    el("text", { x: X(sf.t[sf.t.length - 3]) + 6, y: Y(sf.boundary[sf.boundary.length - 3]) + 18, class: "label" }, svg).textContent = "Exercise boundary";
  }
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, class: "hit" }, svg);
  hit.addEventListener("mousemove", (e) => {
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    const t = Math.min(1, Math.max(0, (p.x - m.l) / (W - m.l - m.r)));
    const i = Math.round(t * (sf.t.length - 1));
    showTip(e, `<b>${(sf.t[i] * 12).toFixed(1)} months in</b><br>Exercise if the stock is below <b>$${fix(sf.boundary[i])}</b><br>${exercised} of ${f.paths.length} paths shown exercise early (orange dots)`);
  });
  hit.addEventListener("mouseleave", hideTip);
}

function mix(a, b, t) {
  const hex = (c) => c.replace("#", "").match(/../g).map((x) => parseInt(x, 16));
  try {
    const [x, y] = [hex(a), hex(b)];
    return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(",")})`;
  } catch {
    return b;
  }
}

function plotTheme() {
  const ink = css("--ink-2");
  const grid = css("--line");
  const axis = (title) => ({ title: { text: title, font: { size: 12, color: ink } }, gridcolor: grid, zerolinecolor: grid, color: ink, backgroundcolor: "rgba(0,0,0,0)", showspikes: false });
  return { axis, font: { family: "system-ui, -apple-system, Segoe UI, sans-serif", color: ink, size: 11 } };
}

function surfaces(ls, hs) {
  if (!window.Plotly) {
    for (const id of ["lsSurface", "hsSurface"]) $("#" + id).innerHTML = '<p class="hint">The 3D view needs Plotly, which did not load.</p>';
    return;
  }
  const { axis, font } = plotTheme();
  const narrow = innerWidth < 600;
  const cfg = { responsive: true, displaylogo: false, displayModeBar: !narrow, modeBarButtonsToRemove: ["toImage", "resetCameraLastSave3d"] };
  const k = narrow ? 1.6 : 1;
  const eye = (x, y, z) => ({ x: x * k, y: y * k, z: z * k });
  const blue = css("--s1");
  const orange = css("--s2");
  const surfaceScale = [[0, mix(css("--surface"), blue, 0.2)], [1, blue]];

  const s = ls.surface;
  const ridgeV = s.t.map((t, i) => Math.max(0, 40 - s.boundary[i]));
  Plotly.react(
    "lsSurface",
    [
      { type: "surface", x: s.s, y: s.t.map((t) => t * 12), z: s.v, colorscale: [[0, css("--c6") ? mix(css("--surface"), orange, 0.15) : css("--bg")], [1, orange]], opacity: 0.95, showscale: false,
        contours: { z: { show: true, usecolormap: false, color: css("--line"), width: 1, start: 0, end: 16, size: 2 } },
        hovertemplate: "Stock $%{x:.0f}<br>%{y:.1f} months in<br>Put worth $%{z:.2f}<extra></extra>" },
      { type: "scatter3d", mode: "lines", x: s.boundary, y: s.t.map((t) => t * 12), z: ridgeV, line: { color: blue, width: 7 }, name: "Exercise boundary",
        hovertemplate: "Boundary $%{x:.2f}<br>%{y:.1f} months in<extra>exercise below this</extra>" },
    ],
    { margin: { l: 0, r: 0, t: 0, b: 0 }, paper_bgcolor: "rgba(0,0,0,0)", font, showlegend: false,
      scene: { xaxis: axis("Stock price ($)"), yaxis: axis("Months in"), zaxis: axis("Put value ($)"), camera: { eye: eye(-1.25, -1.2, 0.62), center: { x: 0, y: 0, z: -0.12 } }, aspectmode: "manual", aspectratio: { x: 1.2, y: 1, z: 0.7 } } },
    cfg,
  );

  const hsurf = hs.surface;
  const mx = [], my = [], mz = [], txt = [];
  for (const sm of hs.smiles) sm.moneyness.forEach((m, i) => { mx.push(m); my.push(sm.days); mz.push(sm.market[i]); txt.push(`Strike $${sm.strike[i]}`); });
  Plotly.react(
    "hsSurface",
    [
      { type: "surface", x: hsurf.moneyness, y: hsurf.days, z: hsurf.iv, colorscale: surfaceScale, opacity: 0.85, showscale: false, name: "Heston",
        hovertemplate: "Heston<br>%{x:.2f} × forward<br>%{y:.0f} days<br>Implied vol %{z:.1f}%<extra></extra>" },
      { type: "scatter3d", mode: "markers", x: mx, y: my, z: mz, text: txt, marker: { size: 2.6, color: orange, line: { width: 0 } }, name: "Market",
        hovertemplate: "Market · %{text}<br>%{x:.2f} × forward<br>%{y} days<br>Implied vol %{z:.1f}%<extra></extra>" },
    ],
    { margin: { l: 0, r: 0, t: 0, b: 0 }, paper_bgcolor: "rgba(0,0,0,0)", font, showlegend: false,
      scene: { xaxis: axis("Strike ÷ forward"), yaxis: axis("Days to expiry"), zaxis: axis("Implied vol (%)"), camera: { eye: eye(1.2, -1.3, 0.55), center: { x: 0, y: 0, z: -0.12 } }, aspectmode: "manual", aspectratio: { x: 1.2, y: 1.2, z: 0.7 } } },
    cfg,
  );
}

async function main() {
  const get = (n) => fetch(`data/${n}.json`).then((r) => r.json());
  const [ff, rg, ls, hs] = await Promise.all(["famafrench", "regimes", "lsm", "heston"].map(get));
  const render = () => {
    famaFrench(ff);
    ladderChart(ff);
    regimes(rg);
    bicChart(rg);
    lsmChapter(ls);
    fanChart(ls);
    hestonChapter(hs);
  };
  render();
  surfaces(ls, hs);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => surfaces(ls, hs));
  let last = innerWidth;
  let timer;
  addEventListener("resize", () => {
    if (innerWidth === last) return;
    last = innerWidth;
    clearTimeout(timer);
    timer = setTimeout(render, 150);
  });
}
main();

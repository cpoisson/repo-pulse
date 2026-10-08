/* repo-pulse deck renderer: data.json -> slides. No dependencies; charts are inline SVG. */
(function () {
  const D = JSON.parse(document.getElementById("data").textContent);
  const M = D.metrics, K = M.kpis, C = M.charts, X = M.context, N = D.narrative || {}, B = D.classifier || {};
  const deck = document.getElementById("deck");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------- formatting
  function fmt(v, unit) {
    if (v === null || v === undefined) return "—";
    if (unit === "ratio") return (v > 0 && v < 0.1 ? (v * 100).toFixed(1) : Math.round(v * 100)) + "%";
    if (unit === "days") return v < 1 ? (v * 24).toFixed(v * 24 < 10 ? 1 : 0) + " h" : (v < 10 ? v.toFixed(1) : Math.round(v)) + " d";
    if (unit === "min") return v.toFixed(1) + " min";
    if (typeof v === "number") return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : (Number.isInteger(v) ? String(v) : v.toFixed(2));
    return String(v);
  }
  function deltaHtml(m) {
    if (m.prior === null || m.prior === undefined || typeof m.value !== "number") return "";
    const d = m.value - m.prior;
    if (Math.abs(d) < 1e-9) return `<span class="delta flat">= prior</span>`;
    const dir = m.direction || (m.lower_is_better ? "down" : "up");
    const better = dir === "down" ? d < 0 : d > 0;
    const cls = dir === "neutral" ? "flat" : better ? "good" : "bad";
    const arrow = d > 0 ? "▲" : "▼";
    let txt;
    if (m.unit === "ratio") txt = (d > 0 ? "+" : "−") + Math.abs(Math.round(d * 100)) + " pts";
    else if (m.prior > 0 && m.value > 0 && m.value / m.prior >= 3) txt = "×" + (m.value / m.prior).toFixed(1);
    else if (m.prior <= 0 || m.value < 0) txt = (d > 0 ? "+" : "−") + fmt(Math.abs(d), m.unit);  // % change is meaningless across zero
    else if (m.prior !== 0 && Math.abs(m.prior) >= 1) txt = (d > 0 ? "+" : "−") + Math.abs(Math.round((d / Math.abs(m.prior)) * 100)) + "%";
    else txt = (d > 0 ? "+" : "−") + fmt(Math.abs(d), m.unit);
    const title = dir === "neutral" ? "change vs prior window (neither good nor bad by itself)" : (better ? "improving" : "worsening") + " vs prior window";
    return `<span class="delta ${cls}" title="${title}">${arrow} ${txt}</span>`;
  }
  const STATUS = { green: "on track", amber: "watch", red: "at risk", na: "" };
  const chip = (s) => (s && s !== "na" ? `<span class="chip ${s}"><i></i>${STATUS[s]}</span>` : "");
  function tile(key, opts = {}) {
    const m = K[key];
    if (!m) return "";
    const prior = m.prior !== null && m.prior !== undefined ? `<span>prior ${fmt(m.prior, m.unit)}</span>` : "";
    const unitSuffix = m.unit && !["ratio", "days", "min"].includes(m.unit) ? ` <span class="small muted">${esc(m.unit)}</span>` : "";
    return `<div class="card tile" title="${esc(m.note || "")}"><div class="lbl">${esc(opts.label || m.label)}${m.note && opts.note !== true ? ' <span class="info" aria-hidden="true">ⓘ</span>' : ""}</div>
      <div class="val">${fmt(m.value, m.unit)}${unitSuffix}</div><div class="sub">${deltaHtml(m)}${prior}${chip(m.status)}</div>
      ${m.note && opts.note === true ? `<div class="small muted" style="margin-top:4px">${esc(m.note)}</div>` : ""}</div>`;
  }
  const cite = (keys) => (keys && keys.length ? `<div class="cite">${keys.map(esc).join(" · ")}</div>` : "");

  // ---------- tooltip
  const tip = document.getElementById("tip");
  document.addEventListener("pointermove", (e) => {
    const t = e.target.closest && e.target.closest("[data-tip]");
    if (!t) { tip.style.opacity = 0; return; }
    tip.innerHTML = t.getAttribute("data-tip");
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    const y = Math.min(e.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
    tip.style.left = x + "px"; tip.style.top = y + "px"; tip.style.opacity = 1;
  });

  // ---------- charts
  const niceMax = (v) => { if (v <= 0) return 1; if (v <= 1) return 1; const raw = v / 4; const p = Math.pow(10, Math.floor(Math.log10(raw))); const n = raw / p; const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; return Math.max(step, raw >= 1 ? Math.ceil(step) : step) * 4; };
  const shortDate = (s) => { const d = new Date(s + "T00:00:00Z"); return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }); };

  /** Weekly series line chart; shades the current window. series: [{name, color, points:[[date, v]]}] */
  const tickFmt = (v) => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : Number.isInteger(v) ? String(v) : v.toFixed(1));
  function lineChart(series, { h = 220, W = 640, yFmt = tickFmt, unit = "", windowStart = M.windows.cur[0], yMax = null } = {}) {
    const pad = { l: 40, r: 12, t: 10, b: 24 };
    const xs = series[0].points.map((p) => p[0]);
    const vals = series.flatMap((s) => s.points.map((p) => p[1]).filter((v) => v !== null));
    const max = yMax ?? niceMax(Math.max(...vals, 0));
    const x = (i) => pad.l + (i / Math.max(xs.length - 1, 1)) * (W - pad.l - pad.r);
    const y = (v) => h - pad.b - (v / max) * (h - pad.t - pad.b);
    const wi = xs.findIndex((d) => d >= windowStart);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img">`;
    if (wi >= 0) s += `<rect class="band" x="${x(wi)}" y="${pad.t}" width="${W - pad.r - x(wi)}" height="${h - pad.t - pad.b}"/>` +
      `<text x="${x(wi) + 4}" y="${pad.t + 11}">current window</text>`;
    for (let k = 0; k <= 4; k++) { const v = (max / 4) * k; s += `<line class="gridline" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${pad.l - 6}" y="${y(v) + 4}" text-anchor="end">${yFmt(v)}</text>`; }
    s += `<line class="baseline" x1="${pad.l}" x2="${W - pad.r}" y1="${y(0)}" y2="${y(0)}"/>`;
    const step = Math.ceil(xs.length / 6);
    xs.forEach((d, i) => { if (i % step === 0) s += `<text x="${x(i)}" y="${h - 6}" text-anchor="middle">${shortDate(d)}</text>`; });
    series.forEach((se) => {
      let dpath = "", pen = false;
      se.points.forEach((p, i) => { if (p[1] === null) { pen = false; return; } dpath += (pen ? "L" : "M") + x(i).toFixed(1) + "," + y(p[1]).toFixed(1); pen = true; });
      s += `<path d="${dpath}" fill="none" stroke="${se.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      const last = se.points.length - 1;
      if (se.points[last][1] !== null) s += `<circle cx="${x(last)}" cy="${y(se.points[last][1])}" r="4" fill="${se.color}" stroke="var(--surface)" stroke-width="2"/>`;
    });
    // hover columns
    xs.forEach((d, i) => {
      const w = (W - pad.l - pad.r) / Math.max(xs.length - 1, 1);
      const tipTxt = `<b>week of ${shortDate(d)}</b><br>` + series.map((se) => `<span style="color:${se.color}">●</span> ${esc(se.name)}: ${se.points[i][1] === null ? "—" : yFmt(se.points[i][1])}${unit}`).join("<br>");
      s += `<rect class="hit" x="${x(i) - w / 2}" y="${pad.t}" width="${w}" height="${h - pad.t - pad.b}" data-tip="${esc(tipTxt)}"/>`;
    });
    return s + "</svg>";
  }
  function legend(items) { return `<div class="legend">${items.map(([n, c]) => `<span><i style="background:${c}"></i>${esc(n)}</span>`).join("")}</div>`; }

  /** Vertical bars for a weekly series (single measure). */
  function weeklyBars(points, { h = 200, W = 640, color = "var(--s1)", name = "", windowStart = M.windows.cur[0] } = {}) {
    const pad = { l: 44, r: 8, t: 10, b: 24 };
    const vals = points.map((p) => p[1] ?? 0);
    const max = niceMax(Math.max(...vals, 0));
    const bw = (W - pad.l - pad.r) / points.length;
    const y = (v) => h - pad.b - (v / max) * (h - pad.t - pad.b);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img">`;
    const wi = points.findIndex((p) => p[0] >= windowStart);
    if (wi >= 0) s += `<rect class="band" x="${pad.l + wi * bw}" y="${pad.t}" width="${W - pad.r - pad.l - wi * bw}" height="${h - pad.t - pad.b}"/>`;
    for (let k = 0; k <= 4; k++) { const v = (max / 4) * k; s += `<line class="gridline" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${pad.l - 6}" y="${y(v) + 4}" text-anchor="end">${tickFmt(v)}</text>`; }
    const step = Math.ceil(points.length / 6);
    points.forEach((p, i) => {
      const x0 = pad.l + i * bw + 1, w = Math.max(bw - 2, 1);
      if (p[1] !== null && p[1] > 0) {
        const top = y(p[1]), r = Math.min(4, w / 2, (y(0) - top));
        s += `<path class="mark" fill="${color}" d="M${x0},${y(0)} V${top + r} q0,-${r} ${r},-${r} H${x0 + w - r} q${r},0 ${r},${r} V${y(0)} Z"/>`;
      }
      s += `<rect class="hit" x="${x0}" y="${pad.t}" width="${w}" height="${h - pad.t - pad.b}" data-tip="${esc(`<b>week of ${shortDate(p[0])}</b><br>${name}: ${p[1] === null ? "—" : fmt(p[1])}`)}"/>`;
      if (i % step === 0) s += `<text x="${x0 + w / 2}" y="${h - 6}" text-anchor="middle">${shortDate(p[0])}</text>`;
    });
    s += `<line class="baseline" x1="${pad.l}" x2="${W - pad.r}" y1="${y(0)}" y2="${y(0)}"/>`;
    return s + "</svg>";
  }

  /** Horizontal bars. rows: [{label, value, prior?, lo?, hi?, color?, tip?, note?}] */
  const EMPTY = (msg = "Nothing in this window.") => `<div class="empty">${esc(msg)}</div>`;
  function hbars(rows, { labelW = 150, valFmt = (v) => fmt(v), max = null, priorName = "prior window", rowH = 26, W = 640, empty } = {}) {
    if (!rows.length || rows.every((r) => !r.value && !r.prior)) return EMPTY(empty);
    const pad = { t: 4, b: 4, r: 56 };
    const h = pad.t + pad.b + rows.length * rowH;
    const mx = max ?? niceMax(Math.max(...rows.map((r) => Math.max(r.value ?? 0, r.hi ?? 0, r.prior ?? 0)), 0.0001));
    const x = (v) => labelW + (v / mx) * (W - labelW - pad.r);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img">`;
    rows.forEach((r, i) => {
      const yc = pad.t + i * rowH + rowH / 2, bh = 14;
      s += `<text class="lab" x="${labelW - 8}" y="${yc + 4}" text-anchor="end">${esc(r.label)}</text>`;
      const w = Math.max(x(r.value ?? 0) - labelW, 0);
      if (w > 0) { const rr = Math.min(4, w); s += `<path class="mark" fill="${r.color || "var(--s1)"}" d="M${labelW},${yc - bh / 2} H${labelW + w - rr} q${rr},0 ${rr},${rr} V${yc + bh / 2 - rr} q0,${rr} -${rr},${rr} H${labelW} Z"/>`; }
      if (r.lo !== undefined && r.lo !== null && r.hi !== null) s += `<line x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${yc}" y2="${yc}" stroke="var(--ink-2)" stroke-width="1.5"/><line x1="${x(r.lo)}" x2="${x(r.lo)}" y1="${yc - 4}" y2="${yc + 4}" stroke="var(--ink-2)" stroke-width="1.5"/><line x1="${x(r.hi)}" x2="${x(r.hi)}" y1="${yc - 4}" y2="${yc + 4}" stroke="var(--ink-2)" stroke-width="1.5"/>`;
      if (r.prior !== undefined && r.prior !== null) s += `<line x1="${x(r.prior)}" x2="${x(r.prior)}" y1="${yc - 9}" y2="${yc + 9}" stroke="var(--ink)" stroke-width="2" stroke-linecap="round"/>`;
      s += `<text class="val" x="${Math.max(x(r.value ?? 0), x(r.hi ?? 0)) + 6}" y="${yc + 4}">${valFmt(r.value)}${r.note ? ` <tspan class="muted" style="fill:var(--muted);font-weight:400">${esc(r.note)}</tspan>` : ""}</text>`;
      const tipTxt = r.tip || `<b>${esc(r.label)}</b><br>${valFmt(r.value)}${r.prior !== undefined && r.prior !== null ? `<br>${priorName}: ${valFmt(r.prior)}` : ""}${r.lo !== undefined && r.lo !== null ? `<br>90% interval: ${valFmt(r.lo)}–${valFmt(r.hi)}` : ""}`;
      s += `<rect class="hit" x="0" y="${yc - rowH / 2}" width="${W}" height="${rowH}" data-tip="${esc(tipTxt)}"/>`;
    });
    s += `<line class="baseline" x1="${labelW}" x2="${labelW}" y1="0" y2="${h}"/>`;
    return s + "</svg>";
  }

  // Horizontal bars split into stacked parts: rows [{label, parts: [[name, value, color]], tip}].
  function stackbars(rows, { labelW = 130, rowH = 30, W = 420, valFmt = (v) => fmt(v), empty } = {}) {
    const tot = (r) => r.parts.reduce((a, [, v]) => a + v, 0);
    if (!rows.length || rows.every((r) => !tot(r))) return EMPTY(empty);
    const pad = { t: 4, b: 4, r: 48 }, h = pad.t + pad.b + rows.length * rowH;
    const mx = niceMax(Math.max(...rows.map(tot), 0.0001));
    const sx = (v) => (v / mx) * (W - labelW - pad.r);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img">`;
    rows.forEach((r, i) => {
      const yc = pad.t + i * rowH + rowH / 2, bh = 14;
      let x0 = labelW;
      s += `<text class="lab" x="${labelW - 8}" y="${yc + 4}" text-anchor="end">${esc(r.label)}</text>`;
      r.parts.forEach(([, v, color]) => { const w = sx(v); if (w > 0) { s += `<rect class="mark" x="${x0}" y="${yc - bh / 2}" width="${w}" height="${bh}" fill="${color}"/>`; x0 += w; } });
      s += `<text class="val" x="${x0 + 6}" y="${yc + 4}">${valFmt(tot(r))}</text>`;
      s += `<rect class="hit" x="0" y="${yc - rowH / 2}" width="${W}" height="${rowH}" data-tip="${esc(r.tip || "")}"/>`;
    });
    return s + `<line class="baseline" x1="${labelW}" x2="${labelW}" y1="0" y2="${h}"/></svg>`;
  }

  function histogram(values, edges, labels, { color = "var(--s1)", extra = null, rowH = 26, W = 640 } = {}) {
    const counts = labels.map(() => 0);
    values.forEach((v) => { for (let i = 0; i < edges.length - 1; i++) if (v >= edges[i] && v < edges[i + 1]) { counts[i]++; break; } });
    const rows = labels.map((l, i) => ({ label: l, value: counts[i], color }));
    if (extra) rows.push(extra);
    return hbars(rows, { labelW: 110, rowH, W });
  }

  // ---------- slides (each is a fixed 1280x720 canvas; content is sized to fit)
  const slides = [];
  const ns = (id) => (N.slides && N.slides[id]) || {};
  const T = (id, fallback) => ns(id).title || fallback;
  /** section: metro line name; station: short label on the map */
  const S = (id, { kicker, title, sowhat = "", metrics = [], section, station, cls = "" }, body) =>
    slides.push({ id, section, station, cls, kicker, title, sowhat, metrics, body });
  const tiles = (keys) => `<div class="tiles">${keys.filter((k) => K[k]).map((k) => tile(k)).join("")}</div>`;
  const famNames = { flow: "Community & flow", adoption: "Adoption & reach", code: "Codebase & quality", themes: "Issue themes" };
  const kpiTable = (keys) => `<table class="kpis"><thead><tr><th>Indicator</th><th class="num">Now</th><th class="num">Prior</th><th class="num">Change</th><th></th></tr></thead><tbody>${
    keys.filter((k) => K[k]).map((k) => { const m = K[k];
      return `<tr title="${esc(m.note)}"><td>${esc(m.label)}</td><td class="num"><b>${fmt(m.value, m.unit)}</b></td><td class="num muted">${m.prior !== null && m.prior !== undefined ? fmt(m.prior, m.unit) : ""}</td><td class="num">${deltaHtml(m)}</td><td>${chip(m.status)}</td></tr>`; }).join("")}</tbody></table>`;
  const plan = (N.recommendations || []).slice().sort((a, b) => (a.priority || 99) - (b.priority || 99));

  // 1 title
  S("title", { cls: "title-slide" },
    `<div class="title-wrap"><div class="kicker">${esc(M.repo)} · project pulse · edition ${esc(M.as_of)}</div>
     <h1 class="hero">${esc(N.headline || "Project health: last " + M.window_days + " days vs the " + M.window_days + " before")}</h1>
     <div class="title-strip">${(D.headline_kpis || []).filter((k) => K[k]).map((k) => `<div><b>${fmt(K[k].value, K[k].unit)}</b><span>${esc(K[k].label)}</span>${deltaHtml(K[k])}</div>`).join("")}</div>
     <p class="title-meta">Current window ${esc(M.windows.cur[0])} → ${esc(M.windows.cur[1])} vs prior ${esc(M.windows.prior[0])} → ${esc(M.windows.prior[1])}.
     Numbers are computed from ${[M.forge || "GitHub", "git", ...(X.adoption.distribution_sources || (K.pypi_downloads ? ["PyPI"] : [])), K.hf_spaces_new ? "the HF Hub" : ""].filter(Boolean).join(", ")}; every narrative claim is checked against them.</p>
     ${D.note ? `<p class="title-meta"><b>${esc(D.note)}</b></p>` : ""}
     <p class="title-meta muted">Press → to start · O for overview · narrative: ${esc(N.source || "none")}</p></div>`);

  // 2 executive summary
  S("summary", { kicker: "Executive summary", title: N.summary_title || "What maintainers need to know", section: "Overview", station: "Summary" },
    `${tiles(D.headline_kpis || [])}
     <div class="cols2 grow"><div class="card"><h3>Key findings</h3>${(N.findings || []).slice(0, 3).map((f) =>
      `<div class="finding"><span class="sev ${esc(f.severity || "medium")}">${esc(f.severity || "")}</span><div>${esc(f.text)}${cite(f.metrics)}</div></div>`).join("") || '<p class="muted">No findings.</p>'}</div>
     <div class="card"><h3>Improvement plan: top priorities</h3>${plan.slice(0, 3).map((r) =>
      `<div class="finding"><span class="prio">P${r.priority || ""}</span><div><b>${esc(r.text)}</b><div class="small muted">${esc(r.outcome || r.why || "")}</div><div class="small muted">${esc(r.horizon || "")} · effort ${esc(r.effort || "?")} · ${esc(r.owner || "")}</div></div></div>`).join("")}</div></div>`);

  // 3-5 scorecards
  const SC = Array.isArray(D.scorecard) ? D.scorecard : Object.entries(M.families).map(([id, ks]) => ({ id, title: famNames[id] || id, tables: { [famNames[id] || id]: ks } }));
  const moveOf = (m) => {
    if (m.prior === null || m.prior === undefined || typeof m.value !== "number" || m.direction === "neutral" || m.value === m.prior) return "flat";
    return (m.direction === "down" ? m.value < m.prior : m.value > m.prior) ? "up" : "down";
  };
  const scShort = { flow: "Flow", adoption: "Reach", code: "Code" };
  SC.forEach((sc, i) => {
    const keys = Object.values(sc.tables).flat().filter((k) => K[k]);
    if (!keys.length) return;
    const better = keys.filter((k) => moveOf(K[k]) === "up").length, worse = keys.filter((k) => moveOf(K[k]) === "down").length;
    const risk = keys.filter((k) => K[k].status === "red").length, watch = keys.filter((k) => K[k].status === "amber").length;
    const nut = (N.nutshells || {})[sc.id] || {};
    const counters = `<div class="counters"><span class="delta good">▲ ${better} improving</span><span class="delta bad">▼ ${worse} worsening</span>${risk ? `<span class="chip red"><i></i>${risk} at risk</span>` : ""}${watch ? `<span class="chip amber"><i></i>${watch} to watch</span>` : ""}<span class="muted small">${keys.length} indicators</span></div>`;
    S(`scorecard-${sc.id}`, { kicker: `Scorecard ${i + 1}/${SC.length}`, title: sc.title, section: "Scorecard", station: scShort[sc.id] || sc.title },
      `<div class="card nutshell"><div class="kicker">In a nutshell</div><p class="nut">${esc(nut.text || "")}</p>${cite(nut.metrics)}${counters}</div>
       <div class="cols2">${Object.entries(sc.tables).map(([t, ks]) => `<div class="card"><h3>${esc(t)}</h3>${kpiTable(ks)}</div>`).join("")}</div>`);
  });

  // 6 flow
  const issueSeries = [{ name: "opened", color: "var(--s2)", points: C.issue_flow.opened }, { name: "closed", color: "var(--s1)", points: C.issue_flow.closed }];
  const prSeries = [{ name: "opened", color: "var(--s2)", points: C.pr_flow.opened }, { name: "merged", color: "var(--s1)", points: C.pr_flow.merged }];
  S("flow", { kicker: "Deep dive · community & flow", title: T("flow", "Issue and PR flow"), sowhat: ns("flow").so_what, metrics: ns("flow").metrics, section: "Deep dives", station: "Flow" },
    `${tiles(["issues_opened", "issues_closed", "issue_backlog_net", "open_issues_over_90d", "prs_merged"])}
     <div class="cols3 grow"><div class="card"><h3>Issues per week</h3>${legend([["opened", "var(--s2)"], ["closed", "var(--s1)"]])}${lineChart(issueSeries, { W: 420, h: 300 })}</div>
     <div class="card"><h3>Pull requests per week (humans)</h3>${legend([["opened", "var(--s2)"], ["merged", "var(--s1)"]])}${lineChart(prSeries, { W: 420, h: 300 })}</div>
     <div class="card"><h3>Open issues by age (${K.open_issues.value} open)</h3>${hbars(Object.entries(C.backlog_age).map(([k, v]) => ({ label: k, value: v, color: k === ">90d" ? "var(--s2)" : "var(--s1)" })), { labelW: 70, W: 420, rowH: 46 })}
       <p class="small muted">Complete weeks only; shaded = current window.</p></div></div>`);

  // 7 responsiveness
  const unans = K.unanswered_open_issues.value;
  S("responsiveness", { kicker: "Deep dive · community & flow", title: T("responsiveness", "How fast maintainers respond and merge"), sowhat: ns("responsiveness").so_what, metrics: ns("responsiveness").metrics, section: "Deep dives", station: "Response" },
    `${tiles(["response_within_7d", "median_first_response_days", "median_pr_first_response_days", "median_time_to_merge_external_days"])}
     <div class="cols3 grow"><div class="card"><h3>First maintainer reply, community issues this window</h3>
       ${histogram(C.resp_dist, [0, 1, 3, 7, 30, 1e9], ["< 1 day", "1–3 days", "3–7 days", "7–30 days", "> 30 days"], { rowH: 40, W: 420, extra: { label: "no reply yet", value: unans, color: "var(--s2)", tip: `<b>${unans} open issues</b> have no maintainer reply at all` } })}</div>
     <div class="card"><h3>Time to merge, PRs merged this window</h3>${histogram(C.ttm_dist, [0, 1 / 24, 1, 3, 7, 1e9], ["< 1 hour", "1 h – 1 day", "1–3 days", "3–7 days", "> 7 days"], { rowH: 46, W: 420 })}</div>
     <div class="card"><h3>Latest issues with no maintainer reply</h3><table class="compact"><tbody>${(X.flow.unanswered_open_issues || []).slice(0, 6).map(([n, t]) => `<tr><td class="num">#${n}</td><td class="clamp">${esc(t)}</td></tr>`).join("")}</tbody></table></div></div>`);

  // 8 contributors
  const WORK_KINDS = [["code", "var(--s1)"], ["tests", "var(--s3)"], ["docs", "var(--s2)"], ["build", "var(--s4)"]];
  const pctFmt = (v) => `${Math.round(v * 100)}%`;
  const FUNC_KINDS = ["feature", "fix", "change", "removal", "docs", "internal", "other"];
  const maint = new Set(X.flow.maintainers);
  // PR type: from the changelog fragment of a merged PR, or from the files it touches (see metrics/code.py pr_type)
  function prTypeChart() {
    const T = C.pr_types || {}, logged = Object.values(T).some((t) => t.feature || t.fix || t.change || t.internal);
    const kinds = [["feature", "feature", "var(--s3)"], ["fix", "fix", "var(--s2)"], ["change", "change", "var(--s1)"], ["internal", "internal", "var(--s4)"],
      ["untyped", "code", "var(--s1)"], ["no_code", "tests/docs/build only", "var(--ink-2)"],
      ["unlogged", "merged, no entry", "var(--muted)"], ["open", "still open", "var(--axis)"], ["closed", "closed, not merged", "var(--grid)"]]
      .filter(([k]) => Object.values(T).some((t) => t[k]));
    if (!C.pr_types) return legend([["maintainer", "var(--s1)"], ["outside contributor", "var(--s3)"]]) + hbars(C.pr_authors.slice(0, 9).map(([a, n]) => ({ label: a, value: n, color: maint.has(a) ? "var(--s1)" : "var(--s3)" })), { labelW: 150, rowH: 30, W: 780 });
    return `${legend(kinds.map(([, l, c]) => [l, c]))}<p class="small muted" style="margin:2px 0 0">◦ = outside contributor${logged ? " · type read from the changelog entry of merged PRs; open and closed ones are not typed yet" : ""}</p>
      ${stackbars(C.pr_authors.slice(0, 9).map(([a, n]) => ({ label: `${maint.has(a) ? "" : "◦ "}${a}`, parts: kinds.map(([k, , c]) => [k, (T[a] || {})[k] || 0, c]),
        tip: `<b>${esc(a)}</b> · ${n} PRs<br>${kinds.filter(([k]) => (T[a] || {})[k]).map(([k, l]) => `${l}: ${T[a][k]}`).join("<br>")}` })), { labelW: 150, rowH: 28, W: 780 })}`;
  }
  S("contributors", { kicker: "Deep dive · community & flow", title: T("contributors", "Who is contributing"), sowhat: ns("contributors").so_what, metrics: ns("contributors").metrics, section: "Deep dives", station: "People" },
    `${tiles(["pr_contributors", "new_contributors", "external_pr_share", "top_merger_share", "bus_factor"])}
     <div class="cols3 grow"><div class="card span2"><h3>PRs opened this window, by author and type</h3>${prTypeChart()}</div>
     <div class="card"><h3>Who merges</h3>${hbars((C.mergers || []).map(([a, n]) => ({ label: a || "?", value: n, color: "var(--s1)" })), { labelW: 130, rowH: 30, W: 420, empty: "No PRs merged in this window." })}
       <h3 style="margin-top:10px">Share of the team's work, by author</h3>${legend(WORK_KINDS.map(([k, c]) => [k, c]))}
       ${C.work_by_author ? stackbars(C.work_by_author.slice(0, 5).map(([a, mix, n, func]) => ({ label: a,
           parts: WORK_KINDS.map(([k, c]) => [k, mix[k] || 0, c]),
           tip: `<b>${esc(a)}</b><br>${n} commits<br>${WORK_KINDS.map(([k]) => `${k}: ${pctFmt(mix[k] || 0)}`).join(" · ")}<br><span class="muted">commits weighted by log2(1 + lines); generated files, lockfiles and changelog fragments excluded</span>${func && func._logged ? `<br>changelog: ${FUNC_KINDS.filter((f) => func[f]).map((f) => `${func[f]} ${f}`).join(" · ")}` : ""}` })), { labelW: 130, rowH: 26, W: 420, valFmt: pctFmt })
         : hbars((C.commit_authors || []).slice(0, 5).map(([a, n]) => ({ label: a, value: n, color: "var(--s1)" })), { labelW: 130, rowH: 30, W: 420 })}</div></div>`);

  // 9 adoption
  const dl = C.downloads_weekly || (C.pypi_weekly ? { name: "PyPI downloads", points: C.pypi_weekly } : null);
  const dlNote = (X.adoption.download_keys || ["pypi_downloads"]).map((k) => K[k]).find((m) => m && m.label === dl?.name)?.note || (C.pypi_weekly && !C.downloads_weekly ? K.pypi_downloads?.note : "");
  const relDl = X.adoption.release_downloads || [];
  const pct = (arr) => { const t = arr.reduce((a, [, v]) => a + v, 0) || 1; return arr.slice(0, 4).map(([k, v]) => `${esc(k)} ${Math.round((v / t) * 100)}%`).join(" · "); };
  S("adoption", { kicker: "Deep dive · adoption & reach", title: T("adoption", "Adoption"), sowhat: ns("adoption").so_what, metrics: ns("adoption").metrics, section: "Deep dives", station: "Adoption" },
    `${tiles(["stars_new", "forks_new", ...(X.adoption.download_keys || ["pypi_downloads"]).filter((k) => K[k] && K[k].value !== null).slice(0, 2), "days_since_release", "forks_active"].filter((k) => K[k]).slice(0, 5))}
     <div class="cols3 grow"><div class="card"><h3>New stars per week ${/approx/.test(K.stars_new?.note || "") ? '<span class="pill">approx.</span>' : ""}</h3>${C.stars_weekly ? weeklyBars(C.stars_weekly, { name: "new stars", W: 420, h: 290 }) : '<p class="muted">no star history</p>'}
       <p class="small muted">${esc(K.stars_new?.note || `From the ${M.forge || "GitHub"} stargazers API.`)}</p></div>
     ${dl ? `<div class="card"><h3>${esc(dl.name)} per week</h3>${weeklyBars(dl.points.filter((p) => p[0] >= M.windows.prior[0]), { name: "downloads", W: 420, h: 290 })}
       <p class="small muted">${esc(dlNote || "")}</p></div>`
       : relDl.length ? `<div class="card"><h3>Binary downloads per release (to date)</h3>${hbars(relDl.slice(0, 7).map(([tag, d, n]) => ({ label: tag, value: n, color: "var(--s1)" })), { labelW: 110, rowH: 30, W: 420 })}
       <p class="small muted">${esc(K.release_downloads?.note || "")}</p></div>`
       : `<div class="card"><h3>New forks per week</h3>${weeklyBars(C.forks_weekly, { name: "new forks", W: 420, h: 290 })}</div>`}
     <div class="card">${(C.pypi_system || []).length ? `<h3>Who downloads (this window)</h3><p class="small"><b>OS</b><br>${pct(C.pypi_system)}</p><p class="small"><b>Python</b><br>${pct(C.pypi_python_minor || [])}</p>` : ""}
       <h3>Releases</h3><p class="small">${(X.adoption.releases || []).slice(0, 4).map(([t, d]) => `${esc(t)} <span class="muted">${esc(d)}</span>`).join("<br>")}</p></div></div>`);

  // 10 code
  const tested = X.code.module_tested || {}, owner = X.code.module_top_author_share || {};
  const churnRows = (C.module_churn || []).filter((r) => !["other"].includes(r[0])).slice(0, 10).map(([m, cur, prior, commits]) => ({
    label: m, value: cur, prior, color: "var(--s1)",
    note: `${commits} commits${owner[m] > 0.8 && commits >= 3 ? " · single-owner" : ""}${m in tested && !tested[m] ? " · no tests" : ""}`,
    tip: `<b>${esc(m)}</b><br>lines changed: ${fmt(cur)} (prior ${fmt(prior)})<br>commits: ${commits}<br>top author share: ${owner[m] !== undefined ? Math.round(owner[m] * 100) + "%" : "—"}${m in tested ? `<br>matching tests: ${tested[m] ? "yes" : "no"}` : ""}` }));
  S("code", { kicker: "Deep dive · codebase", title: T("code", "Where the code is changing"), sowhat: ns("code").so_what, metrics: ns("code").metrics, section: "Deep dives", station: "Code" },
    `${tiles(["commits", "commit_authors", "code_concentration", "modules_single_owner", "test_loc_ratio"])}
     <div class="cols2 grow"><div class="card"><h3>Lines changed per module (bar = now, tick = prior)</h3>${hbars(churnRows, { labelW: 80, rowH: 33, W: 600, empty: "No commits landed in this window." })}</div>
     <div class="card"><h3>Hottest files this window</h3>${(C.hotspot_files || []).length ? "" : EMPTY("No files changed in this window.")}<table class="compact"><tbody>${(C.hotspot_files || []).slice(0, 11).map(([f, n]) => `<tr><td class="clamp mono">${esc(f)}</td><td class="num">${fmt(n)}</td></tr>`).join("")}</tbody></table></div></div>`);

  // 11 quality
  const deps = X.code.dependencies || [];
  const untested = Object.entries(X.code.backends || {}).filter(([, t]) => !t).map(([b]) => b);
  S("quality", { kicker: "Deep dive · quality & risk", title: T("quality", "CI, tests and dependency risk"), sowhat: ns("quality").so_what, metrics: ns("quality").metrics, section: "Deep dives", station: "Quality" },
    `${tiles(["ci_pass_rate_main", "ci_pass_rate_pr", "ci_median_minutes", "backends_with_tests", "critical_deps_behind"])}
     <div class="cols2 grow"><div class="card"><h3>Weekly CI pass rate (all CI runs)</h3>${(C.ci_weekly || []).length ? lineChart([{ name: "pass rate", color: "var(--s1)", points: C.ci_weekly.map(([d, r]) => [d, r]) }], { yFmt: (v) => Math.round(v * 100) + "%", yMax: 1, W: 600, h: 290 }) : EMPTY("No CI runs on record for this workflow.")}
       ${Object.keys(X.code.backends || {}).length ? `<p class="small muted">Backends without a matching test file: ${untested.map(esc).join(", ") || "none"} (file-name match, not line coverage).</p>` : ""}</div>
     <div class="card"><h3>Critical dependencies</h3><table class="compact"><thead><tr><th>Package</th><th>Pinned</th><th>Latest</th><th></th></tr></thead><tbody>${deps.map((d) =>
       `<tr><td>${esc(d.dep)}</td><td>${esc(d.pinned || (d.spec.startsWith("(") ? "—" : "range"))}</td><td>${esc(d.latest || "?")}</td><td>${d.behind ? '<span class="chip amber"><i></i>behind</span>' : ""}${d.unbounded ? ' <span class="chip red"><i></i>no upper bound</span>' : ""}</td></tr>`).join("")}</tbody></table>
       ${(X.code.known_incidents || []).map((i) => `<p class="small muted">Incident ${esc(i.date)}: ${esc(i.title)} (${(i.refs || []).map(esc).join(", ")})</p>`).join("")}</div></div>`);

  // 12 themes
  const th = X.themes || {};
  if (th.available) {
    const tc = C.theme_counts, ty = C.type_counts;
    const themeRows = tc.classes.filter((c) => tc.cur[c][0] > 0 || (tc.prior[c] || 0) > 0).sort((a, b) => tc.cur[b][0] - tc.cur[a][0]).map((c) => ({
      label: c, value: tc.cur[c][0], lo: tc.cur[c][1], hi: tc.cur[c][2], prior: tc.prior[c] || 0, color: c === "unclassified" ? "var(--axis)" : "var(--s1)" }));
    const typeRows = ty.classes.filter((c) => ty.cur[c][0] > 0).map((c) => ({ label: c, value: ty.cur[c][0], prior: ty.prior[c] || 0, color: c === "bug" ? "var(--s2)" : "var(--s1)" }));
    const pm = (th.pain_map || []).filter((r) => r.cur || r.open);
    const prov = Object.entries(th.provenance || {}).map(([k, v]) => `${v} ${k}`).join(", ");
    const gateMsg = !th.themes_ok ? `<div class="warnbox">Theme counts hidden: the issue classifier did not pass the accuracy gate (${esc((B.themes || {}).reason || "")}).</div>` :
      (!th.gold_reviewed ? `<div class="warnbox">Provisional: labels come from a one-time LLM pre-label pass (${esc(prov)}) not yet reviewed by a maintainer.</div>` : "");
    S("themes", { kicker: "Deep dive · issue themes", title: T("themes", "Where users are hurting"), sowhat: ns("themes").so_what, metrics: ns("themes").metrics, section: "Deep dives", station: "Themes" },
      `${gateMsg}${th.themes_ok ? `<div class="cols3 grow"><div class="card"><h3>New issues by theme (bar = now, tick = prior)</h3>${hbars(themeRows, { labelW: 110, rowH: 27, W: 420 })}</div>
       <div class="card span2"><h3>Pain map</h3><table class="compact"><thead><tr><th>Theme</th><th class="num">New</th><th class="num">Open</th><th class="num" title="issues closed this window; includes old issues swept in triage">Age at close</th><th>Open examples</th></tr></thead><tbody>${
         pm.slice(0, 6).map((r) => `<tr><td>${esc(r.theme)}</td><td class="num">${r.cur}</td><td class="num">${r.open}</td><td class="num">${r.median_days_to_close === null ? "—" : fmt(r.median_days_to_close, "days")}</td><td class="clamp">${r.examples.slice(0, 1).map(([n, t]) => `<span title="${esc(t)}">#${n} ${esc(t)}</span>`).join("")}</td></tr>`).join("")}</tbody></table>
         <h3 style="margin-top:10px">Issue type</h3>${hbars(typeRows, { labelW: 110, rowH: 22, W: 780 })}</div></div>` : ""}`);
  }

  // 13 improvement plan: overview, then one slide per priority
  const lanes = ["2 weeks", "this quarter", "next quarter"].filter((h) => plan.some((r) => (r.horizon || "this quarter") === h));
  S("recs", { kicker: "Improvement plan proposal", title: N.recs_title || "Improvement plan proposal",
    sowhat: "Ranked by impact on project health and urgency. One slide per priority follows.", section: "Plan", station: "All" },
    `<div class="card roadmap">${lanes.map((h) => `<div class="lane"><div class="kicker">${esc(h)}</div>${plan.filter((r) => (r.horizon || "this quarter") === h).map((r) =>
        `<button class="lane-item" data-goto="p${r.priority}"><span class="prio">P${r.priority}</span>${esc(r.text)}</button>`).join("")}</div>`).join("")}</div>
     <div class="card grow"><table class="plan-table"><thead><tr><th></th><th>Action</th><th>Issue</th><th>Outcome</th><th>When · effort · owner</th></tr></thead><tbody>${
       plan.map((r) => `<tr><td><span class="prio">P${r.priority}</span></td><td><b>${esc(r.text)}</b></td><td><div class="clamp3">${esc(r.issue || r.why || "")}</div></td><td><div class="clamp3">${esc(r.outcome || "")}</div></td><td class="small">${esc(r.horizon || "")} · ${esc(r.effort || "?")}<br><span class="muted">${esc(r.owner || "")}</span></td></tr>`).join("")
     }</tbody></table></div>`);
  plan.forEach((r) => {
    const now = (r.metrics || []).filter((k) => K[k]).slice(0, 3).map((k) => `<div class="measure"><span class="small muted">${esc(K[k].label)}</span><b>${fmt(K[k].value, K[k].unit)}</b>${deltaHtml(K[k])}</div>`).join("");
    S(`p${r.priority}`, { kicker: `Improvement plan · priority ${r.priority} of ${plan.length}`, title: r.text, section: "Plan", station: `P${r.priority}` },
      `<div class="plan-slide grow"><div class="plan-main">
         <div class="plan-meta"><span class="prio big">P${r.priority}</span><span class="pill">${esc(r.horizon || "")}</span><span class="pill">effort ${esc(r.effort || "?")}</span><span class="small muted">owner: ${esc(r.owner || "")}</span></div>
         <div class="io"><div class="issue"><div class="kicker">Issue</div><p>${esc(r.issue || r.why || "")}</p>${cite(r.metrics)}</div>
           <div class="outcome"><div class="kicker">Outcome</div><p>${esc(r.outcome || "")}</p></div></div>
         ${(r.actions || []).length ? `<div class="card"><div class="kicker">First actions</div><ol class="actions">${r.actions.map((x) => `<li>${esc(x)}</li>`).join("")}</ol></div>` : ""}</div>
       <aside class="plan-measure card"><div class="kicker">Now</div>${now}<div class="kicker" style="margin-top:12px">Target next edition</div><div class="target">${esc(r.target || "")}</div></aside></div>`);
  });

  // appendix
  const tb = D.token_report || {};
  const bk = B.types ? `<p>Type: <b>${esc(B.types.model)}</b> — macro-F1 ${B.types.macro_f1}, ECE ${B.types.ece}, coverage ${Math.round((B.types.coverage || 0) * 100)}% at ${Math.round((D.target_precision || .85) * 100)}% precision — gate ${B.types.passed ? "passed" : "not passed"}.</p>
    <p>Theme: <b>${esc(B.themes.model)}</b> — macro-F1 ${B.themes.macro_f1}, ECE ${B.themes.ece}, coverage ${Math.round((B.themes.coverage || 0) * 100)}% — gate ${B.themes.passed ? "passed" : "not passed"} (${esc(B.themes.reason)}).</p>
    <p class="muted">Mode: <b>${esc(B.mode || "local")}</b> (local = free models only; auto = best measured incl. API; jev = forced). Rule: ${esc(B.rule || "")}. Gold set reviewed: ${B.gold_reviewed ? "yes" : "no"}. Full comparison in out/${esc(M.title || "")}-bakeoff.html.</p>` : '<p class="muted">No classifier bake-off on record.</p>';
  S("appendix", { kicker: "Appendix", title: "Methodology, sources and caveats", section: "Appendix", station: "Method" },
    `<div class="cols2 grow small"><div class="card"><h3>Method</h3>
      <p>Current window = last ${M.window_days} days to ${esc(M.as_of)}; prior = the ${M.window_days} days before. Bots excluded; maintainers = people who merged a PR in the last year.
      Response times count the first comment or review by a maintainer on items opened by someone else.</p>
      <h3>Sources</h3><p>${M.forge === "GitLab" ? "GitLab REST API (issues, merge requests and their notes, stars, forks, releases, default-branch pipelines)" : `GitHub via <code>gh</code> (issues, PRs, reviews, stars, forks, releases, Actions runs of <code>${esc(X.code.ci_workflow || "CI")}</code>)`}; git clone at <code>${esc(X.code.head || "")}</code>${(X.adoption.distribution_sources || (K.pypi_downloads ? ["pypistats.org"] : [])).map((s) => "; " + esc(s)).join("")}${K.hf_spaces_new ? "; Hugging Face Hub search" : ""}.</p>
      <h3>Caveats</h3><p>${["stars_new", ...(X.adoption.download_keys || ["pypi_downloads"]), "hf_spaces_new", "dependents", "backends_with_tests"].filter((k) => K[k]).map((k) => `<b>${esc(K[k].label)}</b>: ${esc(K[k].note || "—")}`).join("<br>")}</p></div>
     <div class="card"><h3>Issue classifier</h3>${bk}
      <h3>Narrative</h3><p>${esc(N.source || "none")}. ${(N.dropped || []).length} claims removed by the number check.</p>
      <h3>Token report</h3><p>${esc(tb.summary || "—")}</p></div></div>`);
  S("all-1", { kicker: "Appendix", title: "All indicators · community & flow", section: "Appendix", station: "KPIs 1" },
    `<div class="cols2 grow">${[0, 1].map((h) => { const ks = M.families.flow; const mid = Math.ceil(ks.length / 2); return `<div class="card">${kpiTable(h ? ks.slice(mid) : ks.slice(0, mid))}</div>`; }).join("")}</div>`);
  S("all-2", { kicker: "Appendix", title: "All indicators · adoption, codebase, themes", section: "Appendix", station: "KPIs 2" },
    (() => { // flow the three families into two balanced columns; a family split across them repeats its heading
      const fams = ["adoption", "themes", "code"].map((f) => [f, M.families[f] || []]).filter(([, ks]) => ks.length);
      const total = fams.reduce((a, [, ks]) => a + ks.length + 2, 0), cols = [[], []];
      let used = 0;
      fams.forEach(([f, ks]) => ks.forEach((k, i) => {
        const c = used + (i ? 0 : 2) > total / 2 + 1 ? 1 : 0;
        const last = cols[c][cols[c].length - 1];
        if (last && last[0] === f) last[1].push(k); else cols[c].push([f, [k]]);
        used += i ? 1 : 2;
      }));
      return `<div class="cols2 grow">${cols.map((col) => `<div class="card">${col.map(([f, ks], i) => `<h3${i ? ' style="margin-top:8px"' : ""}>${famNames[f]}</h3>${kpiTable(ks)}`).join("")}</div>`).join("")}</div>`; })());

  // ---------- render: metro band, frame, footer
  const LINES = [
    { name: "Overview", color: "var(--ink-2)" }, { name: "Scorecard", color: "var(--s1)" }, { name: "Deep dives", color: "var(--s3)" },
    { name: "Plan", color: "var(--s2)" }, { name: "Appendix", color: "var(--muted)" },
  ].filter((l) => slides.some((s) => s.section === l.name));
  const metro = (cur) => `<nav class="metro" aria-label="Presentation map">${LINES.map((l) => {
    const st = slides.map((s, i) => ({ s, i })).filter(({ s }) => s.section === l.name);
    const active = st.some(({ i }) => i === cur);
    return `<div class="metro-line${active ? " active" : ""}" style="--c:${l.color};--n:${Math.max(2, st.length)}"><div class="metro-name">${esc(l.name)}</div><div class="metro-stops">${
      st.map(({ s, i }) => `<button class="stop${i === cur ? " here" : i < cur ? " past" : ""}" data-goto="${s.id}" title="${esc(s.station)}"${i === cur ? ' aria-current="step"' : ""}><i></i><span>${esc(s.station)}</span></button>`).join("")
    }</div></div>`; }).join("")}</nav>`;
  const total = slides.length;
  deck.innerHTML = slides.map((s, i) => `<section class="slide ${s.cls}" id="s-${s.id}" data-i="${i}" aria-roledescription="slide" aria-label="${i + 1} of ${total}">
    ${s.section ? metro(i) : ""}
    ${s.title ? `<header class="slide-head"><div class="kicker">${esc(s.kicker || "")}</div><h2>${esc(s.title)}</h2>${s.sowhat ? `<p class="sowhat">${esc(s.sowhat)}</p>` : ""}${cite(s.metrics)}</header>` : ""}
    <div class="slide-body">${s.body}</div>
    <footer class="slide-foot"><span>${esc(M.repo)} · pulse · ${esc(M.as_of)}</span><span>${i + 1} / ${total}</span></footer></section>`).join("");

  // ---------- engine: one slide at a time, scaled 1280x720 canvas; scroll mode on narrow screens
  const secs = [...deck.querySelectorAll(".slide")];
  const pos = document.getElementById("pos");
  const root = document.documentElement;
  let cur = 0;
  const idx = (id) => slides.findIndex((s) => s.id === id);
  const narrow = () => matchMedia("(max-width: 760px)").matches;
  function fit() {
    const s = Math.min(window.innerWidth / 1280, (window.innerHeight - 0) / 720);
    root.style.setProperty("--scale", s.toFixed(4));
  }
  function show(i, push = true) {
    cur = Math.max(0, Math.min(total - 1, i));
    secs.forEach((el, j) => { el.classList.toggle("active", j === cur); el.classList.toggle("before", j < cur); });
    pos.textContent = `${cur + 1} / ${total}`;
    if (narrow()) secs[cur].scrollIntoView({ block: "start" });
    if (push) history.replaceState(null, "", `#${cur + 1}`);
  }
  const go = (i) => show(i);
  document.getElementById("prev").onclick = () => go(cur - 1);
  document.getElementById("next").onclick = () => go(cur + 1);
  deck.addEventListener("click", (e) => {
    const t = e.target.closest("[data-goto]");
    if (t) { e.preventDefault(); const i = idx(t.dataset.goto); if (i >= 0) { if (body.classList.contains("overview")) toggleOverview(false); go(i); } }
  });
  const body = document.body;
  function toggleOverview(on = !body.classList.contains("overview")) {
    body.classList.toggle("overview", on);
    if (on) secs[cur].scrollIntoView({ block: "center" });
  }
  deck.addEventListener("click", (e) => {
    if (!body.classList.contains("overview")) return;
    const sl = e.target.closest(".slide");
    if (sl) { toggleOverview(false); go(+sl.dataset.i); }
  });
  document.getElementById("ovBtn").onclick = () => toggleOverview();
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) { e.preventDefault(); go(cur + 1); }
    else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(e.key)) { e.preventDefault(); go(cur - 1); }
    else if (e.key === "Home") go(0); else if (e.key === "End") go(total - 1);
    else if (e.key === "o" || e.key === "O" || (e.key === "Escape" && body.classList.contains("overview"))) toggleOverview();
  });
  let tx = null;
  deck.addEventListener("touchstart", (e) => { tx = e.touches[0].clientX; }, { passive: true });
  deck.addEventListener("touchend", (e) => { if (tx === null || narrow()) return; const dx = e.changedTouches[0].clientX - tx; if (Math.abs(dx) > 50) go(cur + (dx < 0 ? 1 : -1)); tx = null; });
  // narrow screens scroll; keep the counter in sync
  deck.addEventListener("scroll", () => { if (!narrow()) return; const y = deck.scrollTop + 40; let i = 0; secs.forEach((s, j) => { if (s.offsetTop <= y) i = j; }); if (i !== cur) { cur = i; pos.textContent = `${cur + 1} / ${total}`; } }, { passive: true });
  window.addEventListener("resize", fit);
  fit();
  const start = parseInt((location.hash || "").slice(1), 10);
  show(Number.isFinite(start) ? start - 1 : 0, false);
  // overflow guard: content must fit the 1280x720 canvas
  if (!narrow()) secs.forEach((el) => {
    const was = el.classList.contains("active"); el.classList.add("active");
    const b = el.querySelector(".slide-body");
    if (b && b.scrollHeight > b.clientHeight + 2) console.warn(`[repo-pulse] overflow on slide ${el.id}: body +${b.scrollHeight - b.clientHeight}px`);
    el.querySelectorAll(".card").forEach((c, k) => { if (c.scrollHeight > c.clientHeight + 2) console.warn(`[repo-pulse] overflow on slide ${el.id}: card ${k} +${c.scrollHeight - c.clientHeight}px`); });
    if (!was) el.classList.remove("active");
  });

  let saved = null; try { saved = localStorage.getItem("repo-pulse-theme"); } catch (e) {}
  if (saved) root.setAttribute("data-theme", saved);
  document.getElementById("themeBtn").onclick = () => {
    const dark = root.getAttribute("data-theme") ? root.getAttribute("data-theme") === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark"; root.setAttribute("data-theme", next);
    try { localStorage.setItem("repo-pulse-theme", next); } catch (e) {}
  };
})();

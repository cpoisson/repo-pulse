"""Gold set: human-validated labels used to select and calibrate the classifier.

Flow: pre-labels (one-time, by an LLM) -> `gold.json` (reviewed=false) -> review page -> reviewer exports
-> `repo-pulse gold --import reviewed.json` (reviewed=true). The bake-off reports whether the gold set is reviewed.
"""
from __future__ import annotations

import hashlib
import html
import json
from collections import defaultdict
from pathlib import Path

from ..collect.cache import load_all
from ..config import Config
from . import issue_text

def _path(cfg: Config) -> Path:
    """Gold labels live with the repo's data: data/<repo-slug>/gold.json."""
    return Path("data") / cfg.slug / "gold.json"



def _split(number: str, theme: str) -> str:
    """Deterministic ~60/40 calib/test split, stratified by hashing within theme."""
    h = int(hashlib.sha1(f"{theme}:{number}".encode()).hexdigest(), 16) % 100
    return "calib" if h < 60 else "test"


def load(cfg: Config) -> dict:
    p = _path(cfg)
    return json.loads(p.read_text()) if p.exists() else {"meta": {}, "items": {}}


def save(cfg: Config, gold: dict) -> None:
    p = _path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(gold, indent=1, sort_keys=True))


def import_prelabels(cfg: Config, path: str, source: str) -> dict:
    """Lines of `<number> <type> <theme>`; '-' marks an item excluded from the gold set."""
    gold = load(cfg)
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        num, typ, *rest = line.split()
        theme = rest[0] if rest else "-"
        if typ == "-":
            gold["items"].pop(num, None)
            continue
        prev = gold["items"].get(num, {})
        if prev.get("reviewed"):
            continue  # never overwrite a human decision
        gold["items"][num] = {"type": typ, "theme": theme, "split": _split(num, theme), "source": source, "reviewed": False}
    gold["meta"]["prelabel_source"] = source
    save(cfg, gold)
    return gold


def import_reviewed(cfg: Config, path: str, reviewer: str = "maintainer") -> dict:
    gold = load(cfg)
    reviewed = json.loads(Path(path).read_text())
    for num, lab in reviewed.items():
        item = gold["items"].setdefault(num, {"split": _split(num, lab["theme"])})
        changed = item.get("type") != lab["type"] or item.get("theme") != lab["theme"]
        item.update(type=lab["type"], theme=lab["theme"], reviewed=True, reviewer=reviewer, corrected=changed)
    save(cfg, gold)
    return gold


def status(gold: dict) -> dict:
    items = gold["items"].values()
    n = len(gold["items"])
    rev = sum(1 for i in items if i.get("reviewed"))
    corrected = sum(1 for i in items if i.get("corrected"))
    return {"n": n, "reviewed": rev, "fully_reviewed": n > 0 and rev == n, "corrected": corrected,
            "calib": sum(1 for i in items if i["split"] == "calib"), "test": sum(1 for i in items if i["split"] == "test")}


def make_review_page(cfg: Config, as_of: str, n: int | None = None) -> Path:
    raw = load_all(cfg.slug, as_of)
    gold = load(cfg)
    issues = {str(i["number"]): i for i in raw["issues"]}
    rows = []
    for num, lab in sorted(gold["items"].items(), key=lambda kv: -int(kv[0])):
        it = issues.get(num)
        if not it:
            continue
        rows.append({"n": num, "title": it["title"], "text": issue_text(it, 900)[len(it["title"]) + 2:], "type": lab["type"],
                     "theme": lab["theme"], "reviewed": lab.get("reviewed", False)})
    page = _REVIEW_HTML.replace("__DATA__", json.dumps(rows)).replace("__TYPES__", json.dumps(cfg.issue_types)) \
        .replace("__THEMES__", json.dumps(cfg.themes)).replace("__REPO__", html.escape(cfg.repo))
    out = Path("out") / f"{cfg.name}-gold-review.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)
    return out


_REVIEW_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gold Label Review</title>
<style>
:root{--bg:#fbfaf8;--fg:#1d1d1f;--mut:#6b6b70;--card:#fff;--line:#e6e3de;--acc:#b4502a;--ok:#2f7d4f}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151517;--fg:#ececee;--mut:#9a9aa0;--card:#1e1e21;--line:#333338;--acc:#e07a4f;--ok:#5cc58a}}
:root[data-theme=dark]{--bg:#151517;--fg:#ececee;--mut:#9a9aa0;--card:#1e1e21;--line:#333338;--acc:#e07a4f;--ok:#5cc58a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:2}
h1{font-size:17px;margin:0}main{max-width:900px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:12px}
.card.done{border-left:4px solid var(--ok)}.t{font-weight:600}.n{color:var(--mut);font-variant-numeric:tabular-nums}
.body{color:var(--mut);font-size:13px;margin:6px 0 10px;max-height:6.2em;overflow:hidden}
select{font:inherit;padding:4px 6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
button.ghost{background:transparent;color:var(--acc)}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.legend{font-size:12px;color:var(--mut)}a{color:var(--acc)}
</style></head><body>
<header><h1>Gold labels · __REPO__</h1><span id="prog" class="n"></span>
<button onclick="exportJson()">Export reviewed JSON</button><button class="ghost" onclick="markAll()">Mark all visible as reviewed</button>
<label class="legend"><input type="checkbox" id="onlyTodo" onchange="render()"> only unreviewed</label></header>
<main><p class="legend">Pre-labels are a one-time LLM pass. Correct anything wrong, tick "ok", then export and run
<code>repo-pulse gold --import reviewed.json</code>. Theme definitions are in the config; hover a theme to see its description.</p><div id="list"></div></main>
<script>
const rows=__DATA__, TYPES=__TYPES__, THEMES=__THEMES__;
let state={};try{state=JSON.parse(localStorage.getItem('gold-review')||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem('gold-review',JSON.stringify(state))}catch(e){}};
const opt=(o,v)=>Object.entries(o).map(([k,d])=>`<option value="${k}" title="${d.replace(/"/g,'&quot;')}" ${k===v?'selected':''}>${k}</option>`).join('');
function cur(r){return state[r.n]||{type:r.type,theme:r.theme,ok:r.reviewed}}
function render(){const only=document.getElementById('onlyTodo').checked;
 document.getElementById('list').innerHTML=rows.filter(r=>!only||!cur(r).ok).map(r=>{const c=cur(r);return `<div class="card ${c.ok?'done':''}" id="c${r.n}">
 <div><span class="n">#${r.n}</span> <span class="t">${esc(r.title)}</span> <a target="_blank" href="https://github.com/__REPO__/issues/${r.n}">open</a></div>
 <div class="body">${esc(r.text)}</div><div class="row">type <select onchange="upd('${r.n}','type',this.value)">${opt(TYPES,c.type)}</select>
 theme <select onchange="upd('${r.n}','theme',this.value)">${opt(THEMES,c.theme)}</select>
 <label><input type="checkbox" ${c.ok?'checked':''} onchange="upd('${r.n}','ok',this.checked)"> ok</label></div></div>`}).join('');prog()}
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function upd(n,k,v){const r=rows.find(x=>x.n===n);state[n]={...cur(r),[k]:v};if(k!=='ok')state[n].ok=true;save();
 document.getElementById('c'+n).classList.toggle('done',state[n].ok);prog()}
function prog(){const d=rows.filter(r=>cur(r).ok).length;document.getElementById('prog').textContent=`${d}/${rows.length} reviewed`}
function markAll(){document.querySelectorAll('.card').forEach(el=>{const n=el.id.slice(1);const r=rows.find(x=>x.n===n);state[n]={...cur(r),ok:true}});save();render()}
function exportJson(){const out={};rows.forEach(r=>{const c=cur(r);if(c.ok)out[r.n]={type:c.type,theme:c.theme}});
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{type:'application/json'}));a.download='reviewed.json';a.click()}
render();
</script></body></html>"""

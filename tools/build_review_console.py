#!/usr/bin/env python3
"""Regenerate outputs/katie-session/review.html from the task CSVs."""
import csv, json, html
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "outputs" / "katie-session"

def load(name):
    return list(csv.DictReader(open(BASE / name, encoding="utf-8-sig")))

TASKS = {
  "A": {"title": "Task A — Verify the evidence for YOUR challenge (25 rows, ~35 min)",
    "intro": ("Each card is one provision the engine mapped for your Singapore-clothing-business scenario "
              "(China / India / Thailand × your indicators). Open the source link, check the verbatim quote "
              "and the indicator mapping, then click a verdict. Your tally becomes our human-verified "
              "precision figure for Thursday's review and the submission."),
    "verdicts": ["Correct", "Wrong", "Unsure"], "rows": load("A-sample-verification.csv")},
  "B": {"title": "Task B — Adjudicate 10 scoring disagreements (~25 min)",
    "intro": ("On these rows our engine scored 1.0 but the official ESCAP evaluators recorded 0. "
              "The official criteria are shown on each card. You are the referee: who read the law right? "
              "Your rulings directly become calibration rules in the scorer."),
    "verdicts": ["Official is right", "Engine is right", "Both defensible"], "rows": load("B-adjudication.csv")},
  "C": {"title": "Task C — Sign off 5 independently discovered NEW laws (~20 min)",
    "intro": ("The engine found these in-force laws beyond the official inventory (the judges' stated "
              "differentiator). Confirm each is (1) real and in force, (2) genuinely absent from the official "
              "inventory, (3) correctly characterised. Same sign-off pattern as the Round 1 golden set."),
    "verdicts": ["Approve", "Reject", "Needs work"], "rows": load("C-new-laws-signoff.csv")},
  "D": {"title": "Task D — Singapore beyond P6/P7 for your challenge (10 rows, ~10 min)",
    "intro": ("Your scenario's Singapore gaps: online advertising (9.3, Singapore Code of Advertising "
              "Practice) and purchase/delivery limitations (12.2, E-Commerce Code + Electronic Transactions "
              "Act). Payment limitations (12.4.x, Payment Services Act) are still being extracted and will "
              "be added. Watch for mislabelled law names — marking those Wrong is exactly the point."),
    "verdicts": ["Correct", "Wrong", "Unsure"], "rows": load("D-sgp-verification.csv")},
  "E": {"title": "Task E — Spot-check 8 machine-inferred citations (~8 min)",
    "intro": ("When the AI leaves the article number blank, a deterministic rule walks back from the quote "
              "to the nearest legal heading and backfills it (flagged 'inferred'). Wrong citations cost "
              "judge points; empty ones merely lose them. Open the source and confirm the quoted text really "
              "sits under the stated heading."),
    "verdicts": ["Heading correct", "Heading wrong", "Unsure"], "rows": load("E-inferred-citations.csv")},
}

def cards(task_id, t):
    out = []
    for i, r in enumerate(t["rows"]):
        fields = []
        for k, v in r.items():
            if not v or k.upper().startswith(("VERDICT", "NOTES", "YOUR", "SIGN-OFF", "WHY")):
                continue
            v = html.escape(v)
            if k in ("source_url", "official_url"):
                v = f'<a href="{v}" target="_blank" rel="noopener">{v}</a> <span class="hint">&larr; open &amp; verify</span>'
            elif k == "verbatim_snippet":
                v = f'<blockquote>{v}</blockquote>'
            fields.append(f'<div class="f"><span class="k">{html.escape(k)}</span><div class="v">{v}</div></div>')
        btns = "".join(
            f'<button class="vbtn" data-task="{task_id}" data-row="{i}" data-verdict="{html.escape(v)}">{html.escape(v)}</button>'
            for v in t["verdicts"])
        out.append(f'<div class="card" id="{task_id}-{i}"><div class="card-head">#{i+1}</div>{"".join(fields)}'
                   f'<div class="verdict-row">{btns}'
                   f'<input class="note" data-task="{task_id}" data-row="{i}" placeholder="optional note"/></div></div>')
    return "\n".join(out)

sections = "\n".join(
    f'<section id="sec-{tid}"><h2>{html.escape(t["title"])}</h2><p class="intro">{html.escape(t["intro"])}</p>'
    f'<div class="progress" id="prog-{tid}"></div>{cards(tid, t)}</section>'
    for tid, t in TASKS.items())

data_json = json.dumps({tid: {"verdicts": t["verdicts"], "n": len(t["rows"]), "rows": t["rows"]}
                        for tid, t in TASKS.items()}, ensure_ascii=False)

STYLE = """
 body{font:15px/1.55 -apple-system,Segoe UI,sans-serif;margin:0;background:#f4f6f8;color:#1a2733}
 header{background:#123456;color:#fff;padding:18px 28px}
 header h1{margin:0;font-size:20px} header p{margin:6px 0 0;opacity:.85;max-width:900px}
 main{max-width:960px;margin:0 auto;padding:20px}
 h2{margin:34px 0 6px;font-size:17px;color:#123456}
 .intro{margin:0 0 12px;color:#43555f}
 .progress{font-weight:600;color:#0a7d33;margin-bottom:10px}
 .card{background:#fff;border:1px solid #dde4ea;border-radius:10px;padding:14px 18px;margin:12px 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}
 .card.done{border-color:#0a7d33;background:#f4fbf6}
 .card-head{font-weight:700;color:#8a99a6;margin-bottom:6px}
 .f{margin:5px 0} .k{display:inline-block;min-width:150px;color:#6a7a86;font-size:12.5px;text-transform:uppercase;letter-spacing:.4px;vertical-align:top}
 .v{display:inline-block;max-width:720px;vertical-align:top}
 blockquote{margin:4px 0;padding:8px 12px;background:#f6f3e8;border-left:3px solid #c9a227;font-style:italic}
 .hint{color:#8a99a6;font-size:12px}
 .verdict-row{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
 .vbtn{padding:7px 14px;border:1px solid #b8c4cd;border-radius:20px;background:#fff;cursor:pointer;font-size:13.5px}
 .vbtn:hover{background:#eef4f9} .vbtn.sel{background:#123456;color:#fff;border-color:#123456}
 .note{flex:1;min-width:180px;padding:7px 10px;border:1px solid #cfd8df;border-radius:6px}
 .exportbar{position:sticky;bottom:0;background:#fff;border-top:2px solid #123456;padding:12px 20px;display:flex;gap:14px;align-items:center;justify-content:space-between}
 .exportbar button{background:#0a7d33;color:#fff;border:0;border-radius:8px;padding:10px 22px;font-size:15px;cursor:pointer}
 .exportbar button:disabled{background:#9db9a8}
 a{color:#0b62c4}
"""

SCRIPT = """
const DATA = __DATA__;
const KEY = "katie-review-v1";
let state = JSON.parse(localStorage.getItem(KEY) || "{}");
function save() { localStorage.setItem(KEY, JSON.stringify(state)); render(); }
function render() {
  let total = 0, done = 0;
  for (const tid in DATA) {
    let d = 0;
    for (let i = 0; i < DATA[tid].n; i++) {
      const st = (state[tid]||{})[i] || {};
      const card = document.getElementById(tid+"-"+i);
      card.classList.toggle("done", !!st.verdict);
      card.querySelectorAll(".vbtn").forEach(b =>
        b.classList.toggle("sel", b.dataset.verdict === st.verdict));
      if (st.verdict) d++;
    }
    total += DATA[tid].n; done += d;
    document.getElementById("prog-"+tid).textContent = d + " / " + DATA[tid].n + " reviewed";
  }
  document.getElementById("total").innerHTML = "<b>" + done + " / " + total + "</b> total reviewed";
  document.getElementById("export").disabled = done === 0;
}
document.addEventListener("click", e => {
  if (!e.target.classList.contains("vbtn")) return;
  const t = e.target.dataset.task, i = e.target.dataset.row;
  state[t] = state[t] || {}; state[t][i] = state[t][i] || {};
  state[t][i].verdict = e.target.dataset.verdict; save();
});
document.addEventListener("input", e => {
  if (!e.target.classList.contains("note")) return;
  const t = e.target.dataset.task, i = e.target.dataset.row;
  state[t] = state[t] || {}; state[t][i] = state[t][i] || {};
  state[t][i].note = e.target.value; localStorage.setItem(KEY, JSON.stringify(state));
});
document.getElementById("export").onclick = () => {
  let lines = ["task,row,economy_or_id,law_name,indicator,verdict,note"];
  for (const tid in DATA) DATA[tid].rows.forEach((r, i) => {
    const st = (state[tid]||{})[i] || {};
    const cell = v => '"' + String(v||"").replace(/"/g,'""') + '"';
    lines.push([tid, i+1, cell(r.economy||r.law_id||""), cell(r.law_name||""),
      cell(r.indicator_id||r.indicator||""), cell(st.verdict||""), cell(st.note||"")].join(","));
  });
  const blob = new Blob(["\\ufeff"+lines.join("\\n")], {type:"text/csv"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "katie-review-results.csv"; a.click();
};
render();
"""

page = ("<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>SENTINEL — Legal Review Session (Katie)</title>"
        f"<style>{STYLE}</style></head><body>"
        "<header><h1>SENTINEL — Legal Review Session</h1>"
        "<p>Hi Katie — five focused review tasks, ~100 minutes total (A–C core, D–E quick add-ons). "
        "Everything is click-based: read the card, open the source link if needed, click one verdict, "
        "optionally add a note. Progress saves automatically in your browser — close and resume anytime. "
        "When done, hit <b>Export results</b> (bottom bar) and send the downloaded file back.</p></header>"
        f"<main>{sections}</main>"
        '<div class="exportbar"><div id="total"></div><button id="export">Export results (CSV)</button></div>'
        f"<script>{SCRIPT.replace('__DATA__', data_json)}</script></body></html>")

out = BASE / "review.html"
out.write_text(page, encoding="utf-8")
print(f"review.html rebuilt: {sum(len(t['rows']) for t in TASKS.values())} cards")

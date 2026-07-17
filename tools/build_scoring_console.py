#!/usr/bin/env python3
"""Build ONE self-contained RDTII scoring console for a legal reviewer.

Consolidates every banked NEW law that needs a human indicator/score judgement
into a single downloadable HTML. The reviewer opens it (no server needed),
scores each item with enough context to decide — verbatim provision text,
official-source link, our suggested indicator, what the pipeline actually
extracted, the specific open question for divergent cases, and the RDTII
criteria on hover — then clicks one button to export a unified JSON + CSV.

    python tools/build_scoring_console.py
    # -> outputs/legal-review/rdtii-scoring-console.html   (gitignored; deliver by file)

The `PIPELINE_GOT` snapshot below is what `run_extraction` produced for each
banked law on 2026-07-17 (see docs/r1-discovery-coverage.md, reproducibility
audit). Regenerate it with a fresh audit if the library or extractor changes.
"""
from __future__ import annotations

import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "outputs" / "legal-review" / "rdtii-scoring-console.html"

# What run_extraction produced for each banked law (2026-07-17 audit snapshot).
# Keys are law_id prefixes; [] means the pipeline extracted no indicator.
PIPELINE_GOT: dict[str, list[str]] = {
    "sgp-pdp-regulations-2021": ["6.1", "6.4", "7.1"],
    "mys-credit-reporting-agencies-act-2010": [],
    "aus-archives-act-1983": ["6.1"],
    "aus-nsw-ppipa-1998": ["6.4", "7.1", "7.5"],
    "aus-digital-id-act-2024-no-25-2024": [],
    "mys-personal-data-protection-amendment-a": ["7.1", "7.3", "7.4", "7.5"],
    "sgp-banking-act-1970-2020-revised-editio": ["7.1", "7.4"],
    "sgp-healthcare-services-general-regulati": ["7.3"],
    "mys-personal-data-protection-regulations": ["7.1", "7.3", "7.4", "7.5"],
    "aus-identity-verification-services-act-2": ["7.1", "7.3"],
    "aus-privacy-and-data-protection-act-2014": ["6.4", "7.1"],
    "aus-information-act-2002-northern-territ": ["6.1", "6.4"],
    "sgp-mas-notice-658-management-of-outsour": [],
    "aus-crimes-act-1914-no-12-of-1914-s-3la-": [],
    "aus-surveillance-devices-act-2004-no-152": ["7.5"],
    "aus-cyber-security-act-2024-no-98-2024": ["11.1"],
    "mys-consumer-protection-electronic-trade": ["12.9"],
    "aus-personal-information-protection-act-": ["6.4"],
    "aus-privacy-and-responsible-information-": ["6.4", "7.1", "7.5"],
}

# Divergent (Priority-A) laws: the pipeline and our suggestion disagree — the
# reviewer's call decides. Each states the exact open question.
PRIORITY: dict[str, str] = {
    "aus-cyber-security-act-2024-no-98-2024":
        "Pipeline maps the provision to 11.1 (Standards). We read the Act as a dedicated "
        "cybersecurity framework = 7.2. Which is right — 7.2, 11.1, or both?",
    "aus-digital-id-act-2024-no-25-2024":
        "Thin excerpt extracts to nothing; with fuller context it maps to 7.4. We hinted 7.1. "
        "Does s48 (biometric collection restrictions) support 7.1, 7.4, or another indicator?",
    "aus-archives-act-1983":
        "Pipeline consistently maps this to 6.1 (storage); we hinted 7.3 (retention). "
        "Which indicator does a Commonwealth-records retention duty belong to?",
    "aus-crimes-act-1914-no-12-of-1914-s-3la-assistance-orders":
        "Pipeline finds no indicator for this excerpt. Do computer-access assistance orders "
        "support 7.5 (lawful access to data), or is it out of scope for P6/P7?",
    "sgp-mas-notice-658-management-of-outsourced-relevant-services-banking-act-1970-s":
        "Pipeline finds no indicator. Does the offshore-outsourcing conditions text support "
        "6.4 (conditional cross-border), or is it not a cross-border-data measure?",
    "mys-credit-reporting-agencies-act-2010":
        "Pipeline finds no indicator. Does 'security of credit information' support 7.1 "
        "(data-protection framework), 7.2/7.3, or none of P6/P7?",
}


def pipeline_got(law_id: str) -> list[str]:
    for pref, got in PIPELINE_GOT.items():
        if law_id.startswith(pref):
            return got
    return []


def build() -> None:
    meth = json.loads((REPO / "data" / "rdtii21_methodology.json").read_text())
    indicators = {}
    for x in meth:
        if isinstance(x, dict) and str(x.get("pillar")) in {"6", "7", "11", "12"}:
            indicators[str(x["indicator_id"])] = {
                "pillar": x.get("pillar"),
                "category": (x.get("category") or "").strip(),
                "criteria": (x.get("criteria") or "").strip(),
                "scores": [s.strip() for s in str(x.get("possible_scores", "")).splitlines() if s.strip()],
            }

    rows = [json.loads(l) for l in (REPO / "data/law_library/manifest.jsonl").read_text().splitlines() if l.strip()]
    laws = []
    for r in rows:
        if r.get("origin") != "discovered":
            continue
        text = (REPO / r["text_path"]).read_text()
        laws.append({
            "law_id": r["law_id"], "economy": r["economy"], "law_name": r["law_name"],
            "url": r["official_url"], "pillars": r.get("pillars", []),
            "hints": r.get("indicator_hints", []),
            "version": r.get("version", "") or r.get("currency_source", ""),
            "provision": text.strip(), "pipeline_got": pipeline_got(r["law_id"]),
            "priority": PRIORITY.get(r["law_id"], ""),
        })
    laws.sort(key=lambda x: (x["priority"] == "", x["economy"]))

    data_json = json.dumps({"laws": laws, "indicators": indicators}, ensure_ascii=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_TEMPLATE.replace("__DATA__", data_json), encoding="utf-8")
    n_pri = sum(1 for l in laws if l["priority"])
    print(f"wrote {OUT.relative_to(REPO)} | {len(laws)} laws | {n_pri} priority")


_TEMPLATE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RDTII 2.1 — NEW-law Scoring Console (Legal Review)</title>
<style>
:root{--ok:#0b8a3b;--flag:#b26a00;--rej:#b3261e;--pri:#7a1fa2;--bd:#d0d0d8;--bg:#fafafc}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;color:#1a1a1e;background:var(--bg);line-height:1.5}
header{position:sticky;top:0;background:#12203a;color:#fff;padding:14px 22px;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,.15)}
header h1{margin:0;font-size:18px}
header .sub{font-size:13px;opacity:.85;margin-top:3px}
.bar{height:8px;background:#2a3a5a;border-radius:4px;margin-top:8px;overflow:hidden}
.bar>span{display:block;height:100%;background:#4caf7d;width:0;transition:width .2s}
.wrap{max-width:940px;margin:0 auto;padding:18px}
details.help{background:#eef2fb;border:1px solid #cdd8ef;border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:14px}
details.help summary{cursor:pointer;font-weight:600}
.card{background:#fff;border:1px solid var(--bd);border-radius:10px;padding:16px 18px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.card.pri{border-left:5px solid var(--pri)}
.card.done{opacity:.62}
.eco{display:inline-block;font-size:11px;font-weight:700;color:#fff;background:#3b5aa6;border-radius:4px;padding:1px 7px;vertical-align:middle}
.lawname{font-size:16px;font-weight:700;margin:6px 0 2px}
.meta{font-size:12.5px;color:#555;margin-bottom:8px}
.meta a{color:#1558d6}
.pribox{background:#f6ecfb;border:1px solid #e0c8ee;border-radius:7px;padding:9px 12px;margin:8px 0;font-size:13.5px}
.pribox b{color:var(--pri)}
.prov{white-space:pre-wrap;font-size:13px;background:#f7f7fa;border:1px solid #ececf2;border-radius:7px;padding:10px 12px;max-height:230px;overflow:auto;margin:8px 0}
.line{font-size:13px;margin:6px 0}
.tag{display:inline-block;font-size:12px;border-radius:5px;padding:1px 8px;margin:2px 3px 2px 0;border:1px solid #bbb;background:#fff}
.tag.hint{border-color:#1558d6;color:#1558d6}
.tag.got{border-color:#0b8a3b;color:#0b8a3b}
.tag.gotnone{border-color:#b3261e;color:#b3261e}
.chips{margin:8px 0}
.chip{display:inline-block;font-size:12.5px;border:1.5px solid #bbb;border-radius:16px;padding:3px 11px;margin:3px 4px 3px 0;cursor:pointer;user-select:none;background:#fff}
.chip.on{background:var(--ok);color:#fff;border-color:var(--ok)}
.verdicts{margin:10px 0 6px}
.vbtn{font-size:13px;border:1.5px solid #bbb;border-radius:7px;padding:5px 12px;margin-right:7px;cursor:pointer;background:#fff}
.vbtn.on-valid{background:var(--ok);color:#fff;border-color:var(--ok)}
.vbtn.on-flag{background:var(--flag);color:#fff;border-color:var(--flag)}
.vbtn.on-reject{background:var(--rej);color:#fff;border-color:var(--rej)}
textarea,input[type=text]{width:100%;font-size:13px;border:1px solid var(--bd);border-radius:6px;padding:7px;margin-top:6px;font-family:inherit}
.exportbar{position:sticky;bottom:0;background:#12203a;padding:12px 22px;display:flex;gap:12px;align-items:center;justify-content:flex-end}
.exportbar button{font-size:14px;font-weight:600;border:0;border-radius:7px;padding:9px 18px;cursor:pointer}
#expjson{background:#4caf7d;color:#fff}#expcsv{background:#f0c040;color:#222}
.exportbar .cnt{color:#fff;margin-right:auto;font-size:13px}
.crithint{font-size:12px;color:#666;margin-top:2px}
.rev{padding:6px 22px;background:#eef2fb;font-size:13px}
</style></head><body>
<header>
  <h1>RDTII 2.1 — NEW-law Scoring Console</h1>
  <div class="sub">Team SENTINEL · UN Digital-Trade regulatory mapping · Pillars 6 / 7 (+ 11 / 12) · for the legal reviewer</div>
  <div class="bar"><span id="prog"></span></div>
</header>
<div class="rev">Reviewer name (goes in the export): <input type="text" id="rev" style="width:240px;display:inline-block" placeholder="your name"></div>
<div class="wrap">
<details class="help" open><summary>How to use (read once) — your judgement is the deciding step</summary>
<p>Our engine <b>discovers</b> and <b>verbatim-verifies</b> each NEW law (the text below is copied character-for-character from the official government source — link on every card). What it cannot decide reliably is the correct <b>RDTII indicator</b> for subtle provisions. That is your call.</p>
<ol>
<li>Read the provision. Open the official source if you want to confirm.</li>
<li><b>Purple cards are priority</b> — the pipeline and our suggestion disagree; each states the exact question.</li>
<li>Click the indicator chip(s) the provision <b>genuinely supports</b> (hover a chip to see its RDTII criteria). Green = selected.</li>
<li>Optionally set the <b>RDTII score</b>, then a verdict: <b>Confirm</b>, <b>Flag for discussion</b>, or <b>Reject (not valid evidence)</b>.</li>
<li>Add a one-line note if useful. Progress saves in your browser automatically.</li>
<li>When done, click <b>Export decisions (JSON)</b> and send us the file (CSV also available). One file, all decisions.</li>
</ol>
<p class="crithint">Chip legend: <span class="tag hint">our suggestion</span> <span class="tag got">pipeline extracted</span> <span class="tag gotnone">pipeline found nothing</span>. Trust the text, not the pre-marks.</p>
</details>
<div id="cards"></div>
</div>
<div class="exportbar">
  <span class="cnt" id="cnt"></span>
  <button id="expcsv">Export CSV</button>
  <button id="expjson">Export decisions (JSON)</button>
</div>
<script>
const DATA = __DATA__;
const KEY = "rdtii_scoring_v1";
let state = JSON.parse(localStorage.getItem(KEY) || "{}");
if(state.__rev){document.getElementById('rev').value=state.__rev;}
document.getElementById('rev').oninput=e=>{state.__rev=e.target.value;save();};
function save(){localStorage.setItem(KEY, JSON.stringify(state));}
function rdtiiOrder(){ return Object.keys(DATA.indicators).sort((a,b)=>{
  const A=a.split('.').map(Number), B=b.split('.').map(Number);
  return A[0]-B[0] || A[1]-B[1];});}
function critText(code){const o=DATA.indicators[code]; if(!o) return code;
  return "P"+o.pillar+" "+code+" — "+(o.category||"")+(o.criteria? "\n"+o.criteria:"")+(o.scores.length? "\nScores: "+o.scores.join(" / "):"");}
function relevantIndicators(law){
  const set=new Set([...(law.hints||[]), ...(law.pipeline_got||[])]);
  (law.pillars||[]).forEach(p=>{ rdtiiOrder().forEach(c=>{ if(c.split('.')[0]==String(p)) set.add(c); }); });
  return rdtiiOrder().filter(c=>set.has(c));
}
function esc(s){return (s==null?"":String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function ensure(i){const id="L"+i; if(!state[id]) state[id]={ind:[],verdict:"",score:"",note:""}; return state[id];}
function render(){
  const root=document.getElementById('cards'); root.innerHTML="";
  DATA.laws.forEach((law,i)=>{
    const id="L"+i, st=state[id]||{ind:[],verdict:"",score:"",note:""};
    const card=document.createElement('div'); card.className="card"+(law.priority?" pri":"")+(st.verdict?" done":"");
    const got=law.pipeline_got||[];
    const gotHtml = got.length? got.map(g=>'<span class="tag got">pipeline: '+g+'</span>').join('') : '<span class="tag gotnone">pipeline: found no indicator</span>';
    const hintHtml = (law.hints||[]).map(h=>'<span class="tag hint">our suggestion: '+h+'</span>').join('');
    const chips = relevantIndicators(law).map(c=>{
      const on = st.ind.includes(c)?" on":"";
      const isHint=(law.hints||[]).includes(c), isGot=got.includes(c);
      const mark = isHint?" ·suggested":(isGot?" ·pipeline":"");
      return '<span class="chip'+on+'" data-i="'+i+'" data-c="'+c+'" title="'+critText(c).replace(/"/g,'&quot;')+'">'+c+mark+'</span>';
    }).join('');
    const pri = law.priority? '<div class="pribox"><b>⛑ Priority — open question:</b> '+esc(law.priority)+'</div>':'';
    card.innerHTML =
      '<span class="eco">'+law.economy+'</span> <span class="line" style="color:#888">P'+(law.pillars||[]).join('/')+'</span>'+
      '<div class="lawname">'+esc(law.law_name)+'</div>'+
      '<div class="meta">'+esc(law.version||'')+' &nbsp;·&nbsp; <a href="'+esc(law.url)+'" target="_blank">📄 Open official source</a></div>'+
      pri+
      '<div class="line">'+hintHtml+' '+gotHtml+'</div>'+
      '<div class="prov">'+esc(law.provision)+'</div>'+
      '<div class="line"><b>Which indicator(s) does this provision genuinely support?</b> <span class="crithint">(hover a chip for its RDTII criteria)</span></div>'+
      '<div class="chips">'+chips+'</div>'+
      '<div class="line"><b>RDTII score</b> (optional): <select data-score="'+i+'"><option value="">—</option><option>1</option><option>0.5</option><option>0</option></select></div>'+
      '<div class="verdicts">'+
        '<button class="vbtn'+(st.verdict=="valid"?" on-valid":"")+'" data-v="valid" data-i="'+i+'">✓ Confirm</button>'+
        '<button class="vbtn'+(st.verdict=="flag"?" on-flag":"")+'" data-v="flag" data-i="'+i+'">⛑ Flag for discussion</button>'+
        '<button class="vbtn'+(st.verdict=="reject"?" on-reject":"")+'" data-v="reject" data-i="'+i+'">✗ Reject (not valid evidence)</button>'+
      '</div>'+
      '<textarea data-note="'+i+'" rows="2" placeholder="Optional note / reasoning / correct citation…">'+esc(st.note||"")+'</textarea>';
    root.appendChild(card);
    card.querySelector('[data-score="'+i+'"]').value = st.score||"";
  });
  bind(); progress();
}
function bind(){
  document.querySelectorAll('.chip').forEach(el=>el.onclick=()=>{
    const i=el.dataset.i, c=el.dataset.c, st=ensure(i);
    const k=st.ind.indexOf(c); if(k>=0) st.ind.splice(k,1); else st.ind.push(c);
    el.classList.toggle('on'); save();
  });
  document.querySelectorAll('.vbtn').forEach(el=>el.onclick=()=>{
    const i=el.dataset.i, v=el.dataset.v, st=ensure(i);
    st.verdict = st.verdict==v? "" : v; save(); render();
  });
  document.querySelectorAll('[data-note]').forEach(el=>el.oninput=()=>{ensure(el.dataset.note).note=el.value; save(); progress();});
  document.querySelectorAll('[data-score]').forEach(el=>el.onchange=()=>{ensure(el.dataset.score).score=el.value; save();});
}
function progress(){
  const done=DATA.laws.filter((_,i)=>state["L"+i]&&state["L"+i].verdict).length;
  document.getElementById('prog').style.width=(100*done/DATA.laws.length)+"%";
  document.getElementById('cnt').textContent=done+" / "+DATA.laws.length+" scored";
}
function decisions(){
  return DATA.laws.map((law,i)=>{const st=state["L"+i]||{};
    return {economy:law.economy, law_name:law.law_name, law_id:law.law_id, official_url:law.url,
      our_suggested_indicators:law.hints, pipeline_extracted:law.pipeline_got,
      reviewer_indicators:st.ind||[], reviewer_score:st.score||"", verdict:st.verdict||"(not reviewed)", note:st.note||""};});
}
document.getElementById('expjson').onclick=()=>{
  const payload={reviewer:state.__rev||"", batch:"rdtii-new-law-scoring", exported_at:new Date().toISOString(),
    schema:"1.0", decisions:decisions()};
  dl(JSON.stringify(payload,null,2), "rdtii-scoring-decisions.json", "application/json");
};
document.getElementById('expcsv').onclick=()=>{
  const hdr=["reviewer","economy","law_name","official_url","our_suggested","pipeline_extracted","reviewer_indicators","reviewer_score","verdict","note"];
  const rev=state.__rev||"";
  const rows=decisions().map(d=>[rev,d.economy,d.law_name,d.official_url,(d.our_suggested_indicators||[]).join("|"),
    (d.pipeline_extracted||[]).join("|"),(d.reviewer_indicators||[]).join("|"),d.reviewer_score,d.verdict,(d.note||"").replace(/\n/g," ")]);
  const csv=[hdr,...rows].map(r=>r.map(c=>'"'+String(c==null?"":c).replace(/"/g,'""')+'"').join(",")).join("\n");
  dl("﻿"+csv, "rdtii-scoring-decisions.csv", "text/csv");
};
function dl(text,name,type){const b=new Blob([text],{type});const a=document.createElement('a');
  a.href=URL.createObjectURL(b);a.download=name;a.click();}
render();
</script></body></html>"""


if __name__ == "__main__":
    build()

#!/usr/bin/env python3
"""Build pitch deck PPTX — 8 slides, Aug 3 live pitch."""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x1a, 0x1a, 0x2e)
ACCENT = RGBColor(0x00, 0xd4, 0xaa)
GRAY = RGBColor(0x88, 0x88, 0x99)
LIGHT_GRAY = RGBColor(0xcc, 0xcc, 0xdd)

def add_bg(slide, color=DARK):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_title(slide, text, y=0.3, size=36):
    txBox = slide.shapes.add_textbox(Inches(1), Inches(y), Inches(11.3), Inches(1))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = WHITE
    p.font.bold = True
    return tf

def add_body(slide, text, y=1.5, size=18):
    txBox = slide.shapes.add_textbox(Inches(1), Inches(y), Inches(11.3), Inches(5))
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, line in enumerate(text.split('\n')):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.color.rgb = LIGHT_GRAY
        p.space_after = Pt(6)
    return tf

def add_footer(slide, text):
    txBox = slide.shapes.add_textbox(Inches(1), Inches(6.8), Inches(11.3), Inches(0.5))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(11)
    p.font.color.rgb = GRAY

# ── Slide 1: Title ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "SENTINEL", y=1.5, size=56)
add_body(s, "AI Tool for Digital Trade Regulatory Analysis\n\n\"Where Code Meets Law\"\n\nMaynooth University · UN ESCAP RDTII 2.1 Hackathon\nTeam: Dong (Tech Lead) · Katie (Legal Lead) · Eric · Able · Rujing", y=2.8, size=20)
add_footer(s, "Aug 3, 2026 · Live Pitch")

# ── Slide 2: Problem ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "The Problem We Solve")
add_body(s, "• 809 baseline laws across 7 economies, 12 languages\n\n• Manual regulatory mapping takes weeks per economy\n\n• Trade negotiators need VERIFIABLE evidence, not AI guesses\n\n• Key question: \"Can I trust this mapping?\"\n\n• Our answer: Every quote, character-for-character, source-verifiable")
add_footer(s, "Team SENTINEL · Slide 2/8")

# ── Slide 3: Pipeline ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "How It Works — The Pipeline")
add_body(s, "1. FETCH — Official government portals, TLS impersonation\n2. CHUNK — Split at article boundaries (regex, not NLP)\n3. CLASSIFY — Keyword filter (8 languages) → candidate indicators\n4. EXTRACT — LLM pulls structured facts + verbatim quote\n5. VERIFY — Quote must exist character-for-character in source\n6. SCORE — Deterministic Python (NO AI in the score)\n\n🔑 The AI only EXTRACTS. Everything else is deterministic.", size=17)
add_footer(s, "Team SENTINEL · Slide 3/8")

# ── Slide 4: Live Demo ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "Live Demo")
add_body(s, "Terminal:\n\n  $ python main.py --economy China --pillar 6 \\\n        --max-documents 1 --from-corpus --provider deepseek\n\n→ Reads Chinese data-protection law from verified corpus\n→ Extracts provisions with verbatim quotes\n→ Writes official 13-column CSV\n→ Key-free with --provider ollama\n\n📄 Output: outputs/round2_submission_merged/all_economies_merged.csv\n   1,456 rows · 171/229 cells (74.7%)", size=17)
add_footer(s, "Team SENTINEL · Slide 4/8")

# ── Slide 5: Numbers ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "Results — By the Numbers")
add_body(s, "Official cell coverage  171/229 (74.7%)\nVerbatim grounding     96.2% (char-for-char in source)\nBlind-verifier override 29% (independent checker catches over-scores)\nDeployment cost         $12.96 full run / $0 open-weight\nTest suite              887 passed\nEconomies               7 (CHN/IND/IDN/LAO/MNG/RUS/THA)\nPillars                 All 12 (61 indicators)\nLanguages               8 (EN/ZH/HI/ID/LO/MN/RU/TH)\nKey-free                Yes (DuckDuckGo Lite → Bing cascade)", size=17)
add_footer(s, "Every number reproducible: coverage_report.py · cost_report.py")

# ── Slide 6: Different ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "What Makes Us Different")
add_body(s, "1. Deterministic scoring — the model never picks the number\n\n2. Anti-hallucination kill switch — unverifiable quote → dropped\n\n3. Key-free by design — judges run without any paid API key\n\n4. Reproducible — same input = same output, every time\n\n5. Honest about gaps — every uncovered cell categorized by root cause\n\n6. Self-auditing — we found our own gate was dropping 125 names → fixed → +4 cells, $0.93", size=17)
add_footer(s, "Team SENTINEL · Slide 6/8")

# ── Slide 7: Rigor ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "Engineering Rigor")
add_body(s, "• 887 automated tests — pipeline, scoring, verification, discovery, OCR\n\n• SHA-256 corpus integrity — corrupted text detected before it poisons output\n\n• Headful browser scraper — JS-rendered government portals\n\n• PDF OCR pipeline — scanned laws in 8 languages\n\n• RusLawOD integration — 304K Russian laws (CC-BY, streaming)\n\n• Real incident: crawler saved Wayback UI as \"law\" → SHA-256 caught it\n  → 11 polluted cells, zero escaped. Vaccine deployed same night.\n\nEvery headline number is reproducible with one command.", size=16)
add_footer(s, "Team SENTINEL · Slide 7/8")

# ── Slide 8: Thank You ──
s = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(s)
add_title(s, "Thank You + Q&A", y=1.5, size=48)
add_body(s, "The engine is loaded and ready.\nPick any economy and pillar — we'll run it for you.\n\nTeam: Dong · Katie · Eric · Able · Rujing\nGitHub: github.com/22abad/UN-DigitalTrade-AI-Mapper-private\n\nSENTINEL — Where Code Meets Law", y=3.0, size=20)
add_footer(s, "Aug 3, 2026 · Live Pitch · 8 min presentation + 7 min Q&A")

output = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/outputs/pitch-deck-20260803.pptx"
prs.save(output)
print(f"Saved: {output}")

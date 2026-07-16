# Pluggable embedding backend — comparison for the deck

> One env var swaps the embedder: `EMBEDDING_PROVIDER=local | gemini`.
> This is the **no-vendor-lock-in** story applied to embeddings, not just the LLM.
> Screenshot the table below straight into the Architecture slide.

## The one-line pitch
**"We don't lock you to one embedder. Default: an open-weight model that runs fully
offline, no API key. Optional: a free-tier cloud embedder for zero-cash scale.
Your infrastructure, your choice — one environment variable."**

## Comparison table (paste into PPT)

| | **Local (default)** | **Gemini (optional)** |
|---|---|---|
| Model | `all-MiniLM-L6-v2` (open-weight) | Google `text-embedding-004` |
| Vector size | 384-dim | 768-dim |
| **Cash cost** | $0 (your own compute) | **$0 (free tier)** |
| Runs offline / on a plane | ✅ yes | ❌ needs internet |
| Needs an API key | ❌ no | ✅ `GOOGLE_API_KEY` |
| Self-hostable | ✅ fully | ⚠️ calls Google |
| Vendor lock-in | ✅ none | ⚠️ Google dependency |
| Data-privacy note | text never leaves the box | public law text only → **no confidentiality issue** |
| Best for | the judge run, air-gapped demos, reproducibility | zero-cost bulk re-embedding when online |

## Why default = local (the point judges reward)
The rubric explicitly requires **open-source, self-hostable, no vendor lock-in**
(Architecture = 30%; Resilience = 30% rewards offline runs). So the *default* must
be the offline open-weight model. Gemini is offered as a **pluggable option**, which
turns "free Google compute" from a liability (lock-in) into an **asset** — it is a
second, live demonstration that the whole stack is provider-swappable.

## Honest caveats (put in speaker notes, not on the slide)
- **Different backends → different vector dimensions** (384 vs 768). You cannot mix
  them in one pgvector index — switch the backend for the *whole corpus* at ingest
  time, then query with the same backend. (The code enforces one active provider.)
- Gemini's free tier is **rate-limited** and **needs a key + internet**, so it is
  *not* used on the offline / judge path — it is an online cost-optimisation.
- **Google Drive full-text search ≠ embeddings.** Drive OCRs and keyword-indexes
  files, but does not expose queryable vectors; **NotebookLM** does real RAG but has
  **no public API**. The callable free path is the **Gemini Embedding API** — which
  is exactly what the `gemini` provider uses.

## NEW-law → knowledge base, embedded
`tools/promote_new_law.py --embed` now pushes a freshly-discovered NEW law straight
into the searchable vector store, embedded via the active provider — so a discovery
becomes instantly retrievable in the web RAG (local by default, or free-tier Gemini
if configured). Discovery → library → embedded knowledge base, in one command.

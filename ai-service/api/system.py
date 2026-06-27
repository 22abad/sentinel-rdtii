from __future__ import annotations

import json
import os

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from providers import list_providers
from schemas import RAGQueryRequest

router = APIRouter()


class TextRequest(BaseModel):
    text: str


@router.get("/health")
def health():
    import main as main_module

    raw, canonical = main_module._active_provider_name()
    return {
        "status": "ok" if canonical else "misconfigured",
        "provider_env": raw,
        "active_provider": canonical,
        "available_providers": list_providers(),
    }


@router.get("/providers")
def providers_info():
    import main as main_module

    raw, canonical = main_module._active_provider_name()
    if canonical is None:
        return {
            "active": None,
            "active_alias": raw,
            "name_recognised": False,
            "available": list_providers(),
        }
    return {
        "active": canonical,
        "active_alias": raw if raw != canonical else None,
        "name_recognised": True,
        "available": list_providers(),
    }


@router.get("/providers/ollama-models")
def ollama_models():
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    api_base = base.rstrip("/v1").rstrip("/")
    url = f"{api_base}/api/tags"
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        models = [model["name"] for model in data.get("models", [])]
        return {"models": sorted(models), "error": None}
    except Exception as exc:
        return {"models": [], "error": str(exc)}


@router.post("/embed")
def embed(req: TextRequest):
    import main as main_module
    from sklearn.preprocessing import normalize

    vector = main_module._get_embed_model().encode([req.text])
    vector = normalize(vector)
    return {"vector": vector[0].tolist()}


_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.6")

_RDTII_SYSTEM_PROMPT = """You are a UN ESCAP digital trade policy analyst specializing in the Regional Digital Trade Integration Index (RDTII) 2.1 framework.

Your role is to help researchers and policymakers evaluate a country's digital trade policies using the RDTII 2.1 methodology.

CORE KNOWLEDGE:
- RDTII covers 12 pillars: Tariffs, Public Procurement, FDI, Intellectual Property Rights, Telecom Regulations, Cross-border Data Policies, Data Protection & Privacy, Intermediary Liability, Content Access, Non-technical NTMs, Standards & Procedures, Online Sales & Transactions.
- Each pillar contains multiple indicators scored {0, 0.25, 0.5, 0.75, 1.0} where 0 = most open / least restrictive and 1 = most restrictive.
- Scoring follows deterministic rules (e.g. a comprehensive data protection law -> score 0 for indicator 7.1; no law -> score 1).
- The LLM extracts structured features from legal text; scores are computed by deterministic Python code.

RESPONSE GUIDELINES:
- Be precise and reference specific RDTII pillars/indicators when relevant.
- Ground your analysis in the legal text provided in the context.
- Explain which provisions of the law map to which indicators.
- If asked about scoring, describe the criteria but do NOT output a final score (that is the system's job).
- Keep answers concise and actionable for a policy audience.
- If the context includes specific legal text, quote relevant clauses before analyzing them."""


@router.post("/api/rag/query")
async def chat_query(req: RAGQueryRequest):
    parts = [f"Question: {req.question}"]
    if req.role:
        parts.insert(0, f"Your role: {req.role}")
    if req.context:
        parts.append(f"Additional context: {req.context}")
    if req.country_code:
        parts.append(f"Country / Economy under review: {req.country_code}")
    if req.source_text:
        parts.append(f"Legal text being analyzed:\n\"\"\"\n{req.source_text}\n\"\"\"")
    user_prompt = "\n\n".join(parts)

    client = OpenAI(base_url=_OLLAMA_BASE, api_key="ollama")

    async def _stream():
        try:
            stream = client.chat.completions.create(
                model=_OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _RDTII_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                temperature=0.3,
            )
            full_answer = ""
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    full_answer += content
                    yield f"event: token\ndata: {json.dumps(content)}\n\n"

            payload = {"answer": full_answer, "provider": f"ollama/{_OLLAMA_MODEL}"}
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


"""Keyword generation helpers.

Goal: improve recall for listing search without hallucinating categories.
- Deterministic baseline always works.
- Optional OpenAI enhancement can be plugged by passing a coroutine `llm_generate`.

Return schema:
  {"keywords": [..], "keywords_text": "..."}
"""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional


def _normalize_keyword(token: str) -> Optional[str]:
    token = (token or "").strip().lower()
    if not token:
        return None

    token = re.sub(r"\s+", " ", token).strip()
    token = token.strip("-•,.;:()[]{}\"'“”‘’")

    if token in {"ürün", "esya", "eşya", "satılık", "satilik", "ikinci el", "2. el"}:
        return None
    if len(token) < 2:
        return None
    return token


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        k = it.lower().strip()
        if not k or k in seen:
            continue
        out.append(it)
        seen.add(k)
    return out


def generate_listing_keywords_deterministic(
    *,
    title: str,
    category: str,
    description: str = "",
    condition: str = "",
    vision_product: Optional[Dict[str, Any]] = None,
    max_keywords: int = 12,
) -> Dict[str, Any]:
    title = (title or "").strip()
    category = (category or "").strip()
    description = (description or "").strip()

    if not title:
        return {"keywords": [], "keywords_text": ""}

    blob = " ".join([title, category, description, condition]).lower()

    tokens = re.findall(r"[0-9a-zçğıöşü+]{2,}", blob)
    tokens = [_normalize_keyword(t) for t in tokens]
    tokens = [t for t in tokens if t]

    # Category boosters (safe synonyms)
    boosters: List[str] = []
    cat_lc = category.lower()

    if "otomotiv" in cat_lc:
        boosters += ["araba", "otomobil", "araç", "vasıta"]
    if "emlak" in cat_lc:
        boosters += ["ev", "daire", "konut"]
        # Keep room formats if present
        boosters += re.findall(r"\b\d\+\d\b", blob)
    if "elektronik" in cat_lc:
        boosters += ["telefon", "elektronik"]

    merged = _dedupe_preserve_order([*boosters, *tokens])
    merged = merged[: max(1, int(max_keywords))]

    return {"keywords": merged, "keywords_text": " ".join(merged)}


async def generate_listing_keywords(
    *,
    title: str,
    category: str,
    description: str = "",
    condition: str = "",
    vision_product: Optional[Dict[str, Any]] = None,
    max_keywords: int = 12,
    llm_generate: Optional[Callable[[str, str], Awaitable[str]]] = None,
) -> Dict[str, Any]:
    """Best-effort: try LLM if provided, else deterministic."""

    base = generate_listing_keywords_deterministic(
        title=title,
        category=category,
        description=description,
        condition=condition,
        vision_product=vision_product,
        max_keywords=max_keywords,
    )

    if llm_generate is None:
        return base

    # Ask the model for extra keyword ideas; merge with deterministic.
    system = (
        "Sen bir ilan anahtar kelime üretim asistanısın. "
        "SADECE JSON döndür: {\"keywords\": [..]}. "
        "Kurallar: Türkçe; 6-12 anahtar kelime; küçük harf; tekrar yok; emoji/noktalama yok; "
        "PII yok (telefon/isim/adres yok), fiyat yok."
    )

    payload = {
        "title": (title or "").strip(),
        "category": (category or "").strip(),
        "description": (description or "").strip(),
        "condition": (condition or "").strip(),
        "vision": vision_product or {},
        "max_keywords": int(max_keywords),
    }

    user = f"ILAN_JSON: {json.dumps(payload, ensure_ascii=False)}"

    try:
        text = (await llm_generate(system, user)).strip()
        data = json.loads(text) if text else {}
        raw = data.get("keywords") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return base

        extra: List[str] = []
        for t in raw:
            kw = _normalize_keyword(str(t))
            if kw:
                extra.append(kw)
        extra = _dedupe_preserve_order(extra)

        merged = _dedupe_preserve_order([*(base.get("keywords") or []), *extra])
        merged = merged[: max(1, int(max_keywords))]
        return {"keywords": merged, "keywords_text": " ".join(merged)}
    except Exception:
        return base

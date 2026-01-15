from __future__ import annotations

import re
from typing import Any

from supabase import Client


def search_listings(supabase: Client, query: str, limit: int = 6) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    keywords = [k for k in re.split(r"\s+", q) if k][:4]
    if not keywords:
        return []

    ors: list[str] = []
    meta_ors: list[str] = []
    for kw in keywords:
        safe = kw.replace(",", " ")
        ors.append(f"title.ilike.%{safe}%")
        ors.append(f"description.ilike.%{safe}%")
        meta_ors.append(f"metadata->>keywords_text.ilike.%{safe}%")

    def _run(or_str: str):
        return (
            supabase.table("listings")
            .select("id,title,price,location,category,condition,images,created_at")
            .eq("status", "active")
            .or_(or_str)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    try:
        res = _run(",".join([*ors, *meta_ors]))
    except Exception:
        res = _run(",".join(ors))
    return res.data or []

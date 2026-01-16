from __future__ import annotations

import re
from typing import Any

from supabase import Client


def search_listings(supabase: Client, query: str, limit: int = 6) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    # Extract price range if exists
    price_min, price_max = _extract_price_range(q)
    
    # Extract location hints
    location_hint = _extract_location_hint(q)

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
        base_query = (
            supabase.table("listings")
            .select("id,title,price,location,category,condition,images,created_at")
            .eq("status", "active")
            .or_(or_str)
        )
        
        # Apply price filters if found
        if price_min is not None:
            base_query = base_query.gte("price", price_min)
        if price_max is not None:
            base_query = base_query.lte("price", price_max)
        
        # Apply location filter if found
        if location_hint:
            base_query = base_query.ilike("location", f"%{location_hint}%")
        
        return base_query.order("created_at", desc=True).limit(limit).execute()

    try:
        res = _run(",".join([*ors, *meta_ors]))
    except Exception:
        res = _run(",".join(ors))
    return res.data or []


def _extract_price_range(query: str) -> tuple[float | None, float | None]:
    """Extract price range from queries like '10000-20000 tl' or 'under 50000'"""
    q = query.lower()
    
    # Range pattern: "10000-20000", "10k-20k"
    range_match = re.search(r"(\d+(?:k|bin|b)?)\s*[-–]\s*(\d+(?:k|bin|b)?)", q)
    if range_match:
        min_val = _parse_number(range_match.group(1))
        max_val = _parse_number(range_match.group(2))
        return min_val, max_val
    
    # Under/below pattern: "50000 altı", "under 50k"
    under_match = re.search(r"(\d+(?:k|bin|b)?)\s*(?:altı|altında|under|below)", q)
    if under_match:
        max_val = _parse_number(under_match.group(1))
        return None, max_val
    
    # Over/above pattern: "100000 üstü", "over 100k"
    over_match = re.search(r"(\d+(?:k|bin|b)?)\s*(?:üstü|üstünde|over|above)", q)
    if over_match:
        min_val = _parse_number(over_match.group(1))
        return min_val, None
    
    return None, None


def _parse_number(s: str) -> float | None:
    """Parse '50k', '100bin' to numbers"""
    s = s.lower().strip()
    if s.endswith('k'):
        return float(s[:-1]) * 1000
    if s.endswith('bin') or s.endswith('b'):
        return float(re.sub(r'[^0-9]', '', s)) * 1000
    try:
        return float(s)
    except Exception:
        return None


def _extract_location_hint(query: str) -> str | None:
    """Extract location from query"""
    q = query.lower()
    # Common Turkish cities
    cities = [
        "istanbul", "ankara", "izmir", "bursa", "antalya", "adana", "konya",
        "gaziantep", "şanlıurfa", "kocaeli", "mersin", "diyarbakır", "kayseri",
        "eskişehir", "izmit", "trabzon", "balıkesir", "malatya", "erzurum"
    ]
    for city in cities:
        if city in q:
            return city
    return None

from __future__ import annotations

import re
from typing import Any

from app.core.helpers import extract_price_try
from app.services.category_library import normalize_category_id


def extract_simple_fields(message: str) -> dict[str, Any]:
    msg = (message or "").strip()
    patch: dict[str, Any] = {}

    p = extract_price_try(msg)
    if p is not None:
        if re.search(r"\b(tl|₺)\b", msg.lower()) or re.fullmatch(r"\s*\d{2,7}\s*", msg):
            patch["price"] = p

    loc = None
    mloc = re.search(r"(?:konum\s*:\s*)?([A-Za-zÇĞİÖŞÜçğıöşü\s]{3,20})$", msg)
    if mloc:
        candidate = mloc.group(1).strip()
        candidate_lc = candidate.lower()
        blocked_location = ["tl", "try", "lira", "türk lirası", "turk lirasi", "arıyorum", "aramak", "var mı", "varmi"]
        if len(candidate.split()) <= 3 and not any(b in candidate_lc for b in blocked_location):
            loc = candidate
    if loc:
        patch["location"] = loc

    cat = normalize_category_id(msg)
    if cat:
        patch["category"] = cat

    if len(msg) >= 4 and not any(k in msg.lower() for k in ["ara", "bul", "listele", "onaylıyorum", "yayınla", "iptal"]):
        if not re.fullmatch(r"\d{2,7}", msg.strip()):
            clean_title = msg
            if p is not None:
                clean_title = re.sub(r"(?<!\d)\d{2,7}\s*(?:tl|₺)?(?!\d)", "", clean_title, flags=re.IGNORECASE)
            if loc:
                clean_title = re.sub(rf"\b{re.escape(loc)}\b", "", clean_title, flags=re.IGNORECASE)
            clean_title = re.sub(r"\s+", " ", clean_title).strip()
            if len(clean_title) >= 3 and not re.fullmatch(r"\d{2,7}", clean_title):
                patch.setdefault("title", clean_title[:80])

    attributes: dict[str, Any] = {}

    # Vehicle-specific attribute extraction
    m_year = re.search(r"\b(19\d{2}|20\d{2})\b", msg)
    if m_year:
        attributes["year"] = m_year.group(1)
    m_km = re.search(r"\b(\d{1,3}(?:[\.,]\d{3})+|\d{1,7})\s*km\b", msg.lower())
    if m_km:
        attributes["km"] = m_km.group(1).replace(".", "").replace(",", "")
    if re.search(r"\b(dizel|diesel)\b", msg.lower()):
        attributes["fuel"] = "Dizel"
    if re.search(r"\b(benzin|benz?n)\b", msg.lower()):
        attributes["fuel"] = "Benzin"
    if re.search(r"\b(hibrit|hybrid)\b", msg.lower()):
        attributes["fuel"] = "Hibrit"
    if re.search(r"\b(elektrik|elektrikli)\b", msg.lower()):
        attributes["fuel"] = "Elektrik"
    if re.search(r"\b(lpg)\b", msg.lower()):
        attributes["fuel"] = "LPG"
    if re.search(r"\b(otomatik)\b", msg.lower()):
        attributes["transmission"] = "Otomatik"
    if re.search(r"\b(manuel)\b", msg.lower()):
        attributes["transmission"] = "Manuel"
    if re.search(r"\b(yarı otomatik|yarı-otomatik)\b", msg.lower()):
        attributes["transmission"] = "Yarı otomatik"
    if re.search(r"\b(tramer yok|hasar kaydı yok|hasar kaydi yok)\b", msg.lower()):
        attributes["tramer"] = "Yok"
    m_tramer = re.search(r"\btramer\s*[:=\-]?\s*(\d+[\.,]?\d*)\b", msg.lower())
    if m_tramer:
        attributes["tramer"] = m_tramer.group(1)

    # Electronics attributes
    m_storage = re.search(r"\b(\d{2,4})\s*gb\b", msg.lower())
    if m_storage:
        attributes["storage"] = f"{m_storage.group(1)}GB"
    m_ram = re.search(r"\b(\d{1,2})\s*gb\s*ram\b", msg.lower())
    if m_ram:
        attributes["ram"] = f"{m_ram.group(1)}GB"
    if re.search(r"\b(garanti var|garantili)\b", msg.lower()):
        attributes["warranty"] = "Var"
    if re.search(r"\b(garanti yok)\b", msg.lower()):
        attributes["warranty"] = "Yok"

    # Apparel attributes
    m_size = re.search(r"\b(xs|s|m|l|xl|xxl|\d{2,3})\b", msg.lower())
    if m_size:
        attributes["size"] = m_size.group(1).upper()
    if re.search(r"\b(deri|pamuk|kot|kumas|kumaş)\b", msg.lower()):
        attributes["material"] = re.search(r"\b(deri|pamuk|kot|kumas|kumaş)\b", msg.lower()).group(1)

    if attributes:
        patch["attributes"] = attributes

    return patch

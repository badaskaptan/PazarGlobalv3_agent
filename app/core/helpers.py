from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_uuid(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value or ""))


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D+", "", raw)
    return digits or None


def extract_price_try(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"(?<!\d)(\d{2,7})(?:\s*(?:tl|₺))?(?!\d)", text.lower())
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _looks_like_location(msg: str) -> bool:
    mloc = re.search(r"(?:konum\s*:\s*)?([A-Za-zÇĞİÖŞÜçğıöşü\s]{3,20})$", msg)
    if not mloc:
        return False
    candidate = mloc.group(1).strip()
    return bool(candidate and len(candidate.split()) <= 3)


def _looks_like_listing_packet(msg: str) -> bool:
    has_price = extract_price_try(msg) is not None
    has_location = _looks_like_location(msg)
    has_words = len(re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", msg)) >= 2
    return has_price and (has_location or has_words)


def detect_intent(message: str) -> Tuple[str, float]:
    msg = (message or "").lower().strip()
    if not msg:
        return "UNKNOWN", 0.0

    if any(k in msg for k in ["selam", "merhaba", "hey", "sa", "selamlar", "günaydın", "iyi akşamlar", "iyi günler"]):
        return "SMALL_TALK", 0.9

    if any(k in msg for k in ["iptal", "vazgeç", "kapat", "cancel", "stop"]):
        return "CANCEL", 0.95

    if any(k in msg for k in ["onaylıyorum", "yayınla", "yayınlayalım", "paylaş", "publish"]):
        return "COMMIT_REQUEST", 0.9

    if any(k in msg for k in ["ara", "bul", "listele", "ilanları", "var mı", "fiyat araştır", "fiyat bak"]):
        return "SEARCH_LISTING", 0.75

    if any(k in msg for k in ["sat", "satılık", "ilan ver", "ilan oluştur", "yayına", "ürün sat"]):
        return "CREATE_LISTING", 0.8

    if _looks_like_listing_packet(msg):
        return "AMBIGUOUS", 0.55

    if extract_price_try(msg) is not None:
        return "AMBIGUOUS", 0.5

    return "UNKNOWN", 0.4

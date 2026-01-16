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

    greeting_tokens = ["selam", "merhaba", "hey", "sa", "selamlar", "günaydın", "iyi akşamlar", "iyi günler"]
    smalltalk_tokens = ["nasılsın", "naber", "ne haber", "hayat nasıl", "nasıl gidiyor", "iyisin", "iyi misin"]
    if any(k == msg or msg.startswith(f"{k} ") for k in greeting_tokens):
        if len(msg.split()) <= 2 and extract_price_try(msg) is None:
            return "SMALL_TALK", 0.9
    if any(k in msg for k in smalltalk_tokens):
        if extract_price_try(msg) is None:
            return "SMALL_TALK", 0.85

    if any(k in msg for k in ["iptal", "vazgeç", "kapat", "cancel", "stop"]):
        return "CANCEL", 0.95

    if any(k in msg for k in ["onaylıyorum", "yayınla", "yayınlayalım", "paylaş", "publish"]):
        return "COMMIT_REQUEST", 0.9

    # CREATE intent - önce kontrol et (SEARCH'ten önce!)
    create_patterns = [
        "ilan ver", "ilan vermek", "ilan oluştur", "ilan yayınla",
        "sat", "satılık", "satmak", "yayına", "ürün sat",
        "ekle", "eklemek", "paylaş", "paylaşmak"
    ]
    if any(k in msg for k in create_patterns):
        return "CREATE_LISTING", 0.85

    # SEARCH intent - güçlendirilmiş pattern matching
    search_verbs = ["ara", "bul", "listele", "göster", "aranır", "bulabilir", "lazım", "bakmak"]
    search_markers = ["arıyorum", "aramak", "var mı", "varmı", "var mi", "varmi", "ilanları", "ilanlar", "ilanlara"]
    search_confidence = 0.0
    
    # "istiyorum" sadece CREATE pattern'leri yoksa SEARCH olarak kabul et
    for verb in search_verbs:
        if verb in msg:
            search_confidence = max(search_confidence, 0.75)
            break
    
    # "istiyorum" kelimesi varsa ve CREATE değilse → SEARCH
    if "istiyorum" in msg and search_confidence == 0.0:
        search_confidence = 0.75
    
    for marker in search_markers:
        if marker in msg:
            search_confidence = max(search_confidence, 0.8)
            break
    
    # "fiyat araştır" patterns
    if any(k in msg for k in ["fiyat araştır", "fiyat bak", "ne kadar", "piyasa fiyatı"]):
        return "SEARCH_LISTING", 0.85
    
    if search_confidence > 0.0:
        return "SEARCH_LISTING", search_confidence

    # AMBIGUOUS - price + location but no clear verb
    if _looks_like_listing_packet(msg):
        return "AMBIGUOUS", 0.55

    if extract_price_try(msg) is not None:
        return "AMBIGUOUS", 0.5

    return "UNKNOWN", 0.4

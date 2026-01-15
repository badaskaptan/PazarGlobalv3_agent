from __future__ import annotations

import re
from typing import Any


_TR_MAP = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "İ": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "Ç": "c",
    "Ğ": "g",
    "Ö": "o",
    "Ş": "s",
    "Ü": "u",
})


def _norm(text: str) -> str:
    return (text or "").strip().lower().translate(_TR_MAP)


def _as_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _pick_first(*values: Any) -> str:
    for v in values:
        s = _as_str(v)
        if s:
            return s
    return ""


def _collect_attributes(listing_data: dict[str, Any], vision: dict[str, Any]) -> dict[str, str]:
    attrs: dict[str, str] = {}
    raw_attrs = _as_dict(listing_data.get("attributes"))

    def put(key: str, *values: Any) -> None:
        val = _pick_first(*values)
        if val:
            attrs[key] = val

    put("brand", listing_data.get("brand"), raw_attrs.get("brand"), vision.get("brand"))
    put("model", listing_data.get("model"), raw_attrs.get("model"), vision.get("model"))
    put("color", listing_data.get("color"), raw_attrs.get("color"), vision.get("color"))
    put("year", listing_data.get("year"), raw_attrs.get("year"))
    put("km", listing_data.get("km"), raw_attrs.get("km"))
    put("fuel", listing_data.get("fuel"), raw_attrs.get("fuel"))
    put("transmission", listing_data.get("transmission"), raw_attrs.get("transmission"))
    put("engine", listing_data.get("engine"), raw_attrs.get("engine"))
    put("tramer", listing_data.get("tramer"), raw_attrs.get("tramer"))
    put("warranty", listing_data.get("warranty"), raw_attrs.get("warranty"))
    put("storage", listing_data.get("storage"), raw_attrs.get("storage"))
    put("ram", listing_data.get("ram"), raw_attrs.get("ram"))
    put("battery", listing_data.get("battery"), raw_attrs.get("battery"))
    put("usage", listing_data.get("usage"), raw_attrs.get("usage"))
    put("features", listing_data.get("features"), raw_attrs.get("features"))

    return attrs


def enrich_title(title: str, listing_data: dict[str, Any], vision: dict[str, Any]) -> str:
    base = _as_str(title)
    if not base:
        return ""

    max_extra = max(10, int(len(base) * 0.3))
    attrs = _collect_attributes(listing_data, vision)

    candidates: list[str] = []
    for key in ["brand", "model", "storage", "ram", "color", "year"]:
        val = attrs.get(key)
        if not val:
            continue
        if _norm(val) in _norm(base):
            continue
        candidates.append(val)

    if not candidates:
        return base

    suffix_parts: list[str] = []
    remaining = max_extra
    for c in candidates:
        if len(c) + 1 > remaining:
            continue
        suffix_parts.append(c)
        remaining -= len(c) + 1
        if remaining <= 0:
            break

    if not suffix_parts:
        return base

    return f"{base} {', '.join(suffix_parts)}".strip()


def compose_description(listing_data: dict[str, Any], vision: dict[str, Any] | None = None) -> str:
    vision_data = _as_dict(vision)
    title = _as_str(listing_data.get("title"))
    category = _as_str(listing_data.get("category"))
    condition = _as_str(listing_data.get("condition")) or "2.el"
    location = _as_str(listing_data.get("location"))
    price = _as_str(listing_data.get("price"))
    notes_raw = _pick_first(listing_data.get("description_notes"), listing_data.get("notes"), _as_dict(listing_data.get("attributes")).get("notes"))

    attrs = _collect_attributes(listing_data, vision_data)

    lines: list[str] = []
    if title:
        lines.append(f"{title} ilanıdır.")
    else:
        lines.append("İlan detayları aşağıdadır.")

    meta_bits: list[str] = []
    if condition:
        meta_bits.append(f"Durum: {condition}")
    if meta_bits:
        lines.append(" · ".join(meta_bits) + ".")

    cat_norm = _norm(category)
    is_vehicle = cat_norm == _norm("Otomotiv") or any(k in cat_norm for k in ["araba", "otomobil", "motosiklet", "arac", "vasita"]) 

    if is_vehicle:
        vehicle_bits: list[str] = []
        for label, key in [
            ("Yıl", "year"),
            ("KM", "km"),
            ("Yakıt", "fuel"),
            ("Vites", "transmission"),
            ("Motor", "engine"),
            ("Tramer", "tramer"),
            ("Renk", "color"),
        ]:
            val = attrs.get(key)
            if val:
                vehicle_bits.append(f"{label}: {val}")
        if vehicle_bits:
            lines.append("Öne çıkanlar: " + ", ".join(vehicle_bits) + ".")
    else:
        generic_bits: list[str] = []
        for label, key in [
            ("Marka", "brand"),
            ("Model", "model"),
            ("Renk", "color"),
            ("Depolama", "storage"),
            ("RAM", "ram"),
            ("Garanti", "warranty"),
        ]:
            val = attrs.get(key)
            if val:
                generic_bits.append(f"{label}: {val}")
        if generic_bits:
            lines.append("Öne çıkanlar: " + ", ".join(generic_bits) + ".")

    vision_condition = _as_str(vision_data.get("condition"))
    vision_color = _as_str(vision_data.get("color"))
    vision_bits: list[str] = []
    if vision_condition:
        vision_bits.append(f"Görsellerdeki durum: {vision_condition}")
    if vision_color and not attrs.get("color"):
        vision_bits.append(f"Görsellerdeki renk: {vision_color}")
    if vision_bits:
        lines.append(" · ".join(vision_bits) + ".")

    cleaned_notes = notes_raw
    if cleaned_notes:
        cleaned_notes = re.sub(r"\b\d{7,}\b", "", cleaned_notes)
        cleaned_notes = re.sub(r"\b\d{2,7}\s*(?:tl|₺)\b", "", cleaned_notes, flags=re.IGNORECASE)
        if location:
            cleaned_notes = re.sub(rf"\b{re.escape(location)}\b", "", cleaned_notes, flags=re.IGNORECASE)
        cleaned_notes = re.sub(r"\s+", " ", cleaned_notes).strip()
        if cleaned_notes:
            lines.append(f"Ek bilgiler: {cleaned_notes}.")

    lines.append("Bilgiler kullanıcı beyanına ve görsellere dayanır.")
    lines.append("Doğru alıcı için iyi bir seçenek.")

    return "\n".join([ln for ln in lines if ln.strip()])


def get_description_question(category: str, listing_data: dict[str, Any]) -> str | None:
    cat_norm = _norm(category)
    attrs = _as_dict(listing_data.get("attributes"))

    is_vehicle = cat_norm == _norm("Otomotiv") or any(k in cat_norm for k in ["araba", "otomobil", "motosiklet", "arac", "vasita"])
    is_electronic = cat_norm == _norm("Elektronik") or any(k in cat_norm for k in ["telefon", "laptop", "bilgisayar", "tv", "tablet"])
    is_apparel = any(k in cat_norm for k in ["moda", "aksesuar", "giyim", "kıyafet", "ayakkabı"])
    is_home = any(k in cat_norm for k in ["ev", "yasam", "mobilya", "dekorasyon"])

    if is_vehicle:
        needed = [k for k in ["year", "km", "fuel", "transmission", "tramer"] if not _as_str(attrs.get(k))]
        if needed:
            return (
                "Açıklamayı daha iyi hazırlamak için isterseniz şu bilgileri paylaşabilirsiniz: "
                "Yıl, KM, Yakıt, Vites, Tramer/hasar durumu, servis geçmişi. "
                "İstemiyorsanız atlayabilirsiniz."
            )

    if is_electronic:
        needed = [k for k in ["storage", "ram", "warranty"] if not _as_str(attrs.get(k))]
        if needed:
            return (
                "Açıklamayı netleştirmek için isterseniz ürün özelliklerini paylaşabilirsiniz: "
                "Depolama/kapasite, RAM, garanti durumu. "
                "İstemiyorsanız atlayabilirsiniz."
            )

    if is_apparel:
        needed = [k for k in ["size", "material"] if not _as_str(attrs.get(k))]
        if needed:
            return "Açıklama için isterseniz beden ve materyal bilgisini paylaşabilirsiniz. İstemiyorsanız atlayabilirsiniz."

    if is_home:
        if not _as_str(attrs.get("dimensions")):
            return "Açıklama için isterseniz ölçü/boyut bilgisini paylaşabilirsiniz. İstemiyorsanız atlayabilirsiniz."

    return None

from __future__ import annotations

from typing import Any, cast

from supabase import Client

from app.core.helpers import now_iso, is_uuid


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Supabase JSON response'ını safely dict'e convert et."""
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def draft_missing_fields(draft: dict[str, Any]) -> list[str]:
    listing_data = _ensure_dict(draft.get("listing_data"))
    missing: list[str] = []

    def need(field: str) -> bool:
        v = listing_data.get(field)
        if v is None:
            return True
        if isinstance(v, str) and not v.strip():
            return True
        return False

    for f in ["title", "category", "price", "location"]:
        if need(f):
            missing.append(f)

    return missing


def format_preview(draft: dict[str, Any]) -> str:
    listing_data = _ensure_dict(draft.get("listing_data"))
    title = listing_data.get("title") or "(başlık yok)"
    category = listing_data.get("category") or "(kategori yok)"
    price = listing_data.get("price") or "(fiyat yok)"
    location = listing_data.get("location") or "(konum yok)"
    condition = listing_data.get("condition") or "2.el"
    description = listing_data.get("description")
    description_text = description if isinstance(description, str) and description.strip() else "(açıklama yok)"

    return (
        "🧾 Taslak Önizleme\n"
        f"• Başlık: {title}\n"
        f"• Kategori: {category}\n"
        f"• Fiyat: {price} ₺\n"
        f"• Konum: {location}\n"
        f"• Durum: {condition}\n"
        f"• Açıklama: {description_text}\n\n"
        "Yayınlamak isterseniz 'onaylıyorum' yazın. Değiştirmek isterseniz yeni bilgiyi yazmanız yeterli."
    )


def get_or_create_draft(supabase: Client, user_id: str) -> dict[str, Any]:
    if not is_uuid(user_id):
        raise ValueError("user_id uuid olmalı (webchat login gerekli)")

    existing = (
        supabase.table("active_drafts")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )

    rows = (existing.data or []) if hasattr(existing, "data") else []
    if rows:
        return cast(dict[str, Any], rows[0])

    created = supabase.table("active_drafts").insert(
        {"user_id": user_id, "state": "DISCOVERY_MODE", "listing_data": {}, "images": {}}
    ).execute()

    created_rows = (created.data or []) if hasattr(created, "data") else []
    if not created_rows:
        reread = (
            supabase.table("active_drafts")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        reread_rows = (reread.data or []) if hasattr(reread, "data") else []
        if reread_rows:
            return cast(dict[str, Any], reread_rows[0])
        raise RuntimeError("Draft oluşturulamadı")

    return cast(dict[str, Any], created_rows[0])


def patch_draft_fields(supabase: Client, draft_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    if not patch:
        current = supabase.table("active_drafts").select("*").eq("id", draft_id).limit(1).execute()
        rows = (current.data or []) if hasattr(current, "data") else []
        if not rows:
            raise RuntimeError("Draft bulunamadı")
        return cast(dict[str, Any], rows[0])

    current = supabase.table("active_drafts").select("listing_data").eq("id", draft_id).limit(1).execute()
    rows = (current.data or []) if hasattr(current, "data") else []
    if not rows:
        raise RuntimeError("Draft bulunamadı")

    listing_data = _ensure_dict(cast(dict[str, Any], rows[0]).get("listing_data"))

    merged = {**listing_data, **patch}
    if isinstance(listing_data.get("attributes"), dict) and isinstance(patch.get("attributes"), dict):
        merged["attributes"] = {**cast(dict[str, Any], listing_data.get("attributes")), **cast(dict[str, Any], patch.get("attributes"))}
    supabase.table("active_drafts").update({"listing_data": merged, "updated_at": now_iso()}).eq(
        "id", draft_id
    ).execute()

    reread = supabase.table("active_drafts").select("*").eq("id", draft_id).limit(1).execute()
    reread_rows = (reread.data or []) if hasattr(reread, "data") else []
    if not reread_rows:
        raise RuntimeError("Draft bulunamadı")
    return cast(dict[str, Any], reread_rows[0])


def store_media_urls(supabase: Client, draft_id: str, media_urls: list[str]) -> dict[str, Any]:
    current = supabase.table("active_drafts").select("images").eq("id", draft_id).limit(1).execute()
    rows = (current.data or []) if hasattr(current, "data") else []
    if not rows:
        raise RuntimeError("Draft bulunamadı")

    images = _ensure_dict(cast(dict[str, Any], rows[0]).get("images"))

    existing_urls: list[str] = []
    urls_raw = images.get("urls")
    if isinstance(urls_raw, list):
        existing_urls = cast(list[str], urls_raw)

    merged: list[str] = list(dict.fromkeys([*existing_urls, *[u for u in media_urls if u]]))
    images["urls"] = merged

    supabase.table("active_drafts").update({"images": images, "updated_at": now_iso()}).eq(
        "id", draft_id
    ).execute()

    reread = supabase.table("active_drafts").select("*").eq("id", draft_id).limit(1).execute()
    reread_rows = (reread.data or []) if hasattr(reread, "data") else []
    if not reread_rows:
        raise RuntimeError("Draft bulunamadı")
    return cast(dict[str, Any], reread_rows[0])

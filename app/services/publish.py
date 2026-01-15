from __future__ import annotations

from typing import Any, cast

from fastapi import HTTPException
from supabase import Client

from app.config import OPENAI_API_KEY
from app.core.helpers import now_iso
from app.services.category_library import normalize_category_id
from app.services.drafts import draft_missing_fields
from app.services.metadata_keywords import generate_listing_keywords
from app.services.description_composer import compose_description, enrich_title
from app.clients.openai import openai_chat


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Supabase JSON response'ını safely dict'e convert et."""
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _ensure_list(value: Any) -> list[str]:
    """Supabase JSON array'ını safely list'e convert et."""
    if isinstance(value, list):
        return cast(list[str], value)
    return []


def _ensure_str(value: Any) -> str:
    """Supabase value'yu safely string'e convert et."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


async def publish_listing_from_draft(supabase: Client, user_id: str, draft: dict[str, Any]) -> dict[str, Any]:
    listing_data = _ensure_dict(draft.get("listing_data"))
    images = _ensure_dict(draft.get("images"))
    urls = _ensure_list(images.get("urls"))

    missing = draft_missing_fields(draft)
    if missing:
        raise HTTPException(status_code=400, detail=f"Eksik alanlar: {', '.join(missing)}")

    category_value = normalize_category_id(_ensure_str(listing_data.get("category"))) or _ensure_str(
        listing_data.get("category") or "Diğer"
    )

    vision_data = _ensure_dict(draft.get("vision"))
    title_raw = _ensure_str(listing_data.get("title"))
    title_value = enrich_title(title_raw, listing_data, vision_data) or title_raw
    description_raw = _ensure_str(listing_data.get("description"))
    description_value = description_raw or compose_description(listing_data, vision_data)

    keywords: dict[str, Any] = {"keywords": [], "keywords_text": ""}
    try:
        async def _llm(system: str, user: str) -> str:
            return await openai_chat(system, user)

        keywords = await generate_listing_keywords(
            title=_ensure_str(listing_data.get("title") or ""),
            category=_ensure_str(category_value or ""),
            description=_ensure_str(listing_data.get("description") or ""),
            condition=_ensure_str(listing_data.get("condition") or ""),
            vision_product=None,
            max_keywords=12,
            llm_generate=_llm if OPENAI_API_KEY else None,
        )
    except Exception:
        pass

    payload: dict[str, Any] = {
        "user_id": user_id,
        "title": title_value[:120],
        "description": (description_value or title_value or "")[:2000],
        "category": category_value,
        "price": float(_ensure_str(listing_data.get("price") or "0")),
        "condition": _ensure_str(listing_data.get("condition") or "used"),
        "location": _ensure_str(listing_data.get("location") or ""),
        "images": urls or [],
        "status": "active",
        "metadata": {
            "source": "agent",
            "draft_id": draft.get("id"),
            "published_at": now_iso(),
            "keywords": keywords.get("keywords") or [],
            "keywords_text": keywords.get("keywords_text") or "",
        },
        "view_count": 0,
    }

    created = supabase.table("listings").insert(payload).execute()
    created_rows = (created.data or []) if hasattr(created, "data") else []
    if not created_rows:
        raise HTTPException(status_code=500, detail="Listing oluşturulamadı")
    created_row = cast(dict[str, Any], created_rows[0])

    # Deduct 55 credits from user (critical operation)
    try:
        profile_result = supabase.table("profiles").select("credits").eq("id", user_id).limit(1).execute()
        profile_rows = (profile_result.data or []) if hasattr(profile_result, "data") else []
        
        if profile_rows:
            current_credits = cast(dict[str, Any], profile_rows[0]).get("credits", 0) or 0
            new_credits = max(0, int(current_credits) - 55)  # Min 0
            
            supabase.table("profiles").update({
                "credits": new_credits,
                "updated_at": now_iso()
            }).eq("id", user_id).execute()
            
            # Log credit deduction
            supabase.table("audit_logs").insert({
                "event_type": "CREDIT_DEDUCTED",
                "data": {
                    "user_id": user_id,
                    "listing_id": created_row.get("id"),
                    "credits_deducted": 55,
                    "credits_remaining": new_credits,
                    "timestamp": now_iso()
                }
            }).execute()
    except Exception as e:
        # Log error but don't fail listing creation (already published)
        supabase.table("audit_logs").insert({
            "event_type": "CREDIT_DEDUCTION_FAILED",
            "data": {
                "user_id": user_id,
                "listing_id": created_row.get("id"),
                "error": str(e),
                "timestamp": now_iso()
            }
        }).execute()

    try:
        supabase.table("active_drafts").update({"state": "PUBLISHED", "updated_at": now_iso()}).eq("id", draft.get("id")).execute()
    except Exception:
        pass

    return created_row

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.clients.openai import openai_chat
from app.clients.supabase import get_supabase
from app.config import OPENAI_API_KEY
from app.core.helpers import detect_intent, is_uuid, normalize_phone, now_iso
from app.schemas import AgentRunRequest
from app.services.audit import append_audit
from app.services.drafts import get_or_create_draft, patch_draft_fields, store_media_urls, draft_missing_fields, format_preview
from app.services.parsing import extract_simple_fields
from app.services.description_composer import compose_description, enrich_title, get_description_question
from app.services.publish import publish_listing_from_draft
from app.services.search import search_listings

router = APIRouter()


async def handle_agent_run(payload: AgentRunRequest, request: Request) -> dict[str, Any]:
    supabase = get_supabase()

    user_id = payload.user_id
    phone = normalize_phone(payload.phone)

    intent, confidence = detect_intent(payload.message)

    if intent == "SEARCH_LISTING":
        results = search_listings(supabase, payload.message)
        cache: dict[str, Any] = {"results": results, "query": payload.message, "ts": now_iso()}
        response_text = (
            "🔎 Bulabildiğim ilanlar aşağıda. İsterseniz filtre de söyleyin (şehir, bütçe, kategori).\n\n"
            f"[SEARCH_CACHE]{json.dumps(cache, ensure_ascii=False)}"
        )

        append_audit(supabase, user_id, phone, "search_listings", payload.model_dump(), 200)

        return {
            "success": True,
            "intent": "search_completed",
            "confidence": confidence,
            "response": response_text,
            "data": {"listings": results},
        }

    if intent == "AMBIGUOUS":
        patch = extract_simple_fields(payload.message)

        # Best-effort draft storage when user_id is a UUID
        draft_id: str | None = None
        if is_uuid(user_id):
            draft = get_or_create_draft(supabase, user_id)
            draft_id = draft.get("id") if isinstance(draft.get("id"), str) else None

            media_urls = payload.media_paths or []
            if media_urls and draft_id:
                draft = store_media_urls(supabase, draft_id, media_urls)

            if patch and draft_id:
                draft = patch_draft_fields(supabase, draft_id, patch)

        summary_bits: list[str] = []
        if patch.get("title"):
            summary_bits.append(str(patch.get("title")))
        if patch.get("price"):
            summary_bits.append(f"{patch.get('price')} TL")
        if patch.get("location"):
            summary_bits.append(str(patch.get("location")))
        summary = " · ".join(summary_bits)

        response_text = (
            (f"Anladım: {summary}. " if summary else "Anladım. ")
            + "Bununla ilan mı yayınlamak istiyorsunuz, yoksa benzer ilanları mı arayayım?"
        )

        append_audit(supabase, user_id, phone, "intent_clarify", payload.model_dump(), 200)
        return {
            "success": True,
            "intent": "intent_clarify",
            "confidence": confidence,
            "response": response_text,
            "draft_listing_id": draft_id,
        }

    if intent in ["CREATE_LISTING", "UNKNOWN"]:
        if not is_uuid(user_id):
            raise HTTPException(status_code=400, detail="user_id uuid olmalı")

        draft = get_or_create_draft(supabase, user_id)

        patch = extract_simple_fields(payload.message)

        media_urls = payload.media_paths or []
        if media_urls:
            draft_id = draft.get("id")
            if not draft_id or not isinstance(draft_id, str):
                raise HTTPException(status_code=500, detail="Draft ID eksik")
            draft = store_media_urls(supabase, draft_id, media_urls)

        if patch:
            draft_id = draft.get("id")
            if not draft_id or not isinstance(draft_id, str):
                raise HTTPException(status_code=500, detail="Draft ID eksik")
            draft = patch_draft_fields(supabase, draft_id, patch)

        # If we previously asked for description details, treat current message as notes
        listing_data = draft.get("listing_data") if isinstance(draft.get("listing_data"), dict) else {}
        if isinstance(listing_data, dict) and listing_data.get("description_pending"):
            has_structured = any(k in patch for k in ["title", "category", "price", "location"])
            if not has_structured:
                notes_patch = {"description_notes": payload.message, "description_pending": False}
                draft_id = draft.get("id")
                if isinstance(draft_id, str):
                    draft = patch_draft_fields(supabase, draft_id, notes_patch)
                listing_data = draft.get("listing_data") if isinstance(draft.get("listing_data"), dict) else {}

        missing = draft_missing_fields(draft)
        if missing:
            ask_map = {
                "title": "Ürün başlığını yazar mısınız? (örn: iPhone 13 Pro 256GB)",
                "category": "Hangi kategori? (örn: Elektronik, Otomotiv, Emlak)",
                "price": "Fiyatı kaç TL yazmak istersiniz?",
                "location": "Konum (şehir/ilçe) neresi?",
            }
            question = ask_map.get(missing[0]) or "Biraz daha detay yazar mısınız?"

            append_audit(supabase, user_id, phone, "draft_collect", payload.model_dump(), 200)
            return {
                "success": True,
                "intent": "draft_collect",
                "confidence": confidence,
                "response": question,
                "draft_listing_id": draft.get("id"),
            }

        # Optional description enrichment questions
        listing_data = draft.get("listing_data") if isinstance(draft.get("listing_data"), dict) else {}
        if isinstance(listing_data, dict):
            has_description = isinstance(listing_data.get("description"), str) and listing_data.get("description").strip()
            pending = bool(listing_data.get("description_pending"))
            if not has_description and not pending:
                question = get_description_question(str(listing_data.get("category") or ""), listing_data)
                if question:
                    draft_id = draft.get("id")
                    if isinstance(draft_id, str):
                        draft = patch_draft_fields(supabase, draft_id, {"description_pending": True})
                    append_audit(supabase, user_id, phone, "description_collect", payload.model_dump(), 200)
                    return {
                        "success": True,
                        "intent": "description_collect",
                        "confidence": confidence,
                        "response": question,
                        "draft_listing_id": draft.get("id"),
                    }

        listing_data = draft.get("listing_data") if isinstance(draft.get("listing_data"), dict) else {}
        vision_data = draft.get("vision") if isinstance(draft.get("vision"), dict) else {}

        if isinstance(listing_data, dict):
            updated_patch: dict[str, Any] = {}
            title = listing_data.get("title")
            if isinstance(title, str) and title.strip():
                enriched = enrich_title(title, listing_data, vision_data)
                if enriched and enriched != title:
                    updated_patch["title"] = enriched

            desc = listing_data.get("description")
            if not isinstance(desc, str) or not desc.strip():
                generated = compose_description(listing_data, vision_data)
                if generated:
                    updated_patch["description"] = generated

            if updated_patch:
                draft_id = draft.get("id")
                if isinstance(draft_id, str):
                    draft = patch_draft_fields(supabase, draft_id, updated_patch)

        preview = format_preview(draft)
        append_audit(supabase, user_id, phone, "draft_preview", payload.model_dump(), 200)
        return {
            "success": True,
            "intent": "draft_preview",
            "confidence": confidence,
            "response": preview,
            "draft_listing_id": draft.get("id"),
        }

    if intent == "COMMIT_REQUEST":
        if not is_uuid(user_id):
            raise HTTPException(status_code=400, detail="user_id uuid olmalı")

        draft = get_or_create_draft(supabase, user_id)

        msg_lc = payload.message.lower()
        if "onay" not in msg_lc and "yayın" not in msg_lc:
            return {
                "success": True,
                "intent": "confirmation_required",
                "response": "Yayınlamak için lütfen 'onaylıyorum' yazın.",
                "draft_listing_id": draft.get("id"),
            }

        created = await publish_listing_from_draft(supabase, user_id, draft)
        response_text = f"✅ İlan yayınlandı!\nID: {created.get('id')}"

        append_audit(supabase, user_id, phone, "publish", payload.model_dump(), 200)
        return {
            "success": True,
            "intent": "completion_published",
            "response": response_text,
            "data": {"listing": created},
        }

    if intent == "CANCEL":
        if is_uuid(user_id):
            try:
                draft = get_or_create_draft(supabase, user_id)
                supabase.table("active_drafts").update({"state": "CANCELLED", "updated_at": now_iso()}).eq("id", draft.get("id")).execute()
            except Exception:
                pass
        append_audit(supabase, user_id, phone, "cancel", payload.model_dump(), 200)
        return {"success": True, "intent": "completion_cancelled", "response": "✅ İşlem iptal edildi."}

    if OPENAI_API_KEY:
        try:
            system = (
                "Sen PazarGlobal ilan asistanısın. Kısa ve net cevap ver.\n"
                "Kullanıcı ilan vermek veya ilan aramak isteyebilir. Emin değilsen tek bir netleştirici soru sor."
            )
            text = await openai_chat(system, payload.message)
            append_audit(supabase, user_id, phone, "llm_fallback", payload.model_dump(), 200)
            return {"success": True, "intent": "llm_fallback", "response": text}
        except Exception as e:
            append_audit(supabase, user_id, phone, "llm_fallback", payload.model_dump(), 500, str(e))

    append_audit(supabase, user_id, phone, "unknown", payload.model_dump(), 200)
    return {
        "success": True,
        "intent": "unknown",
        "response": "İlan vermek mi istiyorsunuz, yoksa ilan aramak mı? (" "'ilan ver' / 'ilan ara' yazabilirsiniz)",
    }


@router.post("/agent/run")
async def agent_run(payload: AgentRunRequest, request: Request) -> dict[str, Any]:
    return await handle_agent_run(payload, request)

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
    if not phone and is_uuid(user_id):
        try:
            profile_res = supabase.table("profiles").select("phone").eq("id", user_id).limit(1).execute()
            rows = (profile_res.data or []) if hasattr(profile_res, "data") else []
            if rows and isinstance(rows[0], dict):
                phone = normalize_phone(rows[0].get("phone"))
        except Exception:
            phone = None

    intent, confidence = detect_intent(payload.message)

    if intent == "SMALL_TALK":
        display_name: str | None = None
        if isinstance(payload.user_context, dict):
            display_name = payload.user_context.get("display_name") or payload.user_context.get("full_name") or payload.user_context.get("name")

        if not display_name and is_uuid(user_id):
            try:
                profile_res = supabase.table("profiles").select("display_name,full_name").eq("id", user_id).limit(1).execute()
                rows = (profile_res.data or []) if hasattr(profile_res, "data") else []
                if rows and isinstance(rows[0], dict):
                    display_name = rows[0].get("display_name") or rows[0].get("full_name")
            except Exception:
                display_name = None

        if isinstance(display_name, str):
            display_name = display_name.strip()
        if not display_name:
            response_text = "Selam! PazarGlobal'e hoş geldiniz. Size nasıl yardımcı olabilirim? İlan vermek ya da ilan aramak için yazabilirsiniz."
        else:
            response_text = f"Selam {display_name}! PazarGlobal'e hoş geldiniz. Size nasıl yardımcı olabilirim? İlan vermek ya da ilan aramak için yazabilirsiniz."
        append_audit(supabase, user_id, phone, "small_talk", payload.model_dump(), 200)
        return {
            "success": True,
            "intent": "small_talk",
            "confidence": confidence,
            "response": response_text,
        }

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

        # ⭐ REFERANS DOKÜMANI: Belirsiz niyet için kullanıcıya soru sor
        response_text = (
            (f"Anladım: {summary}.\n\n" if summary else "")
            + "🤔 Bununla ne yapmak istersiniz?\n\n"
            + "1️⃣ İlan vermek istiyorsanız → 'ilan ver' veya 'yayınla' yazın\n"
            + "2️⃣ Benzer ilanları aramak istiyorsanız → 'ara' veya 'bul' yazın"
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

        patch = extract_simple_fields(payload.message)

        def _draft_recent(draft_row: dict[str, Any], minutes: int = 30) -> bool:
            updated_at = draft_row.get("updated_at") or draft_row.get("created_at")
            if not isinstance(updated_at, str):
                return False
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except Exception:
                return False
            now = datetime.now(timezone.utc)
            return now - dt <= timedelta(minutes=minutes)

        def _is_location_only(p: dict[str, Any]) -> bool:
            keys = set(p.keys())
            return keys == {"location"}

        # If message doesn't look like listing info, respond with a gentle prompt
        if intent == "UNKNOWN" and not patch:
            append_audit(supabase, user_id, phone, "unknown_no_listing", payload.model_dump(), 200)
            return {
                "success": True,
                "intent": "unknown",
                "confidence": confidence,
                "response": "Size nasıl yardımcı olabilirim? İlan vermek istiyorsanız ürün bilgilerini, ilan aramak istiyorsanız aradığınız ürünü yazabilirsiniz.",
            }

        if intent == "UNKNOWN" and _is_location_only(patch):
            # Check if there's an active recent draft that needs location
            # BUT don't create a draft just for this check
            if is_uuid(user_id):
                try:
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
                        draft = rows[0]
                        missing = draft_missing_fields(draft)
                        # Only use draft if it's recent AND needs location
                        if "location" in missing and _draft_recent(draft, 30):
                            # This is a draft completion, continue to normal flow
                            pass
                        else:
                            # This is a search query, not draft completion
                            results = search_listings(supabase, payload.message)
                            cache: dict[str, Any] = {"results": results, "query": payload.message, "ts": now_iso()}
                            response_text = (
                                f"🔎 Şehir filtresi olarak algıladım. {payload.message} için bulabildiğim ilanlar aşağıda. "
                                "İsterseniz bütçe veya kategori de söyleyin.\n\n"
                                f"[SEARCH_CACHE]{json.dumps(cache, ensure_ascii=False)}"
                            )

                            append_audit(supabase, user_id, phone, "search_location_only", payload.model_dump(), 200)
                            return {
                                "success": True,
                                "intent": "search_completed",
                                "confidence": confidence,
                                "response": response_text,
                                "data": {"listings": results},
                            }
                    else:
                        # No draft exists, this is definitely a search
                        results = search_listings(supabase, payload.message)
                        cache: dict[str, Any] = {"results": results, "query": payload.message, "ts": now_iso()}
                        response_text = (
                            f"🔎 Şehir filtresi olarak algıladım. {payload.message} için bulabildiğim ilanlar aşağıda. "
                            "İsterseniz bütçe veya kategori de söyleyin.\n\n"
                            f"[SEARCH_CACHE]{json.dumps(cache, ensure_ascii=False)}"
                        )

                        append_audit(supabase, user_id, phone, "search_location_only", payload.model_dump(), 200)
                        return {
                            "success": True,
                            "intent": "search_completed",
                            "confidence": confidence,
                            "response": response_text,
                            "data": {"listings": results},
                        }
                except Exception:
                    # Error checking draft, treat as search
                    results = search_listings(supabase, payload.message)
                    cache: dict[str, Any] = {"results": results, "query": payload.message, "ts": now_iso()}
                    response_text = (
                        f"🔎 Şehir filtresi olarak algıladım. {payload.message} için bulabildiğim ilanlar aşağıda. "
                        "İsterseniz bütçe veya kategori de söyleyin.\n\n"
                        f"[SEARCH_CACHE]{json.dumps(cache, ensure_ascii=False)}"
                    )

                    append_audit(supabase, user_id, phone, "search_location_only", payload.model_dump(), 200)
                    return {
                        "success": True,
                        "intent": "search_completed",
                        "confidence": confidence,
                        "response": response_text,
                        "data": {"listings": results},
                    }

        if intent == "UNKNOWN" and patch:
            has_title_or_category = any(k in patch for k in ["title", "category"])
            has_price_or_location = any(k in patch for k in ["price", "location"])
            if has_title_or_category and not has_price_or_location:
                results = search_listings(supabase, payload.message)
                cache: dict[str, Any] = {"results": results, "query": payload.message, "ts": now_iso()}
                response_text = (
                    "🔎 Bunu arama talebi olarak algıladım. Bulabildiğim ilanlar aşağıda. "
                    "İsterseniz şehir, bütçe veya kategori de söyleyin.\n\n"
                    f"[SEARCH_CACHE]{json.dumps(cache, ensure_ascii=False)}"
                )

                append_audit(supabase, user_id, phone, "search_query_unknown", payload.model_dump(), 200)
                return {
                    "success": True,
                    "intent": "search_completed",
                    "confidence": confidence,
                    "response": response_text,
                    "data": {"listings": results},
                }

        # ⭐ KRİTİK FIX: Yeni ilan bilgisi geldiğinde eski draft'ı temizle
        # "kırmızı kazak" gibi yeni bir ilan yazdığında, eski "seagate harddisk" draft'ını silmeli
        if intent in ["CREATE_LISTING", "UNKNOWN"] and patch:
            # Eğer patch'te title, price veya category gibi yeni ilan başlangıç bilgisi varsa
            has_new_listing_info = any(k in patch for k in ["title", "price", "category"])
            
            if has_new_listing_info:
                # Varolan draft'ı kontrol et
                try:
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
                        old_draft = rows[0]
                        old_listing_data = old_draft.get("listing_data") if isinstance(old_draft.get("listing_data"), dict) else {}
                        old_title = old_listing_data.get("title") or ""
                        new_title = patch.get("title") or ""
                        
                        # Eğer yeni title farklıysa (yeni ilan!), eski draft'ı sil
                        if new_title and old_title and new_title.lower() != old_title.lower():
                            supabase.table("active_drafts").delete().eq("user_id", user_id).execute()
                except Exception:
                    pass  # Ignore errors

        draft = get_or_create_draft(supabase, user_id)

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
                # Delete draft instead of just marking as cancelled
                supabase.table("active_drafts").delete().eq("user_id", user_id).execute()
            except Exception:
                pass
        append_audit(supabase, user_id, phone, "cancel", payload.model_dump(), 200)
        return {"success": True, "intent": "completion_cancelled", "response": "✅ İşlem iptal edildi. Yeni bir işlem için mesaj gönderebilirsiniz."}

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

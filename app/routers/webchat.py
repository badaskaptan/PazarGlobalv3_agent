from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.clients.supabase import get_supabase
from app.core.helpers import is_uuid
from app.schemas import AgentRunRequest, WebchatMediaAnalyzeRequest, WebchatMessageRequest
from app.services.audit import append_audit
from app.services.category_library import get_category_options
from app.services.drafts import get_or_create_draft, store_media_urls
from app.routers.agent_run import handle_agent_run

router = APIRouter()


@router.get("/webchat/categories")
def webchat_categories() -> dict[str, Any]:
    return {"options": get_category_options()}


@router.post("/webchat/message")
async def webchat_message(payload: WebchatMessageRequest, request: Request) -> dict[str, Any]:
    merged_context: dict[str, Any] = {"session": {"source": "webchat"}}
    if isinstance(payload.user_context, dict):
        ctx_session = payload.user_context.get("session") if isinstance(payload.user_context.get("session"), dict) else {}
        merged_context = {
            **payload.user_context,
            "session": {**ctx_session, "source": "webchat"},
        }

    run_payload = AgentRunRequest(
        user_id=payload.user_id,
        phone=None,
        message=payload.message,
        conversation_history=[],
        media_paths=(payload.media_urls or ([payload.media_url] if payload.media_url else None)),
        media_type="image" if (payload.media_url or (payload.media_urls and len(payload.media_urls) > 0)) else None,
        draft_listing_id=None,
        session_token=None,
        user_context=merged_context,
    )

    return await handle_agent_run(run_payload, request)


@router.post("/webchat/media/analyze")
async def webchat_media_analyze(payload: WebchatMediaAnalyzeRequest, request: Request) -> dict[str, Any]:
    supabase = get_supabase()

    if not is_uuid(payload.user_id):
        raise HTTPException(status_code=400, detail="user_id uuid olmalı (webchat login gerekli)")

    draft = get_or_create_draft(supabase, payload.user_id)
    draft_id = draft.get("id")
    if not draft_id or not isinstance(draft_id, str):
        raise HTTPException(status_code=500, detail="Draft ID eksik")
    draft = store_media_urls(supabase, draft_id, payload.media_urls)

    msg = (
        f"✅ {len(payload.media_urls)} görsel alındı.\n\n"
        "İlan başlığını ve fiyatını yazarsanız taslağı tamamlayıp önizleme gönderebilirim."
    )

    append_audit(supabase, payload.user_id, None, "webchat_media_analyze", payload.model_dump(), 200)

    return {"success": True, "message": msg, "data": {"draft_listing_id": draft.get("id")}}

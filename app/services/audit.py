from __future__ import annotations

from typing import Any

from supabase import Client

from app.config import APP_NAME
from app.core.helpers import is_uuid


def append_audit(
    supabase: Client,
    user_id: str | None,
    phone: str | None,
    action: str,
    request_data: dict[str, Any],
    response_status: int,
    error_message: str | None = None,
):
    try:
        supabase.table("audit_logs").insert(
            {
                "user_id": user_id if (user_id and is_uuid(user_id)) else None,
                "phone": phone,
                "action": action,
                "resource_type": "agent",
                "source": (request_data.get("user_context") or {}).get("session", {}).get("source") if isinstance(request_data.get("user_context"), dict) else None,
                "request_data": request_data,
                "response_status": response_status,
                "error_message": error_message,
                "metadata": {"app": APP_NAME},
            }
        ).execute()
    except Exception:
        return
